"""ارسال اعلان دعوت جلسه از دو کانال پیامک و ایمیل.

قواعد کلیدی:

* مرز مستأجر: همهٔ کوئری‌ها با ``organization_id`` فیلتر می‌شوند.
* شکست ارسال هرگز ایجاد جلسه را باطل نمی‌کند؛ وضعیت هر گیرنده در
  ``notify_deliveries`` ثبت می‌شود و «ارسال دوباره» امکان‌پذیر است.
* مرزهای نشست: خواندن → commit → فراخوان بیرونی کند → ثبت نتیجه → commit.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agenda_items import Agenda_items
from models.app_users import App_users
from models.meeting_attachments import Meeting_attachments
from models.meetings import Meetings
from models.memberships import Memberships
from models.notify_deliveries import Notify_deliveries
from models.organizations import Organizations
from models.participants import Participants
from services import notify_channels as channels
from services.app_auth import USER_PREFIX
from services.meeting_files import (
    MAX_EMAIL_ATTACHMENT_BYTES,
    fetch_attachment_bytes,
)

logger = logging.getLogger(__name__)


async def _collect_agenda(db: AsyncSession, organization_id: int, meeting_id: int) -> List[Dict[str, Any]]:
    """بندهای دستور جلسه به ترتیب نمایش، برای درج در متن ایمیل."""
    result = await db.execute(
        select(Agenda_items)
        .where(
            Agenda_items.organization_id == organization_id,
            Agenda_items.meeting_id == meeting_id,
        )
        .order_by(Agenda_items.position.asc(), Agenda_items.id.asc())
    )
    return [
        {
            "title": (row.title or "").strip(),
            "notes": (row.notes or "").strip(),
            "planned_minutes": int(row.planned_minutes or 0),
            "owner_name": (row.owner_name or "").strip(),
        }
        for row in result.scalars().all()
    ]


async def _collect_attachments(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> List[Meeting_attachments]:
    """فایل‌های پیوست جلسه در همان سازمان."""
    result = await db.execute(
        select(Meeting_attachments)
        .where(
            Meeting_attachments.organization_id == organization_id,
            Meeting_attachments.meeting_id == meeting_id,
        )
        .order_by(Meeting_attachments.id.asc())
    )
    return list(result.scalars().all())


async def _collect_recipients(
    db: AsyncSession,
    organization_id: int,
    meeting_id: int,
    only_membership_ids: Optional[List[int]] = None,
) -> List[Dict[str, Any]]:
    """گیرندگان جلسه با نام، جنسیت، موبایل و ایمیل واقعی."""
    result = await db.execute(
        select(Participants).where(
            Participants.organization_id == organization_id,
            Participants.meeting_id == meeting_id,
        )
    )
    participants = list(result.scalars().all())
    if only_membership_ids:
        allowed = {int(item) for item in only_membership_ids}
        participants = [p for p in participants if int(p.membership_id or 0) in allowed]

    recipients: List[Dict[str, Any]] = []
    for participant in participants:
        membership_id = int(participant.membership_id or 0)
        if not membership_id:
            continue
        member_result = await db.execute(
            select(Memberships).where(
                Memberships.id == membership_id,
                Memberships.organization_id == organization_id,
            )
        )
        membership = member_result.scalars().first()
        if membership is None:
            continue

        app_user: Optional[App_users] = None
        raw_user_id = membership.member_user_id or ""
        if raw_user_id.startswith(USER_PREFIX):
            try:
                app_user_id = int(raw_user_id[len(USER_PREFIX) :])
            except ValueError:
                app_user_id = 0
            if app_user_id:
                user_result = await db.execute(
                    select(App_users).where(
                        App_users.id == app_user_id,
                        App_users.organization_id == organization_id,
                    )
                )
                app_user = user_result.scalars().first()

        recipients.append(
            {
                "membership_id": membership_id,
                "full_name": (
                    (f"{app_user.first_name} {app_user.last_name}".strip() if app_user else "")
                    or membership.full_name
                    or "عضو جلسه"
                ),
                "gender": (app_user.gender if app_user else "") or "",
                "mobile": (app_user.mobile if app_user else "") or "",
                "email": (app_user.email if app_user else "") or membership.email or "",
            }
        )
    return recipients


async def send_meeting_invites(
    db: AsyncSession,
    *,
    organization_id: int,
    meeting_id: int,
    only_membership_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """ارسال دعوت به اعضای جلسه؛ خروجی شمارش نتایج و پیام قابل نمایش است."""
    meeting_result = await db.execute(
        select(Meetings).where(
            Meetings.id == meeting_id,
            Meetings.organization_id == organization_id,
        )
    )
    meeting = meeting_result.scalars().first()
    if meeting is None:
        return {"sms_sent": 0, "sms_failed": 0, "email_sent": 0, "email_failed": 0, "skipped": 0, "detail": "جلسه یافت نشد."}

    org_result = await db.execute(select(Organizations).where(Organizations.id == organization_id))
    organization = org_result.scalars().first()
    organization_name = (organization.name if organization else "") or "سازمان"

    settings_row = await channels.get_or_create_settings(db, organization_id)
    settings_snapshot = {
        "sms_enabled": bool(settings_row.sms_enabled),
        "smtp_enabled": bool(settings_row.smtp_enabled),
        "from_email": settings_row.smtp_from_email or "",
    }
    recipients = await _collect_recipients(db, organization_id, meeting_id, only_membership_ids)
    agenda_items = await _collect_agenda(db, organization_id, meeting_id)
    attachment_rows = await _collect_attachments(db, organization_id, meeting_id)
    attachment_specs = [
        {
            "object_key": row.object_key,
            "file_name": row.file_name,
            "content_type": row.content_type or "application/octet-stream",
            "size_bytes": int(row.size_bytes or 0),
        }
        for row in attachment_rows
    ]

    meeting_snapshot = {
        "id": int(meeting.id),
        "title": meeting.title or "جلسه",
        "description": meeting.description or "",
        "starts_at": channels.parse_iso(meeting.starts_at),
        "duration_minutes": int(meeting.duration_minutes or 60),
        "location": meeting.location or "",
        "online_url": meeting.online_url or "",
        "secretary_name": meeting.secretary_name or "",
    }

    # پایان فاز خواندن پیش از فراخوان‌های کند بیرونی.
    await db.commit()

    if meeting_snapshot["starts_at"] is None:
        return {
            "sms_sent": 0,
            "sms_failed": 0,
            "email_sent": 0,
            "email_failed": 0,
            "skipped": len(recipients),
            "detail": "زمان جلسه معتبر نیست؛ اعلان ارسال نشد.",
        }

    ics_content = channels.build_ics(
        meeting_id=meeting_snapshot["id"],
        meeting_title=meeting_snapshot["title"],
        description=meeting_snapshot["description"],
        starts_at=meeting_snapshot["starts_at"],
        duration_minutes=meeting_snapshot["duration_minutes"],
        location=meeting_snapshot["location"],
        organizer_email=settings_snapshot["from_email"],
    )

    # پیوست‌ها یک بار از Object Storage خوانده می‌شوند و برای همهٔ گیرندگان
    # بازاستفاده می‌گردند؛ فایل‌های بزرگ‌تر از سقف ایمیل فقط در فهرست نام‌ها
    # ذکر می‌شوند تا ارسال ایمیل با خطای اندازه رد نشود.
    email_attachments: List[channels.EmailAttachment] = []
    attachment_names: List[str] = []
    oversize_names: List[str] = []
    if settings_snapshot["smtp_enabled"] and attachment_specs:
        for spec in attachment_specs:
            attachment_names.append(spec["file_name"])
            if spec["size_bytes"] and spec["size_bytes"] > MAX_EMAIL_ATTACHMENT_BYTES:
                oversize_names.append(spec["file_name"])
                continue
            content = await fetch_attachment_bytes(spec["object_key"])
            if content is None or len(content) > MAX_EMAIL_ATTACHMENT_BYTES:
                oversize_names.append(spec["file_name"])
                continue
            email_attachments.append(
                channels.EmailAttachment(
                    file_name=spec["file_name"],
                    content=content,
                    content_type=spec["content_type"],
                )
            )

    outcomes: List[Dict[str, Any]] = []
    counters = {"sms_sent": 0, "sms_failed": 0, "email_sent": 0, "email_failed": 0, "skipped": 0}

    for recipient in recipients:
        touched = False

        if settings_snapshot["sms_enabled"] and recipient["mobile"]:
            touched = True
            sms_text = channels.build_invite_sms(
                recipient_name=recipient["full_name"],
                gender=recipient["gender"],
                starts_at=meeting_snapshot["starts_at"],
            )
            sms_result = await channels.send_sms(
                settings_row,
                receptor=recipient["mobile"],
                message=sms_text,
                client_reference_id=f"meeting-{meeting_snapshot['id']}-{recipient['membership_id']}",
            )
            counters["sms_sent" if sms_result.ok else "sms_failed"] += 1
            outcomes.append(
                {
                    "membership_id": recipient["membership_id"],
                    "channel": "sms",
                    "recipient": recipient["mobile"],
                    "recipient_name": recipient["full_name"],
                    "status": "sent" if sms_result.ok else "failed",
                    "provider_message_id": sms_result.provider_message_id,
                    "error_message": sms_result.error,
                    "body_preview": sms_text[:300],
                }
            )

        if settings_snapshot["smtp_enabled"] and recipient["email"]:
            touched = True
            subject, text_body, html_body = channels.build_invite_email(
                recipient_name=recipient["full_name"],
                gender=recipient["gender"],
                organization_name=organization_name,
                meeting_title=meeting_snapshot["title"],
                description=meeting_snapshot["description"],
                starts_at=meeting_snapshot["starts_at"],
                duration_minutes=meeting_snapshot["duration_minutes"],
                location=meeting_snapshot["location"],
                online_url=meeting_snapshot["online_url"],
                secretary_name=meeting_snapshot["secretary_name"],
                agenda_items=agenda_items,
                attachment_names=attachment_names,
            )
            email_result = await channels.send_email(
                settings_row,
                to_email=recipient["email"],
                subject=subject,
                text_body=text_body,
                html_body=html_body,
                ics_content=ics_content,
                attachments=email_attachments,
            )
            counters["email_sent" if email_result.ok else "email_failed"] += 1
            outcomes.append(
                {
                    "membership_id": recipient["membership_id"],
                    "channel": "email",
                    "recipient": recipient["email"],
                    "recipient_name": recipient["full_name"],
                    "status": "sent" if email_result.ok else "failed",
                    "provider_message_id": "",
                    "error_message": email_result.error,
                    "body_preview": subject[:300],
                }
            )

        if not touched:
            counters["skipped"] += 1
            outcomes.append(
                {
                    "membership_id": recipient["membership_id"],
                    "channel": "sms" if not recipient["email"] else "email",
                    "recipient": recipient["mobile"] or recipient["email"],
                    "recipient_name": recipient["full_name"],
                    "status": "skipped",
                    "provider_message_id": "",
                    "error_message": "کانال ارسال فعال نیست یا اطلاعات تماس ثبت نشده است.",
                    "body_preview": "",
                }
            )

    for outcome in outcomes:
        db.add(
            Notify_deliveries(
                organization_id=organization_id,
                meeting_id=meeting_snapshot["id"],
                membership_id=outcome["membership_id"],
                channel=outcome["channel"],
                recipient=outcome["recipient"],
                recipient_name=outcome["recipient_name"],
                status=outcome["status"],
                provider_message_id=outcome["provider_message_id"],
                error_message=(outcome["error_message"] or "")[:900],
                body_preview=outcome["body_preview"],
            )
        )
    await db.commit()

    counters["detail"] = _summary(counters, len(recipients))
    counters["agenda_items"] = len(agenda_items)
    counters["attachments_sent"] = len(email_attachments)
    counters["attachments_skipped"] = len(oversize_names)
    if oversize_names:
        counters["detail"] += (
            "؛ "
            + "، ".join(oversize_names)
            + " به دلیل حجم زیاد پیوست نشد و فقط نام آن در ایمیل ذکر شد."
        )
    return counters


def _summary(counters: Dict[str, Any], total: int) -> str:
    if total == 0:
        return "عضوی برای ارسال اعلان در این جلسه ثبت نشده است."
    parts = []
    if counters["sms_sent"]:
        parts.append(f"{counters['sms_sent']} پیامک ارسال شد")
    if counters["sms_failed"]:
        parts.append(f"{counters['sms_failed']} پیامک ناموفق")
    if counters["email_sent"]:
        parts.append(f"{counters['email_sent']} ایمیل ارسال شد")
    if counters["email_failed"]:
        parts.append(f"{counters['email_failed']} ایمیل ناموفق")
    if counters["skipped"]:
        parts.append(f"{counters['skipped']} گیرنده بدون کانال فعال")
    return "، ".join(parts) or "اعلانی ارسال نشد."
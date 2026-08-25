"""روترهای هستهٔ فضای کاری سازمان.

این روتر مرزهای منطقی سند معماری را حفظ می‌کند:

* هر درخواست ابتدا ``TenantContext`` می‌سازد (ورود خودکار به سازمان یا ساخت سازمان نمایشی).
* هیچ کوئری دامنه‌ای بدون ``organization_id`` اجرا نمی‌شود.
* هر تصمیم دسترسی در سرور گرفته می‌شود و با ۴۰۳ رد می‌گردد.
"""

from __future__ import annotations

import logging
import secrets
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.app_auth import get_workspace_user as get_current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from schemas.auth import UserResponse
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from services.meeting_invites import send_meeting_invites

from models.action_items import Action_items
from models.agenda_items import Agenda_items
from models.ai_usage_events import Ai_usage_events
from models.audit_logs import Audit_logs
from models.decisions import Decisions
from models.invitations import Invitations
from models.jobs import Jobs
from models.meetings import Meetings
from models.memberships import Memberships
from models.minute_versions import Minute_versions
from models.minutes import Minutes
from models.notifications import Notifications
from models.participants import Participants
from models.recordings import Recordings
from models.transcripts import Transcripts
from services import mgmt_core as core
from services import upload_limits as limits_service
from services.mgmt_core import (
    ACTION_STATUSES,
    AGENDA_FIELDS,
    ALL_ROLES,
    MEETING_FIELDS,
    MEETING_TYPES,
    MEMBER_FIELDS,
    PARTICIPANT_FIELDS,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_MEMBER,
    ROLE_SECRETARY,
    audit,
    bad_request,
    dump,
    get_owned,
    list_owned,
    notify,
    quota_snapshot,
    require_meeting_manager,
    require_role,
    resolve_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workspace", tags=["workspace"])


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------


class AgendaItemIn(BaseModel):
    """یک بند دستور جلسه که همراه فرم «تعریف جلسه جدید» ثبت می‌شود."""

    title: str = Field(..., min_length=2, max_length=300)
    notes: str = ""
    planned_minutes: int = 15
    owner_name: str = ""


class MeetingIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=300)
    description: str = ""
    meeting_type: str = MEETING_TYPES[0]
    starts_at: str = Field(..., description="زمان شروع به UTC")
    duration_minutes: int = 60
    location: str = ""
    online_url: str = ""
    secretary_membership_id: Optional[int] = None
    participant_membership_ids: List[int] = Field(default_factory=list)
    # بندهای دستور جلسه در همان فرم ایجاد؛ پیش از ارسال دعوت ثبت می‌شوند تا
    # متن ایمیل/پیامک دعوت شامل دستور جلسه باشد.
    agenda_items: List[AgendaItemIn] = Field(default_factory=list)


class MeetingUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    meeting_type: Optional[str] = None
    starts_at: Optional[str] = None
    duration_minutes: Optional[int] = None
    location: Optional[str] = None
    online_url: Optional[str] = None
    secretary_membership_id: Optional[int] = None
    status: Optional[str] = None


class AgendaIn(BaseModel):
    title: str = Field(..., min_length=2, max_length=300)
    notes: str = ""
    planned_minutes: int = 15
    owner_name: str = ""


class AgendaReorderIn(BaseModel):
    ordered_ids: List[int]


class ParticipantsIn(BaseModel):
    membership_ids: List[int]


class RsvpIn(BaseModel):
    rsvp_status: str = Field(..., description="accepted|declined|tentative|pending")
    rsvp_note: str = ""


class AttendanceIn(BaseModel):
    attendance: Dict[str, bool] = Field(default_factory=dict)


class MemberIn(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=200)
    email: str = ""
    role: str = ROLE_MEMBER


class MemberUpdateIn(BaseModel):
    role: Optional[str] = None
    status: Optional[str] = None
    full_name: Optional[str] = None


class InviteIn(BaseModel):
    email: str = Field(..., min_length=5, max_length=200)
    role: str = ROLE_MEMBER


class PurgeDemoIn(BaseModel):
    confirm: str = ""


class SettingsIn(BaseModel):
    name: Optional[str] = None
    timezone: Optional[str] = None
    audio_retention_days: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_audio_minutes: Optional[int] = None


class UploadLimitsIn(BaseModel):
    """سقف‌های بارگذاری قابل تنظیم توسط مدیر سازمان.

    هر فیلد اختیاری است تا فرم تنظیمات بتواند فقط مقدارهای تغییریافته را
    بفرستد؛ مقادیر خارج از بازهٔ مجاز در سرویس کلمپ می‌شوند.
    """

    max_audio_minutes: Optional[int] = None
    max_audio_mb: Optional[int] = None
    max_attachment_mb: Optional[int] = None


# ---------------------------------------------------------------------------
# پروفایل و بوت‌استرپ
# ---------------------------------------------------------------------------


@router.get("/bootstrap")
async def bootstrap(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ورود کاربر به فضای کاری: سازمان، نقش، سهمیه و شمارندهٔ اعلان."""
    ctx = await resolve_context(db, current_user)
    await core.refresh_overdue_actions(db, ctx.organization_id)
    unread = await db.execute(
        select(Notifications).where(
            Notifications.organization_id == ctx.organization_id,
            Notifications.recipient_membership_id == ctx.membership_id,
            Notifications.is_read == False,  # noqa: E712
        )
    )
    unread_count = len(list(unread.scalars().all()))
    await db.commit()
    return {
        "user": {"id": ctx.user_id, "email": ctx.user_email, "name": ctx.actor_name},
        "organization": {
            "id": ctx.organization_id,
            "name": ctx.organization.name,
            "slug": ctx.organization.slug,
            "plan_code": ctx.organization.plan_code,
            "timezone": ctx.organization.timezone,
            "is_demo": bool(ctx.organization.is_demo),
        },
        "membership": {
            "id": ctx.membership_id,
            "role": ctx.role,
            "role_label": ROLE_LABELS.get(ctx.role, ctx.role),
        },
        "quota": quota_snapshot(ctx.organization),
        "upload_limits": await limits_service.get_limits(db, ctx.organization_id),
        "unread_notifications": unread_count,
        "meeting_types": MEETING_TYPES,
        "roles": [{"value": role, "label": ROLE_LABELS[role]} for role in ALL_ROLES],
    }


# ---------------------------------------------------------------------------
# جلسات
# ---------------------------------------------------------------------------


@router.get("/meetings")
async def list_meetings(
    scope: str = "all",
    search: str = "",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meetings = await list_owned(db, Meetings, ctx, order_by=Meetings.starts_at.desc())

    minutes_rows = await list_owned(db, Minutes, ctx)
    minutes_by_meeting = {int(row.meeting_id): row.status for row in minutes_rows}
    participants = await list_owned(db, Participants, ctx)
    counts: Dict[int, Dict[str, int]] = {}
    for participant in participants:
        bucket = counts.setdefault(int(participant.meeting_id), {"total": 0, "accepted": 0, "attended": 0})
        bucket["total"] += 1
        if participant.rsvp_status == "accepted":
            bucket["accepted"] += 1
        if participant.attended:
            bucket["attended"] += 1

    now = core.utc_now()
    needle = core.fa_normalize(search)
    items: List[Dict[str, Any]] = []
    for meeting in meetings:
        starts_at = core.parse_iso(meeting.starts_at)
        is_future = bool(starts_at and starts_at >= now)
        if scope == "upcoming" and not is_future:
            continue
        if scope == "past" and is_future:
            continue
        if needle and needle not in core.fa_normalize(f"{meeting.title} {meeting.description} {meeting.location}"):
            continue
        payload = dump(meeting, MEETING_FIELDS)
        payload["minutes_status"] = minutes_by_meeting.get(int(meeting.id))
        payload["counts"] = counts.get(int(meeting.id), {"total": 0, "accepted": 0, "attended": 0})
        payload["is_future"] = is_future
        items.append(payload)
    await db.commit()
    return {"items": items, "total": len(items)}


@router.post("/meetings")
async def create_meeting(
    payload: MeetingIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN, ROLE_SECRETARY)

    starts_at = core.normalize_iso(payload.starts_at)
    if not starts_at:
        raise bad_request("زمان شروع جلسه معتبر نیست.")
    if payload.meeting_type and payload.meeting_type not in MEETING_TYPES:
        raise bad_request("نوع جلسه معتبر نیست.")
    duration_minutes = int(payload.duration_minutes or 60)
    if not 5 <= duration_minutes <= 480:
        raise bad_request("مدت جلسه باید بین ۵ تا ۴۸۰ دقیقه باشد.")

    secretary_name = ""
    secretary_id = payload.secretary_membership_id or ctx.membership_id
    secretary = await get_owned(db, Memberships, secretary_id, ctx, "عضو انتخاب‌شده به‌عنوان دبیر")
    secretary_name = secretary.full_name

    meeting = Meetings(
        organization_id=ctx.organization_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip(),
        meeting_type=payload.meeting_type or MEETING_TYPES[0],
        starts_at=starts_at,
        duration_minutes=duration_minutes,
        location=(payload.location or "").strip(),
        online_url=(payload.online_url or "").strip(),
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary_name,
        status="scheduled",
        created_by_user_id=ctx.user_id,
        created_by_name=ctx.actor_name,
    )
    db.add(meeting)
    await db.flush()

    # ثبت بندهای دستور جلسه پیش از ارسال دعوت‌ها.
    for position, item in enumerate(payload.agenda_items, start=1):
        title = (item.title or "").strip()
        if len(title) < 2:
            continue
        db.add(
            Agenda_items(
                organization_id=ctx.organization_id,
                meeting_id=int(meeting.id),
                position=position,
                title=title,
                notes=(item.notes or "").strip(),
                planned_minutes=max(int(item.planned_minutes or 15), 1),
                owner_name=(item.owner_name or "").strip(),
            )
        )

    for membership_id in dict.fromkeys(payload.participant_membership_ids):
        member = await get_owned(db, Memberships, membership_id, ctx, "عضو دعوت‌شده")
        db.add(
            Participants(
                organization_id=ctx.organization_id,
                meeting_id=int(meeting.id),
                membership_id=int(member.id),
                member_user_id=member.member_user_id,
                full_name=member.full_name,
                rsvp_status="pending",
                rsvp_note="",
                attended=False,
            )
        )
        await notify(
            db,
            ctx.organization_id,
            membership_id=int(member.id),
            user_id=member.member_user_id,
            kind="invite",
            title=f"دعوت به «{meeting.title}»",
            body="حضور شما در این جلسه درخواست شده است.",
            link=f"/meetings/{int(meeting.id)}",
            dedupe_key=f"invite-{meeting.id}-{member.id}",
        )

    await audit(db, ctx, "meeting.created", "meeting", int(meeting.id), meeting.title)
    organization_id = ctx.organization_id
    meeting_id = int(meeting.id)
    payload_out = dump(meeting, MEETING_FIELDS)
    await db.commit()

    # ارسال اعلان دعوت (پیامک + ایمیل) پس از پایدارسازی جلسه؛
    # شکست ارسال هرگز ایجاد جلسه را باطل نمی‌کند.
    try:
        payload_out["notification"] = await send_meeting_invites(
            db,
            organization_id=organization_id,
            meeting_id=meeting_id,
        )
    except Exception:  # noqa: BLE001 - اعلان نباید جریان اصلی را متوقف کند
        logger.exception("ارسال اعلان دعوت جلسه %s ناموفق بود", meeting_id)
        payload_out["notification"] = {
            "sms_sent": 0,
            "sms_failed": 0,
            "email_sent": 0,
            "email_failed": 0,
            "skipped": 0,
            "detail": "جلسه ثبت شد، اما ارسال اعلان با خطا مواجه شد. از بخش جلسه می‌توانید دوباره ارسال کنید.",
        }
    return payload_out


@router.get("/meetings/{meeting_id}")
async def meeting_detail(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")

    agenda = await list_owned(
        db, Agenda_items, ctx, Agenda_items.meeting_id == meeting_id, order_by=Agenda_items.position
    )
    participants = await list_owned(
        db, Participants, ctx, Participants.meeting_id == meeting_id, order_by=Participants.id
    )
    recordings = await list_owned(
        db, Recordings, ctx, Recordings.meeting_id == meeting_id, order_by=Recordings.id.desc()
    )
    decisions = await list_owned(
        db, Decisions, ctx, Decisions.meeting_id == meeting_id, order_by=Decisions.position
    )
    actions = await list_owned(
        db, Action_items, ctx, Action_items.meeting_id == meeting_id, order_by=Action_items.id
    )
    minutes_result = await db.execute(
        select(Minutes).where(
            Minutes.organization_id == ctx.organization_id, Minutes.meeting_id == meeting_id
        )
    )
    minutes_row = minutes_result.scalars().first()

    my_participant = next(
        (p for p in participants if int(p.membership_id or 0) == ctx.membership_id), None
    )
    await db.commit()
    return {
        "meeting": dump(meeting, MEETING_FIELDS),
        "agenda": [dump(item, AGENDA_FIELDS) for item in agenda],
        "participants": [dump(item, PARTICIPANT_FIELDS) for item in participants],
        "recordings": [dump(item, core.RECORDING_FIELDS) for item in recordings],
        "minutes": dump(minutes_row, core.MINUTES_FIELDS) if minutes_row else None,
        "decisions": [dump(item, core.DECISION_FIELDS) for item in decisions],
        "actions": [dump(item, core.ACTION_FIELDS) for item in actions],
        "my_rsvp": my_participant.rsvp_status if my_participant else None,
        "permissions": {
            "can_manage": ctx.is_secretary_of(meeting),
            "can_approve": ctx.is_admin(),
            "role": ctx.role,
        },
    }


@router.patch("/meetings/{meeting_id}")
async def update_meeting(
    meeting_id: int,
    payload: MeetingUpdateIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    if payload.title is not None:
        meeting.title = payload.title.strip() or meeting.title
    if payload.description is not None:
        meeting.description = payload.description.strip()
    if payload.meeting_type is not None:
        if payload.meeting_type not in MEETING_TYPES:
            raise bad_request("نوع جلسه معتبر نیست.")
        meeting.meeting_type = payload.meeting_type
    if payload.starts_at is not None:
        normalized = core.normalize_iso(payload.starts_at)
        if not normalized:
            raise bad_request("زمان شروع جلسه معتبر نیست.")
        meeting.starts_at = normalized
    if payload.duration_minutes is not None:
        new_duration = int(payload.duration_minutes)
        if not 5 <= new_duration <= 480:
            raise bad_request("مدت جلسه باید بین ۵ تا ۴۸۰ دقیقه باشد.")
        meeting.duration_minutes = new_duration
    if payload.location is not None:
        meeting.location = payload.location.strip()
    if payload.online_url is not None:
        meeting.online_url = payload.online_url.strip()
    if payload.secretary_membership_id is not None:
        secretary = await get_owned(
            db, Memberships, payload.secretary_membership_id, ctx, "عضو انتخاب‌شده به‌عنوان دبیر"
        )
        meeting.secretary_membership_id = int(secretary.id)
        meeting.secretary_name = secretary.full_name
    if payload.status is not None:
        if payload.status not in ("scheduled", "held", "cancelled"):
            raise bad_request("وضعیت جلسه معتبر نیست.")
        meeting.status = payload.status

    await audit(db, ctx, "meeting.updated", "meeting", meeting_id, meeting.title)
    await db.commit()
    return dump(meeting, MEETING_FIELDS)


@router.delete("/meetings/{meeting_id}")
async def delete_meeting(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    title = meeting.title
    await db.delete(meeting)
    await audit(db, ctx, "meeting.deleted", "meeting", meeting_id, title)
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# دستور جلسه
# ---------------------------------------------------------------------------


@router.post("/meetings/{meeting_id}/agenda")
async def add_agenda_item(
    meeting_id: int,
    payload: AgendaIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    existing = await list_owned(db, Agenda_items, ctx, Agenda_items.meeting_id == meeting_id)
    item = Agenda_items(
        organization_id=ctx.organization_id,
        meeting_id=meeting_id,
        position=len(existing) + 1,
        title=payload.title.strip(),
        notes=(payload.notes or "").strip(),
        planned_minutes=max(int(payload.planned_minutes or 15), 1),
        owner_name=(payload.owner_name or "").strip(),
    )
    db.add(item)
    await audit(db, ctx, "agenda.created", "agenda_item", meeting_id, item.title)
    await db.commit()
    return dump(item, AGENDA_FIELDS)


@router.patch("/agenda/{item_id}")
async def update_agenda_item(
    item_id: int,
    payload: AgendaIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    item = await get_owned(db, Agenda_items, item_id, ctx, "بند دستور جلسه")
    meeting = await get_owned(db, Meetings, int(item.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    item.title = payload.title.strip() or item.title
    item.notes = (payload.notes or "").strip()
    item.planned_minutes = max(int(payload.planned_minutes or 15), 1)
    item.owner_name = (payload.owner_name or "").strip()
    await audit(db, ctx, "agenda.updated", "agenda_item", item_id, item.title)
    await db.commit()
    return dump(item, AGENDA_FIELDS)


@router.delete("/agenda/{item_id}")
async def delete_agenda_item(
    item_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    item = await get_owned(db, Agenda_items, item_id, ctx, "بند دستور جلسه")
    meeting = await get_owned(db, Meetings, int(item.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    await db.delete(item)
    await audit(db, ctx, "agenda.deleted", "agenda_item", item_id, item.title)
    await db.commit()
    return {"success": True}


@router.post("/meetings/{meeting_id}/agenda/reorder")
async def reorder_agenda(
    meeting_id: int,
    payload: AgendaReorderIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    items = await list_owned(db, Agenda_items, ctx, Agenda_items.meeting_id == meeting_id)
    by_id = {int(item.id): item for item in items}
    position = 1
    for item_id in payload.ordered_ids:
        item = by_id.get(int(item_id))
        if item is not None:
            item.position = position
            position += 1
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# حاضران، RSVP و حضور
# ---------------------------------------------------------------------------


@router.post("/meetings/{meeting_id}/participants")
async def set_participants(
    meeting_id: int,
    payload: ParticipantsIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    existing = await list_owned(db, Participants, ctx, Participants.meeting_id == meeting_id)
    existing_ids = {int(item.membership_id or 0) for item in existing}
    requested = list(dict.fromkeys(int(value) for value in payload.membership_ids))

    for membership_id in requested:
        if membership_id in existing_ids:
            continue
        member = await get_owned(db, Memberships, membership_id, ctx, "عضو دعوت‌شده")
        db.add(
            Participants(
                organization_id=ctx.organization_id,
                meeting_id=meeting_id,
                membership_id=int(member.id),
                member_user_id=member.member_user_id,
                full_name=member.full_name,
                rsvp_status="pending",
                rsvp_note="",
                attended=False,
            )
        )
        await notify(
            db,
            ctx.organization_id,
            membership_id=int(member.id),
            user_id=member.member_user_id,
            kind="invite",
            title=f"دعوت به «{meeting.title}»",
            body="حضور شما در این جلسه درخواست شده است.",
            link=f"/meetings/{meeting_id}",
            dedupe_key=f"invite-{meeting_id}-{member.id}",
        )

    for participant in existing:
        if int(participant.membership_id or 0) not in requested:
            await db.delete(participant)

    await audit(db, ctx, "participants.updated", "meeting", meeting_id, f"{len(requested)} نفر")
    await db.commit()
    return {"success": True, "total": len(requested)}


@router.post("/meetings/{meeting_id}/rsvp")
async def submit_rsvp(
    meeting_id: int,
    payload: RsvpIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    if payload.rsvp_status not in ("accepted", "declined", "tentative", "pending"):
        raise bad_request("وضعیت پاسخ دعوت معتبر نیست.")

    result = await db.execute(
        select(Participants).where(
            Participants.organization_id == ctx.organization_id,
            Participants.meeting_id == meeting_id,
            Participants.membership_id == ctx.membership_id,
        )
    )
    participant = result.scalars().first()
    if participant is None:
        participant = Participants(
            organization_id=ctx.organization_id,
            meeting_id=meeting_id,
            membership_id=ctx.membership_id,
            member_user_id=ctx.user_id,
            full_name=ctx.actor_name,
            attended=False,
        )
        db.add(participant)
    participant.rsvp_status = payload.rsvp_status
    participant.rsvp_note = (payload.rsvp_note or "").strip()

    if meeting.secretary_membership_id:
        await notify(
            db,
            ctx.organization_id,
            membership_id=int(meeting.secretary_membership_id),
            user_id=None,
            kind="rsvp",
            title=f"پاسخ دعوت {ctx.actor_name} برای «{meeting.title}»",
            body=f"وضعیت جدید: {payload.rsvp_status}",
            link=f"/meetings/{meeting_id}",
        )
    await audit(db, ctx, "meeting.rsvp", "meeting", meeting_id, payload.rsvp_status)
    await db.commit()
    return dump(participant, PARTICIPANT_FIELDS)


@router.post("/meetings/{meeting_id}/attendance")
async def save_attendance(
    meeting_id: int,
    payload: AttendanceIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    participants = await list_owned(db, Participants, ctx, Participants.meeting_id == meeting_id)
    present = 0
    for participant in participants:
        key = str(int(participant.id))
        if key in payload.attendance:
            participant.attended = bool(payload.attendance[key])
        if participant.attended:
            present += 1
    if meeting.status == "scheduled":
        meeting.status = "held"
    await audit(db, ctx, "meeting.attendance", "meeting", meeting_id, f"{present} حاضر")
    await db.commit()
    return {"success": True, "present": present, "total": len(participants)}


# ---------------------------------------------------------------------------
# اعضا و دعوت
# ---------------------------------------------------------------------------


@router.get("/members")
async def list_members(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    members = await list_owned(db, Memberships, ctx, order_by=Memberships.id)
    invitations = await list_owned(db, Invitations, ctx, order_by=Invitations.id.desc())
    await db.commit()
    return {
        "members": [dump(member, MEMBER_FIELDS) for member in members],
        "invitations": [dump(invite, core.INVITATION_FIELDS) for invite in invitations],
        "can_manage": ctx.is_admin(),
        "my_membership_id": ctx.membership_id,
    }


@router.post("/members")
async def add_member(
    payload: MemberIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """افزودن عضو داخلی (برای دمو، بدون نیاز به حساب واقعی)."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    if payload.role not in ALL_ROLES:
        raise bad_request("نقش انتخاب‌شده معتبر نیست.")
    member = Memberships(
        organization_id=ctx.organization_id,
        member_user_id="",
        email=(payload.email or "").strip().lower(),
        full_name=payload.full_name.strip(),
        role=payload.role,
        status="active",
        is_virtual=True,
    )
    db.add(member)
    await audit(db, ctx, "member.created", "membership", None, member.full_name)
    await db.commit()
    return dump(member, MEMBER_FIELDS)


@router.patch("/members/{member_id}")
async def update_member(
    member_id: int,
    payload: MemberUpdateIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    member = await get_owned(db, Memberships, member_id, ctx, "عضو")

    if payload.role is not None:
        if payload.role not in ALL_ROLES:
            raise bad_request("نقش انتخاب‌شده معتبر نیست.")
        if member_id == ctx.membership_id and payload.role != ROLE_ADMIN:
            raise bad_request("نقش مدیر فعلی سازمان را نمی‌توان از خودِ او گرفت.")
        member.role = payload.role
    if payload.status is not None:
        if payload.status not in ("active", "disabled"):
            raise bad_request("وضعیت عضو معتبر نیست.")
        if member_id == ctx.membership_id and payload.status != "active":
            raise bad_request("حساب خودتان را نمی‌توانید غیرفعال کنید.")
        member.status = payload.status
    if payload.full_name is not None and payload.full_name.strip():
        member.full_name = payload.full_name.strip()

    await audit(db, ctx, "member.updated", "membership", member_id, f"{member.full_name} / {member.role}")
    await db.commit()
    return dump(member, MEMBER_FIELDS)


@router.post("/invitations")
async def create_invitation(
    payload: InviteIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    if payload.role not in ALL_ROLES:
        raise bad_request("نقش انتخاب‌شده معتبر نیست.")
    email = payload.email.strip().lower()
    if "@" not in email:
        raise bad_request("نشانی ایمیل معتبر نیست.")

    invite = Invitations(
        organization_id=ctx.organization_id,
        email=email,
        role=payload.role,
        token=secrets.token_urlsafe(24),
        status="pending",
        expires_at=core.iso_utc(core.utc_now() + core.timedelta(days=7)),
        invited_by_name=ctx.actor_name,
    )
    db.add(invite)
    await audit(db, ctx, "invitation.created", "invitation", None, email)
    await db.commit()
    return dump(invite, core.INVITATION_FIELDS)


@router.post("/invitations/{invite_id}/revoke")
async def revoke_invitation(
    invite_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    invite = await get_owned(db, Invitations, invite_id, ctx, "دعوت‌نامه")
    invite.status = "revoked"
    await audit(db, ctx, "invitation.revoked", "invitation", invite_id, invite.email)
    await db.commit()
    return dump(invite, core.INVITATION_FIELDS)


# ---------------------------------------------------------------------------
# تنظیمات سازمان
# ---------------------------------------------------------------------------


@router.patch("/settings")
async def update_settings(
    payload: SettingsIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    org = ctx.organization
    if payload.name is not None and payload.name.strip():
        org.name = payload.name.strip()
    if payload.timezone is not None and payload.timezone.strip():
        org.timezone = payload.timezone.strip()
    if payload.audio_retention_days is not None:
        org.audio_retention_days = max(min(int(payload.audio_retention_days), 365), 1)
    if payload.max_audio_mb is not None:
        org.max_audio_mb = max(min(int(payload.max_audio_mb), core.DEMO_MAX_AUDIO_MB), 5)
    if payload.max_audio_minutes is not None:
        org.max_audio_minutes = max(min(int(payload.max_audio_minutes), core.DEMO_MAX_AUDIO_MINUTES), 5)
    await audit(db, ctx, "organization.settings_updated", "organization", ctx.organization_id, org.name)
    await db.commit()
    return {
        "organization": {
            "id": ctx.organization_id,
            "name": org.name,
            "timezone": org.timezone,
            "audio_retention_days": org.audio_retention_days,
        },
        "quota": quota_snapshot(org),
    }


@router.get("/upload-limits")
async def read_upload_limits(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """سقف‌های مؤثر بارگذاری سازمان؛ برای همهٔ اعضا خواندنی است.

    فرانت پیش از انتخاب فایل از همین مقادیر برای اعتبارسنجی و نمایش راهنما
    استفاده می‌کند تا پیام خطا با رفتار واقعی سرور یکی باشد.
    """
    ctx = await resolve_context(db, current_user)
    data = await limits_service.get_limits(db, ctx.organization_id)
    await db.commit()
    return data


@router.patch("/upload-limits")
async def update_upload_limits(
    payload: UploadLimitsIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تغییر سقف مدت صوت و حجم پیوست توسط مدیر سازمان (با ثبت در Audit)."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    data, changes = await limits_service.save_limits(
        db,
        ctx.organization_id,
        values=payload.model_dump(),
        actor_name=ctx.actor_name,
    )
    # سقف حجم/مدت صوت روی رکورد سازمان هم بازنویسی می‌شود تا اعتبارسنجی‌های
    # موجود (سهمیه و آپلود صوت) بدون شاخهٔ اضافی همان مقدار تازه را ببینند.
    ctx.organization.max_audio_minutes = int(data["max_audio_minutes"])
    ctx.organization.max_audio_mb = int(data["max_audio_mb"])
    await audit(
        db,
        ctx,
        "organization.upload_limits_updated",
        "organization",
        ctx.organization_id,
        "؛ ".join(changes) if changes else "بدون تغییر مؤثر",
    )
    await db.commit()
    return data


@router.post("/demo-data/purge")
async def purge_demo_data(
    payload: PurgeDemoIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """پاک‌سازی صریح دادهٔ نمایشی سازمان تا کار با دادهٔ واقعی آغاز شود.

    این عملیات فقط با تأیید مدیر سازمان و ارسال عبارت تأیید اجرا می‌شود.
    همهٔ جلسات، صورتجلسه‌ها، مصوبات، اقدامات، فایل‌های صوتی و اعضای نمایشی حذف
    می‌شوند؛ حساب‌های واقعی و گزارش Audit دست‌نخورده می‌مانند.
    """
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    if (payload.confirm or "").strip() != "پاک‌سازی":
        raise bad_request("برای تأیید، عبارت «پاک‌سازی» را دقیقاً وارد کنید.")

    org_id = ctx.organization_id
    removed: Dict[str, int] = {}
    domain_tables = (
        ("actions", Action_items),
        ("decisions", Decisions),
        ("minute_versions", Minute_versions),
        ("minutes", Minutes),
        ("transcripts", Transcripts),
        ("recordings", Recordings),
        ("jobs", Jobs),
        ("ai_usage_events", Ai_usage_events),
        ("agenda_items", Agenda_items),
        ("participants", Participants),
        ("meetings", Meetings),
        ("notifications", Notifications),
        ("invitations", Invitations),
    )
    for label, model in domain_tables:
        result = await db.execute(delete(model).where(model.organization_id == org_id))
        removed[label] = int(result.rowcount or 0)

    virtual_members = await db.execute(
        delete(Memberships).where(
            Memberships.organization_id == org_id,
            Memberships.is_virtual.is_(True),
            Memberships.id != ctx.membership_id,
        )
    )
    removed["demo_members"] = int(virtual_members.rowcount or 0)

    org = ctx.organization
    org.is_demo = False
    org.ai_minutes_used = 0
    total = sum(removed.values())
    await audit(
        db,
        ctx,
        "organization.demo_data_purged",
        "organization",
        org_id,
        f"حذف {total} رکورد نمایشی",
    )
    await db.commit()
    return {"success": True, "removed": removed, "total": total, "is_demo": False}


# ---------------------------------------------------------------------------
# اعلان‌ها و Audit
# ---------------------------------------------------------------------------


@router.get("/notifications")
async def list_notifications(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    rows = await list_owned(
        db,
        Notifications,
        ctx,
        Notifications.recipient_membership_id == ctx.membership_id,
        order_by=Notifications.id.desc(),
        limit=60,
    )
    await db.commit()
    unread = sum(1 for row in rows if not row.is_read)
    return {
        "items": [dump(row, core.NOTIFICATION_FIELDS) for row in rows],
        "unread": unread,
    }


@router.post("/notifications/read")
async def mark_notifications_read(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    rows = await list_owned(
        db, Notifications, ctx, Notifications.recipient_membership_id == ctx.membership_id
    )
    for row in rows:
        if not row.is_read:
            row.is_read = True
            row.read_at = core.now_iso()
    await db.commit()
    return {"success": True}


@router.get("/audit")
async def list_audit(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    rows = await list_owned(db, Audit_logs, ctx, order_by=Audit_logs.id.desc(), limit=150)
    await db.commit()
    return {"items": [dump(row, core.AUDIT_FIELDS) for row in rows]}


# ---------------------------------------------------------------------------
# داشبورد شاخص‌ها
# ---------------------------------------------------------------------------


@router.get("/dashboard")
async def dashboard(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    await core.refresh_overdue_actions(db, ctx.organization_id)

    meetings = await list_owned(db, Meetings, ctx, order_by=Meetings.starts_at)
    participants = await list_owned(db, Participants, ctx)
    actions = await list_owned(db, Action_items, ctx)
    minutes_rows = await list_owned(db, Minutes, ctx)

    now = core.utc_now()
    upcoming = [m for m in meetings if (core.parse_iso(m.starts_at) or now) >= now]
    past = [m for m in meetings if (core.parse_iso(m.starts_at) or now) < now]

    past_ids = {int(m.id) for m in past}
    invited = [p for p in participants if int(p.meeting_id) in past_ids]
    attended = [p for p in invited if p.attended]
    attendance_rate = round(len(attended) / len(invited) * 100) if invited else 0

    action_counts = {status: 0 for status in ACTION_STATUSES}
    for action in actions:
        action_counts[action.status if action.status in action_counts else "open"] += 1
    completion_rate = (
        round(action_counts["done"] / len(actions) * 100) if actions else 0
    )

    minutes_counts: Dict[str, int] = {}
    for row in minutes_rows:
        minutes_counts[row.status] = minutes_counts.get(row.status, 0) + 1

    by_type: Dict[str, int] = {}
    for meeting in meetings:
        key = meeting.meeting_type or "نامشخص"
        by_type[key] = by_type.get(key, 0) + 1

    monthly: Dict[str, int] = {}
    for meeting in meetings:
        starts = core.parse_iso(meeting.starts_at)
        if starts:
            key = starts.strftime("%Y-%m")
            monthly[key] = monthly.get(key, 0) + 1

    my_actions = [
        dump(action, core.ACTION_FIELDS)
        for action in actions
        if int(action.owner_membership_id or 0) == ctx.membership_id
        and action.status in ("open", "in_progress", "overdue")
    ]

    await db.commit()
    return {
        "totals": {
            "meetings": len(meetings),
            "upcoming": len(upcoming),
            "past": len(past),
            "attendance_rate": attendance_rate,
            "actions": len(actions),
            "action_completion_rate": completion_rate,
            "overdue_actions": action_counts["overdue"],
            "pending_minutes": minutes_counts.get("in_review", 0),
        },
        "action_counts": action_counts,
        "minutes_counts": minutes_counts,
        "meetings_by_type": [{"name": key, "value": value} for key, value in by_type.items()],
        "meetings_by_month": [
            {"month": key, "value": monthly[key]} for key in sorted(monthly.keys())
        ],
        "next_meetings": [dump(m, MEETING_FIELDS) for m in upcoming[:5]],
        "my_open_actions": my_actions[:8],
        "quota": quota_snapshot(ctx.organization),
    }
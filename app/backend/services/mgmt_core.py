"""هستهٔ مشترک سامانهٔ مدیریت جلسات.

این ماژول مرزهای منطقی سند معماری را روی زیرساخت پلتفرم پیاده می‌کند:

* ``TenantContext`` — جایگزین ``RequestContext`` و ``SET LOCAL app.current_org``؛
  هر درخواست فقط با ``organization_id`` کاربر جاری کار می‌کند.
* ``require_role`` — ماتریس RBAC سه نقش با پاسخ ۴۰۳.
* ``QuotaGuard`` — بررسی سهمیهٔ دقیقهٔ صوت پیش از شروع کار AI و ثبت مصرف پس از پایان.
* ``audit`` / ``notify`` — لاگ رویدادهای حساس و اعلان درون‌برنامه‌ای.
* ``seed_demo_data`` — دادهٔ نمایشی تا سامانه از لحظهٔ اول قابل نمایش باشد.

قاعدهٔ زمان: همهٔ زمان‌ها به UTC و در قالب ``YYYY-MM-DDTHH:MM:SSZ`` ذخیره می‌شوند؛
تبدیل به تقویم شمسی فقط در مرز رابط کاربری انجام می‌گیرد.
"""

from __future__ import annotations

import json
import logging
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.action_items import Action_items
from models.agenda_items import Agenda_items
from models.ai_usage_events import Ai_usage_events
from models.audit_logs import Audit_logs
from models.decisions import Decisions
from models.invitations import Invitations
from models.meetings import Meetings
from models.memberships import Memberships
from models.minute_versions import Minute_versions
from models.minutes import Minutes
from models.notifications import Notifications
from models.organizations import Organizations
from models.participants import Participants
from models.recordings import Recordings
from models.transcripts import Transcripts

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ثابت‌ها و پیکربندی «استفادهٔ محدود»
# ---------------------------------------------------------------------------

ROLE_ADMIN = "org_admin"
ROLE_SECRETARY = "secretary"
ROLE_MEMBER = "member"
ALL_ROLES = (ROLE_ADMIN, ROLE_SECRETARY, ROLE_MEMBER)

ROLE_LABELS = {
    ROLE_ADMIN: "مدیر سازمان",
    ROLE_SECRETARY: "دبیر جلسه",
    ROLE_MEMBER: "عضو",
}

MEETING_TYPES = ["هیئت‌مدیره", "عملیاتی", "پروژه‌ای", "کمیته"]

# سقف‌های محافظه‌کارانهٔ نسخهٔ نمایشی (مطابق بخش ۳.۱.۲ سند معماری)
DEMO_MONTHLY_AI_MINUTES = 300
DEMO_MAX_CONCURRENT_AI_JOBS = 3
SYSTEM_MAX_CONCURRENT_AI_JOBS = 10
DEMO_MAX_AUDIO_MB = 80
DEMO_MAX_AUDIO_MINUTES = 90
DEMO_AUDIO_RETENTION_DAYS = 90

AUDIO_BUCKET = "meeting-audio"
ALLOWED_AUDIO_EXTENSIONS = ["mp3", "wav", "m4a", "ogg", "webm", "aac", "flac"]

TRANSCRIBE_MODEL = "scribe_v2"
MINUTES_MODEL = "gpt-5.6-sol"

MINUTES_DRAFT = "draft"
MINUTES_IN_REVIEW = "in_review"
MINUTES_APPROVED = "approved"
MINUTES_LOCKED = "locked"
MINUTES_FLOW = [MINUTES_DRAFT, MINUTES_IN_REVIEW, MINUTES_APPROVED, MINUTES_LOCKED]

ACTION_STATUSES = ["open", "in_progress", "done", "overdue"]


# ---------------------------------------------------------------------------
# ابزارهای زمان
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """زمان جاری با منطقهٔ زمانی UTC."""
    return datetime.now(timezone.utc)


def iso_utc(value: datetime) -> str:
    """قالب یکنواخت ذخیره‌سازی زمان (UTC و قابل مرتب‌سازی رشته‌ای)."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def now_iso() -> str:
    return iso_utc(utc_now())


def parse_iso(value: Optional[str]) -> Optional[datetime]:
    """تفسیر رشتهٔ زمانی ذخیره‌شده یا ورودی کاربر به ``datetime`` آگاه از منطقهٔ زمانی."""
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def normalize_iso(value: Optional[str]) -> Optional[str]:
    parsed = parse_iso(value)
    return iso_utc(parsed) if parsed else None


def secrets_token(length: int = 8) -> str:
    """رشتهٔ تصادفی کوتاه برای یکتاسازی کلید فایل در Object Storage."""
    return secrets.token_hex(max(length // 2, 2))


def current_period() -> str:
    """دورهٔ سهمیه به‌صورت ``YYYY-MM`` بر پایهٔ UTC."""
    return utc_now().strftime("%Y-%m")


# ---------------------------------------------------------------------------
# زمینهٔ مستأجر
# ---------------------------------------------------------------------------


@dataclass
class TenantContext:
    """زمینهٔ اجرای هر درخواست؛ هیچ کوئری دامنه‌ای بدون ``organization_id`` اجرا نمی‌شود."""

    organization: Organizations
    membership: Memberships
    user_id: str
    user_email: str

    @property
    def organization_id(self) -> int:
        return int(self.organization.id)

    @property
    def role(self) -> str:
        return self.membership.role or ROLE_MEMBER

    @property
    def membership_id(self) -> int:
        return int(self.membership.id)

    @property
    def actor_name(self) -> str:
        return self.membership.full_name or self.user_email or "کاربر"

    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN

    def is_secretary_of(self, meeting: Meetings) -> bool:
        if self.role == ROLE_ADMIN:
            return True
        if self.role != ROLE_SECRETARY:
            return False
        return meeting.secretary_membership_id in (None, self.membership_id)


def forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def require_role(ctx: TenantContext, *roles: str) -> None:
    """اعمال ماتریس RBAC؛ در صورت نداشتن نقش لازم، ۴۰۳ با پیام فارسی."""
    if ctx.role in roles:
        return
    allowed = "، ".join(ROLE_LABELS.get(role, role) for role in roles)
    raise forbidden(
        f"دسترسی لازم را ندارید. این عملیات فقط برای نقش {allowed} مجاز است "
        f"(نقش فعلی شما: {ROLE_LABELS.get(ctx.role, ctx.role)})."
    )


def require_meeting_manager(ctx: TenantContext, meeting: Meetings) -> None:
    """ویرایش جلسه فقط برای مدیر سازمان یا دبیر همان جلسه."""
    if ctx.is_secretary_of(meeting):
        return
    raise forbidden(
        "دسترسی لازم را ندارید. مدیریت این جلسه فقط برای مدیر سازمان یا دبیر همان جلسه مجاز است."
    )


# ---------------------------------------------------------------------------
# جست‌وجوی امن در مرز مستأجر
# ---------------------------------------------------------------------------


async def get_owned(db: AsyncSession, model: Any, obj_id: int, ctx: TenantContext, label: str):
    """واکشی رکورد با فیلتر اجباری سازمان؛ رکورد سازمان دیگر «یافت نشد» است."""
    result = await db.execute(
        select(model).where(model.id == obj_id, model.organization_id == ctx.organization_id)
    )
    obj = result.scalar_one_or_none()
    if obj is None:
        raise not_found(f"{label} یافت نشد.")
    return obj


async def list_owned(
    db: AsyncSession,
    model: Any,
    ctx: TenantContext,
    *extra_conditions: Any,
    order_by: Any = None,
    limit: Optional[int] = None,
) -> List[Any]:
    stmt = select(model).where(model.organization_id == ctx.organization_id)
    for condition in extra_conditions:
        stmt = stmt.where(condition)
    if order_by is not None:
        stmt = stmt.order_by(order_by)
    if limit:
        stmt = stmt.limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Audit و اعلان
# ---------------------------------------------------------------------------


async def audit(
    db: AsyncSession,
    ctx: TenantContext,
    action: str,
    entity_type: str = "",
    entity_id: Optional[int] = None,
    detail: str = "",
) -> None:
    """ثبت رویداد حساس؛ نوشتن Audit هرگز جریان اصلی را متوقف نمی‌کند."""
    try:
        db.add(
            Audit_logs(
                organization_id=ctx.organization_id,
                actor_user_id=ctx.user_id,
                actor_name=ctx.actor_name,
                actor_role=ctx.role,
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail[:900],
            )
        )
    except Exception as exc:  # pragma: no cover - محافظ عملیاتی
        logger.warning("ثبت Audit ناموفق بود: %s", exc)


async def notify(
    db: AsyncSession,
    organization_id: int,
    *,
    membership_id: Optional[int],
    user_id: Optional[str],
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    dedupe_key: str = "",
) -> None:
    """ایجاد اعلان درون‌برنامه‌ای با محافظ تکرار."""
    if dedupe_key:
        existing = await db.execute(
            select(Notifications).where(
                Notifications.organization_id == organization_id,
                Notifications.dedupe_key == dedupe_key,
            )
        )
        if existing.scalars().first() is not None:
            return
    db.add(
        Notifications(
            organization_id=organization_id,
            recipient_membership_id=membership_id,
            recipient_user_id=user_id,
            kind=kind,
            title=title[:300],
            body=body[:900],
            link=link,
            dedupe_key=dedupe_key,
            is_read=False,
        )
    )


async def notify_role(
    db: AsyncSession,
    organization_id: int,
    roles: List[str],
    *,
    kind: str,
    title: str,
    body: str = "",
    link: str = "",
    dedupe_prefix: str = "",
) -> None:
    """اعلان برای همهٔ اعضای دارای نقش‌های مشخص (مثلاً درخواست تأیید صورتجلسه)."""
    result = await db.execute(
        select(Memberships).where(
            Memberships.organization_id == organization_id,
            Memberships.role.in_(roles),
            Memberships.status == "active",
        )
    )
    for member in result.scalars().all():
        await notify(
            db,
            organization_id,
            membership_id=int(member.id),
            user_id=member.member_user_id,
            kind=kind,
            title=title,
            body=body,
            link=link,
            dedupe_key=f"{dedupe_prefix}:{member.id}" if dedupe_prefix else "",
        )


# ---------------------------------------------------------------------------
# سهمیه و همزمانی (QuotaGuard)
# ---------------------------------------------------------------------------


def _reset_period_if_needed(org: Organizations) -> None:
    period = current_period()
    if (org.quota_period or "") != period:
        org.quota_period = period
        org.ai_minutes_used = 0


def quota_snapshot(org: Organizations) -> Dict[str, Any]:
    _reset_period_if_needed(org)
    limit = int(org.monthly_ai_minutes_quota or DEMO_MONTHLY_AI_MINUTES)
    used = int(org.ai_minutes_used or 0)
    return {
        "period": org.quota_period,
        "limit_minutes": limit,
        "used_minutes": used,
        "remaining_minutes": max(limit - used, 0),
        "max_audio_mb": int(org.max_audio_mb or DEMO_MAX_AUDIO_MB),
        "max_audio_minutes": int(org.max_audio_minutes or DEMO_MAX_AUDIO_MINUTES),
        "max_concurrent_ai_jobs": int(org.max_concurrent_ai_jobs or DEMO_MAX_CONCURRENT_AI_JOBS),
        "allowed_formats": ALLOWED_AUDIO_EXTENSIONS,
    }


def ensure_quota(org: Organizations, minutes_needed: int) -> None:
    """بررسی سهمیه پیش از شروع کار AI (سد اصلی هزینهٔ کنترل‌نشده)."""
    snapshot = quota_snapshot(org)
    if minutes_needed <= 0:
        return
    if snapshot["remaining_minutes"] < minutes_needed:
        raise conflict(
            "سهمیهٔ هوش مصنوعی این سازمان کافی نیست. "
            f"باقی‌ماندهٔ دورهٔ {snapshot['period']}: {snapshot['remaining_minutes']} دقیقه، "
            f"نیاز این کار: {minutes_needed} دقیقه. برای افزایش سهمیه با مدیر پلتفرم تماس بگیرید."
        )


async def record_usage(
    db: AsyncSession,
    org: Organizations,
    *,
    kind: str,
    provider: str,
    model: str,
    minutes: int,
    job_id: Optional[int] = None,
    meeting_id: Optional[int] = None,
    detail: str = "",
) -> None:
    """ثبت مصرف واقعی پس از پایان موفق کار AI."""
    _reset_period_if_needed(org)
    org.ai_minutes_used = int(org.ai_minutes_used or 0) + max(minutes, 0)
    db.add(
        Ai_usage_events(
            organization_id=int(org.id),
            job_id=job_id,
            meeting_id=meeting_id,
            kind=kind,
            provider=provider,
            model=model,
            minutes_charged=max(minutes, 0),
            detail=detail[:900],
        )
    )


def validate_audio_file(org: Organizations, file_name: str, size_bytes: int) -> str:
    """اعتبارسنجی فرمت و حجم فایل صوتی با پیام خطای روشن فارسی."""
    extension = (file_name.rsplit(".", 1)[-1] if "." in file_name else "").lower()
    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise bad_request(
            "فرمت فایل صوتی پشتیبانی نمی‌شود. فرمت‌های مجاز: "
            + "، ".join(ALLOWED_AUDIO_EXTENSIONS)
        )
    max_mb = int(org.max_audio_mb or DEMO_MAX_AUDIO_MB)
    if size_bytes <= 0:
        raise bad_request("فایل صوتی خالی است یا حجم آن قابل تشخیص نیست.")
    if size_bytes > max_mb * 1024 * 1024:
        actual = round(size_bytes / (1024 * 1024), 1)
        raise bad_request(
            f"حجم فایل صوتی ({actual} مگابایت) از سقف مجاز این سازمان ({max_mb} مگابایت) بیشتر است."
        )
    return extension


# ---------------------------------------------------------------------------
# اقدامات: به‌روزرسانی وضعیت تأخیر
# ---------------------------------------------------------------------------


async def refresh_overdue_actions(db: AsyncSession, organization_id: int) -> None:
    """اقدامات باز با مهلت گذشته به وضعیت «تأخیر» منتقل می‌شوند."""
    result = await db.execute(
        select(Action_items).where(
            Action_items.organization_id == organization_id,
            Action_items.status.in_(["open", "in_progress"]),
        )
    )
    now = utc_now()
    for item in result.scalars().all():
        due = parse_iso(item.due_date)
        if due and due < now:
            item.status = "overdue"


# ---------------------------------------------------------------------------
# متن فارسی: نرمال‌سازی برای جست‌وجو
# ---------------------------------------------------------------------------

_FA_TRANSLATION = str.maketrans(
    {
        "ي": "ی",
        "ك": "ک",
        "آ": "ا",
        "إ": "ا",
        "أ": "ا",
        "ؤ": "و",
        "ة": "ه",
        "ۀ": "ه",
        "ى": "ی",
        "\u200c": " ",
    }
)


def fa_normalize(text: Optional[str]) -> str:
    """یکسان‌سازی ی/ک/نیم‌فاصله و اعراب برای جست‌وجوی فارسی."""
    if not text:
        return ""
    normalized = str(text).translate(_FA_TRANSLATION)
    normalized = re.sub(r"[\u064B-\u0652\u0640]", "", normalized)
    return re.sub(r"\s+", " ", normalized).strip().lower()


# ---------------------------------------------------------------------------
# سریال‌سازی برای پاسخ API
# ---------------------------------------------------------------------------


def dump(obj: Any, fields: List[str]) -> Dict[str, Any]:
    payload: Dict[str, Any] = {}
    for field in fields:
        value = getattr(obj, field, None)
        if isinstance(value, datetime):
            value = iso_utc(value)
        payload[field] = value
    return payload


MEETING_FIELDS = [
    "id",
    "title",
    "description",
    "meeting_type",
    "starts_at",
    "duration_minutes",
    "location",
    "online_url",
    "secretary_membership_id",
    "secretary_name",
    "status",
    "created_by_name",
    "created_at",
]
MEMBER_FIELDS = ["id", "member_user_id", "email", "full_name", "role", "status", "is_virtual"]
INVITATION_FIELDS = [
    "id",
    "email",
    "role",
    "token",
    "status",
    "expires_at",
    "invited_by_name",
    "created_at",
]
AGENDA_FIELDS = ["id", "meeting_id", "position", "title", "notes", "planned_minutes", "owner_name"]
PARTICIPANT_FIELDS = [
    "id",
    "meeting_id",
    "membership_id",
    "full_name",
    "rsvp_status",
    "rsvp_note",
    "attended",
]
RECORDING_FIELDS = [
    "id",
    "meeting_id",
    "bucket_name",
    "object_key",
    "file_name",
    "mime_type",
    "size_bytes",
    "duration_seconds",
    "upload_status",
    "consent_ack",
    "purge_after",
    "uploaded_by_name",
    "created_at",
]
TRANSCRIPT_FIELDS = [
    "id",
    "meeting_id",
    "recording_id",
    "provider",
    "model",
    "full_text",
    "duration_seconds",
    "known_word_ratio",
    "stats_words",
    "stats_known_words",
    "job_id",
    "created_at",
]
MINUTES_FIELDS = [
    "id",
    "meeting_id",
    "status",
    "body_markdown",
    "summary",
    "current_version",
    "generated_by",
    "review_requested_at",
    "approved_by_name",
    "approved_at",
    "locked_at",
    "updated_at",
]
DECISION_FIELDS = ["id", "meeting_id", "minutes_id", "position", "title", "description", "source"]
ACTION_FIELDS = [
    "id",
    "meeting_id",
    "decision_id",
    "title",
    "description",
    "owner_membership_id",
    "owner_name",
    "due_date",
    "status",
    "progress_note",
    "source",
]
JOB_FIELDS = [
    "id",
    "meeting_id",
    "job_type",
    "status",
    "progress",
    "attempts",
    "max_attempts",
    "error_message",
    "provider",
    "started_at",
    "finished_at",
    "created_by_name",
    "created_at",
]
NOTIFICATION_FIELDS = ["id", "kind", "title", "body", "link", "is_read", "created_at"]
AUDIT_FIELDS = [
    "id",
    "actor_name",
    "actor_role",
    "action",
    "entity_type",
    "entity_id",
    "detail",
    "created_at",
]


def transcript_payload(transcript: Transcripts) -> Dict[str, Any]:
    payload = dump(transcript, TRANSCRIPT_FIELDS)
    try:
        payload["segments"] = json.loads(transcript.segments_json or "[]")
    except (TypeError, ValueError):
        payload["segments"] = []
    return payload


# ---------------------------------------------------------------------------
# ساخت سازمان و دادهٔ نمایشی
# ---------------------------------------------------------------------------


async def resolve_context(db: AsyncSession, user: Any) -> TenantContext:
    """یافتن عضویت کاربر جاری؛ در نخستین ورود سازمان و دادهٔ نمایشی ساخته می‌شود."""
    user_id = str(user.id)
    result = await db.execute(select(Memberships).where(Memberships.member_user_id == user_id))
    membership = result.scalars().first()

    if membership is None:
        if user_id.startswith("app:"):
            # کاربران احراز هویت مستقل همیشه هنگام ساخت، عضویت می‌گیرند؛
            # نبودِ عضویت یعنی دادهٔ ناسازگار، نه نخستین ورود.
            raise not_found("عضویت این حساب کاربری در سازمان یافت نشد.")
        membership = await _bootstrap_organization(db, user)

    org_result = await db.execute(
        select(Organizations).where(Organizations.id == membership.organization_id)
    )
    organization = org_result.scalar_one_or_none()
    if organization is None:
        raise not_found("سازمان این حساب کاربری یافت نشد.")
    if (organization.status or "active") != "active":
        raise forbidden("این سازمان توسط مدیر پلتفرم موقتاً غیرفعال شده است.")
    if (membership.status or "active") != "active":
        raise forbidden("حساب شما در این سازمان غیرفعال شده است.")

    _reset_period_if_needed(organization)
    return TenantContext(
        organization=organization,
        membership=membership,
        user_id=user_id,
        user_email=getattr(user, "email", "") or "",
    )


async def _bootstrap_organization(db: AsyncSession, user: Any) -> Memberships:
    """ایجاد خودکار سازمان در نخستین ورود + بارگذاری دادهٔ نمایشی."""
    email = (getattr(user, "email", "") or "").strip()
    display_name = (getattr(user, "name", None) or email.split("@")[0] or "کاربر مهمان").strip()
    slug_base = re.sub(r"[^a-zA-Z0-9]+", "-", (email.split("@")[0] or "org")).strip("-").lower()
    slug = f"{slug_base or 'org'}-{str(user.id)[:8]}"

    organization = Organizations(
        name=f"سازمان {display_name}",
        slug=slug,
        plan_code="standard",
        timezone="Asia/Tehran",
        status="active",
        monthly_ai_minutes_quota=DEMO_MONTHLY_AI_MINUTES,
        ai_minutes_used=0,
        quota_period=current_period(),
        max_concurrent_ai_jobs=DEMO_MAX_CONCURRENT_AI_JOBS,
        audio_retention_days=DEMO_AUDIO_RETENTION_DAYS,
        max_audio_mb=DEMO_MAX_AUDIO_MB,
        max_audio_minutes=DEMO_MAX_AUDIO_MINUTES,
        is_demo=False,
    )
    db.add(organization)
    await db.flush()

    membership = Memberships(
        organization_id=int(organization.id),
        member_user_id=str(user.id),
        email=email,
        full_name=display_name,
        role=ROLE_ADMIN,
        status="active",
        is_virtual=False,
    )
    db.add(membership)
    await db.flush()

    # دادهٔ نمایشی هرگز به‌صورت خودکار ساخته نمی‌شود؛ سازمان تازه خالی و واقعی است.
    await db.commit()
    return membership


async def seed_demo_data(
    db: AsyncSession, organization: Organizations, owner: Memberships
) -> None:
    """دادهٔ نمونهٔ سازمان نمایشی: اعضا، جلسات گذشته/آینده، صورتجلسهٔ تأییدشده و مصوبات."""
    org_id = int(organization.id)
    now = utc_now()

    virtual_members = [
        ("مریم رضایی", "maryam.rezaei@demo.local", ROLE_SECRETARY),
        ("علی محمدی", "ali.mohammadi@demo.local", ROLE_MEMBER),
        ("سارا کریمی", "sara.karimi@demo.local", ROLE_MEMBER),
        ("حسین نوری", "hossein.nouri@demo.local", ROLE_MEMBER),
    ]
    members: Dict[str, Memberships] = {}
    for full_name, email, role in virtual_members:
        member = Memberships(
            organization_id=org_id,
            member_user_id="",
            email=email,
            full_name=full_name,
            role=role,
            status="active",
            is_virtual=True,
        )
        db.add(member)
        members[full_name] = member
    await db.flush()

    secretary = members["مریم رضایی"]
    ali = members["علی محمدی"]
    sara = members["سارا کریمی"]
    hossein = members["حسین نوری"]

    # ── جلسهٔ ۱: گذشته، صورتجلسهٔ تأییدشده و قفل‌شده ───────────────────────────
    board = Meetings(
        organization_id=org_id,
        title="جلسهٔ هیئت‌مدیره — بازبینی بودجهٔ فصل جاری",
        description="بررسی انحراف بودجه و تصویب اولویت‌های هزینه‌ای فصل آینده.",
        meeting_type="هیئت‌مدیره",
        starts_at=iso_utc(now - timedelta(days=12, hours=3)),
        duration_minutes=90,
        location="اتاق جلسات مرکزی — طبقهٔ ۵",
        online_url="",
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary.full_name,
        status="held",
        created_by_user_id=owner.member_user_id,
        created_by_name=owner.full_name,
    )
    # ── جلسهٔ ۲: گذشته، صورتجلسه در انتظار تأیید ─────────────────────────────
    weekly = Meetings(
        organization_id=org_id,
        title="جلسهٔ عملیاتی هفتگی — پیشرفت خطوط تولید",
        description="مرور شاخص‌های هفتگی و رفع موانع اجرایی.",
        meeting_type="عملیاتی",
        starts_at=iso_utc(now - timedelta(days=4, hours=1)),
        duration_minutes=60,
        location="",
        online_url="https://meet.demo.local/weekly-ops",
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary.full_name,
        status="held",
        created_by_user_id=owner.member_user_id,
        created_by_name=owner.full_name,
    )
    # ── جلسهٔ ۳: گذشته و بدون صورتجلسه (نمایش نقطهٔ شروع جریان AI) ───────────
    review = Meetings(
        organization_id=org_id,
        title="کمیتهٔ فناوری — جمع‌بندی ارزیابی تأمین‌کنندگان",
        description="گزارش نتایج ارزیابی فنی سه تأمین‌کنندهٔ نهایی.",
        meeting_type="کمیته",
        starts_at=iso_utc(now - timedelta(days=1, hours=2)),
        duration_minutes=75,
        location="اتاق جلسات فناوری",
        online_url="",
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary.full_name,
        status="held",
        created_by_user_id=owner.member_user_id,
        created_by_name=owner.full_name,
    )
    # ── جلسهٔ ۴ و ۵: آینده ─────────────────────────────────────────────────
    upcoming = Meetings(
        organization_id=org_id,
        title="جلسهٔ پروژه‌ای — کیک‌آف فاز دوم استقرار",
        description="تعیین تیم اجرایی، زمان‌بندی و ریسک‌های فاز دوم.",
        meeting_type="پروژه‌ای",
        starts_at=iso_utc(now + timedelta(days=2, hours=4)),
        duration_minutes=120,
        location="",
        online_url="https://meet.demo.local/phase2-kickoff",
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary.full_name,
        status="scheduled",
        created_by_user_id=owner.member_user_id,
        created_by_name=owner.full_name,
    )
    future_board = Meetings(
        organization_id=org_id,
        title="جلسهٔ هیئت‌مدیره — تصویب برنامهٔ سالانه",
        description="ارائهٔ برنامهٔ سالانه و تصویب سرفصل‌های بودجه.",
        meeting_type="هیئت‌مدیره",
        starts_at=iso_utc(now + timedelta(days=9, hours=2)),
        duration_minutes=90,
        location="اتاق جلسات مرکزی — طبقهٔ ۵",
        online_url="",
        secretary_membership_id=int(secretary.id),
        secretary_name=secretary.full_name,
        status="scheduled",
        created_by_user_id=owner.member_user_id,
        created_by_name=owner.full_name,
    )
    for meeting in (board, weekly, review, upcoming, future_board):
        db.add(meeting)
    await db.flush()

    agenda_plan = [
        (board, [("گزارش انحراف بودجهٔ فصل", 25, owner), ("اولویت‌بندی هزینه‌های فصل آینده", 35, ali), ("جمع‌بندی و مصوبات", 20, secretary)]),
        (weekly, [("مرور شاخص‌های هفتگی تولید", 20, ali), ("موانع اجرایی و راهکارها", 25, sara)]),
        (review, [("نتایج ارزیابی فنی تأمین‌کنندگان", 40, hossein), ("پیشنهاد نهایی کمیته", 25, secretary)]),
        (upcoming, [("محدودهٔ فاز دوم", 30, owner), ("تیم اجرایی و نقش‌ها", 30, sara), ("ریسک‌ها و برنامهٔ کاهش", 40, hossein)]),
        (future_board, [("ارائهٔ برنامهٔ سالانه", 45, owner), ("پرسش و پاسخ اعضا", 30, secretary)]),
    ]
    for meeting, items in agenda_plan:
        for index, (title, minutes, owner_member) in enumerate(items, start=1):
            db.add(
                Agenda_items(
                    organization_id=org_id,
                    meeting_id=int(meeting.id),
                    position=index,
                    title=title,
                    notes="",
                    planned_minutes=minutes,
                    owner_name=owner_member.full_name,
                )
            )

    attendance_plan = [
        (board, [(owner, "accepted", True), (secretary, "accepted", True), (ali, "accepted", True), (sara, "declined", False), (hossein, "accepted", True)]),
        (weekly, [(owner, "accepted", True), (secretary, "accepted", True), (ali, "accepted", True), (sara, "accepted", False)]),
        (review, [(secretary, "accepted", True), (hossein, "accepted", True), (ali, "tentative", True)]),
        (upcoming, [(owner, "accepted", None), (secretary, "accepted", None), (sara, "pending", None), (hossein, "pending", None)]),
        (future_board, [(owner, "pending", None), (secretary, "accepted", None), (ali, "pending", None)]),
    ]
    for meeting, rows in attendance_plan:
        for member, rsvp, attended in rows:
            db.add(
                Participants(
                    organization_id=org_id,
                    meeting_id=int(meeting.id),
                    membership_id=int(member.id),
                    member_user_id=member.member_user_id,
                    full_name=member.full_name,
                    rsvp_status=rsvp,
                    rsvp_note="",
                    attended=bool(attended) if attended is not None else False,
                )
            )

    # رونویسی نمونه برای جلسهٔ هیئت‌مدیره
    board_segments = [
        {"start_ms": 0, "end_ms": 18000, "text": "جلسه با حضور اعضای هیئت‌مدیره آغاز شد و دستور جلسه قرائت شد."},
        {"start_ms": 18000, "end_ms": 96000, "text": "گزارش انحراف بودجه ارائه شد؛ انحراف اصلی در سرفصل خرید تجهیزات و برابر نه درصد بود."},
        {"start_ms": 96000, "end_ms": 210000, "text": "اعضا بر تفکیک بودجهٔ تجهیزات از بودجهٔ نگه‌داری توافق کردند تا پایش دقیق‌تر شود."},
        {"start_ms": 210000, "end_ms": 320000, "text": "مقرر شد گزارش ماهانهٔ انحراف بودجه تا پانزدهم هر ماه برای هیئت‌مدیره ارسال شود."},
        {"start_ms": 320000, "end_ms": 402000, "text": "سقف اختیار هزینه‌کرد مدیران عملیاتی بازبینی و جمع‌بندی جلسه اعلام شد."},
    ]
    board_text = " ".join(segment["text"] for segment in board_segments)
    db.add(
        Recordings(
            organization_id=org_id,
            meeting_id=int(board.id),
            bucket_name=AUDIO_BUCKET,
            object_key=f"demo/{org_id}/board-meeting-sample.mp3",
            file_name="board-meeting-sample.mp3",
            mime_type="audio/mpeg",
            size_bytes=7_340_032,
            duration_seconds=402,
            upload_status="uploaded",
            consent_ack=True,
            purge_after=iso_utc(now + timedelta(days=DEMO_AUDIO_RETENTION_DAYS)),
            uploaded_by_name=secretary.full_name,
        )
    )
    await db.flush()
    recording_result = await db.execute(
        select(Recordings).where(
            Recordings.organization_id == org_id, Recordings.meeting_id == int(board.id)
        )
    )
    board_recording = recording_result.scalars().first()

    db.add(
        Transcripts(
            organization_id=org_id,
            meeting_id=int(board.id),
            recording_id=int(board_recording.id) if board_recording else None,
            provider="atoms_platform",
            model=TRANSCRIBE_MODEL,
            full_text=board_text,
            segments_json=json.dumps(board_segments, ensure_ascii=False),
            duration_seconds=402,
            known_word_ratio=0.94,
            stats_words=len(board_text.split()),
            stats_known_words=int(len(board_text.split()) * 0.94),
            job_id=None,
        )
    )

    board_minutes_body = (
        "## جمع‌بندی جلسه\n"
        "هیئت‌مدیره گزارش انحراف بودجهٔ فصل جاری را بررسی و اولویت‌های هزینه‌ای فصل آینده را تصویب کرد.\n\n"
        "## مذاکرات بر پایهٔ دستور جلسه\n"
        "۱. **گزارش انحراف بودجهٔ فصل:** انحراف کل نه درصد و متمرکز در سرفصل خرید تجهیزات بود.\n"
        "۲. **اولویت‌بندی هزینه‌های فصل آینده:** تفکیک بودجهٔ تجهیزات از نگه‌داری مورد توافق قرار گرفت.\n"
        "۳. **جمع‌بندی و مصوبات:** گزارش‌دهی ماهانه و بازبینی سقف اختیار هزینه‌کرد تعیین شد.\n"
    )
    board_minutes = Minutes(
        organization_id=org_id,
        meeting_id=int(board.id),
        status=MINUTES_LOCKED,
        body_markdown=board_minutes_body,
        summary="تصویب تفکیک بودجهٔ تجهیزات و الزام گزارش ماهانهٔ انحراف بودجه.",
        current_version=2,
        generated_by="ai",
        review_requested_at=iso_utc(now - timedelta(days=11)),
        approved_by_name=owner.full_name,
        approved_at=iso_utc(now - timedelta(days=10)),
        locked_at=iso_utc(now - timedelta(days=10)),
    )
    weekly_minutes = Minutes(
        organization_id=org_id,
        meeting_id=int(weekly.id),
        status=MINUTES_IN_REVIEW,
        body_markdown=(
            "## جمع‌بندی جلسه\n"
            "شاخص‌های هفتگی تولید مرور شد و دو مانع اجرایی برای رفع فوری شناسایی گردید.\n\n"
            "## مذاکرات بر پایهٔ دستور جلسه\n"
            "۱. **مرور شاخص‌های هفتگی تولید:** تحقق برنامه نود و دو درصد بود.\n"
            "۲. **موانع اجرایی و راهکارها:** کمبود قطعهٔ یدکی و تأخیر تأمین‌کنندهٔ حمل مطرح شد.\n"
        ),
        summary="تحقق نود و دو درصدی برنامه و شناسایی دو مانع تأمین.",
        current_version=1,
        generated_by="ai",
        review_requested_at=iso_utc(now - timedelta(days=3)),
        approved_by_name="",
        approved_at="",
        locked_at="",
    )
    db.add(board_minutes)
    db.add(weekly_minutes)
    await db.flush()

    db.add(
        Minute_versions(
            organization_id=org_id,
            minutes_id=int(board_minutes.id),
            meeting_id=int(board.id),
            version=1,
            body_markdown=board_minutes_body,
            summary="پیش‌نویس تولیدشده توسط هوش مصنوعی.",
            status_at_version=MINUTES_DRAFT,
            changed_by_name=secretary.full_name,
            change_note="پیش‌نویس خودکار از رونویسی جلسه",
        )
    )
    db.add(
        Minute_versions(
            organization_id=org_id,
            minutes_id=int(board_minutes.id),
            meeting_id=int(board.id),
            version=2,
            body_markdown=board_minutes_body,
            summary=board_minutes.summary,
            status_at_version=MINUTES_APPROVED,
            changed_by_name=owner.full_name,
            change_note="تأیید نهایی و قفل صورتجلسه",
        )
    )
    db.add(
        Minute_versions(
            organization_id=org_id,
            minutes_id=int(weekly_minutes.id),
            meeting_id=int(weekly.id),
            version=1,
            body_markdown=weekly_minutes.body_markdown,
            summary=weekly_minutes.summary,
            status_at_version=MINUTES_DRAFT,
            changed_by_name=secretary.full_name,
            change_note="پیش‌نویس خودکار از رونویسی جلسه",
        )
    )

    decisions_plan = [
        (board, board_minutes, 1, "تفکیک بودجهٔ تجهیزات از بودجهٔ نگه‌داری", "از فصل آینده دو سرفصل مستقل در سامانهٔ مالی ایجاد شود."),
        (board, board_minutes, 2, "گزارش ماهانهٔ انحراف بودجه", "گزارش تا پانزدهم هر ماه برای هیئت‌مدیره ارسال شود."),
        (weekly, weekly_minutes, 1, "تأمین اضطراری قطعات یدکی بحرانی", "فهرست قطعات بحرانی تهیه و سفارش اضطراری ثبت شود."),
    ]
    created_decisions = []
    for meeting, minutes_row, position, title, description in decisions_plan:
        decision = Decisions(
            organization_id=org_id,
            meeting_id=int(meeting.id),
            minutes_id=int(minutes_row.id),
            position=position,
            title=title,
            description=description,
            source="ai",
        )
        db.add(decision)
        created_decisions.append(decision)
    await db.flush()

    actions_plan = [
        (board, created_decisions[0], "ایجاد دو سرفصل مستقل در سامانهٔ مالی", ali, now + timedelta(days=6), "in_progress", "هماهنگی با واحد مالی انجام شد."),
        (board, created_decisions[1], "تدوین قالب گزارش ماهانهٔ انحراف بودجه", owner, now - timedelta(days=3), "overdue", "در انتظار تأیید قالب."),
        (board, created_decisions[1], "ارسال نخستین گزارش ماهانه", secretary, now - timedelta(days=6), "done", "گزارش ارسال شد."),
        (weekly, created_decisions[2], "تهیهٔ فهرست قطعات بحرانی", sara, now + timedelta(days=3), "open", ""),
        (weekly, created_decisions[2], "ثبت سفارش اضطراری قطعات", hossein, now + timedelta(days=8), "open", ""),
        (review, None, "تدوین گزارش نهایی ارزیابی تأمین‌کنندگان", hossein, now + timedelta(days=5), "in_progress", "پیش‌نویس آماده است."),
    ]
    for meeting, decision, title, owner_member, due, status_value, note in actions_plan:
        db.add(
            Action_items(
                organization_id=org_id,
                meeting_id=int(meeting.id),
                decision_id=int(decision.id) if decision is not None else None,
                title=title,
                description="",
                owner_membership_id=int(owner_member.id),
                owner_name=owner_member.full_name,
                due_date=iso_utc(due),
                status=status_value,
                progress_note=note,
                source="ai" if decision is not None else "manual",
            )
        )

    organization.ai_minutes_used = 7
    db.add(
        Ai_usage_events(
            organization_id=org_id,
            job_id=None,
            meeting_id=int(board.id),
            kind="transcribe",
            provider="atoms_platform",
            model=TRANSCRIBE_MODEL,
            minutes_charged=7,
            detail="رونویسی نمونهٔ جلسهٔ هیئت‌مدیره",
        )
    )

    await notify(
        db,
        org_id,
        membership_id=int(owner.id),
        user_id=owner.member_user_id,
        kind="review_request",
        title="صورتجلسهٔ «جلسهٔ عملیاتی هفتگی» در انتظار تأیید شماست",
        body="دبیر جلسه پیش‌نویس را برای بازبینی ارسال کرده است.",
        link=f"/meetings/{int(weekly.id)}",
        dedupe_key=f"seed-review-{weekly.id}",
    )
    await notify(
        db,
        org_id,
        membership_id=int(owner.id),
        user_id=owner.member_user_id,
        kind="due_soon",
        title="یک اقدام با مهلت گذشته در انتظار شماست",
        body="«تدوین قالب گزارش ماهانهٔ انحراف بودجه» از مهلت خود گذشته است.",
        link="/actions",
        dedupe_key=f"seed-overdue-{org_id}",
    )
    await notify(
        db,
        org_id,
        membership_id=int(owner.id),
        user_id=owner.member_user_id,
        kind="invite",
        title="دعوت به «جلسهٔ پروژه‌ای — کیک‌آف فاز دوم استقرار»",
        body="حضور شما در این جلسه درخواست شده است.",
        link=f"/meetings/{int(upcoming.id)}",
        dedupe_key=f"seed-invite-{upcoming.id}",
    )

    db.add(
        Audit_logs(
            organization_id=org_id,
            actor_user_id=owner.member_user_id,
            actor_name=owner.full_name,
            actor_role=ROLE_ADMIN,
            action="organization.created",
            entity_type="organization",
            entity_id=org_id,
            detail="ایجاد سازمان و بارگذاری دادهٔ نمایشی",
        )
    )
    db.add(
        Audit_logs(
            organization_id=org_id,
            actor_user_id=owner.member_user_id,
            actor_name=owner.full_name,
            actor_role=ROLE_ADMIN,
            action="minutes.locked",
            entity_type="minutes",
            entity_id=int(board_minutes.id),
            detail="تأیید و قفل صورتجلسهٔ جلسهٔ هیئت‌مدیره",
        )
    )
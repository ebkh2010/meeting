"""روتر ضبط صوت و کارهای غیرهمزمان هوش مصنوعی.

مرزهای منطقی سند معماری در این روتر پیاده شده است:

* **Storage خصوصی** — فرانت‌اند فایل را با URL امضاشده مستقیماً بارگذاری می‌کند و
  فقط ``object_key`` در پایگاه داده ذخیره می‌شود؛ لینک پخش هر بار تازه ساخته می‌شود.
* **صف کار پایدار** — هر کار AI یک رکورد در جدول ``jobs`` است؛ اجرا در پس‌زمینه و
  پیگیری با polling انجام می‌شود، پس بستن مرورگر کار را از بین نمی‌برد.
* **محافظ هزینه** — سهمیه پیش از شروع کار بررسی و پس از پایان موفق ثبت می‌شود؛
  در ``retry`` اگر نتیجهٔ تأمین‌کننده از قبل ذخیره شده باشد، فراخوان دوباره انجام نمی‌شود.
* **سقف همزمانی سه سطحی** — ۱۰ کار در کل سیستم، ۳ کار در هر سازمان.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from core.database import db_manager, get_db
from dependencies.app_auth import get_workspace_user as get_current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from schemas.auth import UserResponse
from schemas.storage import FileUpDownRequest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.agenda_items import Agenda_items
from models.jobs import Jobs
from models.meetings import Meetings
from models.minute_versions import Minute_versions
from models.minutes import Minutes
from models.decisions import Decisions
from models.action_items import Action_items
from models.memberships import Memberships
from models.organizations import Organizations
from models.participants import Participants
from models.recordings import Recordings
from models.transcripts import Transcripts
from services import ai_providers
from services import mgmt_core as core
from services import upload_limits as limits_service
from services.ai_gateway import (
    AIGatewayError,
    get_minutes_port,
    get_transcription_port,
)
from services.mgmt_core import (
    AUDIO_BUCKET,
    JOB_FIELDS,
    MINUTES_DRAFT,
    MINUTES_LOCKED,
    SYSTEM_MAX_CONCURRENT_AI_JOBS,
    TenantContext,
    audit,
    bad_request,
    conflict,
    dump,
    get_owned,
    list_owned,
    notify,
    require_meeting_manager,
    resolve_context,
)
from services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/meeting-ai", tags=["meeting-ai"])

JOB_TRANSCRIBE = "transcribe"
JOB_MINUTES = "minutes_draft"
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
ACTIVE_JOB_STATUSES = (JOB_QUEUED, JOB_RUNNING)


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------


class UploadUrlIn(BaseModel):
    meeting_id: int
    file_name: str = Field(..., min_length=3, max_length=200)
    size_bytes: int = 0


class RegisterRecordingIn(BaseModel):
    meeting_id: int
    object_key: str = Field(..., min_length=3)
    file_name: str
    mime_type: str = "audio/mpeg"
    size_bytes: int = 0
    duration_seconds: int = 0
    consent_ack: bool = False


class StartTranscribeIn(BaseModel):
    recording_id: int


class StartMinutesIn(BaseModel):
    meeting_id: int


class SuggestItemsIn(BaseModel):
    meeting_id: int


# ---------------------------------------------------------------------------
# ابزارهای صف
# ---------------------------------------------------------------------------


async def _count_active_jobs(db: AsyncSession, organization_id: Optional[int] = None) -> int:
    stmt = select(func.count(Jobs.id)).where(Jobs.status.in_(ACTIVE_JOB_STATUSES))
    if organization_id is not None:
        stmt = stmt.where(Jobs.organization_id == organization_id)
    result = await db.execute(stmt)
    return int(result.scalar() or 0)


async def _ensure_capacity(db: AsyncSession, ctx: TenantContext) -> None:
    """سقف همزمانی سه سطحی؛ پیام خطا وضعیت واقعی صف را توضیح می‌دهد."""
    org_limit = int(ctx.organization.max_concurrent_ai_jobs or core.DEMO_MAX_CONCURRENT_AI_JOBS)
    org_active = await _count_active_jobs(db, ctx.organization_id)
    if org_active >= org_limit:
        raise conflict(
            f"در این لحظه {org_active} کار هوش مصنوعی برای سازمان شما در حال اجراست "
            f"(سقف همزمان: {org_limit}). پس از پایان یکی از کارها دوباره تلاش کنید."
        )
    system_active = await _count_active_jobs(db)
    if system_active >= SYSTEM_MAX_CONCURRENT_AI_JOBS:
        raise conflict(
            "ظرفیت پردازش هوش مصنوعی سامانه پر است. کار شما را چند لحظه بعد می‌توانید ثبت کنید."
        )


async def _find_active_job(
    db: AsyncSession, ctx: TenantContext, job_type: str, meeting_id: int
) -> Optional[Jobs]:
    result = await db.execute(
        select(Jobs)
        .where(
            Jobs.organization_id == ctx.organization_id,
            Jobs.meeting_id == meeting_id,
            Jobs.job_type == job_type,
            Jobs.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(Jobs.id.desc())
    )
    return result.scalars().first()


def _spawn(job_id: int) -> None:
    """اجرای کار در پس‌زمینه؛ نشست پایگاه داده مستقل از درخواست HTTP است."""
    asyncio.create_task(_run_job(job_id))


# ---------------------------------------------------------------------------
# Endpoint: آماده‌سازی آپلود و ثبت فایل صوتی
# ---------------------------------------------------------------------------


@router.post("/upload-url")
async def create_upload_url(
    payload: UploadUrlIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ساخت URL امضاشدهٔ آپلود؛ باکت خصوصی است و کلید شامل شناسهٔ سازمان می‌شود."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    # سقف حجم صوت از تنظیمات سازمان خوانده می‌شود تا با فرم تنظیمات مدیریتی یکی باشد.
    limits = await limits_service.get_limits(db, ctx.organization_id)
    ctx.organization.max_audio_mb = int(limits["max_audio_mb"])
    extension = core.validate_audio_file(ctx.organization, payload.file_name, max(payload.size_bytes, 1))

    object_key = (
        f"org-{ctx.organization_id}/meeting-{payload.meeting_id}/"
        f"{core.utc_now().strftime('%Y%m%d%H%M%S')}-{core.secrets_token()}.{extension}"
    )
    await db.commit()

    storage = StorageService()
    signed = await storage.create_upload_url(
        FileUpDownRequest(bucket_name=AUDIO_BUCKET, object_key=object_key)
    )
    return {
        "bucket_name": AUDIO_BUCKET,
        "object_key": object_key,
        "upload_url": signed.upload_url,
        "expires_at": signed.expires_at,
    }


@router.post("/recordings")
async def register_recording(
    payload: RegisterRecordingIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ثبت فراداده فایل بارگذاری‌شده + مهر رضایت + تاریخ حذف خودکار."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    limits = await limits_service.get_limits(db, ctx.organization_id)
    ctx.organization.max_audio_mb = int(limits["max_audio_mb"])
    core.validate_audio_file(ctx.organization, payload.file_name, max(payload.size_bytes, 1))

    if not payload.consent_ack:
        raise bad_request(
            "برای بارگذاری فایل صوتی جلسه، تأیید اطلاع‌رسانی به حاضران الزامی است."
        )
    # سقف مدت صوت تنظیم‌پذیر است؛ مقدار ثابت قبلی (۹۰ دقیقه) فقط پیش‌فرض است.
    max_minutes = int(limits["max_audio_minutes"])
    if payload.duration_seconds and payload.duration_seconds > max_minutes * 60:
        actual_minutes = round(int(payload.duration_seconds) / 60, 1)
        raise bad_request(
            f"مدت فایل صوتی ({actual_minutes} دقیقه) از سقف مجاز این سازمان "
            f"({max_minutes} دقیقه) بیشتر است. مدیر سازمان می‌تواند این سقف را در "
            "تنظیمات سازمان › سقف‌های بارگذاری افزایش دهد."
        )

    recording = Recordings(
        organization_id=ctx.organization_id,
        meeting_id=payload.meeting_id,
        bucket_name=AUDIO_BUCKET,
        object_key=payload.object_key,
        file_name=payload.file_name,
        mime_type=payload.mime_type or "audio/mpeg",
        size_bytes=max(int(payload.size_bytes or 0), 0),
        duration_seconds=max(int(payload.duration_seconds or 0), 0),
        upload_status="uploaded",
        consent_ack=True,
        purge_after=core.iso_utc(
            core.utc_now()
            + core.timedelta(days=int(ctx.organization.audio_retention_days or core.DEMO_AUDIO_RETENTION_DAYS))
        ),
        uploaded_by_name=ctx.actor_name,
    )
    db.add(recording)
    await audit(db, ctx, "recording.uploaded", "recording", None, payload.file_name)
    await db.commit()
    return dump(recording, core.RECORDING_FIELDS)


@router.get("/recordings/{recording_id}/play-url")
async def recording_play_url(
    recording_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """لینک پخش موقت؛ هرگز در پایگاه داده ذخیره نمی‌شود."""
    ctx = await resolve_context(db, current_user)
    recording = await get_owned(db, Recordings, recording_id, ctx, "فایل صوتی")
    bucket = recording.bucket_name or AUDIO_BUCKET
    object_key = recording.object_key
    await db.commit()

    storage = StorageService()
    signed = await storage.create_download_url(
        FileUpDownRequest(bucket_name=bucket, object_key=object_key)
    )
    return {"download_url": signed.download_url, "expires_at": signed.expires_at}


@router.delete("/recordings/{recording_id}")
async def delete_recording(
    recording_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """حذف صوت بنا به درخواست حریم خصوصی؛ رونویسی متنی حفظ می‌شود."""
    ctx = await resolve_context(db, current_user)
    recording = await get_owned(db, Recordings, recording_id, ctx, "فایل صوتی")
    meeting = await get_owned(db, Meetings, int(recording.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    file_name = recording.file_name
    await db.delete(recording)
    await audit(db, ctx, "recording.deleted", "recording", recording_id, file_name or "")
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# Endpoint: شروع کارهای AI
# ---------------------------------------------------------------------------


@router.post("/jobs/transcribe")
async def start_transcribe(
    payload: StartTranscribeIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    recording = await get_owned(db, Recordings, payload.recording_id, ctx, "فایل صوتی")
    meeting = await get_owned(db, Meetings, int(recording.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    running = await _find_active_job(db, ctx, JOB_TRANSCRIBE, int(meeting.id))
    if running is not None:
        await db.commit()
        return dump(running, JOB_FIELDS)

    minutes_needed = max(1, (int(recording.duration_seconds or 0) + 59) // 60)
    core.ensure_quota(ctx.organization, minutes_needed)
    await _ensure_capacity(db, ctx)

    provider = get_transcription_port()
    job = Jobs(
        organization_id=ctx.organization_id,
        meeting_id=int(meeting.id),
        job_type=JOB_TRANSCRIBE,
        status=JOB_QUEUED,
        progress=0,
        attempts=0,
        max_attempts=3,
        payload_json=json.dumps(
            {
                "recording_id": int(recording.id),
                "bucket_name": recording.bucket_name or AUDIO_BUCKET,
                "object_key": recording.object_key,
                "duration_seconds": int(recording.duration_seconds or 0),
            },
            ensure_ascii=False,
        ),
        provider=provider.name,
        created_by_name=ctx.actor_name,
    )
    db.add(job)
    await audit(db, ctx, "job.transcribe_started", "meeting", int(meeting.id), meeting.title)
    await db.commit()

    _spawn(int(job.id))
    return dump(job, JOB_FIELDS)


@router.post("/jobs/minutes")
async def start_minutes_draft(
    payload: StartMinutesIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    transcript_result = await db.execute(
        select(Transcripts)
        .where(
            Transcripts.organization_id == ctx.organization_id,
            Transcripts.meeting_id == int(meeting.id),
        )
        .order_by(Transcripts.id.desc())
    )
    transcript = transcript_result.scalars().first()
    if transcript is None or not (transcript.full_text or "").strip():
        raise bad_request(
            "برای تولید پیش‌نویس صورتجلسه ابتدا باید رونویسی جلسه انجام شود."
        )

    minutes_result = await db.execute(
        select(Minutes).where(
            Minutes.organization_id == ctx.organization_id, Minutes.meeting_id == int(meeting.id)
        )
    )
    existing_minutes = minutes_result.scalars().first()
    if existing_minutes is not None and existing_minutes.status == MINUTES_LOCKED:
        raise conflict("صورتجلسهٔ این جلسه قفل شده و بازتولید آن مجاز نیست.")

    running = await _find_active_job(db, ctx, JOB_MINUTES, int(meeting.id))
    if running is not None:
        await db.commit()
        return dump(running, JOB_FIELDS)

    core.ensure_quota(ctx.organization, 1)
    await _ensure_capacity(db, ctx)

    job = Jobs(
        organization_id=ctx.organization_id,
        meeting_id=int(meeting.id),
        job_type=JOB_MINUTES,
        status=JOB_QUEUED,
        progress=0,
        attempts=0,
        max_attempts=3,
        payload_json=json.dumps({"transcript_id": int(transcript.id)}, ensure_ascii=False),
        provider=get_minutes_port().name,
        created_by_name=ctx.actor_name,
    )
    db.add(job)
    await audit(db, ctx, "job.minutes_started", "meeting", int(meeting.id), meeting.title)
    await db.commit()

    _spawn(int(job.id))
    return dump(job, JOB_FIELDS)


@router.post("/suggest-items")
async def suggest_decision_items(
    payload: SuggestItemsIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """پیشنهاد مصوبات و اقدامات از روی متن رونویسی، بدون ذخیره در پایگاه داده.

    نتیجه فقط برای بازبینی به فرانت برمی‌گردد تا کاربر هر مورد را جداگانه
    ویرایش یا تأیید کند؛ بنابراین هیچ رکورد مصوبه/اقدامی در این مسیر ساخته
    نمی‌شود. دسترسی محدود به مدیر جلسه است (مدیر سازمان یا دبیر همان جلسه).
    """
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    transcript_rows = await list_owned(
        db,
        Transcripts,
        ctx,
        Transcripts.meeting_id == int(meeting.id),
        order_by=Transcripts.id.desc(),
    )
    transcript = transcript_rows[0] if transcript_rows else None
    if transcript is None or not (transcript.full_text or "").strip():
        raise bad_request(
            "برای پیشنهاد هوشمند، ابتدا باید فایل صوتی جلسه رونویسی شود یا متن رونویسی ثبت گردد."
        )

    agenda = await list_owned(
        db,
        Agenda_items,
        ctx,
        Agenda_items.meeting_id == int(meeting.id),
        order_by=Agenda_items.position,
    )
    participants = await list_owned(
        db, Participants, ctx, Participants.meeting_id == int(meeting.id), order_by=Participants.id
    )
    attendee_names = [p.full_name for p in participants if p.attended] or [
        p.full_name for p in participants
    ]

    try:
        draft, attempts = await ai_providers.run_minutes_draft(
            db,
            int(ctx.organization.id),
            meeting_title=meeting.title,
            meeting_type=meeting.meeting_type or "",
            agenda_titles=[item.title for item in agenda],
            attendee_names=attendee_names,
            transcript_text=transcript.full_text or "",
        )
    except AIGatewayError as exc:
        raise bad_request(str(exc)) from exc

    members = await list_owned(db, Memberships, ctx, Memberships.status == "active")
    member_by_name = {core.fa_normalize(member.full_name): member for member in members}
    default_due = core.iso_utc(core.utc_now() + core.timedelta(days=14))

    suggested_actions: List[Dict[str, Any]] = []
    for item in draft.action_items:
        owner = member_by_name.get(core.fa_normalize(item.get("owner_name", "")))
        suggested_actions.append(
            {
                "title": item["title"],
                "description": item.get("due_hint", ""),
                "owner_membership_id": int(owner.id) if owner is not None else None,
                "owner_name": owner.full_name if owner is not None else item.get("owner_name", ""),
                "due_date": default_due,
            }
        )

    await audit(
        db,
        ctx,
        action="meeting.suggest_items",
        entity="meetings",
        entity_id=int(meeting.id),
        detail="پیشنهاد هوشمند مصوبات و اقدامات از متن رونویسی",
    )
    await db.commit()

    return {
        "decisions": [
            {"title": item["title"], "description": item.get("description", "")}
            for item in draft.decisions
        ],
        "actions": suggested_actions,
        "model": getattr(draft, "model", "") or "",
        "attempts": ai_providers.format_attempts(attempts),
    }


@router.get("/jobs/{job_id}")
async def job_status(
    job_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """نقطهٔ polling؛ نتیجه در همان پاسخ برگردانده می‌شود."""
    ctx = await resolve_context(db, current_user)
    job = await get_owned(db, Jobs, job_id, ctx, "کار پردازشی")
    payload = dump(job, JOB_FIELDS)
    try:
        payload["result"] = json.loads(job.result_json or "{}")
    except (TypeError, ValueError):
        payload["result"] = {}
    await db.commit()
    return payload


@router.get("/meetings/{meeting_id}/jobs")
async def meeting_jobs(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    jobs = await list_owned(db, Jobs, ctx, Jobs.meeting_id == meeting_id, order_by=Jobs.id.desc(), limit=20)
    transcript_result = await db.execute(
        select(Transcripts)
        .where(
            Transcripts.organization_id == ctx.organization_id,
            Transcripts.meeting_id == meeting_id,
        )
        .order_by(Transcripts.id.desc())
    )
    transcript = transcript_result.scalars().first()
    await db.commit()
    return {
        "jobs": [dump(job, JOB_FIELDS) for job in jobs],
        "transcript": core.transcript_payload(transcript) if transcript else None,
    }


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تلاش دوباره؛ اگر نتیجهٔ تأمین‌کننده ذخیره شده باشد فراخوان تکرار نمی‌شود."""
    ctx = await resolve_context(db, current_user)
    job = await get_owned(db, Jobs, job_id, ctx, "کار پردازشی")
    meeting = await get_owned(db, Meetings, int(job.meeting_id or 0), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    if job.status in ACTIVE_JOB_STATUSES:
        await db.commit()
        return dump(job, JOB_FIELDS)
    if job.status == JOB_SUCCEEDED:
        raise bad_request("این کار با موفقیت پایان یافته و نیازی به تلاش دوباره ندارد.")
    if int(job.attempts or 0) >= int(job.max_attempts or 3):
        raise conflict(
            "سقف تلاش دوبارهٔ این کار به پایان رسیده است. لطفاً فایل صوتی و کیفیت آن را بررسی کنید."
        )
    await _ensure_capacity(db, ctx)

    job.status = JOB_QUEUED
    job.error_message = ""
    job.progress = 0
    await audit(db, ctx, "job.retried", "job", job_id, job.job_type)
    await db.commit()

    _spawn(job_id)
    return dump(job, JOB_FIELDS)


# ---------------------------------------------------------------------------
# اجراکنندهٔ کار (پس‌زمینه)
# ---------------------------------------------------------------------------


async def _load_job(session: AsyncSession, job_id: int) -> Optional[Jobs]:
    result = await session.execute(select(Jobs).where(Jobs.id == job_id))
    return result.scalars().first()


async def _fail_job(session: AsyncSession, job: Jobs, message: str) -> None:
    job.status = JOB_FAILED
    job.error_message = message[:900]
    job.finished_at = core.now_iso()
    await session.commit()


async def _run_job(job_id: int) -> None:
    """چرخهٔ اجرای یک کار: علامت‌گذاری، فراخوان AI بیرون از تراکنش، ذخیرهٔ نتیجه."""
    if db_manager.async_session_maker is None:
        try:
            await db_manager.ensure_initialized()
        except Exception:  # pragma: no cover - محافظ راه‌اندازی
            logger.exception("راه‌اندازی پایگاه داده برای اجرای کار ناموفق بود")
            return

    async with db_manager.async_session_maker() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        job.status = JOB_RUNNING
        job.attempts = int(job.attempts or 0) + 1
        job.started_at = core.now_iso()
        job.progress = 10
        await session.commit()

        try:
            if job.job_type == JOB_TRANSCRIBE:
                await _execute_transcribe(session, job)
            elif job.job_type == JOB_MINUTES:
                await _execute_minutes(session, job)
            else:
                await _fail_job(session, job, "نوع کار پردازشی پشتیبانی نمی‌شود.")
        except AIGatewayError as exc:
            await session.rollback()
            fresh = await _load_job(session, job_id)
            if fresh is not None:
                await _fail_job(session, fresh, str(exc))
        except Exception as exc:  # pragma: no cover - محافظ عملیاتی
            logger.exception("اجرای کار %s ناموفق بود", job_id)
            await session.rollback()
            fresh = await _load_job(session, job_id)
            if fresh is not None:
                await _fail_job(
                    session,
                    fresh,
                    f"خطای پردازش: {str(exc)[:200]}. لطفاً تلاش دوباره را امتحان کنید.",
                )


async def _execute_transcribe(session: AsyncSession, job: Jobs) -> None:
    """رونویسی صوت: لینک موقت → فراخوان تأمین‌کننده → ذخیرهٔ متن و مصرف."""
    try:
        payload = json.loads(job.payload_json or "{}")
    except (TypeError, ValueError):
        payload = {}
    recording_id = int(payload.get("recording_id") or 0)
    bucket = payload.get("bucket_name") or AUDIO_BUCKET
    object_key = payload.get("object_key") or ""
    duration_hint = int(payload.get("duration_seconds") or 0)
    organization_id = int(job.organization_id)
    meeting_id = int(job.meeting_id or 0)
    job_id = int(job.id)

    if not object_key:
        await _fail_job(session, job, "کلید فایل صوتی در این کار ثبت نشده است.")
        return

    job.progress = 25
    await session.commit()  # پایان فاز پایگاه داده پیش از فراخوان کند

    storage = StorageService()
    signed = await storage.create_download_url(
        FileUpDownRequest(bucket_name=bucket, object_key=object_key)
    )
    # زنجیرهٔ اولویت/fallback همان سازمان؛ در صورت شکست همه، آداپتر پلتفرم.
    result, attempts = await ai_providers.run_transcription(
        session,
        organization_id,
        audio_url=signed.download_url,
        duration_hint_seconds=duration_hint,
    )
    attempts_line = ai_providers.format_attempts(attempts)

    # فاز جدید پایگاه داده: ذخیرهٔ رونویسی، مصرف و اعلان
    job_row = await _load_job(session, job_id)
    if job_row is None:
        return
    org_result = await session.execute(select(Organizations).where(Organizations.id == organization_id))
    organization = org_result.scalars().first()

    existing = await session.execute(
        select(Transcripts).where(
            Transcripts.organization_id == organization_id,
            Transcripts.meeting_id == meeting_id,
            Transcripts.recording_id == recording_id,
        )
    )
    transcript = existing.scalars().first()
    if transcript is None:
        transcript = Transcripts(
            organization_id=organization_id,
            meeting_id=meeting_id,
            recording_id=recording_id,
        )
        session.add(transcript)
    transcript.provider = result.provider
    transcript.model = result.model
    transcript.full_text = result.full_text
    transcript.segments_json = json.dumps(
        [segment.to_dict() for segment in result.segments], ensure_ascii=False
    )
    transcript.duration_seconds = result.duration_seconds
    transcript.known_word_ratio = result.known_word_ratio
    transcript.stats_words = result.stats_words
    transcript.stats_known_words = result.stats_known_words
    transcript.job_id = job_id

    minutes_charged = result.billable_minutes()
    if organization is not None:
        await core.record_usage(
            session,
            organization,
            kind="transcribe",
            provider=result.provider,
            model=result.model,
            minutes=minutes_charged,
            job_id=job_id,
            meeting_id=meeting_id,
            detail="رونویسی فایل صوتی جلسه",
        )

    meeting_result = await session.execute(select(Meetings).where(Meetings.id == meeting_id))
    meeting = meeting_result.scalars().first()
    if meeting is not None and meeting.secretary_membership_id:
        await notify(
            session,
            organization_id,
            membership_id=int(meeting.secretary_membership_id),
            user_id=None,
            kind="transcript_ready",
            title=f"رونویسی «{meeting.title}» آماده شد",
            body=(
                "کیفیت تشخیص واژه‌ها پایین است؛ متن را بازبینی کنید."
                if result.known_word_ratio and result.known_word_ratio < 0.8
                else "می‌توانید پیش‌نویس صورتجلسه را تولید کنید."
            ),
            link=f"/meetings/{meeting_id}",
            dedupe_key=f"transcript-{job_id}",
        )

    job_row.status = JOB_SUCCEEDED
    job_row.progress = 100
    job_row.finished_at = core.now_iso()
    job_row.error_message = ""
    job_row.result_json = json.dumps(
        {
            "kind": JOB_TRANSCRIBE,
            "words": result.stats_words,
            "known_word_ratio": result.known_word_ratio,
            "duration_seconds": result.duration_seconds,
            "minutes_charged": minutes_charged,
            "provider": result.provider,
            "provider_attempts": attempts_line,
        },
        ensure_ascii=False,
    )
    await session.commit()


async def _execute_minutes(session: AsyncSession, job: Jobs) -> None:
    """پیش‌نویس صورتجلسه + مصوبات + اقدامات در یک فراخوان AI."""
    organization_id = int(job.organization_id)
    meeting_id = int(job.meeting_id or 0)
    job_id = int(job.id)

    meeting_result = await session.execute(select(Meetings).where(Meetings.id == meeting_id))
    meeting = meeting_result.scalars().first()
    if meeting is None:
        await _fail_job(session, job, "جلسهٔ مرتبط با این کار یافت نشد.")
        return

    transcript_result = await session.execute(
        select(Transcripts)
        .where(Transcripts.organization_id == organization_id, Transcripts.meeting_id == meeting_id)
        .order_by(Transcripts.id.desc())
    )
    transcript = transcript_result.scalars().first()
    if transcript is None or not (transcript.full_text or "").strip():
        await _fail_job(session, job, "متن رونویسی برای تولید صورتجلسه موجود نیست.")
        return

    agenda_result = await session.execute(
        select(Agenda_items)
        .where(Agenda_items.organization_id == organization_id, Agenda_items.meeting_id == meeting_id)
        .order_by(Agenda_items.position)
    )
    agenda_titles = [item.title for item in agenda_result.scalars().all()]

    participant_result = await session.execute(
        select(Participants).where(
            Participants.organization_id == organization_id, Participants.meeting_id == meeting_id
        )
    )
    participants = list(participant_result.scalars().all())
    attendee_names = [p.full_name for p in participants if p.attended] or [
        p.full_name for p in participants
    ]

    meeting_title = meeting.title
    meeting_type = meeting.meeting_type or ""
    transcript_text = transcript.full_text or ""

    job.progress = 35
    await session.commit()  # پایان فاز پایگاه داده پیش از فراخوان کند

    # زنجیرهٔ مدل زبانی همان سازمان؛ در صورت شکست همه، آداپتر پلتفرم.
    draft, minutes_attempts = await ai_providers.run_minutes_draft(
        session,
        organization_id,
        meeting_title=meeting_title,
        meeting_type=meeting_type,
        agenda_titles=agenda_titles,
        attendee_names=attendee_names,
        transcript_text=transcript_text,
    )
    minutes_attempts_line = ai_providers.format_attempts(minutes_attempts)

    # فاز جدید پایگاه داده: ذخیرهٔ صورتجلسه، نسخه، مصوبات و اقدامات
    job_row = await _load_job(session, job_id)
    if job_row is None:
        return

    minutes_result = await session.execute(
        select(Minutes).where(
            Minutes.organization_id == organization_id, Minutes.meeting_id == meeting_id
        )
    )
    minutes = minutes_result.scalars().first()
    if minutes is None:
        minutes = Minutes(
            organization_id=organization_id,
            meeting_id=meeting_id,
            current_version=0,
            approved_by_name="",
            approved_at="",
            locked_at="",
            review_requested_at="",
        )
        session.add(minutes)
    minutes.status = MINUTES_DRAFT
    minutes.body_markdown = draft.body_markdown
    minutes.summary = draft.summary
    minutes.generated_by = "ai"
    minutes.current_version = int(minutes.current_version or 0) + 1
    await session.flush()

    session.add(
        Minute_versions(
            organization_id=organization_id,
            minutes_id=int(minutes.id),
            meeting_id=meeting_id,
            version=int(minutes.current_version),
            body_markdown=draft.body_markdown,
            summary=draft.summary,
            status_at_version=MINUTES_DRAFT,
            changed_by_name=job_row.created_by_name or "سامانه",
            change_note="پیش‌نویس خودکار از رونویسی جلسه",
        )
    )

    # حذف مصوبات و اقدامات تولیدشدهٔ قبلی توسط AI تا داده تکراری نشود
    old_decisions = await session.execute(
        select(Decisions).where(
            Decisions.organization_id == organization_id,
            Decisions.meeting_id == meeting_id,
            Decisions.source == "ai",
        )
    )
    old_decision_ids = []
    for decision in old_decisions.scalars().all():
        old_decision_ids.append(int(decision.id))
        await session.delete(decision)
    if old_decision_ids:
        old_actions = await session.execute(
            select(Action_items).where(
                Action_items.organization_id == organization_id,
                Action_items.decision_id.in_(old_decision_ids),
                Action_items.source == "ai",
            )
        )
        for action in old_actions.scalars().all():
            await session.delete(action)
    await session.flush()

    member_result = await session.execute(
        select(Memberships).where(
            Memberships.organization_id == organization_id, Memberships.status == "active"
        )
    )
    members = list(member_result.scalars().all())
    member_by_name = {core.fa_normalize(member.full_name): member for member in members}

    created_decisions: List[Decisions] = []
    for index, item in enumerate(draft.decisions, start=1):
        decision = Decisions(
            organization_id=organization_id,
            meeting_id=meeting_id,
            minutes_id=int(minutes.id),
            position=index,
            title=item["title"],
            description=item.get("description", ""),
            source="ai",
        )
        session.add(decision)
        created_decisions.append(decision)
    await session.flush()

    default_due = core.iso_utc(core.utc_now() + core.timedelta(days=14))
    for index, item in enumerate(draft.action_items):
        owner = member_by_name.get(core.fa_normalize(item.get("owner_name", "")))
        linked = created_decisions[index] if index < len(created_decisions) else (
            created_decisions[0] if created_decisions else None
        )
        session.add(
            Action_items(
                organization_id=organization_id,
                meeting_id=meeting_id,
                decision_id=int(linked.id) if linked is not None else None,
                title=item["title"],
                description=item.get("due_hint", ""),
                owner_membership_id=int(owner.id) if owner is not None else None,
                owner_name=owner.full_name if owner is not None else item.get("owner_name", ""),
                due_date=default_due,
                status="open",
                progress_note="",
                source="ai",
            )
        )

    org_result = await session.execute(select(Organizations).where(Organizations.id == organization_id))
    organization = org_result.scalars().first()
    if organization is not None:
        await core.record_usage(
            session,
            organization,
            kind="minutes_draft",
            provider=getattr(draft, "provider", "") or ai_providers.PLATFORM_PROVIDER,
            model=getattr(draft, "model", "") or "",
            minutes=1,
            job_id=job_id,
            meeting_id=meeting_id,
            detail="تولید پیش‌نویس صورتجلسه و مصوبات",
        )

    if meeting.secretary_membership_id:
        await notify(
            session,
            organization_id,
            membership_id=int(meeting.secretary_membership_id),
            user_id=None,
            kind="minutes_ready",
            title=f"پیش‌نویس صورتجلسهٔ «{meeting_title}» آماده شد",
            body=f"{len(draft.decisions)} مصوبه و {len(draft.action_items)} اقدام پیشنهاد شد.",
            link=f"/meetings/{meeting_id}",
            dedupe_key=f"minutes-{job_id}",
        )

    job_row.status = JOB_SUCCEEDED
    job_row.progress = 100
    job_row.finished_at = core.now_iso()
    job_row.error_message = ""
    job_row.result_json = json.dumps(
        {
            "kind": JOB_MINUTES,
            "minutes_id": int(minutes.id),
            "version": int(minutes.current_version),
            "decisions": len(draft.decisions),
            "actions": len(draft.action_items),
            "provider": draft.model,
            "provider_attempts": minutes_attempts_line,
        },
        ensure_ascii=False,
    )
    await session.commit()
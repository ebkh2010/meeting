"""روتر «استوریج خارجی و آرشیو جلسات» — فقط برای مدیر سازمان.

قواعد دسترسی و ایمنی:

* همهٔ مسیرها با ``get_app_admin`` محافظت می‌شوند؛ نقش دبیر و عضو ۴۰۳ می‌گیرد.
* هیچ اعتبارنامهٔ خامی بازنمی‌گردد؛ تنها نمای ماسک‌شدهٔ ``storage_targets.payload``.
* عملیات سنگین (آرشیو/بازیابی) هرگز در چرخهٔ درخواست انجام نمی‌شود؛ یک رکورد
  در صف ``jobs`` ساخته می‌شود و اجرای واقعی در پس‌زمینه با نشان‌دادن درصد
  پیشرفت ادامه می‌یابد. اگر کار فعالی برای همان جلسه در جریان باشد، همان کار
  بازگردانده می‌شود (idempotency در سطح صف).
* هر تغییر تنظیمات، هر تست اتصال و هر آرشیو/بازیابی در ``audit_logs`` ثبت می‌شود.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional

from core.database import db_manager, get_db
from dependencies.app_auth import get_app_admin
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_logs import Audit_logs
from models.jobs import Jobs
from models.meetings import Meetings
from services import app_auth
from services import external_storage as ext
from services import meeting_archive as archive
from services import mgmt_core as core
from services import storage_targets
from services.mgmt_core import audit, get_owned, resolve_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/archive", tags=["archive"])

JOB_ARCHIVE = "meeting_archive"
JOB_RESTORE = "meeting_restore"
JOB_QUEUED = "queued"
JOB_RUNNING = "running"
JOB_SUCCEEDED = "succeeded"
JOB_FAILED = "failed"
ACTIVE_JOB_STATUSES = (JOB_QUEUED, JOB_RUNNING)

JOB_FIELDS = [
    "id",
    "meeting_id",
    "job_type",
    "status",
    "progress",
    "attempts",
    "max_attempts",
    "error_message",
    "result_json",
    "started_at",
    "finished_at",
    "created_by_name",
    "created_at",
]

MAX_ORG_ARCHIVE_JOBS = 2


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------


class TargetIn(BaseModel):
    provider: Optional[str] = None
    display_name: Optional[str] = None
    enabled: Optional[bool] = None
    endpoint: Optional[str] = None
    bucket: Optional[str] = None
    region: Optional[str] = None
    path_prefix: Optional[str] = None
    access_key: Optional[str] = None
    secret_key: Optional[str] = None
    force_path_style: Optional[bool] = None
    webdav_base_url: Optional[str] = None
    webdav_username: Optional[str] = None
    webdav_password: Optional[str] = None
    restore_retention_days: Optional[int] = None


class MeetingActionIn(BaseModel):
    file_ids: Optional[List[int]] = None


# ---------------------------------------------------------------------------
# تنظیمات مقصد خارجی
# ---------------------------------------------------------------------------


@router.get("/target")
async def read_target(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تنظیمات مقصد خارجی سازمان + راهنمای تأمین‌کنندگان پشتیبانی‌شده."""
    row = await storage_targets.get_row(db, principal.organization_id)
    return {
        "target": storage_targets.payload(row),
        "catalog": storage_targets.catalog_payload(),
        "retention_bounds": {
            "min": storage_targets.RESTORE_RETENTION_BOUNDS[0],
            "max": storage_targets.RESTORE_RETENTION_BOUNDS[1],
        },
    }


@router.put("/target")
async def save_target(
    data: TargetIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ذخیرهٔ تنظیمات مقصد؛ اعتبارنامهٔ خالی یعنی «بدون تغییر»."""
    payload = data.model_dump(exclude_unset=True)
    try:
        row, changes = await storage_targets.save_target(
            db,
            principal.organization_id,
            data=payload,
            actor_name=principal.name or principal.email,
        )
    except ext.ExternalStorageError as exc:
        raise app_auth.bad_request(str(exc))

    ctx = await resolve_context(db, principal)
    await audit(
        db,
        ctx,
        "storage_target.update",
        entity_type="org_storage_target",
        entity_id=int(row.id),
        detail="تنظیمات مقصد ذخیره‌سازی خارجی به‌روزرسانی شد"
        + (f" — {'، '.join(changes)}" if changes else ""),
    )
    result = storage_targets.payload(row)
    await db.commit()
    return {"target": result, "changes": changes}


@router.post("/target/test")
async def test_target(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تست واقعی اتصال: نوشتن، خواندن، مقایسهٔ چکسام و حذف فایل آزمایشی."""
    row = await storage_targets.get_row(db, principal.organization_id)
    if row is None:
        raise app_auth.bad_request("ابتدا تنظیمات مقصد ذخیره‌سازی خارجی را ثبت کنید.")

    ok = True
    try:
        cfg = storage_targets.build_config(row)
        message = await ext.test_connection(cfg, probe_prefix=storage_targets.tenant_prefix(row))
    except ext.ExternalStorageError as exc:
        ok, message = False, str(exc)
    except Exception as exc:  # noqa: BLE001 - محافظ عملیاتی
        logger.exception("تست اتصال مقصد خارجی سازمان %s ناموفق بود", principal.organization_id)
        ok, message = False, f"خطای پیش‌بینی‌نشده در تست اتصال: {str(exc)[:200]}"

    storage_targets.record_test_result(row, ok, message, core.now_iso())
    ctx = await resolve_context(db, principal)
    await audit(
        db,
        ctx,
        "storage_target.test",
        entity_type="org_storage_target",
        entity_id=int(row.id),
        detail=f"تست اتصال مقصد خارجی: {'موفق' if ok else 'ناموفق'} — {message}",
    )
    result = storage_targets.payload(row)
    await db.commit()
    return {"ok": ok, "message": message, "target": result}


# ---------------------------------------------------------------------------
# وضعیت آرشیو جلسه
# ---------------------------------------------------------------------------


@router.get("/meetings/{meeting_id}")
async def meeting_state(
    meeting_id: int,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """وضعیت آرشیو فایل‌های جانبی یک جلسه به‌همراه کار فعال احتمالی."""
    ctx = await resolve_context(db, principal)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    overview = await archive.meeting_overview(db, ctx.organization_id, int(meeting.id))
    row = await storage_targets.get_row(db, ctx.organization_id)
    active = await _find_active_job(db, ctx.organization_id, int(meeting.id))
    await db.commit()
    return {
        "meeting_title": meeting.title or "",
        "target_ready": storage_targets.is_active(row),
        "active_job": core.dump(active, JOB_FIELDS) if active is not None else None,
        **overview,
    }


@router.get("/meetings")
async def meetings_summary(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """خلاصهٔ وضعیت آرشیو همهٔ جلسات سازمان برای پنل مدیریت."""
    ctx = await resolve_context(db, principal)
    result = await db.execute(
        select(Meetings)
        .where(Meetings.organization_id == ctx.organization_id)
        .order_by(Meetings.id.desc())
        .limit(100)
    )
    meetings = list(result.scalars().all())
    rows = await db.execute(
        select(archive.Meeting_archive_files).where(
            archive.Meeting_archive_files.organization_id == ctx.organization_id
        )
    )
    by_meeting: Dict[int, List[Any]] = {}
    for row in rows.scalars().all():
        by_meeting.setdefault(int(row.meeting_id), []).append(row)

    items: List[Dict[str, Any]] = []
    for meeting in meetings:
        states = by_meeting.get(int(meeting.id), [])
        archived = sum(1 for row in states if (row.status or "") == archive.STATUS_ARCHIVED)
        items.append(
            {
                "meeting_id": int(meeting.id),
                "title": meeting.title or "",
                "starts_at": meeting.starts_at or "",
                "tracked_count": len(states),
                "archived_count": archived,
                "archived_bytes": sum(
                    int(row.size_bytes or 0)
                    for row in states
                    if (row.status or "") == archive.STATUS_ARCHIVED
                ),
                "has_error": any((row.status or "") == archive.STATUS_ERROR for row in states),
            }
        )

    target = await storage_targets.get_row(db, ctx.organization_id)
    await db.commit()
    return {"items": items, "target_ready": storage_targets.is_active(target)}


# ---------------------------------------------------------------------------
# صف آرشیو و بازیابی
# ---------------------------------------------------------------------------


async def _find_active_job(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> Optional[Jobs]:
    result = await db.execute(
        select(Jobs)
        .where(
            Jobs.organization_id == int(organization_id),
            Jobs.meeting_id == int(meeting_id),
            Jobs.job_type.in_((JOB_ARCHIVE, JOB_RESTORE)),
            Jobs.status.in_(ACTIVE_JOB_STATUSES),
        )
        .order_by(Jobs.id.desc())
    )
    return result.scalars().first()


async def _ensure_capacity(db: AsyncSession, organization_id: int) -> None:
    result = await db.execute(
        select(Jobs).where(
            Jobs.organization_id == int(organization_id),
            Jobs.job_type.in_((JOB_ARCHIVE, JOB_RESTORE)),
            Jobs.status.in_(ACTIVE_JOB_STATUSES),
        )
    )
    if len(list(result.scalars().all())) >= MAX_ORG_ARCHIVE_JOBS:
        raise app_auth.bad_request(
            "در حال حاضر بیش از حد مجاز عملیات آرشیو/بازیابی در سازمان شما در جریان است. "
            "لطفاً تا پایان آن‌ها صبر کنید."
        )


def _spawn(job_id: int) -> None:
    try:
        asyncio.create_task(_run_job(job_id))
    except RuntimeError:  # pragma: no cover - نبود event loop فعال
        logger.warning("اجرای پس‌زمینهٔ کار %s آغاز نشد", job_id)


async def _queue(
    db: AsyncSession,
    principal: app_auth.AppPrincipal,
    meeting: Meetings,
    job_type: str,
    file_ids: Optional[List[int]],
) -> Dict[str, Any]:
    organization_id = int(principal.organization_id)
    running = await _find_active_job(db, organization_id, int(meeting.id))
    if running is not None:
        await db.commit()
        return core.dump(running, JOB_FIELDS)

    target_row = await storage_targets.get_row(db, organization_id)
    if not storage_targets.is_active(target_row):
        raise app_auth.bad_request(
            "مقصد ذخیره‌سازی خارجی تعریف یا فعال نشده است. ابتدا در همین صفحه مقصد را "
            "ثبت کنید، تست اتصال را با موفقیت بگذرانید و آن را فعال کنید."
        )
    await _ensure_capacity(db, organization_id)

    job = Jobs(
        organization_id=organization_id,
        meeting_id=int(meeting.id),
        job_type=job_type,
        status=JOB_QUEUED,
        progress=0,
        attempts=0,
        max_attempts=3,
        payload_json=json.dumps(
            {
                "actor_name": principal.name or principal.email,
                "file_ids": [int(item) for item in (file_ids or [])],
            },
            ensure_ascii=False,
        ),
        provider="external-storage",
        created_by_name=principal.name or principal.email,
    )
    db.add(job)

    ctx = await resolve_context(db, principal)
    action = "archive.meeting_started" if job_type == JOB_ARCHIVE else "archive.restore_started"
    verb = "آرشیو" if job_type == JOB_ARCHIVE else "بازیابی از آرشیو"
    await audit(
        db,
        ctx,
        action,
        entity_type="meeting",
        entity_id=int(meeting.id),
        detail=f"عملیات {verb} برای جلسهٔ «{meeting.title or meeting.id}» در صف قرار گرفت.",
    )
    await db.commit()
    _spawn(int(job.id))
    return core.dump(job, JOB_FIELDS)


@router.post("/meetings/{meeting_id}/archive")
async def start_archive(
    meeting_id: int,
    data: MeetingActionIn = MeetingActionIn(),
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """قرار دادن عملیات آرشیو فایل‌های جانبی جلسه در صف."""
    ctx = await resolve_context(db, principal)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    return await _queue(db, principal, meeting, JOB_ARCHIVE, data.file_ids)


@router.post("/meetings/{meeting_id}/restore")
async def start_restore(
    meeting_id: int,
    data: MeetingActionIn = MeetingActionIn(),
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """قرار دادن عملیات بازیابی از آرشیو در صف."""
    ctx = await resolve_context(db, principal)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    return await _queue(db, principal, meeting, JOB_RESTORE, data.file_ids)


@router.get("/jobs/{job_id}")
async def read_job(
    job_id: int,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """وضعیت و درصد پیشرفت یک کار آرشیو/بازیابی در مرز همان سازمان."""
    result = await db.execute(
        select(Jobs).where(
            Jobs.id == int(job_id),
            Jobs.organization_id == int(principal.organization_id),
            Jobs.job_type.in_((JOB_ARCHIVE, JOB_RESTORE)),
        )
    )
    job = result.scalars().first()
    if job is None:
        raise app_auth.bad_request("کار درخواستی در سازمان شما یافت نشد.")
    return core.dump(job, JOB_FIELDS)


@router.post("/jobs/{job_id}/retry")
async def retry_job(
    job_id: int,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تلاش دوبارهٔ یک کار ناموفق (بدون ساخت فایل تکراری در مقصد)."""
    result = await db.execute(
        select(Jobs).where(
            Jobs.id == int(job_id),
            Jobs.organization_id == int(principal.organization_id),
            Jobs.job_type.in_((JOB_ARCHIVE, JOB_RESTORE)),
        )
    )
    job = result.scalars().first()
    if job is None:
        raise app_auth.bad_request("کار درخواستی در سازمان شما یافت نشد.")
    if job.status in ACTIVE_JOB_STATUSES:
        return core.dump(job, JOB_FIELDS)
    if job.status == JOB_SUCCEEDED:
        raise app_auth.bad_request(
            "این کار با موفقیت پایان یافته و نیازی به تلاش دوباره ندارد."
        )
    if int(job.attempts or 0) >= int(job.max_attempts or 3):
        raise app_auth.bad_request(
            "سقف تلاش دوبارهٔ این کار به پایان رسیده است. لطفاً تنظیمات مقصد را بررسی کنید."
        )

    job.status = JOB_QUEUED
    job.progress = 0
    job.error_message = ""
    ctx = await resolve_context(db, principal)
    await audit(
        db,
        ctx,
        "archive.job_retried",
        entity_type="job",
        entity_id=int(job.id),
        detail=f"تلاش دوبارهٔ کار {job.job_type} برای جلسهٔ {job.meeting_id}",
    )
    await db.commit()
    _spawn(int(job.id))
    return core.dump(job, JOB_FIELDS)


# ---------------------------------------------------------------------------
# اجراکنندهٔ پس‌زمینه
# ---------------------------------------------------------------------------


async def _load_job(session: AsyncSession, job_id: int) -> Optional[Jobs]:
    result = await session.execute(select(Jobs).where(Jobs.id == int(job_id)))
    return result.scalars().first()


def _bg_audit(
    session: AsyncSession,
    job: Jobs,
    action: str,
    detail: str,
    entity_id: Optional[int] = None,
) -> None:
    """ثبت Audit در پس‌زمینه (بدون TenantContext درخواست)."""
    try:
        session.add(
            Audit_logs(
                organization_id=int(job.organization_id),
                actor_user_id="",
                actor_name=job.created_by_name or "سیستم",
                actor_role="admin",
                action=action,
                entity_type="meeting",
                entity_id=int(entity_id if entity_id is not None else (job.meeting_id or 0)),
                detail=detail[:900],
            )
        )
    except Exception as exc:  # pragma: no cover - محافظ عملیاتی
        logger.warning("ثبت Audit پس‌زمینه ناموفق بود: %s", exc)


async def _fail_job(session: AsyncSession, job: Jobs, message: str) -> None:
    job.status = JOB_FAILED
    job.error_message = message[:900]
    job.finished_at = core.now_iso()
    _bg_audit(session, job, f"{job.job_type}.failed", f"عملیات ناموفق بود: {message}")
    await session.commit()


async def _run_job(job_id: int) -> None:
    """چرخهٔ اجرای کار آرشیو/بازیابی با نشست مستقل پایگاه داده."""
    if db_manager.async_session_maker is None:
        try:
            await db_manager.ensure_initialized()
        except Exception:  # pragma: no cover
            logger.exception("راه‌اندازی پایگاه داده برای کار آرشیو ناموفق بود")
            return

    async with db_manager.async_session_maker() as session:
        job = await _load_job(session, job_id)
        if job is None:
            return
        job.status = JOB_RUNNING
        job.attempts = int(job.attempts or 0) + 1
        job.started_at = core.now_iso()
        job.progress = 5
        await session.commit()

        try:
            if job.job_type == JOB_ARCHIVE:
                await _execute_archive(session, job)
            elif job.job_type == JOB_RESTORE:
                await _execute_restore(session, job)
            else:
                await _fail_job(session, job, "نوع کار آرشیو پشتیبانی نمی‌شود.")
        except (archive.ArchiveError, ext.ExternalStorageError) as exc:
            await session.rollback()
            fresh = await _load_job(session, job_id)
            if fresh is not None:
                await _fail_job(session, fresh, str(exc))
        except Exception as exc:  # pragma: no cover - محافظ عملیاتی
            logger.exception("اجرای کار آرشیو %s ناموفق بود", job_id)
            await session.rollback()
            fresh = await _load_job(session, job_id)
            if fresh is not None:
                await _fail_job(
                    session, fresh, f"خطای پیش‌بینی‌نشده: {str(exc)[:200]}"
                )


def _job_payload(job: Jobs) -> Dict[str, Any]:
    try:
        return json.loads(job.payload_json or "{}")
    except (TypeError, ValueError):
        return {}


async def _execute_archive(session: AsyncSession, job: Jobs) -> None:
    """انتقال فایل‌های جانبی جلسه به مقصد خارجی، فایل به فایل."""
    payload = _job_payload(job)
    actor_name = str(payload.get("actor_name") or job.created_by_name or "")
    wanted = {int(item) for item in (payload.get("file_ids") or [])}
    organization_id = int(job.organization_id)
    meeting_id = int(job.meeting_id or 0)

    cfg, prefix, _ = await archive.target_for(session, organization_id)
    sources = await archive.list_sources(session, organization_id, meeting_id)
    if wanted:
        rows = await archive.list_state_rows(session, organization_id, meeting_id)
        allowed = {
            (row.source_kind, int(row.source_id)) for row in rows if int(row.id) in wanted
        }
        sources = [
            item for item in sources if (item["source_kind"], int(item["source_id"])) in allowed
        ]

    if not sources:
        job.progress = 100
        job.status = JOB_SUCCEEDED
        job.finished_at = core.now_iso()
        job.result_json = json.dumps(
            {"archived": 0, "skipped": 0, "message": "فایل جانبی قابل آرشیو یافت نشد."},
            ensure_ascii=False,
        )
        await session.commit()
        return

    total = len(sources)
    archived = 0
    skipped = 0
    failures: List[str] = []

    for index, source in enumerate(sources, start=1):
        try:
            row, message = await archive.archive_one(
                session,
                cfg,
                prefix,
                organization_id,
                meeting_id,
                source,
                actor_name=actor_name,
            )
            if (row.status or "") == archive.STATUS_ARCHIVED and "تکراری" in message:
                skipped += 1
            else:
                archived += 1
                _bg_audit(
                    session,
                    job,
                    "archive.file_archived",
                    f"فایل «{row.file_name}» به مسیر {row.remote_path} منتقل و نسخهٔ سرور حذف شد "
                    f"(چکسام {row.checksum_sha256}).",
                )
        except archive.ArchiveError as exc:
            failures.append(f"{source.get('file_name')}: {exc}")
            _bg_audit(
                session,
                job,
                "archive.file_failed",
                f"آرشیو فایل «{source.get('file_name')}» ناموفق بود و فایل اصلی حذف نشد: {exc}",
            )

        fresh = await _load_job(session, int(job.id))
        if fresh is not None:
            fresh.progress = min(99, int(5 + index * 94 / total))
            await session.commit()
            job = fresh

    job = await _load_job(session, int(job.id)) or job
    if failures and archived == 0 and skipped == 0:
        await _fail_job(session, job, "؛ ".join(failures)[:900])
        return

    job.status = JOB_SUCCEEDED
    job.progress = 100
    job.finished_at = core.now_iso()
    job.error_message = "؛ ".join(failures)[:900] if failures else ""
    job.result_json = json.dumps(
        {"archived": archived, "skipped": skipped, "failed": len(failures)}, ensure_ascii=False
    )
    _bg_audit(
        session,
        job,
        "archive.meeting_completed",
        f"آرشیو جلسه پایان یافت: {archived} فایل منتقل شد، {skipped} فایل از قبل آرشیو بود، "
        f"{len(failures)} فایل ناموفق.",
    )
    await session.commit()


async def _execute_restore(session: AsyncSession, job: Jobs) -> None:
    """بازگرداندن فایل‌های آرشیوشدهٔ جلسه به فضای ذخیره‌سازی اصلی."""
    payload = _job_payload(job)
    actor_name = str(payload.get("actor_name") or job.created_by_name or "")
    wanted = {int(item) for item in (payload.get("file_ids") or [])}
    organization_id = int(job.organization_id)
    meeting_id = int(job.meeting_id or 0)

    cfg, _, retention_days = await archive.target_for(session, organization_id)
    rows = await archive.list_state_rows(session, organization_id, meeting_id)
    targets = [
        row
        for row in rows
        if (row.status or "") in (archive.STATUS_ARCHIVED, archive.STATUS_ERROR)
        and (row.remote_path or "")
        and (not wanted or int(row.id) in wanted)
    ]

    if not targets:
        job.progress = 100
        job.status = JOB_SUCCEEDED
        job.finished_at = core.now_iso()
        job.result_json = json.dumps(
            {"restored": 0, "message": "فایل آرشیوشده‌ای برای بازیابی یافت نشد."},
            ensure_ascii=False,
        )
        await session.commit()
        return

    total = len(targets)
    restored = 0
    failures: List[str] = []

    for index, row in enumerate(targets, start=1):
        try:
            fresh_row, _ = await archive.restore_one(
                session, cfg, row, actor_name=actor_name, retention_days=retention_days
            )
            restored += 1
            _bg_audit(
                session,
                job,
                "archive.file_restored",
                f"فایل «{fresh_row.file_name}» از مسیر {fresh_row.remote_path} بازیابی شد "
                f"(اعتبار نسخهٔ محلی تا {fresh_row.restore_expires_at}).",
            )
        except archive.ArchiveError as exc:
            failures.append(f"{row.file_name}: {exc}")
            _bg_audit(
                session,
                job,
                "archive.restore_failed",
                f"بازیابی فایل «{row.file_name}» ناموفق بود؛ نسخهٔ آرشیو دست‌نخورده است: {exc}",
            )

        job_row = await _load_job(session, int(job.id))
        if job_row is not None:
            job_row.progress = min(99, int(5 + index * 94 / total))
            await session.commit()
            job = job_row

    job = await _load_job(session, int(job.id)) or job
    if failures and restored == 0:
        await _fail_job(session, job, "؛ ".join(failures)[:900])
        return

    job.status = JOB_SUCCEEDED
    job.progress = 100
    job.finished_at = core.now_iso()
    job.error_message = "؛ ".join(failures)[:900] if failures else ""
    job.result_json = json.dumps(
        {"restored": restored, "failed": len(failures)}, ensure_ascii=False
    )
    _bg_audit(
        session,
        job,
        "archive.restore_completed",
        f"بازیابی جلسه پایان یافت: {restored} فایل بازگردانده شد، {len(failures)} فایل ناموفق.",
    )
    await session.commit()
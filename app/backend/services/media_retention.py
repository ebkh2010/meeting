"""سیاست نگهداری فایل‌های مدیا در سطح سامانه.

مدیر سامانه یک «مدت نگهداری» سراسری تعیین می‌کند. هر فایل مدیای قدیمی‌تر از این
مدت، بسته به وضعیت سازمان، یکی از دو سرنوشت را دارد:

* اگر سازمان «مقصد ذخیره‌سازی خارجی» فعال داشته باشد، فایل با همان زنجیرهٔ امن
  آرشیو (نوشتن در مقصد → بررسی حجم → مقایسهٔ چکسام → حذف نسخهٔ سرور) به آن مقصد
  منتقل می‌شود و فضای سرور آزاد می‌گردد.
* اگر مقصدی تعریف نشده باشد، فایل از سرور پاک می‌شود.

قواعد ایمنی (همه از الزام «دادهٔ موجود نباید از دست برود» می‌آید):

* **اجرای خودکار پیش‌فرض خاموش است**؛ مدیر سامانه باید آن را در پنل روشن کند.
  تا آن زمان فقط «گزارش» ساخته می‌شود و هیچ فایلی حذف نمی‌گردد.
* رونویسی متنی، صورتجلسه، مصوبات و اقدامات هرگز حذف نمی‌شوند؛ تنها خودِ فایل
  صوتی/ویدیویی و پیوست‌ها مشمول این سیاست‌اند.
* فایل‌هایی که پیش‌تر آرشیو شده‌اند و سازمان‌های سطل‌آشغالی دست‌نخورده می‌مانند.
* هر فایل تنها پس از تأیید موفقیت‌آمیز انتقال حذف می‌شود؛ شکست انتقال، نسخهٔ
  سرور را سالم باقی می‌گذارد.
* هر اجرا (خودکار یا دستی) در ``audit_logs`` ثبت می‌شود.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from schemas.storage import ObjectRequest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.audit_logs import Audit_logs
from models.meeting_archive_files import Meeting_archive_files
from models.meeting_attachments import Meeting_attachments
from models.meetings import Meetings
from models.organizations import Organizations
from models.recordings import Recordings
from services import meeting_archive as archive
from services import meeting_files as files
from services import mgmt_core as core
from services import platform_settings
from services import storage_targets
from services.storage import StorageService

logger = logging.getLogger(__name__)

TRASHED_STATUS = "trashed"
KIND_RECORDING = archive.KIND_RECORDING
KIND_ATTACHMENT = archive.KIND_ATTACHMENT
KIND_LABELS = dict(archive.KIND_LABELS)

ACTION_ARCHIVE = "archive"
ACTION_DELETE = "delete"
ACTION_LABELS = {
    ACTION_ARCHIVE: "انتقال به استوریج خارجی",
    ACTION_DELETE: "حذف از سرور",
}

#: سقف تعداد فایل در هر اجرا تا یک اجرا بی‌نهایت طول نکشد.
MAX_ITEMS_PER_RUN = 500
#: تعداد موردی که در گزارش پنل نمایش داده می‌شود.
REPORT_ITEM_LIMIT = 200

#: فاصلهٔ اجرای خودکار (۶ ساعت) و مهلت نخستین اجرا پس از راه‌اندازی.
SWEEP_INTERVAL_SECONDS = 6 * 3600
FIRST_SWEEP_DELAY_SECONDS = 300


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    """همهٔ زمان‌ها UTC-آگاه می‌شوند تا مقایسه با مهلت‌ها درست باشد."""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _age_days(created: Optional[datetime], now: datetime) -> int:
    if created is None:
        return 0
    return max(0, int((now - created).total_seconds() // 86400))


async def _archived_keys(db: AsyncSession, organization_id: int) -> set:
    """کلید (نوع منبع، شناسه) فایل‌هایی که همین حالا در آرشیو خارجی هستند."""
    result = await db.execute(
        select(Meeting_archive_files.source_kind, Meeting_archive_files.source_id).where(
            Meeting_archive_files.organization_id == int(organization_id),
            Meeting_archive_files.status == archive.STATUS_ARCHIVED,
        )
    )
    return {
        (str(kind), int(source_id))
        for kind, source_id in result.all()
        if source_id is not None
    }


async def _collect(
    db: AsyncSession,
    *,
    settings: Dict[str, Any],
    limit: int = MAX_ITEMS_PER_RUN,
    organization_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """فهرست فایل‌های منقضی با تصمیم مشخص (آرشیو یا حذف) — بدون هیچ تغییری."""
    if organization_id is not None:
        org_stmt = select(Organizations).where(Organizations.id == int(organization_id))
    else:
        org_stmt = (
            select(Organizations)
            .where(Organizations.status != TRASHED_STATUS)
            .order_by(Organizations.id)
        )
    organizations = list((await db.execute(org_stmt)).scalars().all())

    now = core.utc_now()
    found: List[Dict[str, Any]] = []
    for organization in organizations:
        days = platform_settings.resolve_retention_days(
            settings, organization.audio_retention_days
        )
        cutoff = now - core.timedelta(days=days)
        target_row = await storage_targets.get_row(db, int(organization.id))
        has_target = storage_targets.is_active(target_row)
        action = ACTION_ARCHIVE if has_target else ACTION_DELETE
        archived = await _archived_keys(db, int(organization.id))

        titles_result = await db.execute(
            select(Meetings.id, Meetings.title).where(
                Meetings.organization_id == int(organization.id)
            )
        )
        meeting_titles = {int(mid): (title or "") for mid, title in titles_result.all()}

        recordings = await db.execute(
            select(Recordings).where(Recordings.organization_id == int(organization.id))
        )
        for row in recordings.scalars().all():
            created = _as_utc(row.created_at)
            if created is None or created >= cutoff:
                continue
            if (KIND_RECORDING, int(row.id)) in archived:
                continue
            found.append(
                {
                    "organization_id": int(organization.id),
                    "organization_name": organization.name or "",
                    "organization_days": days,
                    "meeting_id": int(row.meeting_id or 0),
                    "meeting_title": meeting_titles.get(int(row.meeting_id or 0), ""),
                    "source_kind": KIND_RECORDING,
                    "kind_label": KIND_LABELS.get(KIND_RECORDING, KIND_RECORDING),
                    "source_id": int(row.id),
                    "file_name": row.file_name or "",
                    "content_type": row.mime_type or "application/octet-stream",
                    "bucket": row.bucket_name or core.AUDIO_BUCKET,
                    "object_key": row.object_key or "",
                    "size_bytes": int(row.size_bytes or 0)
                    + int(row.video_size_bytes or 0),
                    "created_at": created,
                    "age_days": _age_days(created, now),
                    "action": action,
                }
            )

        attachments = await db.execute(
            select(Meeting_attachments).where(
                Meeting_attachments.organization_id == int(organization.id)
            )
        )
        for row in attachments.scalars().all():
            created = _as_utc(row.created_at)
            if created is None or created >= cutoff:
                continue
            if (KIND_ATTACHMENT, int(row.id)) in archived:
                continue
            found.append(
                {
                    "organization_id": int(organization.id),
                    "organization_name": organization.name or "",
                    "organization_days": days,
                    "meeting_id": int(row.meeting_id or 0),
                    "meeting_title": meeting_titles.get(int(row.meeting_id or 0), ""),
                    "source_kind": KIND_ATTACHMENT,
                    "kind_label": KIND_LABELS.get(KIND_ATTACHMENT, KIND_ATTACHMENT),
                    "source_id": int(row.id),
                    "file_name": row.file_name or "",
                    "content_type": row.content_type or "application/octet-stream",
                    "bucket": files.ATTACHMENTS_BUCKET,
                    "object_key": row.object_key or "",
                    "size_bytes": int(row.size_bytes or 0),
                    "created_at": created,
                    "age_days": _age_days(created, now),
                    "action": action,
                }
            )

    found.sort(key=lambda item: item["created_at"])
    return found[: max(1, int(limit))]


def _serialize(item: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "organization_id": item["organization_id"],
        "organization_name": item["organization_name"],
        "organization_days": item["organization_days"],
        "meeting_id": item["meeting_id"],
        "meeting_title": item["meeting_title"],
        "source_kind": item["source_kind"],
        "kind_label": item["kind_label"],
        "source_id": item["source_id"],
        "file_name": item["file_name"],
        "size_bytes": item["size_bytes"],
        "age_days": item["age_days"],
        "created_at": core.iso_utc(item["created_at"]),
        "action": item["action"],
        "action_label": ACTION_LABELS.get(item["action"], item["action"]),
    }


def _summary(items: List[Dict[str, Any]], settings: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "days": int(settings.get("days") or platform_settings.DEFAULT_MEDIA_RETENTION_DAYS),
        "auto": bool(settings.get("auto")),
        "allow_org_override": bool(settings.get("allow_org_override", True)),
        "bounds": settings.get("bounds")
        or {
            "min": platform_settings.MEDIA_RETENTION_BOUNDS[0],
            "max": platform_settings.MEDIA_RETENTION_BOUNDS[1],
        },
        "generated_at": core.now_iso(),
        "total": len(items),
        "total_bytes": sum(int(item["size_bytes"] or 0) for item in items),
        "archive_count": sum(1 for item in items if item["action"] == ACTION_ARCHIVE),
        "delete_count": sum(1 for item in items if item["action"] == ACTION_DELETE),
        "organizations": len({item["organization_id"] for item in items}),
    }


async def plan(
    db: AsyncSession,
    *,
    limit: int = MAX_ITEMS_PER_RUN,
    include_items: bool = True,
    organization_id: Optional[int] = None,
) -> Dict[str, Any]:
    """گزارش «چه فایلی منقضی شده و چه سرنوشتی دارد» بدون هیچ تغییری."""
    settings = await platform_settings.get_media_retention(db)
    items = await _collect(
        db, settings=settings, limit=limit, organization_id=organization_id
    )
    payload = _summary(items, settings)
    payload["items"] = (
        [_serialize(item) for item in items[:REPORT_ITEM_LIMIT]] if include_items else []
    )
    payload["truncated"] = include_items and len(items) > REPORT_ITEM_LIMIT
    return payload


async def _delete_item(db: AsyncSession, item: Dict[str, Any]) -> None:
    """حذف فایل منقضی از سرور (رکورد + شیء Storage)."""
    organization_id = int(item["organization_id"])
    if item["source_kind"] == KIND_RECORDING:
        result = await db.execute(
            select(Recordings).where(
                Recordings.id == int(item["source_id"]),
                Recordings.organization_id == organization_id,
            )
        )
        row = result.scalars().first()
        if row is None:
            return
        bucket = row.bucket_name or core.AUDIO_BUCKET
        object_keys = [key for key in {row.object_key, row.video_object_key} if key]
        await db.delete(row)
        await db.commit()
        storage = StorageService()
        for object_key in object_keys:
            try:
                await storage.delete_object(
                    ObjectRequest(bucket_name=bucket, object_key=object_key)
                )
            except Exception:  # noqa: BLE001 - حذف شیء نباید کل اجرا را متوقف کند
                logger.warning("حذف شیء %s از استوریج ناموفق بود", object_key)
        return

    result = await db.execute(
        select(Meeting_attachments).where(
            Meeting_attachments.id == int(item["source_id"]),
            Meeting_attachments.organization_id == organization_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        return
    object_key = row.object_key
    await db.delete(row)
    await db.commit()
    await files.delete_attachment_object(object_key)


async def _audit(
    db: AsyncSession, items: List[Dict[str, Any]], report: Dict[str, Any], actor_name: str
) -> None:
    """ثبت نتیجهٔ اجرا در Audit Log (یک رکورد برای هر سازمان + یک رکورد سراسری)."""
    actor = (actor_name or "سیاست نگهداری سامانه")[:120]
    per_org: Dict[int, Dict[str, int]] = {}
    for item in items:
        stats = per_org.setdefault(
            int(item["organization_id"]), {"archive": 0, "delete": 0, "bytes": 0}
        )
        stats[item["action"]] += 1
        stats["bytes"] += int(item["size_bytes"] or 0)

    try:
        for organization_id, stats in per_org.items():
            db.add(
                Audit_logs(
                    organization_id=organization_id,
                    actor_name=actor,
                    actor_role="platform_admin",
                    action="media.retention_enforced",
                    entity_type="organization",
                    entity_id=organization_id,
                    detail=(
                        f"سیاست نگهداری مدیا اجرا شد؛ "
                        f"{stats['archive']} فایل به استوریج خارجی منتقل و "
                        f"{stats['delete']} فایل حذف شد "
                        f"({round(stats['bytes'] / (1024 * 1024), 2)} مگابایت)"
                    )[:900],
                )
            )
        db.add(
            Audit_logs(
                organization_id=0,
                actor_name=actor,
                actor_role="platform_admin",
                action="platform.media_retention_run",
                entity_type="platform",
                entity_id=None,
                detail=(
                    f"اجرای {'خودکار' if report.get('automatic') else 'دستی'} سیاست نگهداری: "
                    f"{report.get('archived', 0)} انتقال، {report.get('deleted', 0)} حذف، "
                    f"{report.get('failed', 0)} خطا"
                )[:900],
            )
        )
        await db.commit()
    except Exception as exc:  # pragma: no cover - ثبت لاگ نباید اجرا را بشکند
        logger.warning("ثبت Audit اجرای نگهداری مدیا ناموفق بود: %s", exc)


async def run(
    db: AsyncSession,
    *,
    actor_name: str = "",
    execute: bool = True,
    limit: int = MAX_ITEMS_PER_RUN,
    organization_id: Optional[int] = None,
    automatic: bool = False,
) -> Dict[str, Any]:
    """اجرای سیاست نگهداری؛ با ``execute=False`` فقط گزارش ساخته می‌شود."""
    settings = await platform_settings.get_media_retention(db)
    items = await _collect(
        db, settings=settings, limit=limit, organization_id=organization_id
    )
    report = _summary(items, settings)
    report["dry_run"] = not execute
    report["automatic"] = automatic
    report["archived"] = 0
    report["deleted"] = 0
    report["failed"] = 0
    report["freed_bytes"] = 0
    report["errors"] = []
    report["items"] = [_serialize(item) for item in items[:REPORT_ITEM_LIMIT]]
    report["truncated"] = len(items) > REPORT_ITEM_LIMIT
    if not execute or not items:
        return report

    for item in items:
        try:
            if item["action"] == ACTION_ARCHIVE:
                cfg, prefix, _ = await archive.target_for(db, int(item["organization_id"]))
                source = {
                    "source_kind": item["source_kind"],
                    "source_id": int(item["source_id"]),
                    "file_name": item["file_name"],
                    "content_type": item["content_type"],
                    "bucket": item["bucket"],
                    "object_key": item["object_key"],
                    "size_bytes": int(item["size_bytes"] or 0),
                }
                await archive.archive_one(
                    db,
                    cfg,
                    prefix,
                    int(item["organization_id"]),
                    int(item["meeting_id"]),
                    source,
                    actor_name=(actor_name or "سیاست نگهداری سامانه"),
                )
                report["archived"] += 1
            else:
                await _delete_item(db, item)
                report["deleted"] += 1
            report["freed_bytes"] += int(item["size_bytes"] or 0)
        except Exception as exc:  # noqa: BLE001 - یک فایل نباید کل اجرا را متوقف کند
            await db.rollback()
            report["failed"] += 1
            report["errors"].append(
                {
                    "file_name": item["file_name"],
                    "organization_name": item["organization_name"],
                    "action": item["action"],
                    "message": str(exc)[:300],
                }
            )
            logger.warning(
                "اجرای نگهداری مدیا برای فایل %s ناموفق بود: %s", item["file_name"], exc
            )

    await _audit(db, items, report, actor_name)
    return report


# ---------------------------------------------------------------------------
# اجرای خودکار دوره‌ای
# ---------------------------------------------------------------------------


async def auto_sweep_once() -> Optional[Dict[str, Any]]:
    """یک اجرای خودکار؛ تنها اگر مدیر سامانه اجرای خودکار را روشن کرده باشد."""
    from core.database import db_manager

    if not db_manager.async_session_maker:
        return None
    async with db_manager.async_session_maker() as session:
        settings = await platform_settings.get_media_retention(session)
        if not settings.get("auto"):
            return None
        report = await run(
            session, actor_name="اجرای خودکار سامانه", execute=True, automatic=True
        )
        if report.get("total"):
            logger.info(
                "سیاست نگهداری مدیا: %s انتقال، %s حذف، %s خطا",
                report.get("archived"),
                report.get("deleted"),
                report.get("failed"),
            )
        return report


async def auto_sweep_forever() -> None:
    """حلقهٔ پس‌زمینهٔ اجرای خودکار با فاصلهٔ ثابت و تحمل خطا."""
    await asyncio.sleep(FIRST_SWEEP_DELAY_SECONDS)
    while True:
        try:
            await auto_sweep_once()
        except asyncio.CancelledError:
            raise
        except Exception:  # pragma: no cover - حلقه نباید بمیرد
            logger.exception("اجرای خودکار سیاست نگهداری مدیا ناموفق بود")
        await asyncio.sleep(SWEEP_INTERVAL_SECONDS)

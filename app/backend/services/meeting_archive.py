"""آرشیو فایل‌های جانبی جلسه روی فضای ذخیره‌سازی خارجی سازمان.

قواعد سخت این ماژول (همه از الزام «انتقال امن» می‌آید):

* **حذف پس از تأیید**: فایل تنها زمانی از فضای ذخیره‌سازی اصلی حذف می‌شود که
  در مقصد خارجی نوشته شده، حجم آن تأیید شده و نسخهٔ بازخوانده‌شده از مقصد
  دقیقاً همان چکسام SHA-256 فایل اصلی را داشته باشد. هر شکستی در این زنجیره،
  فایل اصلی را دست‌نخورده باقی می‌گذارد و رکورد را با وضعیت خطا علامت می‌زند.
* **جریانی بودن**: انتقال با قطعه‌های یک مگابایتی و فایل موقت انجام می‌شود؛
  هیچ فایلی کامل در حافظه بار نمی‌شود.
* **idempotency**: مسیر مقصد هر فایل تابعی قطعی از
  (سازمان، جلسه، نوع منبع، شناسهٔ منبع) است؛ اجرای دوبارهٔ آرشیو همان مسیر را
  بازنویسی می‌کند و فایل تکراری در مقصد نمی‌سازد.
* **مرز مستأجر**: همهٔ کوئری‌ها با ``organization_id`` محدود و مسیر مقصد با
  پیشوند ``org-<id>`` جدا می‌شود.
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.meeting_archive_files import Meeting_archive_files
from models.meeting_attachments import Meeting_attachments
from models.recordings import Recordings
from schemas.storage import FileUpDownRequest, ObjectRequest
from services import external_storage as ext
from services import mgmt_core as core
from services import storage_targets
from services.meeting_files import ATTACHMENTS_BUCKET, safe_object_name
from services.storage import StorageService

logger = logging.getLogger(__name__)

# وضعیت‌های چرخهٔ عمر یک فایل جانبی
STATUS_ON_SERVER = "on_server"
STATUS_ARCHIVING = "archiving"
STATUS_ARCHIVED = "archived"
STATUS_RESTORING = "restoring"
STATUS_RESTORED = "restored"
STATUS_ERROR = "error"

STATUS_LABELS = {
    STATUS_ON_SERVER: "روی سرور",
    STATUS_ARCHIVING: "در حال انتقال به آرشیو",
    STATUS_ARCHIVED: "آرشیو شده",
    STATUS_RESTORING: "در حال بازیابی",
    STATUS_RESTORED: "بازیابی‌شده روی سرور",
    STATUS_ERROR: "خطا",
}

KIND_RECORDING = "recording"
KIND_ATTACHMENT = "attachment"
KIND_LABELS = {KIND_RECORDING: "فایل صوتی جلسه", KIND_ATTACHMENT: "پیوست دستور جلسه"}

ARCHIVE_FIELDS = [
    "id",
    "meeting_id",
    "source_kind",
    "source_id",
    "file_name",
    "content_type",
    "remote_path",
    "size_bytes",
    "checksum_sha256",
    "status",
    "error_message",
    "archived_at",
    "restored_at",
    "restore_expires_at",
    "archived_by_name",
    "restored_by_name",
]

_TIMEOUT = httpx.Timeout(connect=20.0, read=600.0, write=600.0, pool=20.0)


class ArchiveError(Exception):
    """خطای قابل نمایش در جریان آرشیو یا بازیابی."""


# ---------------------------------------------------------------------------
# منابع قابل آرشیو
# ---------------------------------------------------------------------------


async def list_sources(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> List[Dict[str, Any]]:
    """فهرست فایل‌های جانبی یک جلسه (صوت‌ها و پیوست‌ها) در مرز همان سازمان."""
    sources: List[Dict[str, Any]] = []

    recordings = await db.execute(
        select(Recordings)
        .where(
            Recordings.organization_id == int(organization_id),
            Recordings.meeting_id == int(meeting_id),
        )
        .order_by(Recordings.id.asc())
    )
    for row in recordings.scalars().all():
        sources.append(
            {
                "source_kind": KIND_RECORDING,
                "source_id": int(row.id),
                "file_name": row.file_name or f"recording-{int(row.id)}",
                "content_type": row.mime_type or "application/octet-stream",
                "bucket": row.bucket_name or core.AUDIO_BUCKET,
                "object_key": row.object_key or "",
                "size_bytes": int(row.size_bytes or 0),
            }
        )

    attachments = await db.execute(
        select(Meeting_attachments)
        .where(
            Meeting_attachments.organization_id == int(organization_id),
            Meeting_attachments.meeting_id == int(meeting_id),
        )
        .order_by(Meeting_attachments.id.asc())
    )
    for row in attachments.scalars().all():
        sources.append(
            {
                "source_kind": KIND_ATTACHMENT,
                "source_id": int(row.id),
                "file_name": row.file_name or f"attachment-{int(row.id)}",
                "content_type": row.content_type or "application/octet-stream",
                "bucket": ATTACHMENTS_BUCKET,
                "object_key": row.object_key or "",
                "size_bytes": int(row.size_bytes or 0),
            }
        )

    return [item for item in sources if item["object_key"]]


async def get_state_row(
    db: AsyncSession, organization_id: int, source_kind: str, source_id: int
) -> Optional[Meeting_archive_files]:
    result = await db.execute(
        select(Meeting_archive_files).where(
            Meeting_archive_files.organization_id == int(organization_id),
            Meeting_archive_files.source_kind == source_kind,
            Meeting_archive_files.source_id == int(source_id),
        )
    )
    return result.scalars().first()


async def list_state_rows(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> List[Meeting_archive_files]:
    result = await db.execute(
        select(Meeting_archive_files)
        .where(
            Meeting_archive_files.organization_id == int(organization_id),
            Meeting_archive_files.meeting_id == int(meeting_id),
        )
        .order_by(Meeting_archive_files.id.asc())
    )
    return list(result.scalars().all())


def remote_path_for(prefix: str, source: Dict[str, Any], meeting_id: int) -> str:
    """مسیر قطعی و یکتای فایل در مقصد خارجی (کلید idempotency)."""
    return ext.join_path(
        prefix,
        f"meeting-{int(meeting_id)}",
        f"{source['source_kind']}-{int(source['source_id'])}",
        safe_object_name(str(source.get("file_name") or "file")),
    )


def file_payload(row: Meeting_archive_files) -> Dict[str, Any]:
    payload = core.dump(row, ARCHIVE_FIELDS)
    payload["status_label"] = STATUS_LABELS.get(row.status or "", row.status or "")
    payload["kind_label"] = KIND_LABELS.get(row.source_kind or "", row.source_kind or "")
    payload["is_archived"] = (row.status or "") == STATUS_ARCHIVED
    payload["is_local"] = (row.status or "") in (STATUS_ON_SERVER, STATUS_RESTORED)
    return payload


# ---------------------------------------------------------------------------
# پل جریانی با فضای ذخیره‌سازی اصلی
# ---------------------------------------------------------------------------


async def _aiter_file(fileobj: Any) -> AsyncIterator[bytes]:
    fileobj.seek(0)
    while True:
        chunk = fileobj.read(ext.CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


async def _stream_from_main(bucket: str, object_key: str, sink: Any) -> Tuple[int, str]:
    """خواندن جریانی فایل از فضای ذخیره‌سازی اصلی؛ (حجم، چکسام) برمی‌گرداند."""
    service = StorageService()
    signed = await service.create_download_url(
        FileUpDownRequest(bucket_name=bucket, object_key=object_key)
    )
    url = signed.download_url or ""
    if not url:
        raise ArchiveError("ساخت نشانی موقت دانلود از فضای ذخیره‌سازی اصلی ناموفق بود.")

    digest = hashlib.sha256()
    total = 0
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                if response.status_code >= 400:
                    await response.aread()
                    raise ArchiveError(
                        "خواندن فایل از فضای ذخیره‌سازی اصلی ناموفق بود "
                        f"(کد {response.status_code}). فایل ممکن است پیش‌تر حذف شده باشد."
                    )
                async for chunk in response.aiter_bytes(ext.CHUNK_SIZE):
                    if not chunk:
                        continue
                    digest.update(chunk)
                    total += len(chunk)
                    sink.write(chunk)
    except httpx.HTTPError as exc:
        raise ArchiveError("ارتباط با فضای ذخیره‌سازی اصلی برقرار نشد.") from exc

    sink.flush()
    if total == 0:
        raise ArchiveError("فایل مبدأ خالی است یا در فضای ذخیره‌سازی اصلی یافت نشد.")
    return total, digest.hexdigest()


async def _stream_to_main(bucket: str, object_key: str, fileobj: Any, size: int) -> None:
    """بازگرداندن جریانی فایل به فضای ذخیره‌سازی اصلی با همان کلید قبلی."""
    service = StorageService()
    signed = await service.create_upload_url(
        FileUpDownRequest(bucket_name=bucket, object_key=object_key)
    )
    url = signed.upload_url or ""
    if not url:
        raise ArchiveError("ساخت نشانی موقت بارگذاری در فضای ذخیره‌سازی اصلی ناموفق بود.")

    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            response = await client.put(
                url,
                headers={"content-length": str(int(size))},
                content=_aiter_file(fileobj),
            )
    except httpx.HTTPError as exc:
        raise ArchiveError("بازگرداندن فایل به فضای ذخیره‌سازی اصلی ناموفق بود.") from exc

    if response.status_code >= 400:
        raise ArchiveError(
            "بازگرداندن فایل به فضای ذخیره‌سازی اصلی رد شد "
            f"(کد {response.status_code}). لطفاً دوباره تلاش کنید."
        )


async def _delete_from_main(bucket: str, object_key: str) -> bool:
    try:
        service = StorageService()
        result = await service.delete_object(
            ObjectRequest(bucket_name=bucket, object_key=object_key)
        )
        return bool(getattr(result, "success", False))
    except Exception:  # noqa: BLE001 - حذف ناموفق نباید رکورد آرشیو را خراب کند
        logger.exception("حذف شیء %s/%s از فضای اصلی ناموفق بود", bucket, object_key)
        return False


# ---------------------------------------------------------------------------
# آرشیو یک فایل
# ---------------------------------------------------------------------------


async def _ensure_row(
    db: AsyncSession,
    organization_id: int,
    meeting_id: int,
    source: Dict[str, Any],
) -> Meeting_archive_files:
    row = await get_state_row(db, organization_id, source["source_kind"], source["source_id"])
    if row is None:
        row = Meeting_archive_files(
            organization_id=int(organization_id),
            meeting_id=int(meeting_id),
            source_kind=source["source_kind"],
            source_id=int(source["source_id"]),
            status=STATUS_ON_SERVER,
        )
        db.add(row)
    row.file_name = str(source.get("file_name") or "")[:300]
    row.content_type = str(source.get("content_type") or "")[:120]
    row.source_bucket = str(source.get("bucket") or "")[:120]
    row.source_object_key = str(source.get("object_key") or "")[:500]
    await db.flush()
    return row


async def sync_rows(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> List[Meeting_archive_files]:
    """همگام‌سازی رکوردهای وضعیت با فایل‌های واقعی جلسه."""
    sources = await list_sources(db, organization_id, meeting_id)
    rows: List[Meeting_archive_files] = []
    for source in sources:
        rows.append(await _ensure_row(db, organization_id, meeting_id, source))
    return rows


async def archive_one(
    db: AsyncSession,
    cfg: ext.TargetConfig,
    prefix: str,
    organization_id: int,
    meeting_id: int,
    source: Dict[str, Any],
    *,
    actor_name: str,
) -> Tuple[Meeting_archive_files, str]:
    """انتقال یک فایل به مقصد خارجی و سپس حذف امن نسخهٔ سرور.

    ترتیب عملیات هرگز جابه‌جا نمی‌شود: نوشتن → بررسی حجم → بازخوانی و مقایسهٔ
    چکسام → و تنها در پایان، حذف نسخهٔ اصلی.
    """
    row = await _ensure_row(db, organization_id, meeting_id, source)

    if (row.status or "") == STATUS_ARCHIVED and (row.remote_path or ""):
        return row, "این فایل پیش‌تر آرشیو شده بود؛ عملیات تکراری انجام نشد."

    remote_path = remote_path_for(prefix, source, meeting_id)
    row.status = STATUS_ARCHIVING
    row.error_message = ""
    row.remote_path = remote_path
    await db.commit()

    buffer = ext.spooled_file()
    try:
        size, checksum = await _stream_from_main(
            str(source["bucket"]), str(source["object_key"]), buffer
        )
        await ext.upload_file(
            cfg,
            remote_path,
            buffer,
            size=size,
            sha256_hex=checksum,
            content_type=str(source.get("content_type") or "application/octet-stream"),
        )

        remote_size = await ext.stat_file(cfg, remote_path)
        if remote_size >= 0 and remote_size != size:
            raise ArchiveError(
                "حجم فایل نوشته‌شده در مقصد با فایل اصلی یکسان نیست؛ "
                "فایل اصلی حذف نشد."
            )

        verify = ext.spooled_file()
        try:
            back_size, back_checksum = await ext.download_file(cfg, remote_path, verify)
        finally:
            verify.close()

        if back_size != size or back_checksum != checksum:
            raise ArchiveError(
                "بازخوانی فایل از مقصد با چکسام فایل اصلی مطابقت نداشت؛ "
                "فایل اصلی حذف نشد."
            )
    except (ext.ExternalStorageError, ArchiveError) as exc:
        buffer.close()
        await db.rollback()
        fresh = await get_state_row(db, organization_id, source["source_kind"], source["source_id"])
        if fresh is not None:
            fresh.status = STATUS_ERROR
            fresh.error_message = str(exc)[:900]
            await db.commit()
        raise ArchiveError(str(exc)) from exc
    finally:
        try:
            buffer.close()
        except Exception:  # noqa: BLE001
            pass

    removed = await _delete_from_main(str(source["bucket"]), str(source["object_key"]))

    row = await get_state_row(db, organization_id, source["source_kind"], source["source_id"])
    if row is None:  # pragma: no cover - محافظ عملیاتی
        raise ArchiveError("رکورد وضعیت آرشیو یافت نشد.")
    row.size_bytes = int(size)
    row.checksum_sha256 = checksum
    row.remote_path = remote_path
    row.status = STATUS_ARCHIVED
    row.archived_at = core.now_iso()
    row.archived_by_name = (actor_name or "")[:120]
    row.restored_at = ""
    row.restore_expires_at = ""
    row.error_message = (
        ""
        if removed
        else "فایل در مقصد ثبت شد اما حذف نسخهٔ سرور کامل نشد؛ فضای اشغال‌شده را بررسی کنید."
    )
    await db.commit()
    return row, "فایل با موفقیت به آرشیو خارجی منتقل شد."


async def restore_one(
    db: AsyncSession,
    cfg: ext.TargetConfig,
    row: Meeting_archive_files,
    *,
    actor_name: str,
    retention_days: int,
) -> Tuple[Meeting_archive_files, str]:
    """بازیابی فایل از مقصد خارجی به فضای ذخیره‌سازی اصلی با همان کلید قبلی."""
    if (row.status or "") in (STATUS_ON_SERVER, STATUS_RESTORED):
        return row, "این فایل همین حالا روی سرور موجود است."
    if not (row.remote_path or "") or not (row.source_object_key or ""):
        raise ArchiveError("مسیر آرشیو یا کلید فایل اصلی برای این رکورد ثبت نشده است.")

    organization_id = int(row.organization_id)
    source_kind, source_id = row.source_kind, int(row.source_id)
    row.status = STATUS_RESTORING
    row.error_message = ""
    await db.commit()

    buffer = ext.spooled_file()
    try:
        size, checksum = await ext.download_file(cfg, str(row.remote_path), buffer)
        expected = (row.checksum_sha256 or "").strip()
        if expected and expected != checksum:
            raise ArchiveError(
                "چکسام نسخهٔ آرشیو با مقدار ثبت‌شده یکسان نیست؛ فایل بازیابی نشد."
            )
        await _stream_to_main(
            str(row.source_bucket or core.AUDIO_BUCKET),
            str(row.source_object_key),
            buffer,
            size,
        )
    except (ext.ExternalStorageError, ArchiveError) as exc:
        buffer.close()
        await db.rollback()
        fresh = await get_state_row(db, organization_id, source_kind, source_id)
        if fresh is not None:
            fresh.status = STATUS_ARCHIVED  # نسخهٔ آرشیو دست‌نخورده است
            fresh.error_message = str(exc)[:900]
            await db.commit()
        raise ArchiveError(str(exc)) from exc
    finally:
        try:
            buffer.close()
        except Exception:  # noqa: BLE001
            pass

    row = await get_state_row(db, organization_id, source_kind, source_id)
    if row is None:  # pragma: no cover
        raise ArchiveError("رکورد وضعیت آرشیو یافت نشد.")
    row.status = STATUS_RESTORED
    row.restored_at = core.now_iso()
    row.restored_by_name = (actor_name or "")[:120]
    row.restore_expires_at = core.iso_utc(
        core.utc_now() + core.timedelta(days=max(1, int(retention_days or 14)))
    )
    row.error_message = ""
    await db.commit()
    return row, "فایل از آرشیو بازیابی شد و اکنون قابل پخش/دانلود است."


async def enforce_retention(db: AsyncSession, organization_id: int) -> int:
    """پاک‌سازی نسخه‌های بازیابی‌شدهٔ منقضی؛ نسخهٔ آرشیو دست‌نخورده می‌ماند."""
    result = await db.execute(
        select(Meeting_archive_files).where(
            Meeting_archive_files.organization_id == int(organization_id),
            Meeting_archive_files.status == STATUS_RESTORED,
        )
    )
    now = core.utc_now()
    cleaned = 0
    for row in result.scalars().all():
        deadline = core.parse_iso(row.restore_expires_at or "")
        if deadline is None or deadline > now:
            continue
        await _delete_from_main(
            str(row.source_bucket or core.AUDIO_BUCKET), str(row.source_object_key or "")
        )
        row.status = STATUS_ARCHIVED
        row.restored_at = ""
        row.restore_expires_at = ""
        row.error_message = ""
        cleaned += 1
    if cleaned:
        await db.commit()
    return cleaned


async def meeting_overview(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> Dict[str, Any]:
    """نمای وضعیت آرشیو یک جلسه برای فرانت."""
    rows = await sync_rows(db, organization_id, meeting_id)
    archived_rows = await list_state_rows(db, organization_id, meeting_id)
    known = {(row.source_kind, int(row.source_id)) for row in rows}
    files = [file_payload(row) for row in rows]
    # رکوردهایی که فایل مبدأ آن‌ها آرشیو شده و دیگر در فهرست منابع نیست
    for row in archived_rows:
        if (row.source_kind, int(row.source_id)) not in known:
            files.append(file_payload(row))

    statuses = [item["status"] for item in files]
    if not files:
        state = "empty"
    elif all(status == STATUS_ARCHIVED for status in statuses):
        state = STATUS_ARCHIVED
    elif any(status in (STATUS_ARCHIVING, STATUS_RESTORING) for status in statuses):
        state = STATUS_ARCHIVING if STATUS_ARCHIVING in statuses else STATUS_RESTORING
    elif any(status == STATUS_ERROR for status in statuses):
        state = STATUS_ERROR
    elif any(status == STATUS_ARCHIVED for status in statuses):
        state = "partial"
    else:
        state = STATUS_ON_SERVER

    return {
        "meeting_id": int(meeting_id),
        "state": state,
        "state_label": STATUS_LABELS.get(state, "بخشی آرشیو شده" if state == "partial" else state),
        "files": files,
        "archived_count": sum(1 for status in statuses if status == STATUS_ARCHIVED),
        "total_count": len(files),
        "archived_bytes": sum(
            int(item.get("size_bytes") or 0) for item in files if item["status"] == STATUS_ARCHIVED
        ),
    }


async def target_for(
    db: AsyncSession, organization_id: int
) -> Tuple[ext.TargetConfig, str, int]:
    """پیکربندی مقصد فعال سازمان؛ در نبود مقصد، خطای راهنما."""
    row = await storage_targets.get_row(db, organization_id)
    if not storage_targets.is_active(row):
        raise ArchiveError(
            "مقصد ذخیره‌سازی خارجی برای این سازمان تعریف یا فعال نشده است. "
            "ابتدا در «تنظیمات › آرشیو و استوریج خارجی» مقصد را ثبت و تست کنید."
        )
    assert row is not None
    cfg = storage_targets.build_config(row)
    cfg.validate()
    return (
        cfg,
        storage_targets.tenant_prefix(row),
        int(row.restore_retention_days or storage_targets.DEFAULT_RESTORE_RETENTION_DAYS),
    )
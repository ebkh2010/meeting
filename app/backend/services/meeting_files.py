"""لایهٔ کمکی فایل‌های جلسه روی Object Storage.

نکته‌های طراحی:

* پیوست‌های جلسه در یک باکت خصوصی نگه‌داری می‌شوند و کلید هر شیء با
  ``organization_id`` آغاز می‌شود تا مرز مستأجر در سطح Storage نیز حفظ شود.
* برای ایمیل، محتوای فایل با URL امضاشدهٔ دانلود خوانده و به‌صورت MIME پیوست
  می‌گردد؛ URL هرگز به گیرندهٔ ایمیل داده نمی‌شود.
* هیچ خطای Storage جریان اصلی (ایجاد جلسه یا ارسال دعوت) را متوقف نمی‌کند؛
  توابع در حالت خطا ``None`` برمی‌گردانند و خطا در لاگ ثبت می‌شود.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from typing import Optional

import httpx
from schemas.storage import BucketRequest, FileUpDownRequest, ObjectRequest
from services.storage import StorageService

logger = logging.getLogger(__name__)

# باکت اختصاصی پیوست‌های دستور جلسه.
ATTACHMENTS_BUCKET = "meeting-attachments"

# سقف حجم هر پیوست ایمیل (۸ مگابایت)؛ فایل‌های بزرگ‌تر فقط در فهرست نام‌ها
# ذکر می‌شوند تا سرور ایمیل درخواست را رد نکند.
MAX_EMAIL_ATTACHMENT_BYTES = 8 * 1024 * 1024

# سقف حجم هر فایل قابل آپلود (۲۵ مگابایت).
MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024

ALLOWED_ATTACHMENT_TYPES = {
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "application/vnd.ms-powerpoint",
    "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "text/plain",
    "text/csv",
    "image/png",
    "image/jpeg",
    "image/webp",
    "application/zip",
}

_UNSAFE_KEY_CHARS = re.compile(r"[^A-Za-z0-9._-]+")


def safe_object_name(file_name: str) -> str:
    """تبدیل نام فایل فارسی به بخش امن کلید شیء (نام اصلی در DB می‌ماند).

    نام‌های کامل فارسی پس از حذف کاراکترهای غیر ASCII خالی می‌شوند؛ برای همین
    پسوند فایل جداگانه استخراج و به کلید امن اضافه می‌شود تا نوع فایل در
    Object Storage گم نشود و دانلود با پسوند درست انجام گیرد.
    """
    raw = (file_name or "").strip()
    stem, _, extension = raw.rpartition(".")
    if not stem:  # نامی بدون پسوند
        stem, extension = raw, ""

    def to_ascii(value: str) -> str:
        normalized = unicodedata.normalize("NFKD", value)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return _UNSAFE_KEY_CHARS.sub("-", ascii_only).strip("-.")

    safe_stem = to_ascii(stem)[:60] or "file"
    safe_extension = to_ascii(extension)[:10].lower()
    return f"{safe_stem}.{safe_extension}" if safe_extension else safe_stem


def build_object_key(organization_id: int, meeting_id: int, token: str, file_name: str) -> str:
    """کلید یکتای شیء با پیشوند سازمان و جلسه."""
    return f"org-{int(organization_id)}/meeting-{int(meeting_id)}/{token}-{safe_object_name(file_name)}"


async def ensure_attachments_bucket(service: StorageService) -> None:
    """اطمینان از وجود باکت خصوصی پیوست‌ها (idempotent)."""
    try:
        buckets = await service.list_buckets()
        if any(item.bucket_name == ATTACHMENTS_BUCKET for item in buckets.buckets):
            return
        await service.create_bucket(
            BucketRequest(bucket_name=ATTACHMENTS_BUCKET, visibility="private")
        )
    except Exception:  # noqa: BLE001 - باکت ممکن است پیش‌تر ساخته شده باشد
        logger.warning("اطمینان از وجود باکت %s ناموفق بود", ATTACHMENTS_BUCKET, exc_info=True)


async def create_attachment_upload_url(object_key: str) -> Optional[str]:
    """URL امضاشدهٔ آپلود برای پیوست جلسه؛ در خطا ``None``."""
    try:
        service = StorageService()
        await ensure_attachments_bucket(service)
        response = await service.create_upload_url(
            FileUpDownRequest(bucket_name=ATTACHMENTS_BUCKET, object_key=object_key)
        )
        return response.upload_url or None
    except Exception:  # noqa: BLE001 - خطای Storage نباید جریان اصلی را بشکند
        logger.exception("ساخت URL آپلود پیوست برای %s ناموفق بود", object_key)
        return None


async def create_attachment_download_url(object_key: str) -> Optional[str]:
    """URL امضاشدهٔ دانلود برای پیوست جلسه؛ در خطا ``None``."""
    try:
        service = StorageService()
        response = await service.create_download_url(
            FileUpDownRequest(bucket_name=ATTACHMENTS_BUCKET, object_key=object_key)
        )
        return response.download_url or None
    except Exception:  # noqa: BLE001
        logger.exception("ساخت URL دانلود پیوست برای %s ناموفق بود", object_key)
        return None


async def fetch_attachment_bytes(object_key: str) -> Optional[bytes]:
    """خواندن محتوای پیوست برای ضمیمه‌کردن به ایمیل؛ در خطا ``None``."""
    download_url = await create_attachment_download_url(object_key)
    if not download_url:
        return None
    try:
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            response = await client.get(download_url)
        if response.status_code >= 400:
            logger.warning("دانلود پیوست %s با کد %s ناموفق بود", object_key, response.status_code)
            return None
        return response.content
    except httpx.HTTPError:
        logger.exception("دانلود پیوست %s با خطای شبکه ناموفق بود", object_key)
        return None


async def delete_attachment_object(object_key: str) -> bool:
    """حذف شیء پیوست از Storage؛ شکست حذف مانع حذف رکورد نمی‌شود."""
    try:
        service = StorageService()
        result = await service.delete_object(
            ObjectRequest(bucket_name=ATTACHMENTS_BUCKET, object_key=object_key)
        )
        return bool(getattr(result, "success", False))
    except Exception:  # noqa: BLE001
        logger.exception("حذف پیوست %s از Storage ناموفق بود", object_key)
        return False
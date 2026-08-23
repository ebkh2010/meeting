"""سقف‌های بارگذاری قابل تنظیم در سطح هر سازمان (تننت).

پیش از این سقف مدت صوت (۹۰ دقیقه) و سقف حجم پیوست (۲۵ مگابایت) در کد ثابت
بودند و مدیر سازمان راهی برای تغییر آن‌ها نداشت. این ماژول تنها منبع حقیقت
سقف‌ها است و هم بک‌اند (اعتبارسنجی) و هم فرانت (اعتبارسنجی پیش از آپلود و
نمایش راهنما) از همین مقادیر تغذیه می‌شوند.

قواعد طراحی:

* هر سازمان حداکثر یک ردیف در ``org_upload_limits`` دارد؛ نبودِ ردیف یعنی
  «مقادیر پیش‌فرض».
* مقادیر ورودی همیشه در بازهٔ امن کلمپ می‌شوند تا یک عدد اشتباه، ذخیره‌سازی یا
  هزینهٔ رونویسی را از کنترل خارج نکند.
* تغییر سقف‌ها در ``audit_logs`` ثبت می‌شود (در لایهٔ روتر، با متن تغییرها).
"""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.org_upload_limits import Org_upload_limits

# مقادیر پیش‌فرض؛ همان رفتار قبلی سیستم تا هیچ سازمانی با تغییر ناگهانی روبه‌رو نشود.
DEFAULT_MAX_AUDIO_MINUTES = 90
DEFAULT_MAX_AUDIO_MB = 300
DEFAULT_MAX_ATTACHMENT_MB = 25

# بازهٔ مجاز هر سقف: کف برای جلوگیری از قفل‌شدن کاربر و سقف برای مهار هزینه.
BOUNDS: Dict[str, Tuple[int, int]] = {
    "max_audio_minutes": (5, 1440),
    "max_audio_mb": (5, 4096),
    "max_attachment_mb": (1, 512),
}

FIELD_LABELS: Dict[str, str] = {
    "max_audio_minutes": "سقف مدت فایل صوتی (دقیقه)",
    "max_audio_mb": "سقف حجم فایل صوتی (مگابایت)",
    "max_attachment_mb": "سقف حجم هر پیوست (مگابایت)",
}

DEFAULTS: Dict[str, int] = {
    "max_audio_minutes": DEFAULT_MAX_AUDIO_MINUTES,
    "max_audio_mb": DEFAULT_MAX_AUDIO_MB,
    "max_attachment_mb": DEFAULT_MAX_ATTACHMENT_MB,
}


def clamp(field: str, value: Any) -> int:
    """کلمپ مقدار ورودی در بازهٔ مجاز همان فیلد."""
    low, high = BOUNDS[field]
    try:
        number = int(value)
    except (TypeError, ValueError):
        return DEFAULTS[field]
    return max(min(number, high), low)


def snapshot(row: Optional[Org_upload_limits]) -> Dict[str, Any]:
    """نمایش یکنواخت سقف‌ها برای API؛ ردیف نبود یعنی پیش‌فرض‌ها."""
    data = {
        field: clamp(field, getattr(row, field, None) or DEFAULTS[field])
        for field in DEFAULTS
    }
    data["max_attachment_bytes"] = data["max_attachment_mb"] * 1024 * 1024
    data["max_audio_bytes"] = data["max_audio_mb"] * 1024 * 1024
    data["bounds"] = {field: {"min": BOUNDS[field][0], "max": BOUNDS[field][1]} for field in BOUNDS}
    data["defaults"] = dict(DEFAULTS)
    data["updated_by_name"] = getattr(row, "updated_by_name", "") or ""
    data["is_custom"] = row is not None
    return data


async def get_row(db: AsyncSession, organization_id: int) -> Optional[Org_upload_limits]:
    """ردیف سقف‌های سازمان (یا ``None`` در حالت پیش‌فرض)."""
    result = await db.execute(
        select(Org_upload_limits)
        .where(Org_upload_limits.organization_id == int(organization_id))
        .order_by(Org_upload_limits.id.asc())
    )
    return result.scalars().first()


async def get_limits(db: AsyncSession, organization_id: int) -> Dict[str, Any]:
    """سقف‌های مؤثر سازمان؛ همیشه مقدار کامل و امن برمی‌گرداند."""
    return snapshot(await get_row(db, organization_id))


async def save_limits(
    db: AsyncSession,
    organization_id: int,
    *,
    values: Dict[str, Any],
    actor_name: str = "",
) -> Tuple[Dict[str, Any], list[str]]:
    """ذخیرهٔ سقف‌ها و برگرداندن (وضعیت تازه، فهرست تغییرهای انسانی‌خوان)."""
    row = await get_row(db, organization_id)
    before = snapshot(row)

    payload = {
        field: clamp(field, values[field])
        for field in DEFAULTS
        if values.get(field) is not None
    }
    if not payload:
        return before, []

    if row is None:
        row = Org_upload_limits(
            organization_id=int(organization_id),
            max_audio_minutes=before["max_audio_minutes"],
            max_audio_mb=before["max_audio_mb"],
            max_attachment_mb=before["max_attachment_mb"],
        )
        db.add(row)

    changes: list[str] = []
    for field, value in payload.items():
        if int(before[field]) != int(value):
            changes.append(f"{FIELD_LABELS[field]}: {before[field]} ← {value}")
        setattr(row, field, value)
    row.updated_by_name = (actor_name or "")[:120]

    await db.flush()
    return snapshot(row), changes
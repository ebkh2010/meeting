"""تنظیمات مقصد ذخیره‌سازی خارجی در سطح هر سازمان (تننت).

قواعد طراحی، هم‌راستا با تنظیمات AI سازمان:

* هر سازمان حداکثر یک ردیف در ``org_storage_targets`` دارد؛ نبودِ ردیف یعنی
  «مقصد خارجی تعریف نشده» و در این حالت بخش آرشیو غیرفعال و راهنما نشان داده می‌شود.
* اعتبارنامه‌ها (کلید محرمانهٔ S3 و رمز WebDAV) فقط **رمزنگاری‌شده** ذخیره
  می‌شوند و هرگز به فرانت بازنمی‌گردند؛ تنها نمای ماسک‌شده ارسال می‌شود.
* مسیر ذخیره‌سازی هر سازمان با ``org-<id>`` جدا می‌شود، پس حتی با مقصد مشترک،
  فایل یک سازمان در مسیر سازمان دیگر قرار نمی‌گیرد.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.org_storage_targets import Org_storage_targets
from services import external_storage as ext
from services.app_auth import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

DEFAULT_RESTORE_RETENTION_DAYS = 14
RESTORE_RETENTION_BOUNDS = (1, 365)

PROVIDER_CATALOG: List[Dict[str, Any]] = [
    {
        "provider": ext.PROVIDER_S3,
        "label": "سرویس سازگار با S3",
        "note": (
            "برای MinIO خارجی، آروان، لیارا، Backblaze B2، Wasabi و AWS S3. "
            "نشانی سرویس، نام باکت، کلید دسترسی و کلید محرمانه لازم است."
        ),
        "fields": ["endpoint", "bucket", "region", "access_key", "secret_key", "force_path_style"],
    },
    {
        "provider": ext.PROVIDER_WEBDAV,
        "label": "WebDAV (Nextcloud / ownCloud)",
        "note": (
            "نشانی پایهٔ WebDAV حساب خود را وارد کنید؛ در Nextcloud معمولاً "
            "https://example.com/remote.php/dav/files/<username> است. "
            "برای رمز عبور، «App Password» توصیه می‌شود."
        ),
        "fields": ["webdav_base_url", "webdav_username", "webdav_password"],
    },
]


def mask_secret(encrypted: str) -> str:
    """نمای ماسک‌شدهٔ اعتبارنامه؛ فقط چهار نویسهٔ آخر دیده می‌شود."""
    raw = decrypt_secret(encrypted or "")
    if not raw:
        return ""
    tail = raw[-4:] if len(raw) > 4 else raw
    return f"••••{tail}"


def catalog_payload() -> List[Dict[str, Any]]:
    return [dict(entry) for entry in PROVIDER_CATALOG]


async def get_row(db: AsyncSession, organization_id: int) -> Optional[Org_storage_targets]:
    result = await db.execute(
        select(Org_storage_targets)
        .where(Org_storage_targets.organization_id == int(organization_id))
        .order_by(Org_storage_targets.id.asc())
    )
    return result.scalars().first()


def tenant_prefix(row: Org_storage_targets) -> str:
    """پیشوند مسیر مخصوص همان سازمان (مرز مستأجر در سطح Storage)."""
    return ext.join_path(row.path_prefix or "vidara", f"org-{int(row.organization_id)}")


def build_config(row: Org_storage_targets) -> ext.TargetConfig:
    """ساخت پیکربندی رمزگشایی‌شده برای تماس با مقصد."""
    return ext.TargetConfig(
        provider=(row.provider or "").strip(),
        endpoint=(row.endpoint or "").strip(),
        bucket=(row.bucket or "").strip(),
        region=(row.region or "us-east-1").strip() or "us-east-1",
        path_prefix=(row.path_prefix or "").strip(),
        access_key=(row.access_key or "").strip(),
        secret_key=decrypt_secret(row.secret_key_enc or ""),
        force_path_style=bool(row.force_path_style if row.force_path_style is not None else True),
        webdav_base_url=(row.webdav_base_url or "").strip(),
        webdav_username=(row.webdav_username or "").strip(),
        webdav_password=decrypt_secret(row.webdav_password_enc or ""),
    )


def has_credentials(row: Org_storage_targets) -> bool:
    if (row.provider or "") == ext.PROVIDER_S3:
        return bool(
            (row.endpoint or "").strip()
            and (row.bucket or "").strip()
            and (row.access_key or "").strip()
            and (row.secret_key_enc or "").strip()
        )
    if (row.provider or "") == ext.PROVIDER_WEBDAV:
        return bool(
            (row.webdav_base_url or "").strip()
            and (row.webdav_username or "").strip()
            and (row.webdav_password_enc or "").strip()
        )
    return False


def is_active(row: Optional[Org_storage_targets]) -> bool:
    """مقصد قابل استفاده = تعریف‌شده، فعال و دارای اعتبارنامهٔ کامل."""
    return bool(row is not None and row.enabled and has_credentials(row))


def payload(row: Optional[Org_storage_targets]) -> Dict[str, Any]:
    """نمای امن تنظیمات برای فرانت؛ هیچ اعتبارنامهٔ خامی برنمی‌گردد."""
    if row is None:
        return {
            "configured": False,
            "provider": "",
            "display_name": "",
            "enabled": False,
            "endpoint": "",
            "bucket": "",
            "region": "us-east-1",
            "path_prefix": "vidara",
            "access_key": "",
            "secret_key_masked": "",
            "has_secret_key": False,
            "force_path_style": True,
            "webdav_base_url": "",
            "webdav_username": "",
            "webdav_password_masked": "",
            "has_webdav_password": False,
            "restore_retention_days": DEFAULT_RESTORE_RETENTION_DAYS,
            "tenant_prefix": "",
            "last_test_ok": False,
            "last_test_at": "",
            "last_test_message": "",
            "updated_by_name": "",
            "is_active": False,
        }
    return {
        "configured": True,
        "provider": row.provider or "",
        "display_name": row.display_name or "",
        "enabled": bool(row.enabled),
        "endpoint": row.endpoint or "",
        "bucket": row.bucket or "",
        "region": row.region or "us-east-1",
        "path_prefix": row.path_prefix or "vidara",
        "access_key": row.access_key or "",
        "secret_key_masked": mask_secret(row.secret_key_enc or ""),
        "has_secret_key": bool((row.secret_key_enc or "").strip()),
        "force_path_style": bool(
            row.force_path_style if row.force_path_style is not None else True
        ),
        "webdav_base_url": row.webdav_base_url or "",
        "webdav_username": row.webdav_username or "",
        "webdav_password_masked": mask_secret(row.webdav_password_enc or ""),
        "has_webdav_password": bool((row.webdav_password_enc or "").strip()),
        "restore_retention_days": int(
            row.restore_retention_days or DEFAULT_RESTORE_RETENTION_DAYS
        ),
        "tenant_prefix": tenant_prefix(row),
        "last_test_ok": bool(row.last_test_ok),
        "last_test_at": row.last_test_at or "",
        "last_test_message": row.last_test_message or "",
        "updated_by_name": row.updated_by_name or "",
        "is_active": is_active(row),
    }


def _clean(value: Any, limit: int = 400) -> str:
    return str(value or "").strip()[:limit]


async def save_target(
    db: AsyncSession,
    organization_id: int,
    *,
    data: Dict[str, Any],
    actor_name: str = "",
) -> Tuple[Org_storage_targets, List[str]]:
    """ذخیرهٔ تنظیمات مقصد؛ اعتبارنامهٔ خالی یعنی «بدون تغییر»."""
    row = await get_row(db, organization_id)
    changes: List[str] = []

    provider = _clean(data.get("provider"), 40) or (row.provider if row else "")
    if provider not in ext.ALL_PROVIDERS:
        raise ext.ExternalStorageError(
            "نوع مقصد ذخیره‌سازی نامعتبر است؛ «سرویس سازگار با S3» یا «WebDAV» را انتخاب کنید."
        )

    if row is None:
        row = Org_storage_targets(
            organization_id=int(organization_id),
            provider=provider,
            enabled=False,
            path_prefix="vidara",
            region="us-east-1",
            force_path_style=True,
            restore_retention_days=DEFAULT_RESTORE_RETENTION_DAYS,
            last_test_ok=False,
            last_test_at="",
            last_test_message="",
        )
        db.add(row)
        changes.append("مقصد ذخیره‌سازی خارجی برای نخستین بار تعریف شد")
    elif (row.provider or "") != provider:
        changes.append(f"نوع مقصد: {row.provider or '—'} ← {provider}")
    row.provider = provider

    text_fields = {
        "display_name": ("نام نمایشی", 120),
        "endpoint": ("نشانی سرویس", 300),
        "bucket": ("نام باکت", 200),
        "region": ("منطقه", 60),
        "path_prefix": ("پیشوند مسیر", 200),
        "access_key": ("کلید دسترسی", 200),
        "webdav_base_url": ("نشانی WebDAV", 400),
        "webdav_username": ("نام کاربری WebDAV", 200),
    }
    for field, (label, limit) in text_fields.items():
        if data.get(field) is None:
            continue
        new_value = _clean(data.get(field), limit)
        if field in ("endpoint", "webdav_base_url"):
            new_value = new_value.rstrip("/")
        if field == "path_prefix":
            new_value = new_value.strip("/") or "vidara"
        old_value = getattr(row, field, "") or ""
        if old_value != new_value:
            changes.append(f"{label} تغییر کرد")
        setattr(row, field, new_value)

    if data.get("secret_key"):
        row.secret_key_enc = encrypt_secret(_clean(data["secret_key"], 500))
        changes.append("کلید محرمانهٔ S3 به‌روزرسانی شد")
    if data.get("webdav_password"):
        row.webdav_password_enc = encrypt_secret(_clean(data["webdav_password"], 500))
        changes.append("رمز عبور WebDAV به‌روزرسانی شد")

    if data.get("force_path_style") is not None:
        row.force_path_style = bool(data["force_path_style"])
    if data.get("restore_retention_days") is not None:
        low, high = RESTORE_RETENTION_BOUNDS
        try:
            days = int(data["restore_retention_days"])
        except (TypeError, ValueError):
            days = DEFAULT_RESTORE_RETENTION_DAYS
        days = max(min(days, high), low)
        if int(row.restore_retention_days or DEFAULT_RESTORE_RETENTION_DAYS) != days:
            changes.append(f"مدت نگه‌داری نسخهٔ بازیابی‌شده: {days} روز")
        row.restore_retention_days = days

    if data.get("enabled") is not None:
        enabled = bool(data["enabled"])
        if enabled and not has_credentials(row):
            raise ext.ExternalStorageError(
                "برای فعال‌سازی مقصد، ابتدا اطلاعات اتصال و اعتبارنامهٔ آن را کامل ثبت کنید."
            )
        if bool(row.enabled) != enabled:
            changes.append("مقصد فعال شد" if enabled else "مقصد غیرفعال شد")
        row.enabled = enabled

    row.updated_by_name = (actor_name or "")[:120]
    await db.flush()
    return row, changes


def record_test_result(row: Org_storage_targets, ok: bool, message: str, when_iso: str) -> None:
    row.last_test_ok = bool(ok)
    row.last_test_message = (message or "")[:400]
    row.last_test_at = when_iso
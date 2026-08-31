"""روتر مدیریت پلتفرم «ویدارا - نسخه جلسات».

مدیر پلتفرم از همان صفحهٔ ورود سامانه وارد می‌شود (``POST /app-auth/login``) ولی
توکن آن نوع ``vidara_platform`` دارد و فقط همین مسیرها را می‌تواند ببیند؛ به هیچ
یک از مسیرهای فضای کاری (جلسات، رونویسی و …) دسترسی ندارد.

قابلیت‌ها:

* ساخت مدیر سازمان با نام/نام خانوادگی/موبایل — نام کاربری = موبایل، رمز رندوم
  که با پیامک ارسال می‌شود؛ تکمیل مشخصات در نخستین ورود اجباری است.
* فهرست همهٔ سازمان‌ها و مدیران آن‌ها.
* تغییر تنظیمات هر سازمان: ایمیل (SMTP)، پیامک، مدل‌های هوش مصنوعی (با تست
  اتصال) و مقصد استوریج خارجی.
* تغییر سقف مصرف هوش مصنوعی: دقیقهٔ رونویسی و سقف دلاری مدل زبانی، هم برای
  کل سازمان و هم برای کاربر مدیر آن سازمان.
* انتقال سازمان به سطل آشغال (غیرفعال‌سازی کامل دسترسی)، بازیابی از سطل آشغال،
  و پاک‌سازی کامل (داده‌ها + فایل‌های Storage) از سطل آشغال.
"""
from __future__ import annotations

import logging
import os
import secrets
from typing import Any, Dict, List, Optional

from core.config import settings as app_settings
from core.database import get_db
from dependencies.platform_admin import get_platform_admin
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_user_usage import Ai_user_quotas
from models.app_users import App_users
from models.audit_logs import Audit_logs
from models.org_ai_providers import Org_ai_providers
from models.organizations import Organizations
from schemas.storage import OSSBaseModel, ObjectRequest
from services import ai_providers
from services import ai_usage
from services import app_auth
from services import notify_channels as channels
from services import platform_admin
from services import storage_targets
from services.mgmt_core import AUDIO_BUCKET
from services.meeting_files import ATTACHMENTS_BUCKET
from services.storage import StorageService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/platform", tags=["platform"])

TRASH_CONFIRM = "حذف کامل"


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------


class PlatformOrgCreateIn(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=200)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    mobile: str


class PlatformNotifyIn(BaseModel):
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    smtp_enabled: Optional[bool] = None
    sms_api_key: Optional[str] = None
    sms_line_number: Optional[str] = None
    sms_enabled: Optional[bool] = None


class PlatformProviderIn(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    diarization: Optional[bool] = None
    auth_username: Optional[str] = None
    api_key: Optional[str] = None
    clear_api_key: Optional[bool] = None
    password: Optional[str] = None
    clear_password: Optional[bool] = None


class PlatformStorageIn(BaseModel):
    provider: str
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


class PlatformQuotasIn(BaseModel):
    org_stt_limit_minutes: Optional[int] = None
    org_llm_limit_cents: Optional[int] = None
    admin_stt_limit_minutes: Optional[int] = None
    admin_llm_limit_cents: Optional[int] = None


class PlatformTrashIn(BaseModel):
    confirm: str
    confirm_org_name: str


# ---------------------------------------------------------------------------
# ابزارها
# ---------------------------------------------------------------------------


def _bad(message: str):
    return app_auth.bad_request(message)


def _not_found(message: str):
    return app_auth.not_found(message)


async def _get_org(db: AsyncSession, org_id: int) -> Organizations:
    result = await db.execute(select(Organizations).where(Organizations.id == org_id))
    org = result.scalar_one_or_none()
    if org is None:
        raise _not_found("سازمان یافت نشد.")
    return org


async def _org_admin(db: AsyncSession, org_id: int) -> Optional[App_users]:
    """نخستین کاربر با نقش مدیر سازمان (به ترتیب ساخت)."""
    result = await db.execute(
        select(App_users)
        .where(
            App_users.organization_id == org_id,
            App_users.role == app_auth.ROLE_ADMIN,
        )
        .order_by(App_users.id.asc())
    )
    return result.scalars().first()


async def _audit(
    db: AsyncSession,
    org_id: int,
    actor: platform_admin.PlatformPrincipal,
    action: str,
    *,
    entity_type: str = "organization",
    entity_id: Optional[int] = None,
    detail: str = "",
) -> None:
    try:
        db.add(
            Audit_logs(
                organization_id=org_id,
                actor_user_id=actor.id,
                actor_name=actor.actor_name,
                actor_role="platform_admin",
                action=action,
                entity_type=entity_type,
                entity_id=entity_id,
                detail=detail[:900],
            )
        )
    except Exception as exc:  # pragma: no cover - محافظ عملیاتی
        logger.warning("ثبت Audit پلتفرم ناموفق بود: %s", exc)


def _org_card(org: Organizations, admin: Optional[App_users], quota: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": int(org.id),
        "name": org.name or "",
        "slug": org.slug or "",
        "status": org.status or "active",
        "created_at": org.created_at.isoformat() if org.created_at else "",
        "admin": (
            {
                "id": int(admin.id),
                "username": admin.username or "",
                "full_name": app_auth.full_name_of(admin.first_name, admin.last_name),
                "mobile": admin.mobile or "",
                "email": admin.email or "",
                "must_change_password": bool(admin.must_change_password),
                "status": admin.status or "active",
            }
            if admin is not None
            else None
        ),
        "quota": quota,
    }


async def _org_quota_card(db: AsyncSession, org: Organizations) -> Dict[str, Any]:
    admin = await _org_admin(db, int(org.id))
    admin_quota: Dict[str, Any] = {"user_id": None, "llm_limit_cents": None, "stt_limit_minutes": None}
    if admin is not None:
        row = await ai_usage.ensure_quota_row(db, int(org.id), f"{app_auth.USER_PREFIX}{int(admin.id)}")
        admin_quota = {
            "user_id": f"{app_auth.USER_PREFIX}{int(admin.id)}",
            "llm_limit_cents": int(row.llm_limit_cents) if row.llm_limit_cents is not None else None,
            "stt_limit_minutes": int(row.stt_limit_minutes) if row.stt_limit_minutes is not None else None,
            "defaults": {
                "llm_limit_cents": ai_usage.DEFAULT_LLM_BUDGET_CENTS,
                "stt_limit_minutes": ai_usage.DEFAULT_STT_BUDGET_MINUTES,
            },
        }
    return {
        "org_stt_limit_minutes": int(org.monthly_ai_minutes_quota or 0) or None,
        "org_ai_minutes_used": int(org.ai_minutes_used or 0),
        "quota_period": org.quota_period or "",
        "org_llm_limit_cents": int(org.ai_llm_limit_cents) if org.ai_llm_limit_cents is not None else None,
        "admin_user": admin_quota,
    }


def _sms_welcome_message(first_name: str, last_name: str, org_name: str, username: str, password: str) -> str:
    base_url = os.environ.get("APP_PUBLIC_URL") or app_settings.backend_url
    return (
        f"{first_name} {last_name} عزیز، حساب مدیر سازمان «{org_name}» در سامانهٔ "
        f"«ویدارا - نسخه جلسات» برای شما ساخته شد.\n"
        f"نام کاربری: {username}\nرمز عبور: {password}\n"
        f"پس از نخستین ورود، رمز عبور را تغییر دهید و کد ملی و ایمیل خود را تکمیل کنید.\n"
        f"نشانی ورود: {base_url}\nلغو ۱۱"
    )


def _sms_reference_id() -> str:
    """شناسهٔ پیگیری یکتای پیامک (پنل فقط مقدار عددی می‌پذیرد)."""
    import time

    return str(int(time.time() * 1000))


# ---------------------------------------------------------------------------
# Endpointها
# ---------------------------------------------------------------------------


@router.get("/me")
async def platform_me(
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    admin = await platform_admin.load_admin(db, principal.admin_id)
    return {"user": platform_admin.admin_payload(admin)}


@router.post("/orgs")
async def create_org(
    data: PlatformOrgCreateIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ساخت سازمان + مدیر آن: نام کاربری = موبایل، رمز رندوم با پیامک."""
    first_name = data.first_name.strip()
    last_name = data.last_name.strip()
    mobile = app_auth.normalize_mobile(data.mobile)
    org_name = data.organization_name.strip()

    # جلوگیری از ساخت سازمانی که مدیرش همین موبایل را در سازمان فعال دیگری دارد؟
    # خیر — یک شخص می‌تواند مدیر چند سازمان باشد؛ فقط یکتایی داخل سازمان ملاک است.

    organization = await app_auth.create_organization(db, org_name)
    password = secrets.token_hex(5)  # ۱۰ نویسهٔ تصادفی قابل تایپ
    app_user = await app_auth.create_app_user(
        db,
        organization_id=int(organization.id),
        username=mobile,
        password=password,
        first_name=first_name,
        last_name=last_name,
        mobile=mobile,
        email="",
        national_id="",
        gender="",
        role=app_auth.ROLE_ADMIN,
        must_change_password=True,
    )
    settings_row = await channels.get_or_create_settings(db, int(organization.id))
    await ai_providers.ensure_defaults(db, int(organization.id))

    # ارسال رمز با پیامک (بهترین تلاش — شکست آن ساخت سازمان را متوقف نمی‌کند)
    sms_result: Dict[str, Any] = {"ok": False, "error": "", "provider_message_id": ""}
    try:
        result = await channels.send_sms(
            settings_row,
            receptor=mobile,
            message=_sms_welcome_message(first_name, last_name, org_name, mobile, password),
            client_reference_id=_sms_reference_id(),
        )
        sms_result = {
            "ok": bool(result.ok),
            "error": result.error or "",
            "provider_message_id": result.provider_message_id or "",
        }
        if not result.ok:
            logger.warning("پیامک رمز مدیر سازمان %s به %s ناموفق بود: %s", organization.id, mobile, result.error)
        else:
            logger.info(
                "پیامک رمز مدیر سازمان %s به %s ارسال شد (messageid=%s)",
                organization.id, mobile, result.provider_message_id,
            )
    except Exception:  # pragma: no cover - پیامک نباید ساخت را متوقف کند
        logger.warning("ارسال پیامک رمز مدیر سازمان %s ناموفق بود", organization.id, exc_info=True)

    await _audit(
        db,
        int(organization.id),
        principal,
        "platform.org_created",
        entity_id=int(organization.id),
        detail=f"سازمان «{org_name}» و مدیر آن «{first_name} {last_name}» ({mobile}) ساخته شد",
    )
    await db.commit()

    membership = await app_auth.membership_of(db, app_user)
    return {
        "organization": {
            "id": int(organization.id),
            "name": organization.name or "",
            "slug": organization.slug or "",
            "status": organization.status or "active",
        },
        "admin": app_auth.user_payload(app_user, int(membership.id) if membership else None),
        "default_credentials": {"username": mobile, "password": password, "is_default_password": False},
        "sms": sms_result,
    }


@router.post("/orgs/{org_id}/resend-admin-sms")
async def resend_admin_sms(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تولید رمز جدید برای مدیر سازمان و ارسال دوبارهٔ آن با پیامک.

    برای حالتی که پیامک نخست به هر دلیل (تأخیر اپراتور و …) نرسیده باشد؛ رمز
    قبلی غیرقابل بازیابی است (هش‌شده)، پس رمز تازه ساخته و ارسال می‌شود و پرچم
    «تکمیل مشخصات در نخستین ورود» دوباره فعال می‌گردد.
    """
    org = await _get_org(db, org_id)
    admin = await _org_admin(db, org_id)
    if admin is None:
        raise _not_found("مدیر سازمان یافت نشد.")

    password = secrets.token_hex(5)
    admin.password_hash = app_auth.hash_password(password)
    admin.must_change_password = True
    settings_row = await channels.get_or_create_settings(db, org_id)

    sms_result: Dict[str, Any] = {"ok": False, "error": "", "provider_message_id": ""}
    try:
        result = await channels.send_sms(
            settings_row,
            receptor=admin.mobile or "",
            message=_sms_welcome_message(
                admin.first_name or "", admin.last_name or "", org.name or "",
                admin.username or admin.mobile or "", password,
            ),
            client_reference_id=_sms_reference_id(),
        )
        sms_result = {
            "ok": bool(result.ok),
            "error": result.error or "",
            "provider_message_id": result.provider_message_id or "",
        }
        if not result.ok:
            logger.warning("ارسال دوبارهٔ رمز مدیر سازمان %s به %s ناموفق بود: %s", org_id, admin.mobile, result.error)
    except Exception:  # pragma: no cover - محافظ عملیاتی
        logger.warning("ارسال دوبارهٔ رمز مدیر سازمان %s ناموفق بود", org_id, exc_info=True)

    await _audit(
        db, org_id, principal, "platform.org_admin_sms_resent", entity_id=org_id,
        detail=f"رمز جدید برای مدیر «{admin.first_name} {admin.last_name}» ({admin.mobile}) ساخته و ارسال شد (ok={sms_result['ok']})",
    )
    await db.commit()
    return {
        "success": bool(sms_result["ok"]),
        "sms": sms_result,
        "default_credentials": {"username": admin.username or admin.mobile or "", "password": password},
    }


@router.get("/orgs")
async def list_orgs(
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست همهٔ سازمان‌ها (فعال و سطل‌آشغالی) همراه مدیر و سهمیه‌ها."""
    result = await db.execute(select(Organizations).order_by(Organizations.id.desc()))
    orgs = list(result.scalars().all())
    items: List[Dict[str, Any]] = []
    for org in orgs:
        quota = await _org_quota_card(db, org)
        admin = await _org_admin(db, int(org.id))
        items.append(_org_card(org, admin, quota))
    await db.commit()
    return {"items": items, "total": len(items)}


@router.get("/trash")
async def list_trash(
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    result = await db.execute(
        select(Organizations).where(Organizations.status == "trashed").order_by(Organizations.id.desc())
    )
    orgs = list(result.scalars().all())
    items: List[Dict[str, Any]] = []
    for org in orgs:
        quota = await _org_quota_card(db, org)
        admin = await _org_admin(db, int(org.id))
        items.append(_org_card(org, admin, quota))
    await db.commit()
    return {"items": items, "total": len(items)}


@router.get("/orgs/{org_id}/overview")
async def org_overview(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """نمای کامل تنظیمات یک سازمان برای دیالوگ مدیریت پلتفرم."""
    org = await _get_org(db, org_id)
    admin = await _org_admin(db, org_id)
    notify_row = await channels.get_or_create_settings(db, org_id)
    provider_rows = await ai_providers.ensure_defaults(db, org_id)
    storage_row = await storage_targets.get_row(db, org_id)
    chain: Dict[str, Any] = {}
    for kind in ai_providers.ALL_KINDS:
        rows = await ai_providers.enabled_providers(db, org_id, kind)
        chain[kind] = [
            {
                "priority": int(row.priority or 99),
                "provider_key": row.provider_key or "",
                "display_name": row.display_name or row.provider_key or "",
                "diarization": bool(row.diarization),
                "model": row.model or "",
            }
            for row in rows
        ]
    await db.commit()
    return {
        "organization": _org_card(org, admin, await _org_quota_card(db, org)),
        "notify": channels.settings_payload(notify_row),
        "ai_providers": [ai_providers.provider_payload(row) for row in provider_rows],
        "ai_chain": {"stt": chain[ai_providers.KIND_STT], "llm": chain[ai_providers.KIND_LLM]},
        "storage": storage_targets.payload(storage_row),
    }


@router.patch("/orgs/{org_id}/notify")
async def update_notify(
    org_id: int,
    data: PlatformNotifyIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _get_org(db, org_id)
    row = await channels.get_or_create_settings(db, org_id)

    if data.smtp_host is not None:
        row.smtp_host = data.smtp_host.strip()
    if data.smtp_port is not None:
        if not 1 <= int(data.smtp_port) <= 65535:
            raise _bad("پورت SMTP باید بین ۱ تا ۶۵۵۳۵ باشد.")
        row.smtp_port = int(data.smtp_port)
    if data.smtp_username is not None:
        row.smtp_username = data.smtp_username.strip()
    if data.smtp_password:
        row.smtp_password_enc = app_auth.encrypt_secret(data.smtp_password)
    if data.smtp_use_tls is not None:
        row.smtp_use_tls = bool(data.smtp_use_tls)
    if data.smtp_use_ssl is not None:
        row.smtp_use_ssl = bool(data.smtp_use_ssl)
    if data.smtp_from_email is not None:
        row.smtp_from_email = app_auth.normalize_email(data.smtp_from_email) if data.smtp_from_email else ""
    if data.smtp_from_name is not None:
        row.smtp_from_name = data.smtp_from_name.strip()
    if data.smtp_enabled is not None:
        if data.smtp_enabled and not (row.smtp_host and row.smtp_from_email):
            raise _bad("برای فعال‌سازی ایمیل، میزبان SMTP و ایمیل فرستنده الزامی است.")
        row.smtp_enabled = bool(data.smtp_enabled)

    if data.sms_api_key:
        row.sms_api_key_enc = app_auth.encrypt_secret(data.sms_api_key.strip())
    if data.sms_line_number is not None:
        row.sms_line_number = app_auth.to_latin_digits(data.sms_line_number.strip())
    if data.sms_enabled is not None:
        if data.sms_enabled and not (row.sms_api_key_enc and row.sms_line_number):
            raise _bad("برای فعال‌سازی پیامک، کلید API پیامک و شمارهٔ خط الزامی است.")
        row.sms_enabled = bool(data.sms_enabled)

    await _audit(
        db, org_id, principal, "platform.org_notify_updated", entity_id=org_id,
        detail="تنظیمات ایمیل/پیامک سازمان توسط مدیر پلتفرم تغییر کرد",
    )
    payload = channels.settings_payload(row)
    await db.commit()
    return payload


@router.get("/orgs/{org_id}/ai-providers")
async def list_ai_providers(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _get_org(db, org_id)
    rows = await ai_providers.ensure_defaults(db, org_id)
    await db.commit()
    return {"providers": [ai_providers.provider_payload(row) for row in rows]}


@router.patch("/orgs/{org_id}/ai-providers/{provider_id}")
async def update_ai_provider(
    org_id: int,
    provider_id: int,
    data: PlatformProviderIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _get_org(db, org_id)
    result = await db.execute(
        select(Org_ai_providers).where(
            Org_ai_providers.id == provider_id,
            Org_ai_providers.organization_id == org_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        raise _not_found("تأمین‌کنندهٔ هوش مصنوعی یافت نشد.")
    ai_providers.apply_update(row, data.model_dump())
    await _audit(
        db, org_id, principal, "platform.org_ai_updated", entity_id=provider_id,
        detail=f"تنظیمات تأمین‌کنندهٔ {row.provider_key} ({row.kind}) توسط مدیر پلتفرم تغییر کرد",
    )
    await db.commit()
    return ai_providers.provider_payload(row)


@router.post("/orgs/{org_id}/ai-providers/{provider_id}/test")
async def test_ai_provider(
    org_id: int,
    provider_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _get_org(db, org_id)
    result = await db.execute(
        select(Org_ai_providers).where(
            Org_ai_providers.id == provider_id,
            Org_ai_providers.organization_id == org_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        raise _not_found("تأمین‌کنندهٔ هوش مصنوعی یافت نشد.")
    try:
        ok, message = await ai_providers.test_provider(row)
    except Exception as exc:  # pragma: no cover - محافظ عملیاتی
        ok, message = False, f"خطای اجرای تست: {exc}"
    ai_providers.record_test_result(row, ok, message)
    await _audit(
        db, org_id, principal, "platform.org_ai_tested", entity_id=provider_id,
        detail=f"تست اتصال {row.provider_key}: {'موفق' if ok else 'ناموفق'} — {message[:200]}",
    )
    await db.commit()
    return {"ok": ok, "message": message, "provider": ai_providers.provider_payload(row)}


@router.put("/orgs/{org_id}/storage")
async def update_storage(
    org_id: int,
    data: PlatformStorageIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    await _get_org(db, org_id)
    row, _changes = await storage_targets.save_target(
        db, org_id, data=data.model_dump(), actor_name=principal.actor_name
    )
    await _audit(
        db, org_id, principal, "platform.org_storage_updated", entity_id=org_id,
        detail="مقصد استوریج خارجی سازمان توسط مدیر پلتفرم تغییر کرد",
    )
    await db.commit()
    return storage_targets.payload(row)


@router.get("/orgs/{org_id}/quotas")
async def read_quotas(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    org = await _get_org(db, org_id)
    card = await _org_quota_card(db, org)
    await db.commit()
    return card


@router.patch("/orgs/{org_id}/quotas")
async def update_quotas(
    org_id: int,
    data: PlatformQuotasIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    org = await _get_org(db, org_id)

    if data.org_stt_limit_minutes is not None:
        value = int(data.org_stt_limit_minutes)
        if value < 1:
            raise _bad("سقف دقیقهٔ رونویسی سازمان باید دست‌کم ۱ باشد.")
        org.monthly_ai_minutes_quota = value
    if data.org_llm_limit_cents is not None:
        value = int(data.org_llm_limit_cents)
        if value < 0:
            raise _bad("سقف دلاری سازمان نمی‌تواند منفی باشد.")
        org.ai_llm_limit_cents = value if value > 0 else None  # صفر = بدون سقف

    admin = await _org_admin(db, org_id)
    if admin is not None and (
        data.admin_stt_limit_minutes is not None or data.admin_llm_limit_cents is not None
    ):
        row = await ai_usage.ensure_quota_row(db, org_id, f"{app_auth.USER_PREFIX}{int(admin.id)}")
        if data.admin_stt_limit_minutes is not None:
            value = int(data.admin_stt_limit_minutes)
            if value < 0:
                raise _bad("سقف دقیقهٔ رونویسی مدیر نمی‌تواند منفی باشد.")
            row.stt_limit_minutes = value if value > 0 else None
        if data.admin_llm_limit_cents is not None:
            value = int(data.admin_llm_limit_cents)
            if value < 0:
                raise _bad("سقف دلاری مدیر نمی‌تواند منفی باشد.")
            row.llm_limit_cents = value if value > 0 else None

    await _audit(
        db, org_id, principal, "platform.org_quotas_updated", entity_id=org_id,
        detail=f"سقف‌های AI: org_stt={data.org_stt_limit_minutes}, org_llm={data.org_llm_limit_cents}, "
        f"admin_stt={data.admin_stt_limit_minutes}, admin_llm={data.admin_llm_limit_cents}",
    )
    card = await _org_quota_card(db, org)
    await db.commit()
    return card


@router.post("/orgs/{org_id}/trash")
async def trash_org(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """انتقال سازمان به سطل آشغال: همهٔ دسترسی‌های اعضا فوراً قطع می‌شود."""
    org = await _get_org(db, org_id)
    if (org.status or "active") == "trashed":
        raise app_auth.conflict("این سازمان از قبل در سطل آشغال است.")
    org.status = "trashed"
    await _audit(
        db, org_id, principal, "platform.org_trashed", entity_id=org_id,
        detail=f"سازمان «{org.name}» به سطل آشغال منتقل شد",
    )
    await db.commit()
    return {"success": True, "status": "trashed", "id": org_id, "name": org.name}


@router.post("/trash/{org_id}/restore")
async def restore_org(
    org_id: int,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    org = await _get_org(db, org_id)
    if (org.status or "active") != "trashed":
        raise app_auth.conflict("این سازمان در سطل آشغال نیست.")
    org.status = "active"
    await _audit(
        db, org_id, principal, "platform.org_restored", entity_id=org_id,
        detail=f"سازمان «{org.name}» از سطل آشغال بازیابی شد",
    )
    await db.commit()
    return {"success": True, "status": "active", "id": org_id, "name": org.name}


@router.delete("/trash/{org_id}")
async def purge_org(
    org_id: int,
    data: PlatformTrashIn,
    principal: platform_admin.PlatformPrincipal = Depends(get_platform_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """پاک‌سازی کامل سازمان از سطل آشغال: داده‌ها + فایل‌های Storage (بازگشت‌ناپذیر)."""
    org = await _get_org(db, org_id)
    if (org.status or "active") != "trashed":
        raise app_auth.conflict("برای پاک‌سازی کامل، سازمان باید ابتدا در سطل آشغال باشد.")

    if (data.confirm or "").strip() != TRASH_CONFIRM:
        raise _bad("برای تأیید، عبارت «حذف کامل» را دقیقاً وارد کنید.")
    if (data.confirm_org_name or "").strip() != (org.name or "").strip():
        raise _bad("نام سازمان واردشده با نام واقعی سازمان یکسان نیست.")

    from routers.app_auth import ORG_DELETION_TABLES

    org_name = org.name or ""

    # ۱) فایل‌های Storage (بهترین تلاش؛ شکست حذف فایل، پاک‌سازی داده را متوقف نمی‌کند)
    storage = StorageService()
    objects_removed = 0
    for bucket in (AUDIO_BUCKET, ATTACHMENTS_BUCKET):
        try:
            listed = await storage.list_objects(OSSBaseModel(bucket_name=bucket), prefix=f"org-{org_id}/")
            for item in listed.objects:
                try:
                    await storage.delete_object(
                        ObjectRequest(bucket_name=bucket, object_key=item.object_key)
                    )
                    objects_removed += 1
                except Exception as exc:  # pragma: no cover - بهترین تلاش
                    logger.warning("حذف شیء %s/%s ناموفق بود: %s", bucket, item.object_key, exc)
        except Exception as exc:  # pragma: no cover - بهترین تلاش
            logger.warning("فهرست/حذف اشیای باکت %s برای سازمان %s ناموفق بود: %s", bucket, org_id, exc)

    # ۲) رکوردهای پایگاه داده با همان ترتیب استاندارد حذف سازمان
    removed: Dict[str, int] = {}
    total = 0
    for label, model in ORG_DELETION_TABLES:
        result = await db.execute(delete(model).where(model.organization_id == org_id))
        count = int(result.rowcount or 0)
        removed[label] = count
        total += count
    org_del = await db.execute(delete(Organizations).where(Organizations.id == org_id))
    total += int(org_del.rowcount or 0)

    await db.commit()
    logger.info(
        "پاک‌سازی کامل سازمان %s «%s» توسط مدیر پلتفرم: %s رکورد، %s شیء",
        org_id, org_name, total, objects_removed,
    )
    return {
        "success": True,
        "id": org_id,
        "name": org_name,
        "removed": removed,
        "total_rows": total,
        "storage_objects_removed": objects_removed,
    }

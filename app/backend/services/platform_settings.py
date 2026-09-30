"""تنظیمات سراسری پلتفرم و قالب‌های متن قابل‌ویرایش.

قالب پیامک یادآوری فعال‌سازی را مدیر پلتفرم ویرایش می‌کند؛ متن ذخیره‌شده
می‌تواند شامل جای‌نگهدارها باشد که هنگام ارسال با مقدار واقعی هر گیرنده پر
می‌شوند.

نکتهٔ امنیتی/پایداری: جانشانی جای‌نگهدارها با ``str.format`` انجام نمی‌شود، چون
هر آکولاد سرگردان در متن دلخواه کاربر باعث ``KeyError``/``ValueError`` در زمان
ارسال پیامک می‌شد. فقط توکن‌های شناخته‌شده و به‌صورت regex جانشین می‌شوند.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any, Dict, List, Optional

from core.config import settings as app_settings
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.platform_settings import Platform_settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# کلیدهای تنظیمات سراسری
# ---------------------------------------------------------------------------

ACTIVATION_REMINDER_KEY = "activation_reminder_sms_template"

#: عبارت «لغو ۱۱» الزامی است؛ بدون آن اپراتور پیامک را فیلتر می‌کند.
SMS_OPTOUT_LINE = "لغو ۱۱"

SUPPORT_PHONE_DEFAULT = "۰۲۱۴۱۰۲۱۰۰۰"

DEFAULT_ACTIVATION_REMINDER_TEMPLATE = (
    "{greeting}\n"
    "سلام\n"
    "شما در سامانه ویدارا نسخه جلسات ثبت نام شده اید اما تا کنون اقدام به ورود و "
    "فعال سازی اکانت خود ننموده اید\n"
    "برای استفاده رایگان از این سرویس به آدرس\n"
    "{url}\n"
    "مراجعه کرده و با نام کاربری {username} و کلمه عبور {password} وارد سامانه شوید.\n"
    "در صورت نیاز به اطلاعات بیشتر می‌توانید با شماره تماس {support_phone} داخلی ۳۳۷ "
    "تماس حاصل فرمایید\n"
    f"{SMS_OPTOUT_LINE}"
)

#: فهرست جای‌نگهدارها برای نمایش در ویرایشگر پنل مدیریت.
PLACEHOLDERS: List[Dict[str, str]] = [
    {
        "token": "{greeting}",
        "label": "خطاب کامل",
        "description": "«جناب آقای»/«سرکار خانم» به‌همراه نام و نام خانوادگی",
        "sample": "جناب آقای ابراهیم خرم‌نژاد",
    },
    {
        "token": "{name}",
        "label": "نام و نام خانوادگی",
        "description": "نام کامل مدیر بدون خطاب",
        "sample": "ابراهیم خرم‌نژاد",
    },
    {"token": "{first_name}", "label": "نام", "description": "نام کوچک", "sample": "ابراهیم"},
    {"token": "{last_name}", "label": "نام خانوادگی", "description": "نام خانوادگی", "sample": "خرم‌نژاد"},
    {
        "token": "{username}",
        "label": "نام کاربری",
        "description": "نام کاربری ورود مدیر",
        "sample": "09121234567",
    },
    {
        "token": "{password}",
        "label": "کلمه عبور",
        "description": "رمز تازه‌ای که هنگام ارسال ساخته می‌شود",
        "sample": "a1b2c3d4e5",
    },
    {
        "token": "{url}",
        "label": "نشانی سامانه",
        "description": "آدرس ورود سامانه (از APP_PUBLIC_URL)",
        "sample": "https://vidara-meeting.ir/",
        "type": "url",
    },
    {
        "token": "{org}",
        "label": "نام سازمان",
        "description": "نام سازمانی که مدیر به آن تعلق دارد",
        "sample": "شرکت نمونه",
    },
    {
        "token": "{support_phone}",
        "label": "تلفن پشتیبانی",
        "description": "شمارهٔ تماس پشتیبانی",
        "sample": SUPPORT_PHONE_DEFAULT,
    },
]

#: سقف طول متن قالب (پیامک اپراتور سقف دارد و متن بلند چند پیامک می‌شود).
MAX_TEMPLATE_LENGTH = 2000

_TOKEN_NAMES = [item["token"][1:-1] for item in PLACEHOLDERS]
_TOKEN_RE = re.compile(r"\{(" + "|".join(re.escape(name) for name in _TOKEN_NAMES) + r")\}")


# ---------------------------------------------------------------------------
# مقدارها
# ---------------------------------------------------------------------------


def public_base_url() -> str:
    """نشانی عمومی سامانه با اسکیم و اسلش پایانی.

    ترتیب اولویت همان رفتار قبلی است (``APP_PUBLIC_URL`` سپس ``backend_url``)
    ولی خروجی نرمال می‌شود تا در متن پیامک همیشه یک URL معتبر دیده شود.
    """
    raw = (os.environ.get("APP_PUBLIC_URL") or app_settings.backend_url or "").strip()
    if not raw:
        return ""
    if not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw if raw.endswith("/") else raw + "/"


def sample_context() -> Dict[str, str]:
    """مقادیر نمونهٔ جای‌نگهدارها برای پیش‌نمایش در پنل مدیریت."""
    context: Dict[str, str] = {}
    for item in PLACEHOLDERS:
        name = item["token"][1:-1]
        if name == "url":
            context[name] = public_base_url() or item["sample"]
        else:
            context[name] = item["sample"]
    return context


def build_context(
    *,
    first_name: str = "",
    last_name: str = "",
    gender: str = "",
    username: str = "",
    password: str = "",
    organization_name: str = "",
) -> Dict[str, str]:
    """مقادیر واقعی جای‌نگهدارها برای یک گیرندهٔ مشخص."""
    # import تنبل: جلوگیری از هر چرخهٔ واردکردنی در بارگذاری سرویس‌ها
    from services import app_auth

    full_name = app_auth.full_name_of(first_name, last_name).strip()
    salutation = app_auth.GENDER_SALUTATION.get((gender or "").strip().lower(), "")
    if salutation and full_name:
        greeting = f"{salutation} {full_name}"
    elif full_name:
        greeting = f"کاربر گرامی {full_name}"
    else:
        greeting = salutation or "کاربر گرامی"

    return {
        "greeting": greeting,
        "name": full_name,
        "first_name": (first_name or "").strip(),
        "last_name": (last_name or "").strip(),
        "username": (username or "").strip(),
        "password": password or "",
        "url": public_base_url() or PLACEHOLDERS[6]["sample"],
        "org": (organization_name or "").strip(),
        "support_phone": SUPPORT_PHONE_DEFAULT,
    }


def render_template(template: str, context: Dict[str, str]) -> str:
    """جانشانی امن جای‌نگهدارهای شناخته‌شده.

    توکن‌های ناشناخته دست‌نخورده می‌مانند تا متن کاربر هرگز باعث خطا نشود.
    """

    def _replace(match: "re.Match[str]") -> str:
        return str(context.get(match.group(1), match.group(0)))

    return _TOKEN_RE.sub(_replace, template or "")


def normalize_template(template: str) -> str:
    """یکدست‌سازی متن قالب: حذف فاصله‌های انتهایی خطوط و خط‌های خالی تکراری."""
    lines = [line.rstrip() for line in (template or "").replace("\r\n", "\n").split("\n")]
    cleaned: List[str] = []
    for line in lines:
        if not line and cleaned and not cleaned[-1]:
            continue
        cleaned.append(line)
    return "\n".join(cleaned).strip()


# ---------------------------------------------------------------------------
# دسترسی به جدول تنظیمات
# ---------------------------------------------------------------------------


async def get_setting(db: AsyncSession, key: str) -> Optional[str]:
    """مقدار یک کلید تنظیمات سراسری؛ ``None`` اگر تعریف نشده باشد."""
    result = await db.execute(select(Platform_settings).where(Platform_settings.key == key))
    row = result.scalars().first()
    if row is None or row.value is None:
        return None
    return str(row.value)


async def set_setting(db: AsyncSession, key: str, value: Optional[str]) -> None:
    """ثبت/به‌روزرسانی یک کلید تنظیمات سراسری (بدون commit).

    ``value=None`` یعنی حذف مقدار و بازگشت به پیش‌فرض؛ در این حالت ردیف هم پاک
    می‌شود تا «بازگشت به پیش‌فرض» هیچ ردیف خالی‌ای در جدول باقی نگذارد.
    """
    result = await db.execute(select(Platform_settings).where(Platform_settings.key == key))
    row = result.scalars().first()
    if row is None:
        if value is None:
            return
        db.add(Platform_settings(key=key, value=value))
    elif value is None:
        await db.delete(row)
    else:
        row.value = value
    await db.flush()


async def get_activation_reminder_template(db: AsyncSession) -> str:
    """قالب فعال پیامک یادآوری فعال‌سازی (ذخیره‌شده یا پیش‌فرض کد)."""
    try:
        stored = await get_setting(db, ACTIVATION_REMINDER_KEY)
    except Exception as exc:  # pragma: no cover - نبود جدول نباید ارسال را بشکند
        logger.warning("خواندن قالب یادآوری فعال‌سازی ناموفق بود: %s", exc)
        return DEFAULT_ACTIVATION_REMINDER_TEMPLATE
    if stored is None or not stored.strip():
        return DEFAULT_ACTIVATION_REMINDER_TEMPLATE
    return stored


def render_activation_reminder(template: str, **kwargs: Any) -> str:
    """ساخت متن نهایی پیامک یادآوری از قالب به‌همراه مقادیر واقعی."""
    return render_template(template, build_context(**kwargs))


# ---------------------------------------------------------------------------
# نگهداری فایل‌های مدیا (تنظیم سراسری مدیر سامانه)
# ---------------------------------------------------------------------------

MEDIA_RETENTION_DAYS_KEY = "media_retention_days"
MEDIA_RETENTION_AUTO_KEY = "media_retention_auto"
MEDIA_RETENTION_ORG_OVERRIDE_KEY = "media_retention_allow_org_override"

#: مدت پیش‌فرض نگهداری مدیا (روز) — همان مقدار پیشین سامانه.
DEFAULT_MEDIA_RETENTION_DAYS = 90

#: کران‌های مجاز مدت نگهداری: دست‌کم یک روز و دست‌اکثر ده سال.
MEDIA_RETENTION_BOUNDS = (1, 3650)


def clamp_retention_days(value: Any) -> Optional[int]:
    """تبدیل ورودی به عدد صحیح در بازهٔ مجاز؛ ``None`` اگر نامعتبر باشد."""
    if value is None or isinstance(value, bool):
        return None
    try:
        days = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    low, high = MEDIA_RETENTION_BOUNDS
    return max(low, min(high, days))


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


async def get_media_retention(db: AsyncSession) -> Dict[str, Any]:
    """تنظیم فعال نگهداری مدیا به‌همراه پیش‌فرض‌ها و وضعیت سفارشی‌بودن."""
    stored_days = await get_setting(db, MEDIA_RETENTION_DAYS_KEY)
    days = clamp_retention_days(stored_days)
    return {
        "days": days if days is not None else DEFAULT_MEDIA_RETENTION_DAYS,
        "default_days": DEFAULT_MEDIA_RETENTION_DAYS,
        "is_custom": days is not None,
        # اجرای خودکار به‌صورت پیش‌فرض خاموش است تا حذف ناخواسته رخ ندهد.
        "auto": _as_bool(await get_setting(db, MEDIA_RETENTION_AUTO_KEY), False),
        # اگر روشن باشد، مقداری که مدیر سازمان در تنظیمات خودش ثبت کرده اولویت دارد.
        "allow_org_override": _as_bool(
            await get_setting(db, MEDIA_RETENTION_ORG_OVERRIDE_KEY), True
        ),
        "bounds": {"min": MEDIA_RETENTION_BOUNDS[0], "max": MEDIA_RETENTION_BOUNDS[1]},
    }


async def set_media_retention(
    db: AsyncSession,
    *,
    days: Optional[int] = None,
    auto: Optional[bool] = None,
    allow_org_override: Optional[bool] = None,
    reset_days: bool = False,
) -> Dict[str, Any]:
    """ثبت تنظیم نگهداری مدیا (بدون commit)."""
    if reset_days:
        await set_setting(db, MEDIA_RETENTION_DAYS_KEY, None)
    elif days is not None:
        clamped = clamp_retention_days(days)
        if clamped is None:
            raise ValueError("مدت نگهداری مدیا باید یک عدد صحیح باشد.")
        await set_setting(db, MEDIA_RETENTION_DAYS_KEY, str(clamped))
    if auto is not None:
        await set_setting(db, MEDIA_RETENTION_AUTO_KEY, "1" if auto else "0")
    if allow_org_override is not None:
        await set_setting(db, MEDIA_RETENTION_ORG_OVERRIDE_KEY, "1" if allow_org_override else "0")
    return await get_media_retention(db)


def resolve_retention_days(settings: Dict[str, Any], org_days: Any) -> int:
    """مدت نگهداری مؤثر یک سازمان: مقدار سازمان (در صورت اجازه) وگرنه مقدار سراسری."""
    if settings.get("allow_org_override", True):
        org_value = clamp_retention_days(org_days)
        if org_value is not None:
            return org_value
    return int(settings.get("days") or DEFAULT_MEDIA_RETENTION_DAYS)


async def effective_media_retention_days(db: AsyncSession, organization: Any) -> int:
    """مدت نگهداری مؤثر برای یک سازمان مشخص (برای نمایش در پنل‌ها)."""
    try:
        settings = await get_media_retention(db)
    except Exception as exc:  # pragma: no cover - نبود جدول نباید صفحه را بشکند
        logger.warning("خواندن تنظیم نگهداری مدیا ناموفق بود: %s", exc)
        settings = {"days": DEFAULT_MEDIA_RETENTION_DAYS, "allow_org_override": True}
    return resolve_retention_days(settings, getattr(organization, "audio_retention_days", None))

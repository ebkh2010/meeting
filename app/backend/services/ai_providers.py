"""تنظیمات و اجرای تأمین‌کنندگان هوش مصنوعی در سطح هر سازمان (مستأجر).

قواعد کلیدی این ماژول:

* **مرز مستأجر**: هر ردیف تنظیمات با ``organization_id`` نگه‌داری می‌شود؛ هیچ
  سازمانی تنظیمات سازمان دیگر را نمی‌بیند و کلید API میان مستأجرها مشترک نیست.
* **محرمانگی کلید**: کلید/رمز فقط رمزنگاری‌شده ذخیره می‌شود و هرگز به فرانت‌اند
  بازنمی‌گردد؛ فقط نمای ماسک‌شده (``••••1234``) نمایش داده می‌شود.
* **اولویت و fallback**: تأمین‌کنندگان فعال به ترتیب ``priority`` امتحان می‌شوند؛
  با خطا یا پاسخ نامعتبر، تأمین‌کنندهٔ بعدی امتحان می‌شود و همهٔ تلاش‌ها
  (موفق/ناموفق) برای ثبت در لاگ و Audit برگردانده می‌شود.
* **تنها تأمین‌کنندگان قابل آزمون**: فقط سرویس‌هایی فهرست شده‌اند که قرارداد
  رسمی و قابل فراخوانی دارند (سرویس «حرف» و سه سرویس سازگار با OpenAI).

قرارداد سرویس «حرف» دقیقاً از مستند رسمی پیروی می‌کند:
``POST /auth/glogin/`` برای احراز هویت با نام کاربری/رمز عبور (تنها روش
پشتیبانی‌شده)، ``POST /api/transcribe_files/`` برای رونویسی زمان‌دار و
``POST /api/speaker_tasks/diarization/`` برای تفکیک گوینده.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.org_ai_providers import Org_ai_providers
from services.ai_gateway import (
    AIGatewayError,
    MinutesDraftResult,
    TranscriptionResult,
    TranscriptSegment,
    build_segments,
    get_minutes_port,
    get_transcription_port,
)
from services.app_auth import decrypt_secret, encrypt_secret

logger = logging.getLogger(__name__)

KIND_STT = "stt"
KIND_LLM = "llm"
ALL_KINDS = (KIND_STT, KIND_LLM)

KIND_LABELS = {KIND_STT: "تبدیل گفتار به نوشتار", KIND_LLM: "مدل زبانی"}

AUTH_API_KEY = "api_key"
AUTH_USERNAME_PASSWORD = "username_password"

PLATFORM_PROVIDER = "atoms_platform"

_TRANSCRIBE_TIMEOUT = 900.0
_HARF_WAIT_TIMEOUT = 3600.0  # «حرف»: آپلود فایل و انتظار پردازش با wait=true
_CHAT_TIMEOUT = 180.0
_TEST_TIMEOUT = 30.0


# ---------------------------------------------------------------------------
# فهرست تأمین‌کنندگان پشتیبانی‌شده
# ---------------------------------------------------------------------------

STT_CATALOG: List[Dict[str, Any]] = [
    {
        "provider_key": "harf",
        "display_name": "حرف (روشن)",
        "base_url": "https://harf.roshan-ai.ir",
        "model": "harf-transcribe",
        "auth_mode": AUTH_USERNAME_PASSWORD,
        "supports_diarization": True,
        "enabled_by_default": True,
        "note": "سرویس بومی رونویسی فارسی؛ با نام کاربری/رمز عبور کار می‌کند (توکن مستقیم لازم نیست) و تفکیک گوینده دارد.",
    },
    {
        "provider_key": "elevenlabs",
        "display_name": "ElevenLabs Scribe",
        "base_url": "https://api.elevenlabs.io",
        "model": "scribe_v1",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": True,
        "enabled_by_default": False,
        "note": "رونویسی چندزبانه با تفکیک گوینده؛ نیازمند کلید API از پنل ElevenLabs.",
    },
    {
        "provider_key": "whisper_openai",
        "display_name": "Whisper (OpenAI)",
        "base_url": "https://api.openai.com/v1",
        "model": "whisper-1",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": False,
        "enabled_by_default": False,
        "note": "رونویسی زمان‌دار Whisper؛ تفکیک گوینده ندارد و فقط به‌عنوان جایگزین اضطراری مناسب است.",
    },
]

LLM_CATALOG: List[Dict[str, Any]] = [
    {
        "provider_key": "deepseek",
        "display_name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "model": "deepseek-chat",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": False,
        "enabled_by_default": False,
        "note": "مدل زبانی پیش‌فرض سامانه؛ سازگار با OpenAI و مقرون‌به‌صرفه برای تهیهٔ پیش‌نویس صورتجلسه.",
    },
    {
        "provider_key": "avalai",
        "display_name": "AvalAI (آوال)",
        "base_url": "https://api.avalai.ir/v1",
        "model": "gpt-4o-mini",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": False,
        "enabled_by_default": False,
        "note": "درگاه ایرانی سازگار با OpenAI؛ نام مدل را مطابق پنل خود تنظیم کنید.",
    },
    {
        "provider_key": "chatgpt",
        "display_name": "ChatGPT (OpenAI)",
        "base_url": "https://api.openai.com/v1",
        "model": "gpt-4o-mini",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": False,
        "enabled_by_default": False,
        "note": "دسترسی مستقیم به مدل‌های OpenAI.",
    },
    {
        "provider_key": "kimi",
        "display_name": "Kimi (Moonshot)",
        "base_url": "https://api.moonshot.cn/v1",
        "model": "moonshot-v1-8k",
        "auth_mode": AUTH_API_KEY,
        "supports_diarization": False,
        "enabled_by_default": False,
        "note": "سازگار با OpenAI؛ پنجرهٔ متنی بلند برای رونویسی‌های طولانی.",
    },
]

CATALOG: Dict[str, List[Dict[str, Any]]] = {KIND_STT: STT_CATALOG, KIND_LLM: LLM_CATALOG}

#: مدل‌های پیشنهادی هر تأمین‌کننده برای انتخاب در پنل. فهرست بسته نیست؛ در رابط
#: گزینهٔ «مدل دیگر» هم هست تا اگر نام مدلی تازه تغییر کرد، بدون تغییر کد ثبت شود.
MODEL_OPTIONS: Dict[str, List[str]] = {
    "harf": ["harf-transcribe"],
    "elevenlabs": ["scribe_v1"],
    "whisper_openai": ["whisper-1", "gpt-4o-transcribe", "gpt-4o-mini-transcribe"],
    "deepseek": ["deepseek-chat", "deepseek-reasoner"],
    "avalai": [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-4.1-mini",
        "gpt-4.1",
        "o4-mini",
        "deepseek-chat",
    ],
    "chatgpt": ["gpt-4o-mini", "gpt-4o", "gpt-4.1-mini", "gpt-4.1", "o4-mini"],
    "kimi": [
        "moonshot-v1-8k",
        "moonshot-v1-32k",
        "moonshot-v1-128k",
        "kimi-k2-0905-preview",
    ],
}


def model_options_for(provider_key: str) -> List[str]:
    """فهرست مدل‌های پیشنهادی یک تأمین‌کننده (همیشه شامل مدل پیش‌فرض کاتالوگ)."""
    entry = catalog_entry_of(provider_key)
    options = [str(item) for item in MODEL_OPTIONS.get(provider_key, []) if str(item).strip()]
    default_model = str(entry.get("model") or "").strip()
    if default_model and default_model not in options:
        options.insert(0, default_model)
    return options


def catalog_entry_of(provider_key: str) -> Dict[str, Any]:
    """ورودی کاتالوگ با کلید تأمین‌کننده (در هر دو نوع STT و LLM)."""
    for kind in ALL_KINDS:
        for entry in CATALOG.get(kind, []):
            if entry["provider_key"] == provider_key:
                return entry
    return {}


def catalog_entry(kind: str, provider_key: str) -> Dict[str, Any]:
    for entry in CATALOG.get(kind, []):
        if entry["provider_key"] == provider_key:
            return entry
    return {}


def catalog_payload() -> Dict[str, Any]:
    """فهرست تأمین‌کنندگان برای نمایش راهنما در رابط کاربری."""
    return {
        kind: [
            {
                "provider_key": entry["provider_key"],
                "display_name": entry["display_name"],
                "auth_mode": entry["auth_mode"],
                "supports_diarization": entry["supports_diarization"],
                "default_base_url": entry["base_url"],
                "default_model": entry["model"],
                "model_options": model_options_for(entry["provider_key"]),
                "note": entry["note"],
            }
            for entry in CATALOG[kind]
        ]
        for kind in ALL_KINDS
    }


# ---------------------------------------------------------------------------
# ابزار مشترک
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0, tzinfo=None)


def iso_utc(value: Optional[datetime]) -> str:
    if value is None:
        return ""
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def mask_secret(encrypted: str) -> str:
    """نمای ماسک‌شدهٔ کلید؛ فقط چهار نویسهٔ آخر دیده می‌شود."""
    raw = decrypt_secret(encrypted or "")
    if not raw:
        return ""
    tail = raw[-4:] if len(raw) > 4 else raw
    return f"••••{tail}"


def to_ms(value: Any) -> int:
    """تبدیل زمان به میلی‌ثانیه؛ هم عدد ثانیه و هم قالب ``0:01:23`` را می‌پذیرد."""
    if value is None:
        return 0
    if isinstance(value, bool):
        return 0
    if isinstance(value, (int, float)):
        return max(int(float(value) * 1000), 0)
    text = str(value).strip()
    if not text:
        return 0
    if re.fullmatch(r"\d+(\.\d+)?", text):
        return int(float(text) * 1000)
    try:
        numbers = [float(part) for part in text.split(":")]
    except ValueError:
        return 0
    seconds = 0.0
    for number in numbers:
        seconds = seconds * 60 + number
    return max(int(seconds * 1000), 0)


def quality_stats(text: str) -> Dict[str, Any]:
    """سیگنال کیفیت: نسبت واژه‌های بدون کروشهٔ تردید."""
    words = [word for word in re.split(r"\s+", (text or "").strip()) if word]
    total = len(words)
    suspicious = sum(1 for word in words if "[" in word or "]" in word)
    known = max(total - suspicious, 0)
    ratio = round(known / total, 4) if total else 0.0
    return {"stats_words": total, "stats_known_words": known, "known_word_ratio": ratio}


def _result_from_segments(
    *,
    provider: str,
    model: str,
    segments: List[TranscriptSegment],
    duration_seconds: int,
) -> TranscriptionResult:
    full_text = "\n".join(segment.text for segment in segments if segment.text).strip()
    if not full_text:
        raise AIGatewayError("سرویس رونویسی متنی برنگرداند. فایل صوتی را بررسی کنید.")
    duration = duration_seconds
    if duration <= 0 and segments:
        duration = math.ceil(max(segment.end_ms for segment in segments) / 1000)
    stats = quality_stats(full_text)
    return TranscriptionResult(
        provider=provider,
        model=model,
        full_text=full_text,
        segments=segments,
        duration_seconds=max(duration, 1),
        stats_words=stats["stats_words"],
        stats_known_words=stats["stats_known_words"],
        known_word_ratio=stats["known_word_ratio"],
    )


async def _download_media(url: str) -> Tuple[str, bytes]:
    """دریافت بایت‌های فایل صوتی از نشانی امضاشدهٔ فضای ذخیره‌سازی."""
    async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        raise AIGatewayError("دریافت فایل صوتی از فضای ذخیره‌سازی ناموفق بود.")
    name = (url.split("?")[0].rsplit("/", 1)[-1] or "audio.mp3").strip()
    return name, response.content


# ---------------------------------------------------------------------------
# دسترسی به تنظیمات سازمان
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# اعتبارنامهٔ پیش‌فرض سرویس «حرف» برای سازمان‌های تازه‌ثبت‌نام‌کرده
# ---------------------------------------------------------------------------
#
# هر سازمان به محض ثبت‌نام، رونویسی «حرف» با این اعتبارنامه فعال است و بدون
# هیچ پیکربندی کار می‌کند. مقادیر از متغیرهای محیطی خوانده می‌شوند؛ در
# نبودشان از همین مقادیر پیش‌فرض استفاده می‌شود.


def _env_flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


DEFAULT_HARF_ENABLED = _env_flag("DEFAULT_HARF_ENABLED", True)
DEFAULT_HARF_AUTH_USERNAME = os.environ.get("DEFAULT_HARF_AUTH_USERNAME", "samim2")
DEFAULT_HARF_AUTH_PASSWORD = os.environ.get("DEFAULT_HARF_AUTH_PASSWORD", "samim2_14050527")

# کلید پیش‌فرض سامانه برای مدل زبانی DeepSeek؛ اگر تعریف شده باشد، ردیف DeepSeek
# هر سازمانی که هنوز کلید ندارد فعال می‌شود و با همین کلید کار می‌کند (مدیر می‌تواند
# بعداً کلید سازمان خودش را جایگزین کند یا سرویس را خاموش کند).
DEFAULT_DEEPSEEK_API_KEY = os.environ.get("DEFAULT_DEEPSEEK_API_KEY", "").strip()


def _apply_default_harf(row: Org_ai_providers) -> None:
    """فعال‌سازی «حرف» با اعتبارنامهٔ پیش‌فرض روی ردیفی که هنوز پیکربندی نشده است."""
    row.enabled = DEFAULT_HARF_ENABLED
    row.auth_username = DEFAULT_HARF_AUTH_USERNAME
    row.auth_password_enc = encrypt_secret(DEFAULT_HARF_AUTH_PASSWORD)


def _harf_unconfigured(row: Org_ai_providers) -> bool:
    """ردیف «حرف» بدون هیچ اعتبارنامه‌ای که مدیر هم صریحاً غیرفعالش نکرده است.

    اگر مدیر سرویس را خاموش کرده باشد (``enabled=False``) یا نام کاربری/رمز
    ثبت کرده باشد، پیش‌فرض روی آن اعمال نمی‌شود.
    """
    if row.kind != KIND_STT or (row.provider_key or "") != "harf":
        return False
    if row.enabled is False:
        return False
    return not ((row.auth_username or "").strip() or (row.auth_password_enc or "").strip())


def _apply_default_deepseek(row: Org_ai_providers) -> bool:
    """فعال‌سازی DeepSeek با کلید پیش‌فرض سامانه روی ردیف بدون کلید.

    فقط وقتی اثری دارد که ``DEFAULT_DEEPSEEK_API_KEY`` در محیط تعریف شده باشد.
    پس از اعمال، ردیف کلید دارد و پیش‌فرض دوباره روی آن اعمال نمی‌شود؛ بنابراین
    غیرفعال‌سازی بعدی توسط مدیر سازمان پایدار می‌ماند.
    """
    if not DEFAULT_DEEPSEEK_API_KEY:
        return False
    row.enabled = True
    row.api_key_enc = encrypt_secret(DEFAULT_DEEPSEEK_API_KEY)
    return True


def _deepseek_unconfigured(row: Org_ai_providers) -> bool:
    """ردیف DeepSeek (مدل زبانی) که هنوز هیچ کلیدی برایش ثبت نشده است."""
    if row.kind != KIND_LLM or (row.provider_key or "") != "deepseek":
        return False
    return not (row.api_key_enc or "").strip()


def _row_unconfigured(row: Org_ai_providers) -> bool:
    """آیا سازمان هنوز هیچ اعتبارنامه‌ای برای این تأمین‌کننده ثبت نکرده است؟

    ملاک، «نبود اعتبارنامه» است نه مقدار ``enabled``؛ چون ردیف تازه با
    ``enabled=False`` ساخته می‌شود و نمی‌توان از آن فهمید مدیر عمداً خاموشش کرده
    یا هنوز دست نزده است. پس از اعمال پیش‌فرض، ردیف اعتبارنامه دارد و خاموش‌کردن
    بعدی مدیر سازمان پایدار می‌ماند.
    """
    entry = catalog_entry(row.kind or "", row.provider_key or "")
    if entry.get("auth_mode") == AUTH_USERNAME_PASSWORD:
        return not ((row.auth_username or "").strip() or (row.auth_password_enc or "").strip())
    return not (row.api_key_enc or "").strip()


# ---------------------------------------------------------------------------
# پیش‌فرض‌های سطح پلتفرم (قابل ویرایش از پنل مدیریت سامانه)
#
# پیش از این، «هوش مصنوعی پیش‌فرض همهٔ سازمان‌ها» فقط در کد و متغیرهای محیطی
# (DEFAULT_HARF_* و DEFAULT_DEEPSEEK_API_KEY) تعریف می‌شد و تغییرش نیاز به
# ویرایش فایل و راه‌اندازی مجدد سرویس داشت. اکنون همین پیش‌فرض‌ها در جدول
# تنظیمات سراسری ذخیره می‌شوند و از پنل قابل ویرایش‌اند؛ متغیرهای محیطی همچنان
# به‌عنوان مقدار پشتیبان عمل می‌کنند.
#
# ترتیب اولویت هنگام ساخت/به‌روزرسانی ردیف هر سازمان:
#   ۱) مقداری که خود سازمان ثبت کرده است (هرگز بازنویسی نمی‌شود)
#   ۲) پیش‌فرض پنل مدیریت سامانه
#   ۳) پیش‌فرض کد/متغیر محیطی
# ---------------------------------------------------------------------------

#: کلید تنظیمات سراسری که پیش‌فرض‌های AI در آن نگه‌داری می‌شود (JSON).
PLATFORM_AI_DEFAULTS_KEY = "ai_defaults"


async def _platform_defaults(db: AsyncSession) -> Dict[str, Dict[str, Any]]:
    """پیش‌فرض‌های ذخیره‌شده در پنل؛ در نبود/خرابی مقدار، دیکشنری خالی."""
    # import تنبل: این ماژول در بسیاری از مسیرها import می‌شود و نمی‌خواهیم
    # چرخهٔ واردکردنی بسازیم.
    from services import platform_settings

    try:
        raw = await platform_settings.get_setting(db, PLATFORM_AI_DEFAULTS_KEY)
    except Exception as exc:  # pragma: no cover - نبود جدول نباید جریان را بشکند
        logger.warning("خواندن پیش‌فرض‌های AI پلتفرم ناموفق بود: %s", exc)
        return {}
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        logger.warning("پیش‌فرض‌های AI پلتفرم قابل تفسیر نبود؛ نادیده گرفته شد.")
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(key): value for key, value in data.items() if isinstance(value, dict)}


def platform_default_payload(
    kind: str, provider_key: str, stored: Dict[str, Any]
) -> Dict[str, Any]:
    """نمای امن پیش‌فرض یک تأمین‌کننده برای پنل؛ کلید/رمز فقط ماسک‌شده."""
    entry = catalog_entry(kind, provider_key)
    uses_login = entry.get("auth_mode") == AUTH_USERNAME_PASSWORD
    api_key_enc = str(stored.get("api_key_enc") or "")
    password_enc = str(stored.get("password_enc") or "")
    return {
        "provider_key": provider_key,
        "kind": kind,
        "display_name": entry.get("display_name", provider_key),
        "auth_mode": entry.get("auth_mode", AUTH_API_KEY),
        "supports_diarization": bool(entry.get("supports_diarization")),
        "note": entry.get("note", ""),
        "model_options": model_options_for(provider_key),
        "default_base_url": entry.get("base_url", ""),
        "default_model": entry.get("model", ""),
        "configured": bool(stored),
        "enabled": bool(stored.get("enabled", False)),
        "model": str(stored.get("model") or entry.get("model") or ""),
        "base_url": str(stored.get("base_url") or entry.get("base_url") or ""),
        "priority": int(stored.get("priority") or 0) or None,
        "diarization": bool(
            stored.get("diarization", entry.get("supports_diarization", False))
        ),
        "auth_username": str(stored.get("auth_username") or ""),
        "api_key_masked": "" if uses_login else mask_secret(api_key_enc),
        "has_api_key": False if uses_login else bool(api_key_enc.strip()),
        "password_masked": mask_secret(password_enc),
        "has_password": bool(password_enc.strip()),
        "updated_at": str(stored.get("updated_at") or ""),
    }


def _default_source(provider_key: str, stored_all: Dict[str, Dict[str, Any]]) -> str:
    """منبع پیش‌فرض فعال: پنل، کد/محیط یا هیچ."""
    if stored_all.get(provider_key):
        return "panel"
    if provider_key == "harf" and (DEFAULT_HARF_ENABLED or DEFAULT_HARF_AUTH_USERNAME):
        return "code"
    if provider_key == "deepseek" and DEFAULT_DEEPSEEK_API_KEY:
        return "code"
    return "none"


def platform_defaults_payload(
    stored_all: Dict[str, Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """فهرست کامل پیش‌فرض‌ها برای هر دو نوع سرویس، به ترتیب کاتالوگ."""
    payload: Dict[str, List[Dict[str, Any]]] = {}
    for kind in ALL_KINDS:
        items: List[Dict[str, Any]] = []
        for index, entry in enumerate(CATALOG[kind], start=1):
            provider_key = entry["provider_key"]
            item = platform_default_payload(kind, provider_key, stored_all.get(provider_key, {}))
            if not item["priority"]:
                item["priority"] = index
            item["source"] = _default_source(provider_key, stored_all)
            items.append(item)
        payload[kind] = items
    return payload


async def read_platform_defaults(db: AsyncSession) -> Dict[str, Any]:
    """خواندن پیش‌فرض‌ها برای پنل، به‌همراه راهنمای کاتالوگ."""
    stored_all = await _platform_defaults(db)
    return {
        "defaults": platform_defaults_payload(stored_all),
        "catalog": catalog_payload(),
    }


async def set_platform_default(
    db: AsyncSession, provider_key: str, kind: str, data: Dict[str, Any]
) -> Dict[str, Any]:
    """ثبت/به‌روزرسانی پیش‌فرض یک تأمین‌کننده در تنظیمات سراسری (بدون commit)."""
    from services import platform_settings

    entry = catalog_entry(kind, provider_key)
    if not entry:
        raise ValueError("تأمین‌کنندهٔ انتخابی در فهرست پشتیبانی‌شده نیست.")

    stored_all = await _platform_defaults(db)
    current = dict(stored_all.get(provider_key) or {})

    if "enabled" in data and data["enabled"] is not None:
        current["enabled"] = bool(data["enabled"])
    if data.get("model"):
        current["model"] = str(data["model"]).strip()[:120]
    if data.get("base_url"):
        current["base_url"] = str(data["base_url"]).strip().rstrip("/")[:300]
    if data.get("priority") is not None:
        try:
            current["priority"] = max(1, min(int(data["priority"]), 99))
        except (TypeError, ValueError):
            pass
    if data.get("diarization") is not None:
        current["diarization"] = bool(data["diarization"]) and bool(
            entry.get("supports_diarization")
        )
    if "auth_username" in data and data["auth_username"] is not None:
        current["auth_username"] = str(data["auth_username"]).strip()[:120]
    if data.get("api_key"):
        current["api_key_enc"] = encrypt_secret(_sanitize_token(str(data["api_key"])))
    if data.get("clear_api_key"):
        current["api_key_enc"] = ""
    if data.get("password"):
        current["password_enc"] = encrypt_secret(str(data["password"]).strip())
    if data.get("clear_password"):
        current["password_enc"] = ""

    current["kind"] = kind
    current["updated_at"] = iso_utc(utc_now())
    stored_all[provider_key] = current
    await platform_settings.set_setting(
        db, PLATFORM_AI_DEFAULTS_KEY, json.dumps(stored_all, ensure_ascii=False)
    )
    payload = platform_default_payload(kind, provider_key, current)
    payload["source"] = "panel"
    return payload


def _default_has_credentials(default: Dict[str, Any], entry: Dict[str, Any]) -> bool:
    if entry.get("auth_mode") == AUTH_USERNAME_PASSWORD:
        return bool(
            str(default.get("auth_username") or "").strip()
            and str(default.get("password_enc") or "").strip()
        )
    return bool(str(default.get("api_key_enc") or "").strip())


def _apply_platform_default(
    row: Org_ai_providers, default: Dict[str, Any], entry: Dict[str, Any]
) -> bool:
    """اعمال پیش‌فرض پنل روی ردیفِ بدون تنظیم سازمان؛ ``True`` اگر تغییری داد."""
    if not default:
        return False
    changed = False
    if default.get("model") and (row.model or "") != default["model"]:
        row.model = str(default["model"])
        changed = True
    if default.get("base_url") and (row.base_url or "") != default["base_url"]:
        row.base_url = str(default["base_url"])
        changed = True
    if default.get("priority"):
        try:
            priority = max(1, min(int(default["priority"]), 99))
        except (TypeError, ValueError):
            priority = int(row.priority or 99)
        if int(row.priority or 0) != priority:
            row.priority = priority
            changed = True
    if default.get("diarization") is not None and entry.get("supports_diarization"):
        value = bool(default["diarization"])
        if bool(row.diarization) != value:
            row.diarization = value
            changed = True
    if default.get("auth_username") and (row.auth_username or "") != default["auth_username"]:
        row.auth_username = str(default["auth_username"])
        changed = True
    if default.get("password_enc") and not (row.auth_password_enc or "").strip():
        row.auth_password_enc = str(default["password_enc"])
        changed = True
    if default.get("api_key_enc") and not (row.api_key_enc or "").strip():
        row.api_key_enc = str(default["api_key_enc"])
        changed = True
    # فعال‌سازی فقط وقتی پیش‌فرض فعال است و اعتبارنامهٔ کامل دارد.
    if (
        bool(default.get("enabled"))
        and _default_has_credentials(default, entry)
        and not bool(row.enabled)
    ):
        row.enabled = True
        changed = True
    return changed


def build_default_provider(
    provider_key: str, kind: str, stored: Dict[str, Any]
) -> Org_ai_providers:
    """ردیف موقت (بدون ذخیره در پایگاه داده) برای تست اتصال پیش‌فرض پنل."""
    entry = catalog_entry(kind, provider_key)
    return Org_ai_providers(
        organization_id=0,
        kind=kind,
        provider_key=provider_key,
        display_name=entry.get("display_name", provider_key),
        enabled=True,
        priority=int(stored.get("priority") or 1),
        base_url=str(stored.get("base_url") or entry.get("base_url") or ""),
        model=str(stored.get("model") or entry.get("model") or ""),
        api_key_enc=str(stored.get("api_key_enc") or ""),
        auth_username=str(stored.get("auth_username") or ""),
        auth_password_enc=str(stored.get("password_enc") or ""),
        diarization=bool(stored.get("diarization", entry.get("supports_diarization", False))),
        extra_json="",
    )


async def platform_default_provider(
    db: AsyncSession, provider_key: str, kind: str, overrides: Optional[Dict[str, Any]] = None
) -> Org_ai_providers:
    """ردیف موقت پیش‌فرض برای تست؛ مقادیر ارسالی (تست پیش از ذخیره) مقدم‌اند."""
    stored_all = await _platform_defaults(db)
    merged = dict(stored_all.get(provider_key) or {})
    overrides = overrides or {}
    if overrides.get("api_key"):
        merged["api_key_enc"] = encrypt_secret(_sanitize_token(str(overrides["api_key"])))
    if overrides.get("password"):
        merged["password_enc"] = encrypt_secret(str(overrides["password"]).strip())
    if overrides.get("auth_username") is not None:
        merged["auth_username"] = str(overrides["auth_username"]).strip()
    if overrides.get("base_url"):
        merged["base_url"] = str(overrides["base_url"]).strip().rstrip("/")
    if overrides.get("model"):
        merged["model"] = str(overrides["model"]).strip()
    return build_default_provider(provider_key, kind, merged)


async def clear_platform_default(db: AsyncSession, provider_key: str) -> Dict[str, Any]:
    """حذف پیش‌فرض پنل یک تأمین‌کننده و بازگشت به پیش‌فرض کد/محیط (بدون commit)."""
    from services import platform_settings

    stored_all = await _platform_defaults(db)
    stored_all.pop(provider_key, None)
    await platform_settings.set_setting(
        db,
        PLATFORM_AI_DEFAULTS_KEY,
        json.dumps(stored_all, ensure_ascii=False) if stored_all else None,
    )
    return {"provider_key": provider_key, "cleared": True}


async def apply_platform_defaults(db: AsyncSession) -> Dict[str, Any]:
    """اعمال پیش‌فرض‌های پنل روی همهٔ سازمان‌های فعال (فقط ردیف‌های بدون تنظیم).

    سازمانی که خودش کلید/اعتبارنامه ثبت کرده باشد هرگز بازنویسی نمی‌شود؛ این تابع
    برای زمانی است که مدیر سامانه پیش‌فرض را عوض می‌کند و می‌خواهد همان لحظه روی
    سازمان‌های تنظیم‌نشده اعمال شود (بدون انتظار برای نخستین درخواست هر سازمان).
    """
    from models.organizations import Organizations

    defaults = await _platform_defaults(db)
    if not defaults:
        return {
            "organizations": 0,
            "updated_organizations": 0,
            "updated_providers": 0,
            "providers": {},
        }

    result = await db.execute(
        select(Organizations).where(Organizations.status != "trashed")
    )
    organizations = list(result.scalars().all())
    updated_orgs = 0
    updated_providers = 0
    per_provider: Dict[str, int] = {}
    for organization in organizations:
        rows = await ensure_defaults(db, int(organization.id))
        org_updated = False
        for row in rows:
            provider_key = row.provider_key or ""
            default = defaults.get(provider_key)
            if not default or not _row_unconfigured(row):
                continue
            entry = catalog_entry(row.kind or "", provider_key)
            if _apply_platform_default(row, default, entry):
                updated_providers += 1
                per_provider[provider_key] = per_provider.get(provider_key, 0) + 1
                org_updated = True
        if org_updated:
            updated_orgs += 1
    if updated_orgs:
        await db.flush()
    return {
        "organizations": len(organizations),
        "updated_organizations": updated_orgs,
        "updated_providers": updated_providers,
        "providers": per_provider,
    }


async def ensure_defaults(db: AsyncSession, organization_id: int) -> List[Org_ai_providers]:
    """ساخت ردیف‌های پیش‌فرض تنظیمات برای سازمان (یک‌بار، بی‌اثر در فراخوان دوباره).

    ترتیب اولویت مقداردهی: مقدار ثبت‌شدهٔ خود سازمان ← پیش‌فرض پنل مدیریت سامانه
    ← پیش‌فرض کد/متغیر محیطی. ردیف سرویس «حرف» با اعتبارنامهٔ پیش‌فرض ساخته
    می‌شود تا رونویسی برای هر سازمان تازه بدون هیچ پیکربندی فعال باشد؛ ردیف‌های
    قدیمیِ بدون اعتبارنامه هم به همین پیش‌فرض منتقل می‌شوند.
    """
    platform_defaults = await _platform_defaults(db)
    result = await db.execute(
        select(Org_ai_providers).where(Org_ai_providers.organization_id == organization_id)
    )
    rows = list(result.scalars().all())
    existing = {(row.kind, row.provider_key) for row in rows}
    created = False
    for kind in ALL_KINDS:
        for index, entry in enumerate(CATALOG[kind], start=1):
            if (kind, entry["provider_key"]) in existing:
                continue
            row = Org_ai_providers(
                organization_id=organization_id,
                kind=kind,
                provider_key=entry["provider_key"],
                display_name=entry["display_name"],
                enabled=bool(entry["enabled_by_default"]),
                priority=index,
                base_url=entry["base_url"],
                model=entry["model"],
                api_key_enc="",
                auth_username="",
                auth_password_enc="",
                diarization=bool(entry["supports_diarization"]),
                extra_json="",
                last_test_ok=False,
                last_test_at="",
                last_test_message="",
            )
            if entry["provider_key"] == "harf":
                _apply_default_harf(row)
            db.add(row)
            rows.append(row)
            created = True
    # ۱) پیش‌فرض پنل سامانه روی ردیف‌هایی که سازمان هنوز اعتبارنامه‌ای ثبت نکرده
    #    است، ۲) در نبود آن، پشتیبانی از ردیف‌های «حرف» قدیمی و فعال‌سازی
    #    پیش‌فرض کد (DeepSeek) روی ردیف‌های مدل زبانی بدون کلید.
    changed = False
    for row in rows:
        if not _row_unconfigured(row):
            continue
        provider_key = row.provider_key or ""
        entry = catalog_entry(row.kind or "", provider_key)
        default = platform_defaults.get(provider_key)
        if default and _apply_platform_default(row, default, entry):
            changed = True
            continue
        if _harf_unconfigured(row):
            _apply_default_harf(row)
            changed = True
        if _deepseek_unconfigured(row):
            changed = _apply_default_deepseek(row) or changed
    if created or changed:
        await db.flush()
    rows.sort(key=lambda row: (row.kind, int(row.priority or 99), int(row.id or 0)))
    return rows


def provider_payload(row: Org_ai_providers) -> Dict[str, Any]:
    """نمای امن یک ردیف تنظیمات؛ کلید و رمز فقط ماسک‌شده."""
    entry = catalog_entry(row.kind or "", row.provider_key or "")
    uses_login = entry.get("auth_mode") == AUTH_USERNAME_PASSWORD
    return {
        "id": int(row.id),
        "kind": row.kind or "",
        "kind_label": KIND_LABELS.get(row.kind or "", row.kind or ""),
        "provider_key": row.provider_key or "",
        "display_name": row.display_name or entry.get("display_name", row.provider_key or ""),
        "enabled": bool(row.enabled),
        "priority": int(row.priority or 99),
        "base_url": row.base_url or entry.get("base_url", ""),
        "model": row.model or entry.get("model", ""),
        "model_options": model_options_for(row.provider_key or ""),
        "auth_mode": entry.get("auth_mode", AUTH_API_KEY),
        "supports_diarization": bool(entry.get("supports_diarization")),
        "diarization": bool(row.diarization),
        "auth_username": row.auth_username or "",
        # سرویس‌های با ورود کاربری/رمز (حرف) کلید API ندارند
        "api_key_masked": "" if uses_login else mask_secret(row.api_key_enc or ""),
        "has_api_key": False if uses_login else bool((row.api_key_enc or "").strip()),
        "password_masked": mask_secret(row.auth_password_enc or ""),
        "has_password": bool((row.auth_password_enc or "").strip()),
        "note": entry.get("note", ""),
        "last_test_ok": bool(row.last_test_ok),
        "last_test_at": row.last_test_at or "",
        "last_test_message": row.last_test_message or "",
    }


async def enabled_providers(
    db: AsyncSession, organization_id: int, kind: str
) -> List[Org_ai_providers]:
    """تأمین‌کنندگان فعال یک نوع سرویس، مرتب بر اساس اولویت."""
    result = await db.execute(
        select(Org_ai_providers).where(
            Org_ai_providers.organization_id == organization_id,
            Org_ai_providers.kind == kind,
            Org_ai_providers.enabled.is_(True),
        )
    )
    rows = [row for row in result.scalars().all() if _has_credentials(row)]
    rows.sort(key=lambda row: (int(row.priority or 99), int(row.id or 0)))
    return rows


def _has_credentials(row: Org_ai_providers) -> bool:
    entry = catalog_entry(row.kind or "", row.provider_key or "")
    if entry.get("auth_mode") == AUTH_USERNAME_PASSWORD:
        # «حرف» فقط با نام کاربری/رمز عبور کار می‌کند (بدون توکن مستقیم)
        return bool((row.auth_username or "").strip() and (row.auth_password_enc or "").strip())
    return bool((row.api_key_enc or "").strip())


def apply_update(row: Org_ai_providers, data: Dict[str, Any]) -> None:
    """اعمال تغییرات مدیر روی یک ردیف تنظیمات (کلید خالی = بدون تغییر)."""
    if "enabled" in data and data["enabled"] is not None:
        row.enabled = bool(data["enabled"])
    if "priority" in data and data["priority"] is not None:
        row.priority = max(1, min(int(data["priority"]), 99))
    if data.get("base_url"):
        row.base_url = str(data["base_url"]).strip().rstrip("/")
    if data.get("model"):
        row.model = str(data["model"]).strip()
    if "diarization" in data and data["diarization"] is not None:
        entry = catalog_entry(row.kind or "", row.provider_key or "")
        row.diarization = bool(data["diarization"]) and bool(entry.get("supports_diarization"))
    if "auth_username" in data and data["auth_username"] is not None:
        row.auth_username = str(data["auth_username"]).strip()
    if data.get("api_key"):
        row.api_key_enc = encrypt_secret(_sanitize_token(str(data["api_key"])))
    if data.get("clear_api_key"):
        row.api_key_enc = ""
    if data.get("password"):
        row.auth_password_enc = encrypt_secret(str(data["password"]).strip())
    if data.get("clear_password"):
        row.auth_password_enc = ""


# ---------------------------------------------------------------------------
# آداپتر «حرف»
# ---------------------------------------------------------------------------


def _base_of(row: Org_ai_providers) -> str:
    entry = catalog_entry(row.kind or "", row.provider_key or "")
    return (row.base_url or entry.get("base_url", "")).rstrip("/")


def _sanitize_token(raw: str) -> str:
    """پاک‌سازی توکن ثبت‌شده: فاصله، پیشوند تکراری Bearer و کوتیشن اطراف.

    تجربهٔ واقعی: کاربر توکن را با پیشوند «Bearer » یا با کاراکترهای اضافه در
    تنظیمات ذخیره کرده بود و سرویس حرف با «Invalid token header» رد می‌کرد.
    """
    value = (raw or "").strip()
    if value.lower().startswith("bearer "):
        value = value[len("bearer "):].strip()
    if len(value) >= 2 and value[0] in "\"'“”" and value[-1] in "\"'“”":
        value = value[1:-1].strip()
    return value


async def harf_access_token(row: Org_ai_providers) -> str:
    """توکن Bearer سرویس «حرف» — فقط از طریق ورود با نام کاربری/رمز عبور.

    سرویس «حرف» در نسخهٔ فعلی API فقط اعتبارنامهٔ ورود (glogin) را می‌پذیرد؛
    پشتیبانی از توکن مستقیم (فیلد کلید API) به‌دلیل بدفرمت شدن‌های مکرر و
    رد شدن با «Invalid token header» به‌کلی حذف شد.
    """
    username = (row.auth_username or "").strip()
    password = decrypt_secret(row.auth_password_enc or "").strip()
    if not (username and password):
        raise AIGatewayError(
            "برای سرویس «حرف» نام کاربری و رمز عبور ثبت نشده است؛ از تنظیمات هوش مصنوعی وارد کنید."
        )
    async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
        response = await client.post(
            f"{_base_of(row)}/auth/glogin/",
            json={"username": username, "password": password},
        )
    if response.status_code >= 400:
        raise AIGatewayError("ورود به سرویس «حرف» ناموفق بود؛ نام کاربری یا رمز عبور را بررسی کنید.")
    token = (response.json() or {}).get("access_token") or ""
    if not token:
        raise AIGatewayError("سرویس «حرف» توکن دسترسی برنگرداند.")
    return str(token)


def _harf_segments(items: List[Dict[str, Any]]) -> Tuple[List[TranscriptSegment], int]:
    if not items:
        raise AIGatewayError("سرویس «حرف» نتیجه‌ای برنگرداند.")
    first = items[0] or {}
    raw_segments = first.get("segments") or []
    segments: List[TranscriptSegment] = []
    for item in raw_segments:
        text = str((item or {}).get("text") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start_ms=to_ms((item or {}).get("start")),
                end_ms=to_ms((item or {}).get("end")),
                text=text,
                speaker=str((item or {}).get("speaker") or "").strip(),
            )
        )
    duration = to_ms(first.get("duration")) // 1000
    return segments, duration


async def _harf_diarize(row: Org_ai_providers, audio_url: str) -> List[Dict[str, Any]]:
    """تفکیک گویندهٔ «حرف» با آپلود مستقیم فایل (multipart).

    حالت ``media_urls`` روی URLهای امضاشدهٔ فضای ذخیرهٔ ما ناپایدار است (سرویس
    حرف هنگام واکشی آن 403/500 برمی‌گرداند)؛ بنابراین فایل از استوریج داخلی
    دانلود و مستقیم ارسال می‌شود — همان تصمیم سند معماری.
    """
    token = await harf_access_token(row)
    file_name, content = await _download_media(audio_url)
    timeout = httpx.Timeout(_HARF_WAIT_TIMEOUT, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            f"{_base_of(row)}/api/speaker_tasks/diarization/",
            headers={"Authorization": f"Bearer {token}"},
            files={"media": (file_name, content, "application/octet-stream")},
        )
    if response.status_code >= 400:
        detail = response.text[:200].replace("\n", " ")
        raise AIGatewayError(
            f"تفکیک گوینده در «حرف» ناموفق بود (کد {response.status_code}). {detail}"
        )
    payload = response.json()
    return payload if isinstance(payload, list) else [payload]


async def _harf_transcribe_files(row: Org_ai_providers, audio_url: str) -> List[Dict[str, Any]]:
    """رونویسی زمان‌دار «حرف» با آپلود مستقیم فایل و ``wait=true``.

    نکتهٔ عملیاتی (با تست واقعی روی API نسخهٔ ۲.۱.۰ تأیید شده):
    * الگوی ``wait=false`` + پیگیری با ``tasks_ids`` که در مستند رسمی آمده، در
      نسخهٔ فعلی API کار نمی‌کند: پیگیری بدون ``media_urls``/``filenames`` با
      ۴۰۰ رد می‌شود و ارسال دوبارهٔ ``media_urls`` به‌جای پرس‌وجوی وضعیت، یک
      کارِ جدید می‌سازد (هزینهٔ تکراری)؛ ``wait=true`` روی ``media_urls`` هم
      اتصال را می‌بُرد. بنابراین فایل از فضای ذخیرهٔ داخلی دانلود و به‌صورت
      multipart با ``wait=true`` ارسال می‌شود — همان تصمیم سند معماری
      («Storage خصوصی بماند؛ ارسال جریانی از Worker»).
    """
    token = await harf_access_token(row)
    headers = {"Authorization": f"Bearer {token}"}
    endpoint = f"{_base_of(row)}/api/transcribe_files/"
    file_name, content = await _download_media(audio_url)
    timeout = httpx.Timeout(_HARF_WAIT_TIMEOUT, connect=30.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(
                endpoint,
                headers=headers,
                files={"media": (file_name, content, "application/octet-stream")},
                data={"wait": "true"},
            )
        except httpx.HTTPError as exc:
            raise AIGatewayError(
                "ارتباط با سرویس «حرف» در میانهٔ پردازش قطع شد؛ دوباره تلاش کنید."
            ) from exc
    if response.status_code >= 400:
        detail = response.text[:200].replace("\n", " ")
        raise AIGatewayError(
            f"ارسال فایل به «حرف» ناموفق بود (کد {response.status_code}). {detail}"
        )
    payload = response.json()
    items = payload if isinstance(payload, list) else [payload]
    if not _harf_ready(items):
        raise AIGatewayError("سرویس «حرف» نتیجهٔ رونویسی برنگرداند؛ دوباره تلاش کنید.")
    return items


def _harf_ready(items: List[Dict[str, Any]]) -> bool:
    for item in items:
        status = str((item or {}).get("status") or "").upper()
        if status in ("PENDING", "RUNNING", "IN_PROGRESS"):
            return False
        if (item or {}).get("segments"):
            return True
    return False


async def harf_transcribe(
    row: Org_ai_providers, *, audio_url: str, duration_hint_seconds: int = 0
) -> TranscriptionResult:
    items: List[Dict[str, Any]]
    if row.diarization:
        # تفکیک گوینده نباید کل رونویسی را از کار بیندازد: در صورت خطا،
        # بدون برچسب گوینده ادامه می‌دهیم (متن کامل همچنان تولید می‌شود).
        try:
            items = await _harf_diarize(row, audio_url)
        except AIGatewayError as exc:
            logger.warning(
                "تفکیک گویندهٔ «حرف» ناموفق بود؛ ادامه با رونویسی ساده: %s", exc
            )
            items = await _harf_transcribe_files(row, audio_url)
    else:
        items = await _harf_transcribe_files(row, audio_url)
    segments, duration = _harf_segments(items)
    if not segments:
        raise AIGatewayError("سرویس «حرف» متنی برنگرداند.")
    return _result_from_segments(
        provider="harf",
        model=row.model or "harf-transcribe",
        segments=segments,
        duration_seconds=duration or duration_hint_seconds,
    )


# ---------------------------------------------------------------------------
# آداپتر ElevenLabs
# ---------------------------------------------------------------------------


async def elevenlabs_transcribe(
    row: Org_ai_providers, *, audio_url: str, duration_hint_seconds: int = 0
) -> TranscriptionResult:
    api_key = decrypt_secret(row.api_key_enc or "")
    if not api_key:
        raise AIGatewayError("کلید API سرویس ElevenLabs ثبت نشده است.")
    file_name, content = await _download_media(audio_url)
    data = {"model_id": row.model or "scribe_v1", "language_code": "fas"}
    if row.diarization:
        data["diarize"] = "true"
    async with httpx.AsyncClient(timeout=_TRANSCRIBE_TIMEOUT) as client:
        response = await client.post(
            f"{_base_of(row)}/v1/speech-to-text",
            headers={"xi-api-key": api_key},
            data=data,
            files={"file": (file_name, content, "application/octet-stream")},
        )
    if response.status_code >= 400:
        raise AIGatewayError(f"رونویسی ElevenLabs ناموفق بود (کد {response.status_code}).")
    payload = response.json() or {}
    segments = _group_words(payload.get("words") or [])
    if not segments:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise AIGatewayError("سرویس ElevenLabs متنی برنگرداند.")
        segments = build_segments(text, duration_hint_seconds or 60)
    return _result_from_segments(
        provider="elevenlabs",
        model=row.model or "scribe_v1",
        segments=segments,
        duration_seconds=duration_hint_seconds,
    )


def _group_words(words: List[Dict[str, Any]]) -> List[TranscriptSegment]:
    """گروه‌بندی واژه‌ها بر پایهٔ گوینده تا قطعهٔ خوانا و زمان‌دار ساخته شود."""
    segments: List[TranscriptSegment] = []
    current: Optional[TranscriptSegment] = None
    for word in words:
        if str((word or {}).get("type") or "word") not in ("word", "spacing", "audio_event"):
            continue
        text = str((word or {}).get("text") or "")
        if not text.strip():
            if current:
                current.text += " "
            continue
        speaker = str((word or {}).get("speaker_id") or "").strip()
        start_ms = to_ms((word or {}).get("start"))
        end_ms = to_ms((word or {}).get("end"))
        if current is None or current.speaker != speaker or end_ms - current.start_ms > 25000:
            current = TranscriptSegment(
                start_ms=start_ms, end_ms=end_ms, text=text, speaker=speaker
            )
            segments.append(current)
        else:
            current.text = f"{current.text.rstrip()} {text}".strip()
            current.end_ms = end_ms
    for segment in segments:
        segment.text = re.sub(r"\s+", " ", segment.text).strip()
    return [segment for segment in segments if segment.text]


# ---------------------------------------------------------------------------
# آداپتر Whisper (OpenAI)
# ---------------------------------------------------------------------------


async def whisper_transcribe(
    row: Org_ai_providers, *, audio_url: str, duration_hint_seconds: int = 0
) -> TranscriptionResult:
    api_key = decrypt_secret(row.api_key_enc or "")
    if not api_key:
        raise AIGatewayError("کلید API سرویس Whisper ثبت نشده است.")
    file_name, content = await _download_media(audio_url)
    async with httpx.AsyncClient(timeout=_TRANSCRIBE_TIMEOUT) as client:
        response = await client.post(
            f"{_base_of(row)}/audio/transcriptions",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": row.model or "whisper-1",
                "language": "fa",
                "response_format": "verbose_json",
            },
            files={"file": (file_name, content, "application/octet-stream")},
        )
    if response.status_code >= 400:
        raise AIGatewayError(f"رونویسی Whisper ناموفق بود (کد {response.status_code}).")
    payload = response.json() or {}
    segments: List[TranscriptSegment] = []
    for item in payload.get("segments") or []:
        text = str((item or {}).get("text") or "").strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start_ms=to_ms((item or {}).get("start")),
                end_ms=to_ms((item or {}).get("end")),
                text=text,
                speaker="",
            )
        )
    duration = int(float(payload.get("duration") or 0))
    if not segments:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise AIGatewayError("سرویس Whisper متنی برنگرداند.")
        segments = build_segments(text, duration or duration_hint_seconds or 60)
    return _result_from_segments(
        provider="whisper_openai",
        model=row.model or "whisper-1",
        segments=segments,
        duration_seconds=duration or duration_hint_seconds,
    )


STT_ADAPTERS = {
    "harf": harf_transcribe,
    "elevenlabs": elevenlabs_transcribe,
    "whisper_openai": whisper_transcribe,
}


# ---------------------------------------------------------------------------
# آداپتر مدل زبانی (سازگار با OpenAI)
# ---------------------------------------------------------------------------


async def openai_chat(
    row: Org_ai_providers, *, system_prompt: str, user_prompt: str, json_mode: bool = False
) -> Tuple[str, Dict[str, int]]:
    """فراخوان مدل سازگار با OpenAI؛ متن پاسخ و سنجهٔ مصرف (توکن ورودی/خروجی)."""
    api_key = decrypt_secret(row.api_key_enc or "")
    if not api_key:
        raise AIGatewayError(f"کلید API سرویس {row.display_name or row.provider_key} ثبت نشده است.")
    body: Dict[str, Any] = {
        "model": row.model or "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0.2,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    async with httpx.AsyncClient(timeout=_CHAT_TIMEOUT) as client:
        response = await client.post(
            f"{_base_of(row)}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json=body,
        )
    if response.status_code >= 400:
        raise AIGatewayError(
            f"فراخوان مدل زبانی {row.display_name or row.provider_key} ناموفق بود (کد {response.status_code})."
        )
    payload = response.json() or {}
    usage_payload = payload.get("usage") or {}
    usage: Dict[str, int] = {
        "tokens_in": int(usage_payload.get("prompt_tokens") or 0),
        "tokens_out": int(usage_payload.get("completion_tokens") or 0),
    }
    choices = payload.get("choices") or []
    if not choices:
        raise AIGatewayError("مدل زبانی پاسخی برنگرداند.")
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    text = str(content).strip()
    if not text:
        raise AIGatewayError("مدل زبانی پاسخ خالی برگرداند.")
    return text, usage


# ---------------------------------------------------------------------------
# تست اتصال واقعی
# ---------------------------------------------------------------------------


async def test_provider(row: Org_ai_providers) -> Tuple[bool, str]:
    """فراخوان واقعی سبک برای بررسی صحت کلید و نشانی سرویس."""
    try:
        if row.provider_key == "harf":
            token = await harf_access_token(row)
            return True, f"اتصال برقرار شد؛ توکن معتبر است (طول {len(token)} نویسه)."
        api_key = decrypt_secret(row.api_key_enc or "")
        if not api_key:
            return False, "کلید API ثبت نشده است."
        if row.provider_key == "elevenlabs":
            url = f"{_base_of(row)}/v1/user"
            headers = {"xi-api-key": api_key}
        else:
            url = f"{_base_of(row)}/models"
            headers = {"Authorization": f"Bearer {api_key}"}
        async with httpx.AsyncClient(timeout=_TEST_TIMEOUT) as client:
            response = await client.get(url, headers=headers)
        if response.status_code < 400:
            return True, "اتصال برقرار شد و کلید API پذیرفته شد."
        if response.status_code in (401, 403):
            return False, "کلید API پذیرفته نشد (خطای احراز هویت)."
        return False, f"سرویس با کد {response.status_code} پاسخ داد."
    except AIGatewayError as exc:
        return False, str(exc)
    except httpx.HTTPError:
        return False, "ارتباط با سرویس برقرار نشد؛ نشانی پایه یا دسترسی شبکه را بررسی کنید."
    except Exception:  # pragma: no cover - وابسته به سرویس بیرونی
        logger.exception("تست اتصال تأمین‌کنندهٔ AI ناموفق بود")
        return False, "خطای پیش‌بینی‌نشده در تست اتصال."


def record_test_result(row: Org_ai_providers, ok: bool, message: str) -> None:
    row.last_test_ok = bool(ok)
    row.last_test_message = message[:400]
    row.last_test_at = iso_utc(utc_now())


# ---------------------------------------------------------------------------
# اجرای زنجیرهٔ اولویت و fallback
# ---------------------------------------------------------------------------


def format_attempts(attempts: List[Dict[str, str]]) -> str:
    """خط خوانا برای ثبت در Audit و لاگ کار."""
    parts = []
    for attempt in attempts:
        state = "موفق" if attempt.get("ok") else "ناموفق"
        detail = attempt.get("error") or ""
        parts.append(f"{attempt.get('provider')}: {state}{(' — ' + detail) if detail else ''}")
    return " | ".join(parts)


async def run_transcription(
    db: AsyncSession,
    organization_id: int,
    *,
    audio_url: str,
    duration_hint_seconds: int = 0,
) -> Tuple[TranscriptionResult, List[Dict[str, Any]]]:
    """رونویسی با زنجیرهٔ تأمین‌کنندگان سازمان و بازگشت به آداپتر پلتفرم."""
    # اطمینان از وجود ردیف‌های پیش‌فرض (و اعتبارنامهٔ پیش‌فرض «حرف») پیش از
    # خواندن تأمین‌کنندگان فعال، تا رونویسی برای سازمان‌های تازه‌ثبت‌نام‌کرده
    # بدون باز کردن صفحهٔ تنظیمات هم کار کند.
    await ensure_defaults(db, organization_id)
    attempts: List[Dict[str, Any]] = []
    rows = await enabled_providers(db, organization_id, KIND_STT)
    for row in rows:
        adapter = STT_ADAPTERS.get(row.provider_key or "")
        if adapter is None:
            continue
        try:
            result = await adapter(
                row, audio_url=audio_url, duration_hint_seconds=duration_hint_seconds
            )
            attempts.append({"provider": row.provider_key, "ok": True, "error": ""})
            return result, attempts
        except AIGatewayError as exc:
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)})
            logger.warning("تأمین‌کنندهٔ %s ناموفق بود: %s", row.provider_key, exc)
        except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)[:200]})
            logger.exception("خطای تأمین‌کنندهٔ %s", row.provider_key)

    try:
        result = await get_transcription_port().transcribe(
            audio_ref=audio_url, duration_hint_seconds=duration_hint_seconds
        )
        attempts.append({"provider": PLATFORM_PROVIDER, "ok": True, "error": ""})
        return result, attempts
    except Exception as exc:
        attempts.append({"provider": PLATFORM_PROVIDER, "ok": False, "error": str(exc)[:200]})
        raise AIGatewayError(
            "هیچ‌یک از سرویس‌های رونویسی پاسخ نداد. " + format_attempts(attempts)
        ) from exc


async def run_chat(
    db: AsyncSession,
    organization_id: int,
    *,
    system_prompt: str,
    user_prompt: str,
    json_mode: bool = False,
) -> Tuple[str, str, List[Dict[str, Any]], Dict[str, int]]:
    """فراخوان مدل زبانی با زنجیرهٔ اولویت سازمان؛ متن، تأمین‌کننده و مصرف برمی‌گردد."""
    attempts: List[Dict[str, Any]] = []
    rows = await enabled_providers(db, organization_id, KIND_LLM)
    for row in rows:
        try:
            text, usage = await openai_chat(
                row, system_prompt=system_prompt, user_prompt=user_prompt, json_mode=json_mode
            )
            attempts.append({"provider": row.provider_key, "ok": True, "error": ""})
            return text, row.provider_key or "", attempts, usage
        except AIGatewayError as exc:
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)})
            logger.warning("مدل زبانی %s ناموفق بود: %s", row.provider_key, exc)
        except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)[:200]})
            logger.exception("خطای مدل زبانی %s", row.provider_key)
    return "", "", attempts, {"tokens_in": 0, "tokens_out": 0}


_MINUTES_SYSTEM_PROMPT = (
    "تو دبیر حرفه‌ای جلسات سازمانی هستی و صورتجلسهٔ رسمی فارسی می‌نویسی. "
    "فقط یک شیء JSON معتبر برگردان، بدون هیچ توضیح اضافه و بدون بلوک کد. "
    "کلیدهای لازم: summary (رشته)، body_markdown (رشته با تیترهای مارک‌داون)، "
    "decisions (آرایه‌ای از اشیا با کلیدهای title و description)، "
    "action_items (آرایه‌ای از اشیا با کلیدهای title، description، owner_name، due_date و due_hint). "
    "مقدار owner_name باید یکی از نام‌های حاضر در جلسه باشد؛ اگر مسئول مشخص نیست، رشتهٔ خالی بگذار. "
    "قانون سختِ زمان: هیچ تاریخ، مهلت یا بازهٔ زمانی از خودت نساز و حدس نزن. "
    "due_date فقط زمانی پر می‌شود که در متن جلسه تاریخ پایان یا مهلت صریح گفته شده باشد و باید "
    "به قالب میلادی YYYY-MM-DD نوشته شود؛ در غیر این صورت due_date را رشتهٔ خالی بگذار. "
    "due_hint فقط نقل دقیق عبارت زمانی گفته‌شده در جلسه است (مثل «تا دو هفته») و اگر زمانی گفته "
    "نشده، رشتهٔ خالی. در body_markdown هم هیچ زمان یا مهلتی که در جلسه گفته نشده ننویس و "
    "ستون یا جای خالیِ زمان را خالی بگذار. "
    "همهٔ متن‌ها فارسی و رسمی باشند."
)


def _clean_text(value: Any, limit: int) -> str:
    if value is None:
        return ""
    text = value.strip() if isinstance(value, str) else str(value).strip()
    return text[:limit]


async def run_minutes_draft(
    db: AsyncSession,
    organization_id: int,
    *,
    meeting_title: str,
    meeting_type: str,
    agenda_titles: List[str],
    attendee_names: List[str],
    transcript_text: str,
    use_agenda: bool = True,
    use_attendees: bool = False,
    target_words: int = 0,
    generate_items: bool = True,
    considerations: str = "",
) -> Tuple[Any, List[Dict[str, Any]]]:
    """پیش‌نویس صورتجلسه با زنجیرهٔ مدل زبانی سازمان و بازگشت به آداپتر پلتفرم.

    پرامپت بر پایهٔ تنظیمات تولید همان جلسه ساخته می‌شود: لحاظ/عدم لحاظ دستور
    جلسه و مدعوین، طول هدف (کلمه)، تولید یا عدم تولید مصوبات/اقدامات و ملاحظات
    دلخواه کاربر.

    ابتدا مدل‌های زبانی فعال سازمان به ترتیب ``priority`` امتحان می‌شوند؛ اگر
    هیچ‌کدام پیکربندی/پاسخ معتبر نداشت، آداپتر پلتفرم اجرا می‌شود تا قابلیت
    هرگز از کار نیفتد. فهرست تلاش‌ها برای ثبت در نتیجهٔ کار برگردانده می‌شود.
    """
    agenda_text = "\n".join(f"- {title}" for title in agenda_titles) or "- (دستور جلسه ثبت نشده)"
    attendees_text = "، ".join(attendee_names) or "(فهرست حاضران ثبت نشده)"

    header_lines = [f"عنوان جلسه: {meeting_title}", f"نوع جلسه: {meeting_type or 'نامشخص'}"]
    if use_attendees:
        header_lines.append(f"حاضران: {attendees_text}")
    if use_agenda:
        header_lines.append(f"دستور جلسه:\n{agenda_text}")

    target_instruction = ""
    if target_words and int(target_words) > 0:
        target_instruction = f" طول صورتجلسهٔ نهایی (body_markdown) حدود {int(target_words)} کلمه باشد."
    considerations_text = ""
    if (considerations or "").strip():
        considerations_text = (
            f"\n\nملاحظات کاربر برای تهیهٔ صورتجلسه — این موارد باید حتماً رعایت شوند:\n"
            f"{considerations.strip()[:1500]}"
        )

    body_sections = (
        "«## جمع‌بندی جلسه» و «## مذاکرات بر پایهٔ دستور جلسه»"
        if use_agenda
        else "«## جمع‌بندی جلسه» و «## مذاکرات»"
    )
    items_instruction = (
        "مصوبات را فقط از متن استخراج کن و برای هر مصوبه حداکثر دو اقدام با مسئول پیشنهاد بده."
        if generate_items
        else "مصوبات و اقدامات لازم نیست؛ آرایه‌های decisions و action_items را خالی برگردان."
    )

    user_prompt = (
        "\n".join(header_lines)
        + "\n\nمتن رونویسی جلسه:\n"
        + f"{(transcript_text or '').strip()[:60000]}\n\n"
        + f"بر پایهٔ متن بالا صورتجلسهٔ رسمی فارسی تهیه کن.{target_instruction} "
        + f"در body_markdown دو بخش داشته باش: {body_sections}. "
        + items_instruction
        + considerations_text
    )

    text, provider_key, attempts, usage = await run_chat(
        db,
        organization_id,
        system_prompt=_MINUTES_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        json_mode=True,
    )
    if text:
        try:
            payload = parse_json_object(text)
            body = _clean_text(payload.get("body_markdown"), 60000)
            if not body:
                raise AIGatewayError("پاسخ مدل زبانی متن صورتجلسه نداشت.")
            decisions = (
                [
                    {
                        "title": _clean_text(item.get("title"), 300),
                        "description": _clean_text(item.get("description"), 1500),
                    }
                    for item in (payload.get("decisions") or [])
                    if isinstance(item, dict) and _clean_text(item.get("title"), 300)
                ]
                if generate_items
                else []
            )
            actions = (
                [
                    {
                        "title": _clean_text(item.get("title"), 300),
                        "description": _clean_text(item.get("description"), 1500),
                        "owner_name": _clean_text(item.get("owner_name"), 120),
                        # تاریخ فقط وقتی می‌آید که در جلسه صریح گفته شده باشد؛
                        # در غیر این صورت خالی می‌ماند و دبیر آن را ثبت می‌کند.
                        "due_date": _clean_text(item.get("due_date"), 40),
                        "due_hint": _clean_text(item.get("due_hint"), 120),
                    }
                    for item in (payload.get("action_items") or [])
                    if isinstance(item, dict) and _clean_text(item.get("title"), 300)
                ]
                if generate_items
                else []
            )
            row_model = ""
            for row in await enabled_providers(db, organization_id, KIND_LLM):
                if (row.provider_key or "") == provider_key:
                    row_model = row.model or ""
                    break
            tokens_in = int(usage.get("tokens_in") or 0)
            tokens_out = int(usage.get("tokens_out") or 0)
            from services.ai_usage import cost_cents_for

            return (
                MinutesDraftResult(
                    summary=_clean_text(payload.get("summary"), 1500),
                    body_markdown=body,
                    decisions=decisions[:12],
                    action_items=actions[:20],
                    model=f"{provider_key}:{row_model}" if row_model else provider_key,
                    provider_key=provider_key or "",
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    cost_cents=cost_cents_for(provider_key, tokens_in, tokens_out),
                ),
                attempts,
            )
        except AIGatewayError as exc:
            attempts.append({"provider": provider_key, "ok": False, "error": str(exc)})
            logger.warning("پاسخ مدل زبانی %s قابل استفاده نبود: %s", provider_key, exc)

    try:
        draft = await get_minutes_port().draft(
            meeting_title=meeting_title,
            meeting_type=meeting_type,
            agenda_titles=agenda_titles,
            attendee_names=attendee_names,
            transcript_text=transcript_text,
        )
        attempts.append({"provider": PLATFORM_PROVIDER, "ok": True, "error": ""})
        return draft, attempts
    except Exception as exc:
        attempts.append({"provider": PLATFORM_PROVIDER, "ok": False, "error": str(exc)[:200]})
        raise AIGatewayError(
            "هیچ‌یک از مدل‌های زبانی پاسخ معتبر ندادند. " + format_attempts(attempts)
        ) from exc


def parse_json_object(text: str) -> Dict[str, Any]:
    """استخراج شیء JSON از پاسخ مدل زبانی (با یا بدون بلوک کد)."""
    cleaned = (text or "").strip()
    cleaned = re.sub(r"^```[a-zA-Z]*", "", cleaned).strip()
    cleaned = re.sub(r"```$", "", cleaned).strip()
    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", cleaned)
        if not match:
            raise AIGatewayError("پاسخ مدل زبانی قابل تفسیر نبود.")
        try:
            payload = json.loads(match.group(0))
        except json.JSONDecodeError as exc:
            raise AIGatewayError("پاسخ مدل زبانی قابل تفسیر نبود.") from exc
    if not isinstance(payload, dict):
        raise AIGatewayError("پاسخ مدل زبانی ساختار مورد انتظار را ندارد.")
    return payload
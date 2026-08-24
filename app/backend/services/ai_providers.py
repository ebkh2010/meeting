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
        "note": "سازگار با OpenAI؛ مقرون‌به‌صرفه برای تهیهٔ پیش‌نویس صورتجلسه.",
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


async def ensure_defaults(db: AsyncSession, organization_id: int) -> List[Org_ai_providers]:
    """ساخت ردیف‌های پیش‌فرض تنظیمات برای سازمان (یک‌بار، بی‌اثر در فراخوان دوباره).

    ردیف سرویس «حرف» با اعتبارنامهٔ پیش‌فرض ساخته می‌شود تا رونویسی برای هر
    سازمانِ تازه‌ثبت‌نام‌کرده بدون هیچ پیکربندی فعال باشد؛ ردیف‌های «حرف»
    دست‌نخوردهٔ قدیمی (بدون نام کاربری و رمز) هم به همین پیش‌فرض منتقل می‌شوند.
    """
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
    # پشتیبانی از ردیف‌های «حرف» قدیمی که بدون اعتبارنامه ساخته شده‌اند
    changed = False
    for row in rows:
        if _harf_unconfigured(row):
            _apply_default_harf(row)
            changed = True
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
) -> str:
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
    choices = payload.get("choices") or []
    if not choices:
        raise AIGatewayError("مدل زبانی پاسخی برنگرداند.")
    content = ((choices[0] or {}).get("message") or {}).get("content") or ""
    text = str(content).strip()
    if not text:
        raise AIGatewayError("مدل زبانی پاسخ خالی برگرداند.")
    return text


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
) -> Tuple[str, str, List[Dict[str, Any]]]:
    """فراخوان مدل زبانی با زنجیرهٔ اولویت سازمان؛ متن خام و نام تأمین‌کننده برمی‌گردد."""
    attempts: List[Dict[str, Any]] = []
    rows = await enabled_providers(db, organization_id, KIND_LLM)
    for row in rows:
        try:
            text = await openai_chat(
                row, system_prompt=system_prompt, user_prompt=user_prompt, json_mode=json_mode
            )
            attempts.append({"provider": row.provider_key, "ok": True, "error": ""})
            return text, row.provider_key or "", attempts
        except AIGatewayError as exc:
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)})
            logger.warning("مدل زبانی %s ناموفق بود: %s", row.provider_key, exc)
        except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
            attempts.append({"provider": row.provider_key, "ok": False, "error": str(exc)[:200]})
            logger.exception("خطای مدل زبانی %s", row.provider_key)
    return "", "", attempts


_MINUTES_SYSTEM_PROMPT = (
    "تو دبیر حرفه‌ای جلسات سازمانی هستی و صورتجلسهٔ رسمی فارسی می‌نویسی. "
    "فقط یک شیء JSON معتبر برگردان، بدون هیچ توضیح اضافه و بدون بلوک کد. "
    "کلیدهای لازم: summary (رشته)، body_markdown (رشته با تیترهای مارک‌داون)، "
    "decisions (آرایه‌ای از اشیا با کلیدهای title و description)، "
    "action_items (آرایه‌ای از اشیا با کلیدهای title، owner_name و due_hint). "
    "مقدار owner_name باید یکی از نام‌های حاضر در جلسه باشد؛ اگر مسئول مشخص نیست، رشتهٔ خالی بگذار. "
    "due_hint یک عبارت کوتاه زمانی فارسی مثل «تا دو هفته» است. "
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
) -> Tuple[Any, List[Dict[str, Any]]]:
    """پیش‌نویس صورتجلسه با زنجیرهٔ مدل زبانی سازمان و بازگشت به آداپتر پلتفرم.

    ابتدا مدل‌های زبانی فعال سازمان به ترتیب ``priority`` امتحان می‌شوند؛ اگر
    هیچ‌کدام پیکربندی/پاسخ معتبر نداشت، آداپتر پلتفرم اجرا می‌شود تا قابلیت
    هرگز از کار نیفتد. فهرست تلاش‌ها برای ثبت در نتیجهٔ کار برگردانده می‌شود.
    """
    agenda_text = "\n".join(f"- {title}" for title in agenda_titles) or "- (دستور جلسه ثبت نشده)"
    attendees_text = "، ".join(attendee_names) or "(فهرست حاضران ثبت نشده)"
    user_prompt = (
        f"عنوان جلسه: {meeting_title}\n"
        f"نوع جلسه: {meeting_type or 'نامشخص'}\n"
        f"حاضران: {attendees_text}\n"
        f"دستور جلسه:\n{agenda_text}\n\n"
        "متن رونویسی جلسه:\n"
        f"{(transcript_text or '').strip()[:14000]}\n\n"
        "بر پایهٔ متن بالا صورتجلسهٔ رسمی فارسی تهیه کن. در body_markdown دو بخش داشته باش: "
        "«## جمع‌بندی جلسه» و «## مذاکرات بر پایهٔ دستور جلسه». "
        "مصوبات را فقط از متن استخراج کن و برای هر مصوبه حداکثر دو اقدام با مسئول پیشنهاد بده."
    )

    text, provider_key, attempts = await run_chat(
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
            decisions = [
                {
                    "title": _clean_text(item.get("title"), 300),
                    "description": _clean_text(item.get("description"), 1500),
                }
                for item in (payload.get("decisions") or [])
                if isinstance(item, dict) and _clean_text(item.get("title"), 300)
            ]
            actions = [
                {
                    "title": _clean_text(item.get("title"), 300),
                    "owner_name": _clean_text(item.get("owner_name"), 120),
                    "due_hint": _clean_text(item.get("due_hint"), 120),
                }
                for item in (payload.get("action_items") or [])
                if isinstance(item, dict) and _clean_text(item.get("title"), 300)
            ]
            row_model = ""
            for row in await enabled_providers(db, organization_id, KIND_LLM):
                if (row.provider_key or "") == provider_key:
                    row_model = row.model or ""
                    break
            return (
                MinutesDraftResult(
                    summary=_clean_text(payload.get("summary"), 1500),
                    body_markdown=body,
                    decisions=decisions[:12],
                    action_items=actions[:20],
                    model=f"{provider_key}:{row_model}" if row_model else provider_key,
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
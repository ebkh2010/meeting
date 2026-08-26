"""لایهٔ AI Gateway با الگوی Port/Adapter.

سند معماری (بخش ۶) دو درگاه تعریف می‌کند:

* ``TranscriptionPort`` — تبدیل گفتار به نوشتار.
* ``MinutesDraftPort`` — پیش‌نویس صورتجلسه + استخراج مصوبات و اقدامات در یک فراخوان.

در نسخهٔ نمایشی، آداپتر پلتفرم (``AtomsTranscriptionAdapter`` / ``AtomsMinutesAdapter``)
فعال است. آداپتر «حرف» (Roshan AI) در همان interface پیاده‌سازی شده ولی غیرفعال است،
چون کلید API آن هنوز در اختیار نیست؛ فعال‌سازی آن فقط با تنظیم متغیرهای محیطی
``HARF_API_TOKEN`` و ``TRANSCRIPTION_PROVIDER=harf`` انجام می‌شود و به هیچ تغییری در
لایهٔ دامنه نیاز ندارد.

کلید API هیچ سرویس AI به فرانت‌اند نمی‌رسد؛ همهٔ فراخوان‌ها سمت سرور انجام می‌شود.
"""

from __future__ import annotations

import json
import logging
import math
import os
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from schemas.aihub import ChatMessage, GenTxtRequest, TranscribeAudioRequest
from services.aihub import AIHubService
from services.mgmt_core import MINUTES_MODEL, TRANSCRIBE_MODEL

logger = logging.getLogger(__name__)

HARF_BASE_URL = os.environ.get("HARF_BASE_URL", "https://harf.roshan-ai.ir")


class AIGatewayError(RuntimeError):
    """خطای قابل نمایش لایهٔ AI؛ پیام آن مستقیماً به کاربر نشان داده می‌شود."""


# ---------------------------------------------------------------------------
# مدل‌های انتقال داده
# ---------------------------------------------------------------------------


@dataclass
class TranscriptSegment:
    """قطعهٔ زمان‌دار رونویسی همراه برچسب گویندهٔ ناشناس (diarization).

    مقدار ``speaker`` مطابق ADR ۲۰۲۶-۰۸-۲۰ برچسب کلی مانند ``speaker_1`` است و
    هیچ دادهٔ بیومتریک یا نمونهٔ صدای ثبت‌شده‌ای لازم ندارد. اگر تأمین‌کننده
    تفکیک گوینده نداشته باشد، این مقدار رشتهٔ خالی می‌ماند.
    """

    start_ms: int
    end_ms: int
    text: str
    speaker: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "start_ms": self.start_ms,
            "end_ms": self.end_ms,
            "text": self.text,
            "speaker": self.speaker,
        }


@dataclass
class TranscriptionResult:
    """خروجی یکسان‌شدهٔ درگاه رونویسی، مستقل از تأمین‌کننده."""

    provider: str
    model: str
    full_text: str
    segments: List[TranscriptSegment] = field(default_factory=list)
    duration_seconds: int = 0
    stats_words: int = 0
    stats_known_words: int = 0
    known_word_ratio: float = 0.0

    def billable_minutes(self) -> int:
        """واحد سنجش مصرف: دقیقهٔ صوت با گرد کردن به بالا."""
        if self.duration_seconds <= 0:
            return 1
        return max(1, math.ceil(self.duration_seconds / 60))


@dataclass
class MinutesDraftResult:
    """خروجی ساختاریافتهٔ پیش‌نویس صورتجلسه."""

    summary: str
    body_markdown: str
    decisions: List[Dict[str, str]] = field(default_factory=list)
    action_items: List[Dict[str, str]] = field(default_factory=list)
    model: str = MINUTES_MODEL
    # سنجه‌های مصرف کاربر (در صورت گزارش تأمین‌کننده)
    provider_key: str = ""
    tokens_in: int = 0
    tokens_out: int = 0
    cost_cents: int = 0


# ---------------------------------------------------------------------------
# درگاه‌ها (Ports)
# ---------------------------------------------------------------------------


class TranscriptionPort(Protocol):
    """قرارداد رونویسی؛ هر تأمین‌کننده باید همین شکل را برگرداند."""

    name: str
    enabled: bool

    async def transcribe(
        self, *, audio_ref: str, duration_hint_seconds: int = 0
    ) -> TranscriptionResult: ...


class MinutesDraftPort(Protocol):
    """قرارداد تولید پیش‌نویس صورتجلسه و استخراج مصوبات."""

    name: str
    enabled: bool

    async def draft(
        self,
        *,
        meeting_title: str,
        meeting_type: str,
        agenda_titles: List[str],
        attendee_names: List[str],
        transcript_text: str,
    ) -> MinutesDraftResult: ...


# ---------------------------------------------------------------------------
# ابزار مشترک: تقسیم متن به قطعات زمان‌دار
# ---------------------------------------------------------------------------


def _split_sentences(text: str) -> List[str]:
    parts = re.split(r"(?<=[.!؟?])\s+|\n+", (text or "").strip())
    sentences = [part.strip() for part in parts if part and part.strip()]
    if sentences:
        return sentences
    return [text.strip()] if text and text.strip() else []


def build_segments(text: str, duration_seconds: int) -> List[TranscriptSegment]:
    """توزیع خطی جملات روی طول صوت تا پخش‌کنندهٔ همگام قابل استفاده باشد."""
    sentences = _split_sentences(text)
    if not sentences:
        return []
    total_chars = sum(len(sentence) for sentence in sentences) or 1
    total_ms = max(int(duration_seconds), 1) * 1000
    segments: List[TranscriptSegment] = []
    cursor = 0
    for index, sentence in enumerate(sentences):
        share = int(total_ms * (len(sentence) / total_chars))
        end = total_ms if index == len(sentences) - 1 else min(cursor + max(share, 800), total_ms)
        segments.append(TranscriptSegment(start_ms=cursor, end_ms=end, text=sentence))
        cursor = end
    return segments


def _quality_stats(text: str) -> Dict[str, Any]:
    """سیگنال کیفیت رونویسی: نسبت واژه‌های شناخته‌شده (بدون کروشهٔ واژهٔ مشکوک)."""
    words = [word for word in re.split(r"\s+", (text or "").strip()) if word]
    total = len(words)
    suspicious = sum(1 for word in words if "[" in word or "]" in word)
    known = max(total - suspicious, 0)
    ratio = round(known / total, 4) if total else 0.0
    return {"stats_words": total, "stats_known_words": known, "known_word_ratio": ratio}


# ---------------------------------------------------------------------------
# آداپتر فعال: پلتفرم Atoms
# ---------------------------------------------------------------------------


class AtomsTranscriptionAdapter:
    """رونویسی با مدل ``scribe_v2`` پلتفرم (آداپتر فعال نسخهٔ نمایشی)."""

    name = "atoms_platform"
    enabled = True

    def __init__(self, service: Optional[AIHubService] = None) -> None:
        self._service = service or AIHubService()

    async def transcribe(
        self, *, audio_ref: str, duration_hint_seconds: int = 0
    ) -> TranscriptionResult:
        try:
            response = await self._service.transcribe(
                TranscribeAudioRequest(audio=audio_ref, model=TRANSCRIBE_MODEL)
            )
        except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
            logger.exception("رونویسی صوت ناموفق بود")
            raise AIGatewayError(
                "رونویسی فایل صوتی انجام نشد. لطفاً چند لحظه بعد دوباره تلاش کنید."
            ) from exc

        text = (getattr(response, "text", "") or "").strip()
        if not text:
            raise AIGatewayError(
                "متنی از فایل صوتی استخراج نشد. کیفیت صدا یا زبان گفتار را بررسی کنید."
            )
        duration = max(int(duration_hint_seconds or 0), 0)
        stats = _quality_stats(text)
        return TranscriptionResult(
            provider=self.name,
            model=TRANSCRIBE_MODEL,
            full_text=text,
            segments=build_segments(text, duration or max(len(text.split()) // 2, 30)),
            duration_seconds=duration or max(len(text.split()) // 2, 30),
            stats_words=stats["stats_words"],
            stats_known_words=stats["stats_known_words"],
            known_word_ratio=stats["known_word_ratio"],
        )


class HarfTranscriptionAdapter:
    """آداپتر «حرف» (Roshan AI) — پیاده‌سازی جایگزین، در نسخهٔ نمایشی غیرفعال.

    مطابق ADR ۱۳ سند معماری، الگوی این سرویس ``wait=false`` به‌همراه پایدارسازی
    ``task_ids`` و polling است (webhook ندارد). چون کلید API در اختیار نیست، این
    آداپتر تنها ثبت شده و فراخوانی آن با خطای روشن رد می‌شود تا هیچ مسیر کاری
    ساکت شکسته نماند.
    """

    name = "harf"

    def __init__(self) -> None:
        self.api_token = os.environ.get("HARF_API_TOKEN", "")
        self.base_url = HARF_BASE_URL

    @property
    def enabled(self) -> bool:
        return bool(self.api_token)

    async def transcribe(
        self, *, audio_ref: str, duration_hint_seconds: int = 0
    ) -> TranscriptionResult:
        raise AIGatewayError(
            "سرویس رونویسی «حرف» در این نسخهٔ نمایشی فعال نیست. "
            "برای فعال‌سازی باید کلید API آن در تنظیمات سرور ثبت شود."
        )


# ---------------------------------------------------------------------------
# آداپتر پیش‌نویس صورتجلسه
# ---------------------------------------------------------------------------

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


def _extract_json_block(text: str) -> str:
    content = (text or "").strip()
    if content.startswith("```"):
        match = re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL)
        if match:
            content = match.group(1).strip()
    start = content.find("{")
    end = content.rfind("}")
    if start != -1 and end != -1 and end > start:
        content = content[start : end + 1]
    return content.strip()


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


class AtomsMinutesAdapter:
    """پیش‌نویس صورتجلسه + مصوبات + اقدامات در یک فراخوان با ``gpt-5.6-sol``."""

    name = "atoms_platform"
    enabled = True

    def __init__(self, service: Optional[AIHubService] = None) -> None:
        self._service = service or AIHubService()

    async def draft(
        self,
        *,
        meeting_title: str,
        meeting_type: str,
        agenda_titles: List[str],
        attendee_names: List[str],
        transcript_text: str,
    ) -> MinutesDraftResult:
        agenda_text = "\n".join(f"- {title}" for title in agenda_titles) or "- (دستور جلسه ثبت نشده)"
        attendees_text = "، ".join(attendee_names) or "(فهرست حاضران ثبت نشده)"
        excerpt = (transcript_text or "").strip()[:14000]

        user_prompt = (
            f"عنوان جلسه: {meeting_title}\n"
            f"نوع جلسه: {meeting_type or 'نامشخص'}\n"
            f"حاضران: {attendees_text}\n"
            f"دستور جلسه:\n{agenda_text}\n\n"
            "متن رونویسی جلسه:\n"
            f"{excerpt}\n\n"
            "بر پایهٔ متن بالا صورتجلسهٔ رسمی فارسی تهیه کن. در body_markdown دو بخش داشته باش: "
            "«## جمع‌بندی جلسه» و «## مذاکرات بر پایهٔ دستور جلسه». "
            "مصوبات را فقط از متن استخراج کن و برای هر مصوبه حداکثر دو اقدام با مسئول پیشنهاد بده."
        )

        payload = await self._request_json(user_prompt)
        decisions: List[Dict[str, str]] = []
        for item in payload.get("decisions") or []:
            if not isinstance(item, dict):
                continue
            title = _as_text(item.get("title"))
            if title:
                decisions.append({"title": title[:300], "description": _as_text(item.get("description"))[:1500]})

        actions: List[Dict[str, str]] = []
        for item in payload.get("action_items") or []:
            if not isinstance(item, dict):
                continue
            title = _as_text(item.get("title"))
            if title:
                actions.append(
                    {
                        "title": title[:300],
                        "owner_name": _as_text(item.get("owner_name"))[:120],
                        "due_hint": _as_text(item.get("due_hint"))[:120],
                    }
                )

        body = _as_text(payload.get("body_markdown"))
        summary = _as_text(payload.get("summary"))
        if not body:
            raise AIGatewayError(
                "پیش‌نویس صورتجلسه ساخته نشد. لطفاً دوباره تلاش کنید."
            )
        return MinutesDraftResult(
            summary=summary[:1500],
            body_markdown=body,
            decisions=decisions[:12],
            action_items=actions[:20],
            model=MINUTES_MODEL,
        )

    async def _request_json(self, user_prompt: str) -> Dict[str, Any]:
        """تولید غیرجریانی + استخراج JSON + یک تلاش ترمیم (قاعدهٔ خروجی ساختاریافته)."""
        raw = await self._gentxt(_MINUTES_SYSTEM_PROMPT, user_prompt)
        parsed = self._safe_parse(raw)
        if parsed is None:
            repaired = await self._gentxt(
                "این متن را به یک شیء JSON معتبر تبدیل کن و فقط JSON برگردان.",
                raw[:12000],
            )
            parsed = self._safe_parse(repaired)
        if parsed is None:
            raise AIGatewayError(
                "خروجی هوش مصنوعی قابل پردازش نبود. لطفاً دوباره تلاش کنید."
            )
        return parsed

    async def _gentxt(self, system_prompt: str, user_prompt: str) -> str:
        try:
            response = await self._service.gentxt(
                GenTxtRequest(
                    messages=[
                        ChatMessage(role="system", content=system_prompt),
                        ChatMessage(role="user", content=user_prompt),
                    ],
                    model=MINUTES_MODEL,
                    stream=False,
                    temperature=0.3,
                    max_tokens=4096,
                )
            )
        except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
            logger.exception("تولید پیش‌نویس صورتجلسه ناموفق بود")
            raise AIGatewayError(
                "ارتباط با سرویس هوش مصنوعی برقرار نشد. لطفاً دوباره تلاش کنید."
            ) from exc
        return (getattr(response, "content", "") or "").strip()

    @staticmethod
    def _safe_parse(raw: str) -> Optional[Dict[str, Any]]:
        if not raw:
            return None
        try:
            data = json.loads(_extract_json_block(raw))
        except (json.JSONDecodeError, ValueError):
            return None
        return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# انتخاب آداپتر فعال
# ---------------------------------------------------------------------------


def get_transcription_port() -> TranscriptionPort:
    """انتخاب تأمین‌کنندهٔ رونویسی بر پایهٔ تنظیمات سرور (پیش‌فرض: پلتفرم)."""
    provider = (os.environ.get("TRANSCRIPTION_PROVIDER") or "atoms_platform").strip().lower()
    if provider == "harf":
        harf = HarfTranscriptionAdapter()
        if harf.enabled:
            return harf
        logger.warning("تأمین‌کنندهٔ «حرف» انتخاب شده ولی کلید API ندارد؛ بازگشت به آداپتر پلتفرم.")
    return AtomsTranscriptionAdapter()


def get_minutes_port() -> MinutesDraftPort:
    return AtomsMinutesAdapter()


def transcription_providers_status() -> List[Dict[str, Any]]:
    """وضعیت تأمین‌کنندگان برای نمایش در کنسول ادمین."""
    harf = HarfTranscriptionAdapter()
    active = get_transcription_port()
    return [
        {
            "name": "atoms_platform",
            "label": "پلتفرم Atoms",
            "model": TRANSCRIBE_MODEL,
            "enabled": True,
            "active": active.name == "atoms_platform",
            "note": "آداپتر فعال نسخهٔ نمایشی",
        },
        {
            "name": "harf",
            "label": "حرف (Roshan AI)",
            "model": "harf-transcribe",
            "enabled": harf.enabled,
            "active": active.name == "harf",
            "note": "پیاده‌سازی جایگزین در همان interface؛ نیازمند ثبت کلید API",
        },
    ]
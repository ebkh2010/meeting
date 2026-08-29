"""گوینده‌های جلسه: تجمیع برچسب‌های diarization، نام‌گذاری توسط کاربر و کلیپ صوتی.

رونویسی «حرف» با تفکیک گوینده، قطعه‌هایی با برچسب کلی مانند ``SPEAKER_0``
برمی‌گرداند. این سرویس:

* برچسب‌ها را به ردیف‌های ``meeting_speakers`` تبدیل می‌کند (idempotent)؛
* نام دلخواه کاربر را روی هر گوینده نگه می‌دارد؛
* برای شناسایی گوینده، یک کلیپ کوتاه (چند ثانیه از صحبت همان گوینده) با
  ffmpeg از فایل صوتی اصلی می‌بُرد و در فضای ذخیرهٔ خصوصی نگه می‌دارد.
"""
from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from typing import Any, Dict, List, Optional, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.meeting_speakers import Meeting_speakers
from models.recordings import Recordings
from models.transcripts import Transcripts
from schemas.storage import FileUpDownRequest
from services.storage import StorageService

logger = logging.getLogger(__name__)

CLIP_BUCKET = "meeting-audio"
CLIP_MIN_MS = 3000
CLIP_MAX_MS = 10000
CLIP_PADDING_MS = 500

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_SPEAKER_INDEX_RE = re.compile(r"speaker[_\-\s]*(\d+)", re.IGNORECASE)


def fa_digits(value: Any) -> str:
    return str(value).translate(str.maketrans("0123456789", _PERSIAN_DIGITS))


def speaker_sort_key(speaker_key: str) -> Tuple[int, str]:
    match = _SPEAKER_INDEX_RE.search(speaker_key or "")
    index = int(match.group(1)) if match else 10**9
    return index, (speaker_key or "")


def default_speaker_label(speaker_key: str) -> str:
    match = _SPEAKER_INDEX_RE.search(speaker_key or "")
    if match:
        return f"گویندهٔ {fa_digits(int(match.group(1)) + 1)}"
    return (speaker_key or "").strip() or "گوینده"


def segments_of(transcript: Optional[Transcripts]) -> List[Dict[str, Any]]:
    if transcript is None:
        return []
    import json

    try:
        segments = json.loads(transcript.segments_json or "[]")
    except (TypeError, ValueError):
        return []
    return [segment for segment in segments if isinstance(segment, dict)]


def _speaker_stats(segments: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """شمار قطعه، مجموع زمان صحبت و اولین زمان هر گوینده (به ترتیب نخستین ظهور)."""
    stats: Dict[str, Dict[str, Any]] = {}
    for segment in segments:
        key = str((segment or {}).get("speaker") or "").strip()
        if not key:
            continue
        start_ms = max(int(segment.get("start_ms") or 0), 0)
        end_ms = max(int(segment.get("end_ms") or 0), start_ms)
        entry = stats.setdefault(
            key,
            {"segment_count": 0, "total_ms": 0, "first_start_ms": start_ms, "longest": (start_ms, end_ms)},
        )
        entry["segment_count"] += 1
        entry["total_ms"] += max(end_ms - start_ms, 0)
        if start_ms < entry["first_start_ms"]:
            entry["first_start_ms"] = start_ms
        if (end_ms - start_ms) > (entry["longest"][1] - entry["longest"][0]):
            entry["longest"] = (start_ms, end_ms)
    return stats


async def ensure_meeting_speakers(
    session: AsyncSession,
    *,
    organization_id: int,
    meeting_id: int,
    transcript: Optional[Transcripts],
) -> List[Meeting_speakers]:
    """ساخت ردیف گوینده برای هر برچسب موجود در رونویسی (idempotent)."""
    segments = segments_of(transcript)
    keys = []
    for segment in segments:
        key = str((segment or {}).get("speaker") or "").strip()
        if key and key not in keys:
            keys.append(key)

    existing_result = await session.execute(
        select(Meeting_speakers).where(
            Meeting_speakers.organization_id == organization_id,
            Meeting_speakers.meeting_id == meeting_id,
        )
    )
    existing = list(existing_result.scalars().all())
    by_key = {row.speaker_key: row for row in existing}

    transcript_id = int(transcript.id) if transcript is not None else None
    created = False
    for key in keys:
        row = by_key.get(key)
        if row is None:
            row = Meeting_speakers(
                organization_id=organization_id,
                meeting_id=meeting_id,
                transcript_id=transcript_id,
                speaker_key=key,
            )
            session.add(row)
            by_key[key] = row
            created = True
        elif row.transcript_id != transcript_id and transcript_id is not None:
            # رونویسی تازه: گوینده به قطعه‌های نسخهٔ جدید پیوند می‌خورد ولی نام حفظ می‌شود.
            row.transcript_id = transcript_id
    if created or any(row.transcript_id != transcript_id for row in by_key.values()):
        await session.flush()
    return [by_key[key] for key in keys]


def speakers_payload(
    rows: List[Meeting_speakers], segments: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """خروجی گوینده‌ها: نام کاربر (در نبودش برچسب پیش‌فرض) + آمار قطعه‌ها."""
    stats = _speaker_stats(segments)
    payload: List[Dict[str, Any]] = []
    for row in rows:
        entry = stats.get(row.speaker_key, {})
        payload.append(
            {
                "id": int(row.id),
                "meeting_id": int(row.meeting_id),
                "transcript_id": row.transcript_id,
                "speaker_key": row.speaker_key,
                "display_name": (row.display_name or "").strip() or None,
                "default_label": default_speaker_label(row.speaker_key),
                "segment_count": entry.get("segment_count", 0),
                "total_ms": entry.get("total_ms", 0),
                "first_start_ms": entry.get("first_start_ms", 0),
            }
        )
    return payload


def pick_clip_window(segments: List[Dict[str, Any]], speaker_key: str) -> Optional[Tuple[int, int]]:
    """بهترین بازهٔ نمونهٔ صدا: طولانی‌ترین قطعهٔ همان گوینده + حاشیهٔ کوتاه."""
    candidates = [
        segment
        for segment in segments
        if str((segment or {}).get("speaker") or "") == speaker_key
    ]
    if not candidates:
        return None
    best = max(
        candidates,
        key=lambda segment: max(int(segment.get("end_ms") or 0), 0)
        - max(int(segment.get("start_ms") or 0), 0),
    )
    start_ms = max(int(best.get("start_ms") or 0), 0)
    end_ms = max(int(best.get("end_ms") or 0), start_ms)
    window_start = max(start_ms - CLIP_PADDING_MS, 0)
    window_end = end_ms + CLIP_PADDING_MS
    if window_end - window_start < CLIP_MIN_MS:
        window_end = window_start + CLIP_MIN_MS
    if window_end - window_start > CLIP_MAX_MS:
        window_end = window_start + CLIP_MAX_MS
    return window_start, window_end


def clip_object_key(*, organization_id: int, meeting_id: int, transcript_id: int, speaker_id: int) -> str:
    return (
        f"org-{organization_id}/meeting-{meeting_id}/speaker-clips/"
        f"tr-{transcript_id}-speaker-{speaker_id}.mp3"
    )


async def _object_exists(storage: StorageService, bucket: str, object_key: str) -> bool:
    from schemas.storage import ObjectRequest

    try:
        await storage.get_object_info(ObjectRequest(bucket_name=bucket, object_key=object_key))
        return True
    except Exception:  # pragma: no cover - هر خطایی یعنی وجود ندارد/در دسترس نیست
        return False


def _run_ffmpeg_clip(source_path: str, target_path: str, start_ms: int, end_ms: int) -> None:
    start_s = max(start_ms, 0) / 1000.0
    duration_s = max(end_ms - start_ms, 1000) / 1000.0
    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-ss",
        f"{start_s:.3f}",
        "-i",
        source_path,
        "-t",
        f"{duration_s:.3f}",
        "-vn",
        "-ar",
        "22050",
        "-ac",
        "1",
        "-b:a",
        "48k",
        target_path,
    ]
    process = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if process.returncode != 0:
        raise RuntimeError(f"ffmpeg clip failed: {process.stderr[:200]}")


async def ensure_speaker_clip(
    session: AsyncSession,
    *,
    speaker: Meeting_speakers,
    transcript: Optional[Transcripts],
    recording: Optional[Recordings],
) -> Dict[str, Any]:
    """ساخت (در صورت نیاز) کلیپ شناسایی گوینده و برگرداندن نشانی پخش امضاشده."""
    if transcript is None or recording is None:
        raise ValueError("برای ساخت کلیپ گوینده، رونویسی و فایل صوتی لازم است.")
    segments = segments_of(transcript)
    window = pick_clip_window(segments, speaker.speaker_key)
    if window is None:
        raise ValueError("قطعهٔ صوتی برای این گوینده یافت نشد.")

    storage = StorageService()
    bucket = recording.bucket_name or CLIP_BUCKET
    object_key = clip_object_key(
        organization_id=int(speaker.organization_id),
        meeting_id=int(speaker.meeting_id),
        transcript_id=int(transcript.id),
        speaker_id=int(speaker.id),
    )

    if not await _object_exists(storage, bucket, object_key):
        start_ms, end_ms = window
        # در صورت نبود رکورد ضبط با متن (رونویسی دستی) کلیپ ساخته نمی‌شود.
        if not (recording.object_key or "").strip():
            raise ValueError("فایل صوتی جلسه در فضای ذخیره‌سازی موجود نیست.")
        download = await storage.create_download_url(
            FileUpDownRequest(bucket_name=bucket, object_key=recording.object_key)
        )
        async with httpx.AsyncClient(timeout=300.0, follow_redirects=True) as client:
            response = await client.get(download.download_url)
        if response.status_code >= 400:
            raise ValueError("دریافت فایل صوتی جلسه برای ساخت کلیپ ناموفق بود.")

        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as source_file:
            source_file.write(response.content)
            source_path = source_file.name
        target_path = source_path + ".clip.mp3"
        try:
            await asyncio.to_thread(_run_ffmpeg_clip, source_path, target_path, start_ms, end_ms)
            with open(target_path, "rb") as clip_file:
                clip_bytes = clip_file.read()
        finally:
            for path in (source_path, target_path):
                try:
                    import os

                    os.unlink(path)
                except OSError:  # pragma: no cover
                    pass

        upload = await storage.create_upload_url(
            FileUpDownRequest(bucket_name=bucket, object_key=object_key)
        )
        async with httpx.AsyncClient(timeout=120.0) as client:
            put_response = await client.put(
                upload.upload_url,
                content=clip_bytes,
                headers={"Content-Type": "audio/mpeg"},
            )
        if put_response.status_code not in (200, 201, 204):
            raise ValueError("بارگذاری کلیپ گوینده در فضای ذخیره‌سازی ناموفق بود.")

    signed = await storage.create_download_url(
        FileUpDownRequest(bucket_name=bucket, object_key=object_key)
    )
    return {
        "clip_url": signed.download_url,
        "expires_at": signed.expires_at,
        "start_ms": window[0],
        "end_ms": window[1],
        "speaker_key": speaker.speaker_key,
    }

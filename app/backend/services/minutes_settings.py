"""سرویس تنظیمات تولید صورتجلسهٔ هر جلسه: خواندن idempotent و ذخیرهٔ مقادیر."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.meeting_minutes_settings import Meeting_minutes_settings

DEFAULT_USE_AGENDA = True
DEFAULT_USE_ATTENDEES = False
DEFAULT_WORDS_PER_HOUR = 1000
DEFAULT_GENERATE_ITEMS = True
MIN_WORDS_PER_HOUR = 100
MAX_WORDS_PER_HOUR = 5000
MAX_CONSIDERATIONS_CHARS = 3000


def defaults() -> Dict[str, Any]:
    return {
        "use_agenda": DEFAULT_USE_AGENDA,
        "use_attendees": DEFAULT_USE_ATTENDEES,
        "words_per_hour": DEFAULT_WORDS_PER_HOUR,
        "generate_items": DEFAULT_GENERATE_ITEMS,
        "considerations": "",
    }


async def get_settings(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> Meeting_minutes_settings:
    """خواندن idempotent تنظیمات جلسه؛ در نبود رکورد، با پیش‌فرض‌ها ساخته می‌شود."""
    result = await db.execute(
        select(Meeting_minutes_settings).where(
            Meeting_minutes_settings.organization_id == organization_id,
            Meeting_minutes_settings.meeting_id == meeting_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = Meeting_minutes_settings(
            organization_id=organization_id,
            meeting_id=meeting_id,
            use_agenda=DEFAULT_USE_AGENDA,
            use_attendees=DEFAULT_USE_ATTENDEES,
            words_per_hour=DEFAULT_WORDS_PER_HOUR,
            generate_items=DEFAULT_GENERATE_ITEMS,
            considerations="",
            updated_by_name="",
        )
        db.add(row)
        await db.flush()
    return row


def payload(row: Optional[Meeting_minutes_settings]) -> Dict[str, Any]:
    if row is None:
        return {**defaults(), "updated_by_name": ""}
    return {
        "meeting_id": int(row.meeting_id),
        "use_agenda": bool(
            row.use_agenda if row.use_agenda is not None else DEFAULT_USE_AGENDA
        ),
        "use_attendees": bool(
            row.use_attendees if row.use_attendees is not None else DEFAULT_USE_ATTENDEES
        ),
        "words_per_hour": int(row.words_per_hour or DEFAULT_WORDS_PER_HOUR),
        "generate_items": bool(
            row.generate_items if row.generate_items is not None else DEFAULT_GENERATE_ITEMS
        ),
        "considerations": row.considerations or "",
        "updated_by_name": row.updated_by_name or "",
        "bounds": {"min_words_per_hour": MIN_WORDS_PER_HOUR, "max_words_per_hour": MAX_WORDS_PER_HOUR},
    }


async def save_settings(
    db: AsyncSession,
    organization_id: int,
    meeting_id: int,
    *,
    values: Dict[str, Any],
    actor_name: str = "",
) -> Dict[str, Any]:
    """ذخیرهٔ تنظیمات جلسه با اعتبارسنجی بازه‌ها؛ مقدار None یعنی بدون تغییر."""
    row = await get_settings(db, organization_id, meeting_id)
    changes: List[str] = []

    if values.get("use_agenda") is not None:
        new_value = bool(values["use_agenda"])
        if bool(row.use_agenda if row.use_agenda is not None else DEFAULT_USE_AGENDA) != new_value:
            changes.append(f"لحاظ دستور جلسه: {'بله' if new_value else 'خیر'}")
        row.use_agenda = new_value
    if values.get("use_attendees") is not None:
        new_value = bool(values["use_attendees"])
        if bool(row.use_attendees if row.use_attendees is not None else DEFAULT_USE_ATTENDEES) != new_value:
            changes.append(f"لحاظ مدعوین: {'بله' if new_value else 'خیر'}")
        row.use_attendees = new_value
    if values.get("words_per_hour") is not None:
        new_value = int(values["words_per_hour"])
        if not MIN_WORDS_PER_HOUR <= new_value <= MAX_WORDS_PER_HOUR:
            raise ValueError(
                f"طول هدف صورتجلسه باید بین {MIN_WORDS_PER_HOUR} تا {MAX_WORDS_PER_HOUR} کلمه در ساعت باشد."
            )
        if int(row.words_per_hour or DEFAULT_WORDS_PER_HOUR) != new_value:
            changes.append(f"طول هدف: {new_value} کلمه در ساعت")
        row.words_per_hour = new_value
    if values.get("generate_items") is not None:
        new_value = bool(values["generate_items"])
        if bool(row.generate_items if row.generate_items is not None else DEFAULT_GENERATE_ITEMS) != new_value:
            changes.append(f"تولید مصوبات/اقدامات: {'بله' if new_value else 'خیر'}")
        row.generate_items = new_value
    if values.get("considerations") is not None:
        new_value = str(values["considerations"]).strip()[:MAX_CONSIDERATIONS_CHARS]
        if (row.considerations or "") != new_value:
            changes.append("ملاحظات کاربر به‌روزرسانی شد")
        row.considerations = new_value

    if changes:
        row.updated_by_name = actor_name or ""

    return payload(row)


def target_words_for(row: Optional[Meeting_minutes_settings], total_duration_seconds: int) -> int:
    """طول هدف صورتجلسه بر پایهٔ مجموع مدت صوت‌ها (ساعت، گردشده به بالا)."""
    words_per_hour = (
        int(row.words_per_hour) if row is not None and row.words_per_hour else DEFAULT_WORDS_PER_HOUR
    )
    hours = max(1, -(-max(int(total_duration_seconds or 0), 1) // 3600))  # ceil، حداقل ۱ ساعت
    return hours * words_per_hour

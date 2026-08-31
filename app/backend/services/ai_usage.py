"""سهمیه و مصرف هوش مصنوعی به‌ازای هر کاربر.

قواعد:
- سقف پیش‌فرض هر کاربر در هر دورهٔ ماهانه (``YYYY-MM``): ۵ دلار مدل زبانی
  (DeepSeek) و ۶۰۰ دقیقه رونویسی (۱۰ ساعت سرویس «حرف»).
- مصرف از روی رویدادهای ``Ai_user_usage`` همان دوره جمع می‌شود؛ بنابراین
  «بازنشانی دوره» به‌صورت طبیعی با تغییر ماه رخ می‌دهد و شمارندهٔ جداگانه
  لازم نیست.
- هزینهٔ مدل زبانی فقط برای DeepSeek محاسبه می‌شود (قیمت قابل تنظیم با متغیر
  محیطی)؛ تأمین‌کننده‌های دیگر فقط توکن شمارش می‌شوند.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.ai_user_usage import Ai_user_quotas, Ai_user_usage
from models.organizations import Organizations
from services.mgmt_core import conflict, current_period

logger = logging.getLogger(__name__)

# سقف‌های پیش‌فرض هر کاربر (قابل تغییر با متغیر محیطی)
DEFAULT_LLM_BUDGET_CENTS = int(os.environ.get("AI_USER_LLM_BUDGET_CENTS", "500"))  # ۵ دلار
DEFAULT_STT_BUDGET_MINUTES = int(os.environ.get("AI_USER_STT_BUDGET_MINUTES", "600"))  # ۱۰ ساعت

# قیمت DeepSeek به دلار برای هر میلیون توکن (deepseek-chat)
DEEPSEEK_INPUT_USD_PER_M = float(os.environ.get("DEEPSEEK_INPUT_USD_PER_M", "0.27"))
DEEPSEEK_OUTPUT_USD_PER_M = float(os.environ.get("DEEPSEEK_OUTPUT_USD_PER_M", "1.10"))

KIND_TRANSCRIBE = "transcribe"
KIND_MINUTES = "minutes_draft"
KIND_ASSISTANT = "assistant"

KIND_LABELS = {
    KIND_TRANSCRIBE: "رونویسی فایل صوتی",
    KIND_MINUTES: "پیش‌نویس صورتجلسه",
    KIND_ASSISTANT: "دستیار هوشمند",
}


def cost_cents_for(provider: str, tokens_in: int, tokens_out: int) -> int:
    """هزینهٔ یک فراخوان به سنت؛ فقط DeepSeek قیمت دارد، بقیه صفر.

    هزینهٔ واقعی گرد می‌شود و هر فراخوان موفق دست‌کم یک سنت محاسبه می‌شود تا
    سقف دلاری برای کاربر قابل فهم و پیش‌بینی‌پذیر باشد.
    """
    provider_key = (provider or "").strip().lower()
    if provider_key != "deepseek":
        return 0
    if tokens_in <= 0 and tokens_out <= 0:
        return 0
    usd = (
        tokens_in * DEEPSEEK_INPUT_USD_PER_M + tokens_out * DEEPSEEK_OUTPUT_USD_PER_M
    ) / 1_000_000
    return max(int(round(usd * 100)), 1)


def estimate_minutes_tokens(transcript_text: str, system_prompt: str = "", user_prompt: str = "") -> int:
    """برآورد محافظه‌کارانهٔ توکن ورودی (فارسی حدود دو نویسه به ازای هر توکن)."""
    chars = len(transcript_text or "") + len(system_prompt or "") + len(user_prompt or "")
    return max(int(chars / 2), 100)


async def ensure_quota_row(db: AsyncSession, organization_id: int, user_id: str) -> Ai_user_quotas:
    """ردیف سهمیهٔ کاربر؛ در نبودش با سقف پیش‌فرض ساخته می‌شود."""
    result = await db.execute(
        select(Ai_user_quotas).where(
            Ai_user_quotas.organization_id == organization_id,
            Ai_user_quotas.user_id == user_id,
        )
    )
    row = result.scalars().first()
    if row is None:
        row = Ai_user_quotas(
            organization_id=organization_id,
            user_id=user_id,
            llm_limit_cents=DEFAULT_LLM_BUDGET_CENTS,
            stt_limit_minutes=DEFAULT_STT_BUDGET_MINUTES,
        )
        db.add(row)
        await db.flush()
    return row


async def _sum_since(db: AsyncSession, model: Any, organization_id: int, user_id: str, column: Any) -> int:
    result = await db.execute(
        select(func.coalesce(func.sum(column), 0)).where(
            model.organization_id == organization_id,
            model.user_id == user_id,
            model.created_at >= _period_start(),
        )
    )
    return int(result.scalar_one() or 0)


async def _sum_org_since(db: AsyncSession, organization_id: int, column: Any) -> int:
    """مجموع مصرف یک ستون برای همهٔ کاربران سازمان در دورهٔ جاری."""
    result = await db.execute(
        select(func.coalesce(func.sum(column), 0)).where(
            Ai_user_usage.organization_id == organization_id,
            Ai_user_usage.created_at >= _period_start(),
        )
    )
    return int(result.scalar_one() or 0)


def _period_start() -> datetime:
    """شروع دورهٔ جاری (روز اول ماه میلادی) برای مقایسهٔ مستقیم با ستون زمانی."""
    return datetime.strptime(current_period() + "-01", "%Y-%m-%d")


async def usage_snapshot(db: AsyncSession, organization_id: int, user_id: str) -> Dict[str, Any]:
    """نمای سهمیهٔ کاربر جاری: سقف، مصرف و باقی‌مانده برای هر دو نوع مصرف."""
    row = await ensure_quota_row(db, organization_id, user_id)
    used_llm_cents = await _sum_since(db, Ai_user_usage, organization_id, user_id, Ai_user_usage.cost_cents)
    used_stt_minutes = await _sum_since(
        db, Ai_user_usage, organization_id, user_id, Ai_user_usage.minutes_charged
    )
    llm_limit = (
        int(row.llm_limit_cents) if row.llm_limit_cents is not None else DEFAULT_LLM_BUDGET_CENTS
    )
    stt_limit = (
        int(row.stt_limit_minutes)
        if row.stt_limit_minutes is not None
        else DEFAULT_STT_BUDGET_MINUTES
    )
    return {
        "period": current_period(),
        "llm": {
            "limit_cents": llm_limit,
            "used_cents": used_llm_cents,
            "remaining_cents": max(llm_limit - used_llm_cents, 0),
            "currency": "USD",
        },
        "stt": {
            "limit_minutes": stt_limit,
            "used_minutes": used_stt_minutes,
            "remaining_minutes": max(stt_limit - used_stt_minutes, 0),
        },
    }


async def ensure_user_budget(
    db: AsyncSession,
    organization_id: int,
    user_id: str,
    *,
    stt_minutes_needed: int = 0,
    llm_cost_cents_needed: int = 0,
) -> None:
    """بررسی سهمیهٔ کاربر پیش از شروع کار؛ در صورت ناکافی بودن خطای روشن فارسی."""
    snapshot = await usage_snapshot(db, organization_id, user_id)
    if stt_minutes_needed > 0 and snapshot["stt"]["remaining_minutes"] < stt_minutes_needed:
        raise conflict(
            "سهمیهٔ رونویسی شما برای این دوره تمام شده است. "
            f"باقی‌مانده: {snapshot['stt']['remaining_minutes']} دقیقه از "
            f"{snapshot['stt']['limit_minutes']} دقیقه؛ نیاز این کار: {stt_minutes_needed} دقیقه. "
            "برای افزایش سهمیه با مدیر سازمان یا پلتفرم تماس بگیرید."
        )
    if llm_cost_cents_needed > 0 and snapshot["llm"]["remaining_cents"] < llm_cost_cents_needed:
        raise conflict(
            "سهمیهٔ مدل زبانی شما برای این دوره تمام شده است. "
            f"باقی‌مانده: {(snapshot['llm']['remaining_cents'] / 100):.2f} دلار از "
            f"{(snapshot['llm']['limit_cents'] / 100):.2f} دلار؛ برآورد هزینهٔ این کار: "
            f"{(llm_cost_cents_needed / 100):.2f} دلار. برای افزایش سهمیه با مدیر سازمان "
            "یا پلتفرم تماس بگیرید."
        )

    # سقف دلاری کل سازمان (تنظیم‌شده توسط مدیر پلتفرم؛ خالی/صفر = بدون سقف)
    if llm_cost_cents_needed > 0:
        org_limit_result = await db.execute(
            select(Organizations.ai_llm_limit_cents).where(
                Organizations.id == organization_id
            )
        )
        org_limit = int(org_limit_result.scalars().first() or 0)
        if org_limit > 0:
            org_used = await _sum_org_since(db, organization_id, Ai_user_usage.cost_cents)
            if org_used + llm_cost_cents_needed > org_limit:
                raise conflict(
                    "سهمیهٔ مدل زبانی سازمان برای این دوره تمام شده است. "
                    f"مصرف کل سازمان: {(org_used / 100):.2f} دلار از {(org_limit / 100):.2f} دلار. "
                    "برای افزایش سهمیه با مدیر پلتفرم تماس بگیرید."
                )


async def record_user_usage(
    db: AsyncSession,
    *,
    organization_id: int,
    user_id: str,
    kind: str,
    provider: str,
    model: str,
    minutes: int = 0,
    tokens_in: int = 0,
    tokens_out: int = 0,
    cost_cents: int = 0,
    job_id: Optional[int] = None,
    meeting_id: Optional[int] = None,
    detail: str = "",
) -> None:
    """ثبت مصرف واقعی یک کار AI برای کاربر مشخص."""
    if not user_id:
        return
    db.add(
        Ai_user_usage(
            organization_id=int(organization_id),
            user_id=str(user_id),
            job_id=job_id,
            meeting_id=meeting_id,
            kind=kind,
            provider=provider,
            model=model,
            minutes_charged=max(minutes, 0) if minutes else None,
            tokens_in=max(tokens_in, 0) if tokens_in else None,
            tokens_out=max(tokens_out, 0) if tokens_out else None,
            cost_cents=max(cost_cents, 0),
            detail=(detail or "")[:900],
        )
    )


async def recent_user_usage(
    db: AsyncSession, organization_id: int, user_id: str, limit: int = 20
) -> List[Dict[str, Any]]:
    """آخرین رویدادهای مصرف کاربر برای نمایش در پنل."""
    result = await db.execute(
        select(Ai_user_usage)
        .where(
            Ai_user_usage.organization_id == organization_id,
            Ai_user_usage.user_id == user_id,
        )
        .order_by(Ai_user_usage.id.desc())
        .limit(limit)
    )
    events = []
    for item in result.scalars().all():
        events.append(
            {
                "id": int(item.id),
                "kind": item.kind,
                "kind_label": KIND_LABELS.get(item.kind, item.kind),
                "provider": item.provider,
                "model": item.model,
                "minutes_charged": int(item.minutes_charged or 0),
                "tokens_in": int(item.tokens_in or 0),
                "tokens_out": int(item.tokens_out or 0),
                "cost_cents": int(item.cost_cents or 0),
                "detail": item.detail,
                "job_id": int(item.job_id) if item.job_id else None,
                "meeting_id": int(item.meeting_id) if item.meeting_id else None,
                "created_at": item.created_at.strftime("%Y-%m-%dT%H:%M:%SZ") if item.created_at else "",
            }
        )
    return events

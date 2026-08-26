"""روتر «دستیار هوشمند» سازمان — فقط برای مدیر سازمان و دبیر جلسه.

قواعد دسترسی و مصرف:

* دسترسی با ``resolve_context`` + ``require_role(ROLE_ADMIN, ROLE_SECRETARY)`` کنترل
  می\u200cشود؛ نقش «عضو» پاسخ ۴۰۳ با پیام فارسی می\u200cگیرد.
* همهٔ بازیابی\u200cها با ``organization_id`` نشست جاری محدود است، پس محتوای سازمان دیگر
  هرگز به context مدل نمی\u200cرسد.
* تولید پاسخ از زنجیرهٔ مدل زبانی همان سازمان (``org_ai_providers``) با اولویت و
  fallback عبور می\u200cکند؛ اگر هیچ مدل فعالی نباشد، پاسخ راهنما و نتایج جست\u200cوجو
  برگردانده می\u200cشود، نه خطای خام.
* هر فراخوان در Audit Log و در رویدادهای مصرف AI (بدون کسر سهمیهٔ دقیقهٔ صوت) ثبت می\u200cشود.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from core.database import get_db
from dependencies.app_auth import get_app_principal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from services import ai_providers, ai_usage, app_auth, assistant
from services.mgmt_core import (
    ROLE_ADMIN,
    ROLE_SECRETARY,
    TenantContext,
    audit,
    bad_request,
    record_usage,
    require_role,
    resolve_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/assistant", tags=["assistant"])


class AskIn(BaseModel):
    mode: str = assistant.MODE_MEETINGS
    question: str = ""


async def _guarded_context(db: AsyncSession, principal: app_auth.AppPrincipal) -> TenantContext:
    """زمینهٔ مستأجر با گارد نقش؛ «عضو» اجازهٔ استفاده از دستیار را ندارد."""
    ctx = await resolve_context(db, principal)
    require_role(ctx, ROLE_ADMIN, ROLE_SECRETARY)
    return ctx


@router.get("/status")
async def assistant_status(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """وضعیت آمادگی دستیار: حالت\u200cها و اینکه مدل زبانی فعالی وجود دارد یا نه."""
    ctx = await _guarded_context(db, principal)
    rows = await ai_providers.enabled_providers(db, ctx.organization_id, ai_providers.KIND_LLM)
    return {
        "available": bool(rows),
        "role": ctx.role,
        "modes": [
            {"value": mode, "label": assistant.MODE_LABELS[mode]} for mode in assistant.ALL_MODES
        ],
        "llm_providers": [
            {"provider_key": row.provider_key or "", "display_name": row.display_name or "", "model": row.model or ""}
            for row in rows
        ],
        "hint": (
            ""
            if rows
            else "هیچ مدل زبانی فعالی برای این سازمان ثبت نشده است. از «تنظیمات ← هوش مصنوعی» یک مدل زبانی را با کلید معتبر فعال کنید."
        ),
    }


@router.post("/ask")
async def assistant_ask(
    data: AskIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """پرسش از دستیار در یکی از دو حالت «محتوای جلسات» یا «راهنمای سامانه»."""
    ctx = await _guarded_context(db, principal)

    mode = (data.mode or assistant.MODE_MEETINGS).strip()
    if mode not in assistant.ALL_MODES:
        raise bad_request("حالت انتخاب\u200cشدهٔ دستیار معتبر نیست.")
    question = (data.question or "").strip()
    if len(question) < 3:
        raise bad_request("پرسش خود را کمی کامل\u200cتر بنویسید (دست\u200cکم سه نویسه).")
    if len(question) > 1000:
        question = question[:1000]

    chunks: List[assistant.Chunk] = (
        assistant.search_guide(question)
        if mode == assistant.MODE_GUIDE
        else await assistant.search_meetings(db, ctx, question)
    )

    answer = ""
    provider_key = ""
    usage: Dict[str, int] = {"tokens_in": 0, "tokens_out": 0}
    attempts: List[Dict[str, Any]] = []
    model_available = True

    if chunks:
        prompt = assistant.build_prompt(mode, question, chunks, ctx)
        estimated = ai_usage.estimate_minutes_tokens(
            "", system_prompt=prompt["system"], user_prompt=prompt["user"]
        )
        estimated_cost = ai_usage.cost_cents_for("deepseek", estimated, 500)
        budget_ok = True
        try:
            await ai_usage.ensure_user_budget(
                db,
                ctx.organization_id,
                ctx.user_id,
                llm_cost_cents_needed=estimated_cost,
            )
        except Exception:
            # سهمیهٔ کاربر تمام شده؛ دستیار با پاسخ راهنما ادامه می‌دهد تا از کار نیفتد.
            budget_ok = False
        if budget_ok:
            try:
                answer, provider_key, attempts, usage = await ai_providers.run_chat(
                    db,
                    ctx.organization_id,
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                )
            except Exception as exc:  # pragma: no cover - وابسته به سرویس بیرونی
                logger.exception("فراخوان دستیار هوشمند ناموفق بود")
                attempts = [{"provider": "llm", "ok": False, "error": str(exc)[:200]}]
                answer = ""

    if not answer:
        model_available = False
        answer = assistant.fallback_answer(mode, chunks)

    if provider_key:
        await record_usage(
            db,
            ctx.organization,
            kind="assistant",
            provider=provider_key,
            model="",
            minutes=0,
            detail=f"دستیار هوشمند ({assistant.MODE_LABELS[mode]}): {question[:160]}",
        )
        await ai_usage.record_user_usage(
            db,
            organization_id=ctx.organization_id,
            user_id=ctx.user_id,
            kind=ai_usage.KIND_ASSISTANT,
            provider=provider_key,
            model="",
            tokens_in=int(usage.get("tokens_in") or 0),
            tokens_out=int(usage.get("tokens_out") or 0),
            cost_cents=ai_usage.cost_cents_for(
                provider_key, int(usage.get("tokens_in") or 0), int(usage.get("tokens_out") or 0)
            ),
            detail=f"دستیار هوشمند ({assistant.MODE_LABELS[mode]}): {question[:160]}",
        )

    await audit(
        db,
        ctx,
        "assistant.ask",
        entity_type="assistant",
        entity_id=None,
        detail=(
            f"حالت: {assistant.MODE_LABELS[mode]} — پرسش: {question[:200]} — "
            f"منابع: {len(chunks)} — تأمین\u200cکننده: {provider_key or 'بدون مدل فعال'}"
            + (f" — تلاش\u200cها: {ai_providers.format_attempts(attempts)}" if attempts else "")
        ),
    )
    await db.commit()

    return {
        "mode": mode,
        "mode_label": assistant.MODE_LABELS[mode],
        "question": question,
        "answer": answer,
        "provider": provider_key,
        "model_available": model_available,
        "sources": [chunk.payload() for chunk in chunks],
        "attempts_note": ai_providers.format_attempts(attempts) if attempts else "",
    }
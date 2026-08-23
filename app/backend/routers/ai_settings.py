"""روتر تنظیمات هوش مصنوعی سازمان (STT و مدل زبانی) با اولویت، fallback و تست واقعی.

قواعد دسترسی:

* خواندن/نوشتن تنظیمات فقط برای **مدیر سازمان** مجاز است (``get_app_admin``).
* هیچ کلید API خامی از این روتر بازنمی‌گردد؛ فقط نمای ماسک‌شده.
* همهٔ کوئری‌ها با ``organization_id`` کاربر جاری محدود می‌شوند تا مرز مستأجر حفظ شود.
* هر تغییر و هر تست اتصال در Audit Log ثبت می‌شود.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.app_auth import get_app_admin
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.org_ai_providers import Org_ai_providers
from services import ai_providers, app_auth
from services.mgmt_core import audit, resolve_context

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/ai-settings", tags=["ai-settings"])


class ProviderUpdateIn(BaseModel):
    enabled: Optional[bool] = None
    priority: Optional[int] = None
    base_url: Optional[str] = None
    model: Optional[str] = None
    diarization: Optional[bool] = None
    auth_username: Optional[str] = None
    api_key: Optional[str] = None
    password: Optional[str] = None
    clear_api_key: Optional[bool] = None
    clear_password: Optional[bool] = None


async def _load_row(
    db: AsyncSession, organization_id: int, provider_id: int
) -> Org_ai_providers:
    result = await db.execute(
        select(Org_ai_providers).where(
            Org_ai_providers.id == provider_id,
            Org_ai_providers.organization_id == organization_id,
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise app_auth.bad_request("تنظیمات این سرویس در سازمان شما یافت نشد.")
    return row


@router.get("/providers")
async def list_providers(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست تنظیمات AI سازمان به‌همراه راهنمای تأمین‌کنندگان پشتیبانی‌شده."""
    rows = await ai_providers.ensure_defaults(db, principal.organization_id)
    payload: Dict[str, List[Dict[str, Any]]] = {kind: [] for kind in ai_providers.ALL_KINDS}
    for row in rows:
        if row.kind in payload:
            payload[row.kind].append(ai_providers.provider_payload(row))
    for kind in payload:
        payload[kind].sort(key=lambda item: (item["priority"], item["id"]))
    await db.commit()
    return {
        "stt": payload[ai_providers.KIND_STT],
        "llm": payload[ai_providers.KIND_LLM],
        "catalog": ai_providers.catalog_payload(),
    }


@router.patch("/providers/{provider_id}")
async def update_provider(
    provider_id: int,
    data: ProviderUpdateIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ذخیرهٔ تنظیمات یک تأمین‌کننده؛ کلید خالی یعنی «کلید فعلی بدون تغییر»."""
    await ai_providers.ensure_defaults(db, principal.organization_id)
    row = await _load_row(db, principal.organization_id, provider_id)
    payload = data.model_dump(exclude_unset=True)
    ai_providers.apply_update(row, payload)

    if row.enabled and not ai_providers._has_credentials(row):
        raise app_auth.bad_request(
            "برای فعال‌سازی این سرویس ابتدا کلید API (یا نام کاربری و رمز عبور) را ثبت کنید."
        )

    changed = ", ".join(sorted(key for key in payload if key not in ("api_key", "password")))
    secret_changed = bool(payload.get("api_key") or payload.get("password"))
    ctx = await resolve_context(db, principal)
    await audit(
        db,
        ctx,
        "ai_provider.update",
        entity_type="org_ai_provider",
        entity_id=int(row.id),
        detail=(
            f"تنظیمات سرویس «{row.display_name or row.provider_key}» به‌روزرسانی شد"
            + (f" (فیلدها: {changed})" if changed else "")
            + ("، کلید دسترسی تغییر کرد" if secret_changed else "")
        ),
    )
    result = ai_providers.provider_payload(row)
    await db.commit()
    return result


@router.post("/providers/{provider_id}/test")
async def test_provider(
    provider_id: int,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تست اتصال واقعی به سرویس با اعتبارنامهٔ ذخیره‌شدهٔ همان سازمان."""
    await ai_providers.ensure_defaults(db, principal.organization_id)
    row = await _load_row(db, principal.organization_id, provider_id)
    ok, message = await ai_providers.test_provider(row)
    ai_providers.record_test_result(row, ok, message)
    ctx = await resolve_context(db, principal)
    state_label = "موفق" if ok else "ناموفق"
    await audit(
        db,
        ctx,
        "ai_provider.test",
        entity_type="org_ai_provider",
        entity_id=int(row.id),
        detail=f"تست اتصال «{row.display_name or row.provider_key}»: {state_label} — {message}",
    )
    payload = ai_providers.provider_payload(row)
    await db.commit()
    return {"ok": ok, "message": message, "provider": payload}


@router.get("/chain")
async def read_chain(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """زنجیرهٔ فعال اولویت/fallback برای نمایش به مدیر."""
    await ai_providers.ensure_defaults(db, principal.organization_id)
    chain: Dict[str, Any] = {}
    for kind in ai_providers.ALL_KINDS:
        rows = await ai_providers.enabled_providers(db, principal.organization_id, kind)
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
        "stt": chain[ai_providers.KIND_STT],
        "llm": chain[ai_providers.KIND_LLM],
        "platform_fallback": ai_providers.PLATFORM_PROVIDER,
    }
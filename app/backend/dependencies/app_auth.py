"""وابستگی احراز هویت مستقل سامانه.

توکن از هدر ``X-App-Token`` خوانده می‌شود تا با هدر ``Authorization`` تداخل
نداشته باشد. اعتبار حساب در هر درخواست از پایگاه داده بازخوانی می‌شود تا
غیرفعال‌سازی کاربر بلافاصله اثر بگذارد.

``get_workspace_user`` پل اتصال به روترهای موجود فضای کاری است: خروجی آن یک
``UserResponse`` با شناسهٔ ``app:<id>`` است که دقیقاً با ``member_user_id``
ذخیره‌شده در جدول عضویت‌ها مطابقت دارد؛ بنابراین ``resolve_context`` بدون تغییر
قرارداد، سازمان و نقش کاربر مستقل را پیدا می‌کند.
"""

from __future__ import annotations

from core.database import get_db
from fastapi import Depends, Request
from schemas.auth import UserResponse
from sqlalchemy.ext.asyncio import AsyncSession

from services import app_auth


def _extract_token(request: Request) -> str:
    token = (request.headers.get("X-App-Token") or "").strip()
    if token:
        return token
    header = (request.headers.get("Authorization") or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


async def get_app_principal(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> app_auth.AppPrincipal:
    token = _extract_token(request)
    if not token:
        raise app_auth.unauthorized("برای دسترسی به این بخش باید وارد سامانه شوید.")

    payload = app_auth.read_token(token)
    app_user = await app_auth.load_app_user(db, int(payload["app_user_id"]))
    return app_auth.principal_of(app_user)


async def get_app_admin(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
) -> app_auth.AppPrincipal:
    if principal.role != app_auth.ROLE_ADMIN:
        raise app_auth.forbidden("این عملیات فقط برای «مدیر سازمان» مجاز است.")
    return principal


async def get_workspace_user(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
) -> UserResponse:
    """تبدیل هویت مستقل به قرارداد کاربر مورد انتظار روترهای فضای کاری."""
    return UserResponse(
        id=f"{app_auth.USER_PREFIX}{principal.app_user_id}",
        email=principal.email or "",
        name=principal.name,
        role="user",
        last_login=None,
    )
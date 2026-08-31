"""وابستگی احراز هویت مدیر پلتفرم برای مسیرهای ``/api/v1/platform``.

توکن از همان هدر ``X-App-Token`` خوانده می‌شود ولی نوع آن باید ``vidara_platform``
باشد؛ توکن‌های فضای کاری اینجا ۴۰۱ می‌گیرند و توکن پلتفرم هم در وابستگی‌های
فضای کاری رد می‌شود — دو فضای دسترسی کاملاً جدا.
"""
from __future__ import annotations

from core.database import get_db
from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from services import platform_admin


def _extract_token(request: Request) -> str:
    token = (request.headers.get("X-App-Token") or "").strip()
    if token:
        return token
    header = (request.headers.get("Authorization") or "").strip()
    if header.lower().startswith("bearer "):
        return header[7:].strip()
    return ""


async def get_platform_admin(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> platform_admin.PlatformPrincipal:
    token = _extract_token(request)
    if not token:
        raise platform_admin.unauthorized("برای دسترسی به این بخش باید وارد سامانه شوید.")

    payload = platform_admin.read_token(token)
    admin = await platform_admin.load_admin(db, int(payload["admin_id"]))
    return platform_admin.principal_of(admin)

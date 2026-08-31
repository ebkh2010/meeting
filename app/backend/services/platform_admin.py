"""سرویس مدیران پلتفرم: ساخت اولیهٔ حساب، ورود، امضای توکن و بارگذاری.

حساب مدیر پلتفرم با متغیرهای محیطی ساخته می‌شود (پیش‌فرض: ``ebAdministrator`` /
``Ebkh@89215110``) و رمز آن با همان PBKDF2 لایهٔ احراز مستقل ذخیره می‌شود. توکن
مدیر پلتفرم با ``typ="vidara_platform"`` امضا می‌شود تا با توکن‌های فضای کاری
(``typ="vidara_app"``) قابل جابه‌جایی نباشد.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from core.auth import AccessTokenError, create_access_token, decode_access_token
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.platform_admins import Platform_admins
from services.app_auth import hash_password, verify_password

logger = logging.getLogger(__name__)

PLATFORM_TOKEN_TYPE = "vidara_platform"
PLATFORM_PREFIX = "padmin:"
PLATFORM_ROLE = "platform_admin"
ROLE_LABEL = "مدیر پلتفرم"

DEFAULT_USERNAME = os.environ.get("PLATFORM_ADMIN_USERNAME", "ebAdministrator")
DEFAULT_PASSWORD = os.environ.get("PLATFORM_ADMIN_PASSWORD", "Ebkh@89215110")
TOKEN_TTL_MINUTES = int(os.environ.get("PLATFORM_TOKEN_TTL_MINUTES", "720"))  # ۱۲ ساعت


def unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


class PlatformPrincipal:
    """هویت مدیر پلتفرم برای وابستگی‌های مسیر ``/api/v1/platform``."""

    admin_id: int
    username: str
    display_name: str

    @property
    def id(self) -> str:
        return f"{PLATFORM_PREFIX}{self.admin_id}"

    @property
    def role(self) -> str:
        return PLATFORM_ROLE

    @property
    def actor_name(self) -> str:
        return self.display_name or self.username or "مدیر پلتفرم"


async def ensure_platform_admin(db: AsyncSession) -> Optional[Platform_admins]:
    """ساخت حساب مدیر پلتفرم در نخستین راه‌اندازی (idempotent).

    اگر رکوردی با همان نام کاربری وجود داشته باشد، دست‌نخورده می‌ماند تا رمز
    تغییرداده‌شده با هر ری‌استارت بازنشانی نشود.
    """
    username = DEFAULT_USERNAME.strip().lower()
    result = await db.execute(select(Platform_admins).where(Platform_admins.username == username))
    row = result.scalars().first()
    if row is not None:
        return row
    row = Platform_admins(
        username=username,
        password_hash=hash_password(DEFAULT_PASSWORD),
        display_name="مدیر پلتفرم",
        status="active",
    )
    db.add(row)
    await db.commit()
    logger.info("Platform admin '%s' created", username)
    return row


async def find_by_username(db: AsyncSession, username: str) -> Optional[Platform_admins]:
    result = await db.execute(
        select(Platform_admins).where(Platform_admins.username == username.strip().lower())
    )
    return result.scalars().first()


async def authenticate(db: AsyncSession, username: str, password: str) -> Optional[Platform_admins]:
    """ورود مدیر پلتفرم؛ ``None`` یعنی اعتبارنامهٔ پلتفرم مطابقت ندارد."""
    row = await find_by_username(db, username)
    if row is None or (row.status or "active") != "active":
        return None
    if not verify_password(password, row.password_hash or ""):
        return None
    return row


def issue_token(admin: Platform_admins) -> str:
    return create_access_token(
        {
            "sub": f"{PLATFORM_PREFIX}{int(admin.id)}",
            "typ": PLATFORM_TOKEN_TYPE,
            "role": PLATFORM_ROLE,
            "username": admin.username,
        },
        expires_minutes=TOKEN_TTL_MINUTES,
    )


def read_token(token: str) -> Dict[str, Any]:
    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        raise unauthorized("نشست شما معتبر نیست یا منقضی شده است. دوباره وارد شوید.") from exc
    if payload.get("typ") != PLATFORM_TOKEN_TYPE:
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.")
    subject = str(payload.get("sub") or "")
    if not subject.startswith(PLATFORM_PREFIX):
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.")
    try:
        payload["admin_id"] = int(subject[len(PLATFORM_PREFIX):])
    except ValueError as exc:
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.") from exc
    return payload


async def load_admin(db: AsyncSession, admin_id: int) -> Platform_admins:
    result = await db.execute(select(Platform_admins).where(Platform_admins.id == admin_id))
    row = result.scalars().first()
    if row is None:
        raise unauthorized("حساب مدیریت پلتفرم یافت نشد. دوباره وارد شوید.")
    if (row.status or "active") != "active":
        raise forbidden("حساب مدیریت پلتفرم غیرفعال شده است.")
    return row


def principal_of(admin: Platform_admins) -> PlatformPrincipal:
    principal = PlatformPrincipal()
    principal.admin_id = int(admin.id)
    principal.username = admin.username or ""
    principal.display_name = admin.display_name or "مدیر پلتفرم"
    return principal


def admin_payload(admin: Platform_admins) -> Dict[str, Any]:
    return {
        "id": int(admin.id),
        "username": admin.username or "",
        "display_name": admin.display_name or "مدیر پلتفرم",
        "role": PLATFORM_ROLE,
        "role_label": ROLE_LABEL,
        "is_platform_admin": True,
        "created_at": admin.created_at.isoformat() if admin.created_at else "",
    }


__all__ = [
    "DEFAULT_PASSWORD",
    "DEFAULT_USERNAME",
    "PLATFORM_PREFIX",
    "PLATFORM_ROLE",
    "PLATFORM_TOKEN_TYPE",
    "PlatformPrincipal",
    "ROLE_LABEL",
    "TOKEN_TTL_MINUTES",
    "admin_payload",
    "authenticate",
    "ensure_platform_admin",
    "find_by_username",
    "forbidden",
    "issue_token",
    "load_admin",
    "principal_of",
    "read_token",
    "unauthorized",
]

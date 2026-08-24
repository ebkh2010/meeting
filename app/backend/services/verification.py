"""کدهای تأیید یکبارمصرف (OTP) برای ایمیل و موبایل کاربران.

قواعد امنیتی:

* کد ۶ رقمی تصادفی است و فقط هش آن (SHA-256) ذخیره می‌شود.
* هر کد ۱۰ دقیقه اعتبار دارد و حداکثر ۵ تلاش برای ورودش مجاز است.
* درخواست کد جدید، کدهای فعال قبلی همان مقصد را باطل می‌کند و تا ۶۰ ثانیه
  بعد از آخرین درخواست، درخواست تکراری پذیرفته نمی‌شود (ضد هرزنامه).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Tuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_users import App_users
from models.user_verification_codes import User_verification_codes

logger = logging.getLogger(__name__)

PURPOSE_EMAIL = "email"
PURPOSE_MOBILE = "mobile"
ALL_PURPOSES = (PURPOSE_EMAIL, PURPOSE_MOBILE)

CODE_LENGTH = 6
CODE_TTL_SECONDS = 600  # ۱۰ دقیقه
MAX_ATTEMPTS = 5
RESEND_COOLDOWN_SECONDS = 60


class VerificationError(Exception):
    """خطای قابل‌نمایش به کاربر در فرایند تأیید (به HTTP 400 تبدیل می‌شود)."""


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def generate_code() -> str:
    """کد ۶ رقمی تصادفی (با صفرهای ابتدایی)."""
    return f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}"


def _hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


async def issue_code(
    db: AsyncSession,
    app_user: App_users,
    purpose: str,
    target: str,
) -> str:
    """صدور کد تازه برای ``purpose``/``target`` و برگرداندن کد خام برای ارسال.

    کدهای فعال قبلی همان کاربر و همان مقصد باطل می‌شوند. اگر کد تازه‌ای در
    کمتر از ``RESEND_COOLDOWN_SECONDS`` صادر شده باشد، ``VerificationError``
    پرتاب می‌شود تا ارسال پیام تکراری ممکن نباشد.
    """
    if purpose not in ALL_PURPOSES:
        raise VerificationError("نوع تأیید نامعتبر است.")
    target = (target or "").strip()
    if not target:
        raise VerificationError("مقصد تأیید (ایمیل یا موبایل) خالی است.")

    now = datetime.now(timezone.utc)

    # ضد هرزنامه: اگر برای همین مقصد کدی تازه صادر شده، درخواست جدید رد می‌شود.
    recent_result = await db.execute(
        select(User_verification_codes)
        .where(
            User_verification_codes.user_id == int(app_user.id),
            User_verification_codes.purpose == purpose,
            User_verification_codes.target == target,
            User_verification_codes.consumed_at.is_(None),
            User_verification_codes.expires_at > now,
        )
        .order_by(User_verification_codes.id.desc())
    )
    recent = recent_result.scalars().first()
    if recent is not None:
        age_seconds = int((now - _utc(recent.created_at)).total_seconds())
        if age_seconds < RESEND_COOLDOWN_SECONDS:
            remaining = RESEND_COOLDOWN_SECONDS - age_seconds
            raise VerificationError(
                f"کد قبلی هنوز ارسال شده و معتبر است؛ {remaining} ثانیهٔ دیگر دوباره درخواست دهید."
            )

    # باطل کردن کدهای فعال قبلی همین کاربر و همین مقصد
    previous_result = await db.execute(
        select(User_verification_codes).where(
            User_verification_codes.user_id == int(app_user.id),
            User_verification_codes.purpose == purpose,
            User_verification_codes.consumed_at.is_(None),
        )
    )
    for row in previous_result.scalars().all():
        row.consumed_at = now

    code = generate_code()
    row = User_verification_codes(
        user_id=int(app_user.id),
        organization_id=int(app_user.organization_id),
        purpose=purpose,
        target=target,
        code_hash=_hash_code(code),
        expires_at=now + timedelta(seconds=CODE_TTL_SECONDS),
        attempts=0,
    )
    db.add(row)
    await db.flush()
    return code


async def confirm_code(
    db: AsyncSession,
    app_user: App_users,
    purpose: str,
    target: str,
    raw_code: str,
) -> Tuple[bool, str]:
    """بررسی کد واردشده؛ خروجی: (موفق بود؟، پیام قابل‌نمایش)."""
    code_text = (raw_code or "").strip()
    if not code_text.isdigit() or len(code_text) != CODE_LENGTH:
        return False, f"کد تأیید باید {CODE_LENGTH} رقم باشد."

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User_verification_codes)
        .where(
            User_verification_codes.user_id == int(app_user.id),
            User_verification_codes.purpose == purpose,
            User_verification_codes.target == target,
            User_verification_codes.consumed_at.is_(None),
            User_verification_codes.expires_at > now,
        )
        .order_by(User_verification_codes.id.desc())
    )
    row = result.scalars().first()
    if row is None:
        return False, "کد تأییدی یافت نشد یا منقضی شده است؛ کد جدید درخواست دهید."

    if int(row.attempts or 0) >= MAX_ATTEMPTS:
        row.consumed_at = now
        await db.flush()
        return False, "تعداد تلاش‌های مجاز تمام شد؛ کد جدید درخواست دهید."

    if hmac.compare_digest(_hash_code(code_text), row.code_hash or ""):
        row.consumed_at = now
        await db.flush()
        return True, "ok"

    row.attempts = int(row.attempts or 0) + 1
    remaining = max(MAX_ATTEMPTS - int(row.attempts), 0)
    await db.flush()
    return False, f"کد واردشده نادرست است؛ {remaining} تلاش دیگر باقی مانده."

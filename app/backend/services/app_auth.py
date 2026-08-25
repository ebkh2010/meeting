"""احراز هویت مستقل و چندمستأجری «ویدارا - نسخه جلسات».

این ماژول هویت را کاملاً درون سامانه نگه می‌دارد:

* ثبت‌نام مدیر → ساخت سازمان (مستأجر) اختصاصی + عضویت مدیر.
* ورود با نام کاربری و رمز عبور → صدور توکن مستقل با claim مخصوص (``typ``).
* ساخت کاربر دبیر/عضو توسط مدیر فقط با نام، نام خانوادگی و موبایل؛ نام کاربری =
  موبایل و رمز عبور = رمز تعیین‌شدهٔ مدیر یا رمز پیش‌فرض سیستم ``vidara@12345``.
* کاربر ساخته‌شده در نخستین ورود باید نام کاربری جدید، رمز عبور جدید و کد ملی
  خود را تکمیل کند (``must_change_password`` دروازهٔ این جریان است).
* رمز عبور فقط به‌صورت هش PBKDF2-SHA256 ذخیره می‌شود.
* کلیدهای حساس (رمز SMTP و کلید API پیامک) با Fernet رمزنگاری می‌شوند.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from core.auth import AccessTokenError, create_access_token, decode_access_token
from core.config import settings as app_settings
from fastapi import HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_users import App_users
from models.memberships import Memberships
from models.organizations import Organizations
from services.mgmt_core import (
    ALL_ROLES,
    DEMO_AUDIO_RETENTION_DAYS,
    DEMO_MAX_AUDIO_MB,
    DEMO_MAX_AUDIO_MINUTES,
    DEMO_MAX_CONCURRENT_AI_JOBS,
    DEMO_MONTHLY_AI_MINUTES,
    ROLE_ADMIN,
    ROLE_LABELS,
    ROLE_MEMBER,
    ROLE_SECRETARY,
    current_period,
)

logger = logging.getLogger(__name__)

TOKEN_TYPE = "vidara_app"
TOKEN_TTL_MINUTES = 60 * 24 * 7
PBKDF2_ITERATIONS = 180_000
USER_PREFIX = "app:"

# رمز عبور پیش‌فرض کاربرانی که مدیر سازمان بدون تعیین رمز می‌سازد؛ کاربر در
# نخستین ورود ملزم به تغییر آن است.
DEFAULT_PASSWORD = "vidara@12345"

GENDER_MALE = "male"
GENDER_FEMALE = "female"
GENDER_LABELS = {GENDER_MALE: "مرد", GENDER_FEMALE: "زن"}
GENDER_SALUTATION = {GENDER_MALE: "جناب آقای", GENDER_FEMALE: "سرکار خانم"}

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS = "٠١٢٣٤٥٦٧٨٩"


# ---------------------------------------------------------------------------
# خطاهای استاندارد
# ---------------------------------------------------------------------------


def bad_request(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=message)


def unauthorized(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=message)


def forbidden(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=message)


def conflict(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)


def not_found(message: str) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=message)


# ---------------------------------------------------------------------------
# نرمال‌سازی ورودی فارسی
# ---------------------------------------------------------------------------


def to_latin_digits(value: str) -> str:
    """تبدیل رقم‌های فارسی/عربی به لاتین تا اعتبارسنجی مستقل از صفحه‌کلید باشد."""
    if not value:
        return ""
    result = []
    for char in value:
        if char in _PERSIAN_DIGITS:
            result.append(str(_PERSIAN_DIGITS.index(char)))
        elif char in _ARABIC_DIGITS:
            result.append(str(_ARABIC_DIGITS.index(char)))
        else:
            result.append(char)
    return "".join(result)


def normalize_mobile(raw: str) -> str:
    """۰۹xxxxxxxxx استاندارد؛ ورودی +۹۸ و ۰۰۹۸ و ۹xxxxxxxxx هم پذیرفته می‌شود."""
    digits = re.sub(r"\D", "", to_latin_digits(raw or ""))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) == 12:
        digits = digits[2:]
    if len(digits) == 10 and digits.startswith("9"):
        digits = "0" + digits
    if not re.fullmatch(r"09\d{9}", digits):
        raise bad_request("شماره موبایل معتبر نیست. قالب درست: ۰۹۱۲۳۴۵۶۷۸۹")
    return digits


def normalize_national_id(raw: str) -> str:
    digits = re.sub(r"\D", "", to_latin_digits(raw or ""))
    if not re.fullmatch(r"\d{10}", digits):
        raise bad_request("کد ملی باید دقیقاً ۱۰ رقم باشد.")
    return digits


def normalize_email(raw: str) -> str:
    value = (raw or "").strip()
    if not value:
        return ""
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[A-Za-z]{2,}", value):
        raise bad_request("نشانی ایمیل معتبر نیست.")
    return value.lower()


def normalize_username(raw: str) -> str:
    value = to_latin_digits((raw or "").strip()).lower()
    if len(value) < 4:
        raise bad_request("نام کاربری باید حداقل ۴ نویسه باشد.")
    if not re.fullmatch(r"[A-Za-z0-9._@-]+", value):
        raise bad_request("نام کاربری فقط می‌تواند شامل حرف لاتین، رقم و نویسه‌های . _ - @ باشد.")
    return value


def normalize_gender(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value in (GENDER_MALE, GENDER_FEMALE):
        return value
    if value in ("آقا", "مرد", "m"):
        return GENDER_MALE
    if value in ("خانم", "زن", "f"):
        return GENDER_FEMALE
    raise bad_request("جنسیت باید «مرد» یا «زن» انتخاب شود.")


def normalize_role(raw: str) -> str:
    value = (raw or "").strip().lower()
    if value not in ALL_ROLES:
        raise bad_request("نقش انتخاب‌شده معتبر نیست.")
    return value


def validate_password(raw: str) -> str:
    value = to_latin_digits((raw or "").strip())
    if len(value) < 6:
        raise bad_request("رمز عبور باید حداقل ۶ نویسه باشد.")
    return value


def full_name_of(first_name: str, last_name: str) -> str:
    return f"{(first_name or '').strip()} {(last_name or '').strip()}".strip()


# ---------------------------------------------------------------------------
# هش رمز عبور
# ---------------------------------------------------------------------------


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    ).hex()
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${digest}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, iterations, salt, digest = (stored or "").split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        calculated = hashlib.pbkdf2_hmac(
            "sha256", (password or "").encode("utf-8"), bytes.fromhex(salt), int(iterations)
        ).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculated, digest)


# ---------------------------------------------------------------------------
# رمزنگاری کلیدهای حساس (رمز SMTP / کلید API پیامک)
# ---------------------------------------------------------------------------


def _fernet():
    from cryptography.fernet import Fernet

    material = (app_settings.jwt_secret_key or "vidara-meetings-local-secret").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(material).digest())
    return Fernet(key)


def encrypt_secret(raw: str) -> str:
    if not raw:
        return ""
    return _fernet().encrypt(raw.encode("utf-8")).decode("utf-8")


def decrypt_secret(encrypted: str) -> str:
    if not encrypted:
        return ""
    try:
        return _fernet().decrypt(encrypted.encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - کلید تغییر کرده یا داده خراب است
        logger.warning("رمزگشایی کلید ذخیره‌شده ناموفق بود: %s", type(exc).__name__)
        return ""


# ---------------------------------------------------------------------------
# هویت درخواست
# ---------------------------------------------------------------------------


@dataclass
class AppPrincipal:
    """هویت کاربر احراز هویت‌شدهٔ مستقل؛ شکل آن با ``resolve_context`` سازگار است."""

    app_user_id: int
    id: str
    email: str
    name: str
    role: str
    organization_id: int
    mobile: str = ""
    gender: str = ""
    must_change_password: bool = False
    no_bootstrap: bool = field(default=True)

    @property
    def role_label(self) -> str:
        return ROLE_LABELS.get(self.role, self.role)


def principal_of(app_user: App_users) -> AppPrincipal:
    return AppPrincipal(
        app_user_id=int(app_user.id),
        id=f"{USER_PREFIX}{int(app_user.id)}",
        email=app_user.email or "",
        name=full_name_of(app_user.first_name, app_user.last_name),
        role=app_user.role or ROLE_MEMBER,
        organization_id=int(app_user.organization_id),
        mobile=app_user.mobile or "",
        gender=app_user.gender or "",
        must_change_password=bool(app_user.must_change_password),
    )


def issue_token(app_user: App_users) -> str:
    return create_access_token(
        {
            "sub": f"{USER_PREFIX}{int(app_user.id)}",
            "typ": TOKEN_TYPE,
            "org": int(app_user.organization_id),
            "role": app_user.role or ROLE_MEMBER,
        },
        expires_minutes=TOKEN_TTL_MINUTES,
    )


def read_token(token: str) -> Dict[str, Any]:
    try:
        payload = decode_access_token(token)
    except AccessTokenError as exc:
        raise unauthorized("نشست شما معتبر نیست یا منقضی شده است. دوباره وارد شوید.") from exc
    if payload.get("typ") != TOKEN_TYPE:
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.")
    subject = str(payload.get("sub") or "")
    if not subject.startswith(USER_PREFIX):
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.")
    try:
        payload["app_user_id"] = int(subject[len(USER_PREFIX) :])
    except ValueError as exc:
        raise unauthorized("نشست شما معتبر نیست. دوباره وارد شوید.") from exc
    return payload


async def load_app_user(db: AsyncSession, app_user_id: int) -> App_users:
    result = await db.execute(select(App_users).where(App_users.id == app_user_id))
    app_user = result.scalar_one_or_none()
    if app_user is None:
        raise unauthorized("حساب کاربری یافت نشد. دوباره وارد شوید.")
    if (app_user.status or "active") != "active":
        raise forbidden("حساب کاربری شما توسط مدیر سازمان غیرفعال شده است.")
    return app_user


# ---------------------------------------------------------------------------
# ساخت سازمان و کاربر
# ---------------------------------------------------------------------------


async def username_taken(
    db: AsyncSession,
    username: str,
    exclude_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> bool:
    """یکتایی نام کاربری در **مرز سازمان**.

    یک شخص می‌تواند در چند سازمان با همان نام کاربری (شمارهٔ موبایل) حساب داشته
    باشد؛ بنابراین یکتایی سراسری نیست و با ``organization_id`` محدود می‌شود.
    """
    stmt = select(App_users).where(App_users.username == username)
    if organization_id is not None:
        stmt = stmt.where(App_users.organization_id == int(organization_id))
    if exclude_id:
        stmt = stmt.where(App_users.id != exclude_id)
    result = await db.execute(stmt)
    return result.scalars().first() is not None


async def find_login_candidates(db: AsyncSession, raw_identifier: str) -> list[App_users]:
    """همهٔ حساب‌های فعال یک شخص در سازمان‌های مختلف برای مرحلهٔ انتخاب سازمان."""
    identifier = to_latin_digits((raw_identifier or "").strip()).lower()
    if not identifier:
        return []
    conditions = [App_users.username == identifier]
    variants = mobile_variants(identifier)
    if variants:
        conditions.append(App_users.mobile.in_(variants))
    result = await db.execute(
        select(App_users).where(or_(*conditions)).order_by(App_users.id.asc())
    )
    return list(result.scalars().all())


async def find_sibling_accounts(db: AsyncSession, app_user: App_users) -> list[App_users]:
    """حساب\u200cهای فعال همین شخص در سازمان\u200cهای مختلف، برای «تغییر سازمان» در نشست.

    هویت شخص با شمارهٔ موبایل یا نام کاربری یکسان تشخیص داده می\u200cشود و در صورت
    وجود کد ملی، با کد ملی هم مقایسه می\u200cشود تا هم\u200cنامی تصادفی حساب\u200cها را به هم
    وصل نکند. برای هر سازمان تنها یک حساب برگردانده می\u200cشود.
    """
    conditions = []
    variants = mobile_variants(app_user.mobile or "")
    if variants:
        conditions.append(App_users.mobile.in_(variants))
    username = (app_user.username or "").strip().lower()
    if username:
        conditions.append(App_users.username == username)
    if not conditions:
        return [app_user]

    result = await db.execute(
        select(App_users).where(or_(*conditions)).order_by(App_users.id.asc())
    )
    rows = [row for row in result.scalars().all() if (row.status or "active") == "active"]

    national_id = (app_user.national_id or "").strip()
    if national_id:
        rows = [
            row
            for row in rows
            if not (row.national_id or "").strip()
            or (row.national_id or "").strip() == national_id
        ]

    if all(int(row.id) != int(app_user.id) for row in rows):
        rows.append(app_user)

    unique: Dict[int, App_users] = {}
    for row in rows:
        unique.setdefault(int(row.organization_id), row)
    return list(unique.values())


def mobile_variants(raw: str) -> list[str]:
    """همهٔ نگارش\u200cهای رایج یک شمارهٔ موبایل تا جست\u200cوجو مستقل از قالب ورودی باشد."""
    digits = re.sub(r"\D", "", to_latin_digits(raw or ""))
    if not digits:
        return []
    variants = {digits}
    if digits.startswith("0098"):
        variants.add(digits[4:])
    if digits.startswith("98") and len(digits) == 12:
        variants.add(digits[2:])
    if len(digits) == 10 and digits.startswith("9"):
        variants.add("0" + digits)
    if digits.startswith("0") and len(digits) == 11:
        variants.add(digits[1:])
    return sorted(variants)


async def find_existing_account(
    db: AsyncSession,
    username: str,
    mobile: str,
    exclude_id: Optional[int] = None,
    organization_id: Optional[int] = None,
) -> Optional[App_users]:
    """یافتن حساب موجود بر پایهٔ نام کاربری یا شمارهٔ موبایل.

    اگر ``organization_id`` داده شود، جست‌وجو فقط در همان سازمان انجام می‌شود؛
    این همان قاعده‌ای است که عضویت یک شخص در چند سازمان را ممکن می‌کند.
    """
    conditions = []
    if username:
        conditions.append(App_users.username == username)
    variants = mobile_variants(mobile)
    if variants:
        conditions.append(App_users.mobile.in_(variants))
    if not conditions:
        return None
    stmt = select(App_users).where(or_(*conditions))
    if organization_id is not None:
        stmt = stmt.where(App_users.organization_id == int(organization_id))
    if exclude_id:
        stmt = stmt.where(App_users.id != exclude_id)
    result = await db.execute(stmt.order_by(App_users.id.asc()))
    return result.scalars().first()


def duplicate_account_message(existing: App_users, mobile: str) -> str:
    """پیام راهنمای دقیق برای حسابی که از قبل وجود دارد (به\u200cجای پیام بن\u200cبست)."""
    login_name = (existing.username or "").strip() or (existing.mobile or "").strip()
    if mobile and (existing.mobile or "") in mobile_variants(mobile):
        return (
            "این شمارهٔ موبایل قبلاً در سامانه ثبت شده است؛ نیازی به ثبت\u200cنام دوباره نیست. "
            f"از بخش «ورود» با نام کاربری «{login_name}» و رمز عبور همان حساب وارد شوید. "
            "اگر رمز عبور را فراموش کرده\u200cاید، از مدیر سازمان بخواهید آن را بازنشانی کند."
        )
    return (
        f"نام کاربری «{login_name}» قبلاً ثبت شده است. نام کاربری دیگری انتخاب کنید، "
        "یا اگر این حساب متعلق به خودتان است از بخش «ورود» استفاده کنید."
    )


async def find_login_user(db: AsyncSession, raw_identifier: str) -> Optional[App_users]:
    """یافتن کاربر برای ورود با نام کاربری یا شمارهٔ موبایل (هر دو پذیرفته می\u200cشود)."""
    identifier = to_latin_digits((raw_identifier or "").strip()).lower()
    if not identifier:
        return None
    result = await db.execute(select(App_users).where(App_users.username == identifier))
    app_user = result.scalars().first()
    if app_user is not None:
        return app_user
    variants = mobile_variants(identifier)
    if not variants:
        return None
    result = await db.execute(
        select(App_users).where(App_users.mobile.in_(variants)).order_by(App_users.id.asc())
    )
    return result.scalars().first()


def build_slug(organization_name: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9]+", "-", (organization_name or "").strip()).strip("-").lower()
    return f"{base or 'org'}-{secrets.token_hex(3)}"


async def create_organization(db: AsyncSession, name: str, timezone_name: str = "Asia/Tehran") -> Organizations:
    organization = Organizations(
        name=(name or "").strip() or "سازمان بدون نام",
        slug=build_slug(name),
        plan_code="standard",
        timezone=timezone_name or "Asia/Tehran",
        status="active",
        monthly_ai_minutes_quota=DEMO_MONTHLY_AI_MINUTES,
        ai_minutes_used=0,
        quota_period=current_period(),
        max_concurrent_ai_jobs=DEMO_MAX_CONCURRENT_AI_JOBS,
        audio_retention_days=DEMO_AUDIO_RETENTION_DAYS,
        max_audio_mb=DEMO_MAX_AUDIO_MB,
        max_audio_minutes=DEMO_MAX_AUDIO_MINUTES,
        is_demo=False,
    )
    db.add(organization)
    await db.flush()
    return organization


async def create_app_user(
    db: AsyncSession,
    *,
    organization_id: int,
    username: str,
    password: str,
    first_name: str,
    last_name: str,
    mobile: str,
    email: str,
    national_id: str,
    gender: str,
    role: str,
    must_change_password: bool,
) -> App_users:
    """ساخت کاربر مستقل + عضویت متناظر در سازمان (مرز مستأجر با ``organization_id``)."""
    if await username_taken(db, username, organization_id=organization_id):
        raise conflict(
            "این نام کاربری در همین سازمان قبلاً ثبت شده است. نام کاربری دیگری انتخاب کنید."
        )

    app_user = App_users(
        organization_id=organization_id,
        username=username,
        password_hash=hash_password(password),
        first_name=first_name,
        last_name=last_name,
        mobile=mobile,
        email=email,
        national_id=national_id,
        gender=gender,
        role=role,
        status="active",
        must_change_password=must_change_password,
    )
    db.add(app_user)
    await db.flush()

    membership = Memberships(
        organization_id=organization_id,
        member_user_id=f"{USER_PREFIX}{int(app_user.id)}",
        email=email,
        full_name=full_name_of(first_name, last_name),
        role=role,
        status="active",
        is_virtual=False,
    )
    db.add(membership)
    await db.flush()
    return app_user


async def membership_of(db: AsyncSession, app_user: App_users) -> Optional[Memberships]:
    result = await db.execute(
        select(Memberships).where(
            Memberships.organization_id == int(app_user.organization_id),
            Memberships.member_user_id == f"{USER_PREFIX}{int(app_user.id)}",
        )
    )
    return result.scalars().first()


def user_payload(app_user: App_users, membership_id: Optional[int] = None) -> Dict[str, Any]:
    return {
        "id": int(app_user.id),
        "membership_id": membership_id,
        "username": app_user.username,
        "first_name": app_user.first_name,
        "last_name": app_user.last_name,
        "full_name": full_name_of(app_user.first_name, app_user.last_name),
        "mobile": app_user.mobile or "",
        "email": app_user.email or "",
        "email_verified": bool(app_user.email_verified),
        "mobile_verified": bool(app_user.mobile_verified),
        "national_id": app_user.national_id or "",
        "gender": app_user.gender or "",
        "gender_label": GENDER_LABELS.get(app_user.gender or "", ""),
        "role": app_user.role,
        "role_label": ROLE_LABELS.get(app_user.role, app_user.role),
        "status": app_user.status or "active",
        "must_change_password": bool(app_user.must_change_password),
        "last_login_at": app_user.last_login_at.isoformat() if app_user.last_login_at else "",
        "created_at": app_user.created_at.isoformat() if app_user.created_at else "",
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


__all__ = [
    "AppPrincipal",
    "DEFAULT_PASSWORD",
    "GENDER_FEMALE",
    "GENDER_LABELS",
    "GENDER_MALE",
    "GENDER_SALUTATION",
    "ROLE_ADMIN",
    "ROLE_MEMBER",
    "ROLE_SECRETARY",
    "USER_PREFIX",
    "bad_request",
    "conflict",
    "create_app_user",
    "create_organization",
    "decrypt_secret",
    "encrypt_secret",
    "find_existing_account",
    "find_login_candidates",
    "find_sibling_accounts",
    "find_login_user",
    "forbidden",
    "full_name_of",
    "hash_password",
    "issue_token",
    "load_app_user",
    "membership_of",
    "normalize_email",
    "normalize_gender",
    "normalize_mobile",
    "normalize_national_id",
    "normalize_role",
    "normalize_username",
    "not_found",
    "principal_of",
    "read_token",
    "unauthorized",
    "user_payload",
    "username_taken",
    "utc_now",
    "validate_password",
    "verify_password",
]
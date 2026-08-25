"""روتر احراز هویت مستقل و مدیریت کاربران سازمان.

قراردادها:

* ``POST /api/v1/app-auth/register`` — ثبت‌نام مدیر + ساخت سازمان اختصاصی.
* ``POST /api/v1/app-auth/login`` — ورود با جفت «نام کاربری + رمز عبور»؛ همین
  جفت است که مشخص می‌کند کاربر وارد کدام فضا (سازمان/نقش) می‌شود.
* ``GET  /api/v1/app-auth/me`` — پروفایل کاربر جاری.
* ``PATCH /api/v1/app-auth/me`` — ویرایش مشخصات توسط خود کاربر (همهٔ نقش‌ها).
* ``POST /api/v1/app-auth/change-password`` — تغییر رمز عبور توسط خود کاربر.
* ``POST /api/v1/app-auth/complete-profile`` — تکمیل اجباری مشخصات در نخستین ورود
  کاربرِ ساخته‌شده توسط مدیر (نام کاربری جدید، رمز جدید، کد ملی).
* ``POST /api/v1/app-auth/verify/email/*`` — تأیید ایمیل با کد یکبارمصرف.
* ``POST /api/v1/app-auth/verify/mobile/*`` — تأیید موبایل با کد یکبارمصرف (پیامک).
* ``GET/POST/PATCH /api/v1/app-auth/users`` — مدیریت کاربران توسط مدیر سازمان.

قاعده‌های هویت:

* **شناسهٔ اصلی هویت، کد ملی است**: اگر کد ملی از قبل در سامانه ثبت شده باشد،
  نام و نام خانوادگی باید با همان هویت سازگار باشد؛ همهٔ حساب‌های یک کد ملی به
  هم پیوند می‌خورند و کاربر می‌تواند بین فضاهای کاری خود جابه‌جا شود.
* **ورود بر پایهٔ جفت «نام کاربری + رمز عبور» است**: کاربر مستقیم وارد همان
  فضای کاریِ همان اعتبارنامه می‌شود؛ برای جابه‌جایی بین فضاها، نام کاربری و
  رمز عبور فضای مقصد الزامی است (``POST /switch-organization``).
* اعتبارنامهٔ پیش‌فرض کاربران ساخته‌شده توسط مدیر: نام کاربری = شمارهٔ موبایل،
  رمز عبور = رمز تعیین‌شده توسط مدیر یا رمز پیش‌فرض سیستم ``vidara@12345``؛
  کاربر در نخستین ورود باید نام کاربری جدید، رمز عبور جدید و کد ملی خود را با
  ``POST /complete-profile`` تکمیل کند.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.app_auth import get_app_admin, get_app_principal
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.app_users import App_users
from models.memberships import Memberships
from models.organizations import Organizations
from services import app_auth
from services import notify_channels as channels
from services import verification
from services.ai_providers import ensure_defaults
from services.notify_channels import get_or_create_settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/app-auth", tags=["app-auth"])


class RegisterIn(BaseModel):
    organization_name: str = Field(..., min_length=2, max_length=200)
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    mobile: str
    national_id: str
    gender: str
    email: str = ""
    username: str = ""
    password: str


class LoginIn(BaseModel):
    """ورود بر پایهٔ جفت «نام کاربری + رمز عبور».

    رمز عبور هر فضای کاری مستقل است؛ همان جفت اعتبارنامه است که مشخص می‌کند کاربر
    وارد کدام فضا (سازمان/نقش) می‌شود و هیچ مرحلهٔ انتخاب سازمان وجود ندارد.
    """

    username: str
    password: str


class SwitchOrganizationIn(BaseModel):
    """تغییر فضای کاری فعال نشست؛ نام کاربری و رمز عبور همان فضا الزامی است."""

    organization_id: int
    username: str
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class MeUpdateIn(BaseModel):
    """ویرایش مشخصات خودِ کاربر — برای همهٔ نقش‌ها (مدیر، دبیر، عضو) باز است."""

    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    national_id: Optional[str] = None
    gender: Optional[str] = None


class VerifyConfirmIn(BaseModel):
    code: str = Field(..., min_length=4, max_length=8, description="کد ۶ رقمی ارسال‌شده")


class UserIn(BaseModel):
    """ساخت دبیر/عضو توسط مدیر سازمان — فقط نام، نام خانوادگی و موبایل الزامی است.

    کد ملی و جنسیت در نخستین ورود توسط خودِ کاربر تکمیل می‌شود؛ رمز عبور اختیاری
    است و در نبودِ آن، رمز پیش‌فرض سیستم ``vidara@12345`` استفاده می‌شود.
    """

    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    mobile: str
    national_id: str = ""
    gender: str = ""
    email: str = ""
    password: Optional[str] = None
    role: str = app_auth.ROLE_MEMBER


class CompleteProfileIn(BaseModel):
    """تکمیل اجباری مشخصات در نخستین ورود کاربرِ ساخته‌شده توسط مدیر.

    نام کاربری جدید، رمز عبور جدید و کد ملی الزامی‌اند؛ جنسیت و ایمیل اختیاری.
    """

    username: str
    new_password: str
    national_id: str
    gender: Optional[str] = None
    email: Optional[str] = None


class UserUpdateIn(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    national_id: Optional[str] = None
    gender: Optional[str] = None
    role: Optional[str] = None
    status: Optional[str] = None
    reset_password: Optional[bool] = None


async def _session_payload(db: AsyncSession, app_user: App_users) -> Dict[str, Any]:
    membership = await app_auth.membership_of(db, app_user)
    org_result = await db.execute(
        select(Organizations).where(Organizations.id == int(app_user.organization_id))
    )
    organization = org_result.scalars().first()
    return {
        "token": app_auth.issue_token(app_user),
        "user": app_auth.user_payload(app_user, int(membership.id) if membership else None),
        "organization": {
            "id": int(app_user.organization_id),
            "name": (organization.name if organization else "") or "",
            "slug": (organization.slug if organization else "") or "",
            "timezone": (organization.timezone if organization else "") or "Asia/Tehran",
        },
    }


@router.post("/register")
async def register(data: RegisterIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """ثبت‌نام مدیر سازمان: هر ثبت‌نام یک مستأجر مستقل می‌سازد."""
    first_name = data.first_name.strip()
    last_name = data.last_name.strip()
    mobile = app_auth.normalize_mobile(data.mobile)
    national_id = app_auth.normalize_national_id(data.national_id)
    gender = app_auth.normalize_gender(data.gender)
    email = app_auth.normalize_email(data.email)
    password = app_auth.validate_password(data.password)
    username = app_auth.normalize_username(data.username) if data.username else mobile

    # شناسهٔ اصلی هویت کد ملی است: اگر این کد ملی قبلاً در سامانه ثبت شده باشد،
    # نام و نام خانوادگی باید با همان هویت سازگار باشد (همین شخص می‌تواند در چند
    # سازمان حساب داشته باشد و ورود با جفت نام کاربری/رمز هر فضا انجام می‌شود).
    await app_auth.ensure_national_id_identity(db, national_id, first_name, last_name)

    organization = await app_auth.create_organization(db, data.organization_name.strip())
    app_user = await app_auth.create_app_user(
        db,
        organization_id=int(organization.id),
        username=username,
        password=password,
        first_name=first_name,
        last_name=last_name,
        mobile=mobile,
        email=email,
        national_id=national_id,
        gender=gender,
        role=app_auth.ROLE_ADMIN,
        must_change_password=False,
    )
    await get_or_create_settings(db, int(organization.id))
    await ensure_defaults(db, int(organization.id))
    payload = await _session_payload(db, app_user)
    await db.commit()
    return payload


async def _organization_brief(db: AsyncSession, app_user: App_users) -> Dict[str, Any]:
    """کارت کوتاه سازمان + نقش همان حساب، برای فهرست «تغییر فضای کاری»."""
    org_result = await db.execute(
        select(Organizations).where(Organizations.id == int(app_user.organization_id))
    )
    organization = org_result.scalars().first()
    return {
        "organization_id": int(app_user.organization_id),
        "name": (organization.name if organization else "") or "سازمان بدون نام",
        "slug": (organization.slug if organization else "") or "",
        "role": app_user.role or app_auth.ROLE_MEMBER,
        "role_label": app_auth.ROLE_LABELS.get(
            app_user.role or "", app_user.role or app_auth.ROLE_MEMBER
        ),
    }


@router.post("/login")
async def login(data: LoginIn, db: AsyncSession = Depends(get_db)) -> Dict[str, Any]:
    """ورود با جفت «نام کاربری + رمز عبور» بدون مرحلهٔ انتخاب سازمان.

    رمز عبور هر فضای کاری مستقل است؛ همین جفت اعتبارنامه است که تعیین می‌کند کاربر
    وارد کدام فضا (سازمان/نقش) می‌شود. اگر یک شناسه (نام کاربری یا شمارهٔ موبایل)
    به چند حساب فعال تعلق داشته باشد، رمز عبور همان فضا حساب مقصد را مشخص می‌کند؛
    تنها حالتی که ابهام می‌ماند، یکسان بودن نام کاربری **و** رمز عبور در چند فضا
    است که با پیام راهنما به کاربر اعلام می‌شود.
    """
    identifier = app_auth.to_latin_digits((data.username or "").strip()).lower()
    if not identifier or not data.password:
        raise app_auth.bad_request("نام کاربری و رمز عبور را وارد کنید.")

    candidates = await app_auth.find_login_candidates(db, identifier)
    active = [row for row in candidates if (row.status or "active") == "active"]
    if not active:
        if candidates:
            raise app_auth.forbidden("حساب کاربری شما توسط مدیر سازمان غیرفعال شده است.")
        raise app_auth.unauthorized("نام کاربری یا رمز عبور نادرست است.")

    # رمز عبور، فضای کاریِ حساب را مشخص می‌کند؛ حساب‌هایی که رمزشان با ورودی
    # یکی نیست کنار گذاشته می‌شوند تا ورود همیشه به همان نقش/سازمانِ همان
    # اعتبارنامه برود.
    matched = [
        row for row in active if app_auth.verify_password(data.password, row.password_hash or "")
    ]
    if not matched:
        raise app_auth.unauthorized("نام کاربری یا رمز عبور نادرست است.")
    if len(matched) > 1:
        raise app_auth.bad_request(
            "نام کاربری و رمز عبور یکسان در چند فضای کاری برای شما ثبت شده است؛ "
            "برای ورود بدون ابهام، رمز عبور یکی از حساب‌ها را تغییر دهید."
        )

    selected = matched[0]
    selected.last_login_at = app_auth.utc_now()
    payload = await _session_payload(db, selected)
    await db.commit()
    return payload


@router.get("/me")
async def me(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    membership = await app_auth.membership_of(db, app_user)
    org_result = await db.execute(
        select(Organizations).where(Organizations.id == int(app_user.organization_id))
    )
    organization = org_result.scalars().first()
    payload = {
        "user": app_auth.user_payload(app_user, int(membership.id) if membership else None),
        "organization": {
            "id": int(app_user.organization_id),
            "name": (organization.name if organization else "") or "",
            "slug": (organization.slug if organization else "") or "",
            "timezone": (organization.timezone if organization else "") or "Asia/Tehran",
        },
    }
    await db.commit()
    return payload


@router.patch("/me")
async def update_me(
    data: MeUpdateIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ویرایش مشخصات خودِ کاربر — در هر زمان و برای همهٔ نقش‌ها باز است.

    تغییر ایمیل یا موبایل، وضعیت تأیید آن را باطل می‌کند تا کاربر با کد
    یکبارمصرف، نشانی جدید را تأیید کند. نقش و وضعیت حساب از اینجا قابل تغییر
    نیستند (فقط مدیر سازمان از بخش کاربران).
    """
    app_user = await app_auth.load_app_user(db, principal.app_user_id)

    if data.first_name is not None:
        app_user.first_name = data.first_name.strip() or app_user.first_name
    if data.last_name is not None:
        app_user.last_name = data.last_name.strip() or app_user.last_name
    if data.national_id is not None and data.national_id.strip():
        new_national_id = app_auth.normalize_national_id(data.national_id)
        if new_national_id != (app_user.national_id or ""):
            # شناسهٔ اصلی هویت کد ملی است؛ نام و نام خانوادگی باید با سوابق
            # همان کد ملی در کل سامانه سازگار باشد.
            await app_auth.ensure_national_id_identity(
                db,
                new_national_id,
                app_user.first_name,
                app_user.last_name,
                exclude_id=app_user.id,
            )
            app_user.national_id = new_national_id
    if data.gender is not None and data.gender.strip():
        app_user.gender = app_auth.normalize_gender(data.gender)

    if data.mobile is not None and data.mobile.strip():
        new_mobile = app_auth.normalize_mobile(data.mobile)
        if new_mobile != (app_user.mobile or ""):
            existing = await app_auth.find_existing_account(
                db,
                new_mobile,
                new_mobile,
                exclude_id=app_user.id,
                organization_id=principal.organization_id,
            )
            if existing is not None:
                raise app_auth.conflict(
                    "این شمارهٔ موبایل در همین سازمان به حساب دیگری تعلق دارد."
                )
            app_user.mobile = new_mobile
            app_user.mobile_verified = False

    if data.email is not None:
        new_email = app_auth.normalize_email(data.email)
        if new_email != (app_user.email or ""):
            app_user.email = new_email
            app_user.email_verified = False

    membership = await app_auth.membership_of(db, app_user)
    if membership is not None:
        membership.full_name = app_auth.full_name_of(app_user.first_name, app_user.last_name)
        membership.email = app_user.email or ""

    payload = app_auth.user_payload(app_user, int(membership.id) if membership else None)
    await db.commit()
    return payload


# ---------------------------------------------------------------------------
# تأیید ایمیل و موبایل با کد یکبارمصرف
# ---------------------------------------------------------------------------


async def _issue_and_send(
    db: AsyncSession,
    principal: app_auth.AppPrincipal,
    app_user: App_users,
    purpose: str,
    target: str,
    subject: str,
    text_body: str,
    html_body: str,
    sms_text: str,
) -> Dict[str, Any]:
    """صدور کد + ارسال با کانال مناسب (ایمیل/پیامک) + ذخیره؛ خطاها به ۴۰۰ تبدیل می‌شوند."""
    try:
        code = await verification.issue_code(db, app_user, purpose, target)
    except verification.VerificationError as exc:
        raise app_auth.bad_request(str(exc))

    settings_row = await get_or_create_settings(db, principal.organization_id)
    if purpose == verification.PURPOSE_EMAIL:
        result = await channels.send_email(
            settings_row,
            to_email=target,
            subject=subject,
            text_body=text_body.replace("{code}", code),
            html_body=html_body.replace("{code}", code),
        )
        channel_label = "ایمیل"
    else:
        result = await channels.send_sms(
            settings_row,
            receptor=target,
            message=sms_text.replace("{code}", code),
            client_reference_id=f"verify-{int(app_user.id)}",
        )
        channel_label = "پیامک"

    if not result.ok:
        raise app_auth.bad_request(f"ارسال {channel_label} ناموفق بود: {result.error}")
    await db.commit()
    return {
        "ok": True,
        "detail": f"کد تأیید به {target} ارسال شد.",
        "expires_in_seconds": verification.CODE_TTL_SECONDS,
        "cooldown_seconds": verification.RESEND_COOLDOWN_SECONDS,
    }


@router.post("/verify/email/request")
async def request_email_verification(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """درخواست کد تأیید ایمیل؛ کد به ایمیل ثبت‌شدهٔ کاربر ارسال می‌شود."""
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    email = (app_user.email or "").strip()
    if not email:
        raise app_auth.bad_request("ابتدا ایمیل خود را در مشخصات حساب ذخیره کنید.")
    if app_user.email_verified:
        return {"ok": True, "already_verified": True, "detail": "ایمیل شما قبلاً تأیید شده است."}
    return await _issue_and_send(
        db,
        principal,
        app_user,
        verification.PURPOSE_EMAIL,
        email,
        subject="کد تأیید ایمیل — ویدارا - نسخه جلسات",
        text_body=(
            f"سلام {app_user.first_name}؛\n"
            "کد تأیید ایمیل شما: {code}\n"
            "این کد تا ۱۰ دقیقه معتبر است.\n"
            "اگر این درخواست از سوی شما نبوده است، این پیام را نادیده بگیرید."
        ),
        html_body=(
            '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;color:#0f172a">'
            f"<h3>سلام {app_user.first_name}؛</h3>"
            '<p>کد تأیید ایمیل شما:</p>'
            '<p style="font-size:28px;font-weight:700;letter-spacing:6px;direction:ltr">{code}</p>'
            "<p>این کد تا ۱۰ دقیقه معتبر است.</p>"
            "<p>اگر این درخواست از سوی شما نبوده است، این پیام را نادیده بگیرید.</p></div>"
        ),
        sms_text="",
    )


@router.post("/verify/email/confirm")
async def confirm_email_verification(
    data: VerifyConfirmIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تأیید ایمیل کاربر با کد ارسال‌شده."""
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    email = (app_user.email or "").strip()
    if not email:
        raise app_auth.bad_request("ابتدا ایمیل خود را در مشخصات حساب ذخیره کنید.")
    ok, message = await verification.confirm_code(
        db, app_user, verification.PURPOSE_EMAIL, email, data.code
    )
    if not ok:
        raise app_auth.bad_request(message)
    app_user.email_verified = True
    await db.commit()
    return {"ok": True, "detail": "ایمیل شما با موفقیت تأیید شد."}


@router.post("/verify/mobile/request")
async def request_mobile_verification(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """درخواست کد تأیید موبایل؛ کد با پیامک به شمارهٔ ثبت‌شده ارسال می‌شود."""
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    mobile = (app_user.mobile or "").strip()
    if not mobile:
        raise app_auth.bad_request("شمارهٔ موبایل ثبت نشده است.")
    if app_user.mobile_verified:
        return {"ok": True, "already_verified": True, "detail": "موبایل شما قبلاً تأیید شده است."}
    return await _issue_and_send(
        db,
        principal,
        app_user,
        verification.PURPOSE_MOBILE,
        mobile,
        subject="",
        text_body="",
        html_body="",
        sms_text="کد تأیید ویدارا: {code}\nاین کد تا ۱۰ دقیقه معتبر است.",
    )


@router.post("/verify/mobile/confirm")
async def confirm_mobile_verification(
    data: VerifyConfirmIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تأیید شمارهٔ موبایل کاربر با کد ارسال‌شده."""
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    mobile = (app_user.mobile or "").strip()
    if not mobile:
        raise app_auth.bad_request("شمارهٔ موبایل ثبت نشده است.")
    ok, message = await verification.confirm_code(
        db, app_user, verification.PURPOSE_MOBILE, mobile, data.code
    )
    if not ok:
        raise app_auth.bad_request(message)
    app_user.mobile_verified = True
    await db.commit()
    return {"ok": True, "detail": "شمارهٔ موبایل شما با موفقیت تأیید شد."}
async def my_organizations(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """سازمان\u200cهایی که کاربر جاری در آن\u200cها حساب فعال دارد (برای تغییر سازمان)."""
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    siblings = await app_auth.find_sibling_accounts(db, app_user)
    items: List[Dict[str, Any]] = []
    for row in siblings:
        brief = await _organization_brief(db, row)
        brief["is_current"] = int(row.organization_id) == int(app_user.organization_id)
        items.append(brief)
    items.sort(key=lambda item: (not item["is_current"], item["name"]))
    await db.commit()
    return {"items": items, "current_organization_id": int(app_user.organization_id)}


@router.post("/switch-organization")
async def switch_organization(
    data: SwitchOrganizationIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تغییر فضای کاری فعال نشست بدون خروج کامل از سامانه.

    توکن تازه برای حساب همان شخص (شناسهٔ اصلی: کد ملی) در فضای مقصد صادر می‌شود؛
    بنابراین نقش و همهٔ گاردهای دسترسی از فضای جدید خوانده می‌شوند. برای جلوگیری
    از ارتقای دسترسی، نام کاربری **و** رمز عبور همان فضا الزاماً بررسی می‌شوند.
    """
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    siblings = await app_auth.find_sibling_accounts(db, app_user)
    target = next(
        (row for row in siblings if int(row.organization_id) == int(data.organization_id)),
        None,
    )
    if target is None:
        raise app_auth.not_found("در سازمان انتخاب‌شده حساب فعالی برای شما وجود ندارد.")

    if int(target.id) == int(app_user.id):
        payload = await _session_payload(db, app_user)
        payload["switched"] = False
        await db.commit()
        return payload

    target_username = (target.username or "").strip().lower()
    given_username = app_auth.to_latin_digits((data.username or "").strip()).lower()
    credentials_ok = target_username == given_username and app_auth.verify_password(
        data.password, target.password_hash or ""
    )
    if not credentials_ok:
        raise app_auth.bad_request(
            "نام کاربری یا رمز عبور حساب شما در سازمان انتخاب‌شده نادرست است."
        )

    target.last_login_at = app_auth.utc_now()
    payload = await _session_payload(db, target)
    payload["switched"] = True
    await db.commit()
    return payload


@router.post("/change-password")
async def change_password(
    data: ChangePasswordIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    if not app_auth.verify_password(data.current_password, app_user.password_hash or ""):
        raise app_auth.bad_request("رمز عبور فعلی نادرست است.")
    new_password = app_auth.validate_password(data.new_password)
    if app_auth.verify_password(new_password, app_user.password_hash or ""):
        raise app_auth.bad_request("رمز عبور جدید باید با رمز فعلی متفاوت باشد.")

    app_user.password_hash = app_auth.hash_password(new_password)
    app_user.must_change_password = False
    await db.commit()
    return {"ok": True, "detail": "رمز عبور با موفقیت تغییر کرد."}


@router.post("/complete-profile")
async def complete_profile(
    data: CompleteProfileIn,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تکمیل اجباری مشخصات کاربرِ ساخته‌شده توسط مدیر در نخستین ورود.

    نام کاربری جدید (یکتا در سازمان)، رمز عبور جدید و کد ملی الزامی‌اند؛ کد ملی
    شناسهٔ اصلی هویت است و اگر قبلاً در سامانه ثبت شده باشد، نام و نام خانوادگی
    باید با همان هویت سازگار باشد. پس از موفقیت، پرچم ``must_change_password``
    برداشته می‌شود و کاربر وارد فضای کاری می‌شود. موبایل از اینجا قابل تغییر
    نیست (مرجع ورود حساب است).
    """
    app_user = await app_auth.load_app_user(db, principal.app_user_id)

    username = app_auth.normalize_username(data.username)
    if await app_auth.username_taken(
        db, username, exclude_id=int(app_user.id), organization_id=principal.organization_id
    ):
        raise app_auth.conflict(
            "این نام کاربری در همین سازمان قبلاً استفاده شده است. نام کاربری دیگری انتخاب کنید."
        )

    new_password = app_auth.validate_password(data.new_password)
    if app_auth.verify_password(new_password, app_user.password_hash or ""):
        raise app_auth.bad_request("رمز عبور جدید باید با رمز فعلی متفاوت باشد.")

    national_id = app_auth.normalize_national_id(data.national_id)
    # یک کد ملی = یک هویت در کل سامانه؛ همهٔ حساب‌های همان کد ملی به هم
    # پیوند می‌خورند و نام و نام خانوادگی باید با سوابق سازگار باشد.
    await app_auth.ensure_national_id_identity(
        db,
        national_id,
        app_user.first_name,
        app_user.last_name,
        exclude_id=int(app_user.id),
    )
    email = app_auth.normalize_email(data.email or "")
    gender = app_auth.normalize_gender(data.gender) if (data.gender or "").strip() else ""

    app_user.username = username
    app_user.password_hash = app_auth.hash_password(new_password)
    app_user.national_id = national_id
    app_user.email = email
    if gender:
        app_user.gender = gender
    app_user.must_change_password = False

    membership = await app_auth.membership_of(db, app_user)
    if membership is not None:
        membership.full_name = app_auth.full_name_of(app_user.first_name, app_user.last_name)
        membership.email = email or ""

    payload = app_auth.user_payload(app_user, int(membership.id) if membership else None)
    await db.commit()
    return {"ok": True, "detail": "مشخصات حساب شما با موفقیت تکمیل شد.", "user": payload}


@router.get("/users")
async def list_users(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست کاربران سازمان جاری (فقط مدیر سازمان)."""
    result = await db.execute(
        select(App_users)
        .where(App_users.organization_id == principal.organization_id)
        .order_by(App_users.id.asc())
    )
    users = list(result.scalars().all())
    items: List[Dict[str, Any]] = []
    for app_user in users:
        membership = await app_auth.membership_of(db, app_user)
        items.append(app_auth.user_payload(app_user, int(membership.id) if membership else None))
    await db.commit()
    return {"items": items}


@router.post("/users")
async def create_user(
    data: UserIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ساخت دبیر/عضو با حداقل اطلاعات: نام، نام خانوادگی، موبایل و نقش.

    نام کاربری = شمارهٔ موبایل؛ رمز عبور = رمز تعیین‌شدهٔ مدیر یا در نبودِ آن
    رمز پیش‌فرض سیستم. کاربر در نخستین ورود ملزم به تکمیل مشخصات (نام کاربری
    جدید، رمز جدید و کد ملی) است.
    """
    mobile = app_auth.normalize_mobile(data.mobile)
    password = app_auth.validate_password(data.password or app_auth.DEFAULT_PASSWORD)
    role = app_auth.normalize_role(data.role)
    email = app_auth.normalize_email(data.email)
    national_id = (
        app_auth.normalize_national_id(data.national_id)
        if (data.national_id or "").strip()
        else ""
    )
    gender = app_auth.normalize_gender(data.gender) if (data.gender or "").strip() else ""

    existing = await app_auth.find_existing_account(
        db, mobile, mobile, organization_id=principal.organization_id
    )
    if existing is not None:
        raise app_auth.conflict(
            "کاربری با این شمارهٔ موبایل در همین سازمان قبلاً ثبت شده است. "
            "برای ویرایش نقش او از فهرست کاربران سازمان استفاده کنید."
        )

    # اگر مدیر کد ملی را هم وارد کرده باشد، باید با سوابق همان کد ملی در کل
    # سامانه سازگار باشد (یک کد ملی = یک هویت).
    await app_auth.ensure_national_id_identity(
        db, national_id, data.first_name.strip(), data.last_name.strip()
    )

    app_user = await app_auth.create_app_user(
        db,
        organization_id=principal.organization_id,
        username=mobile,
        password=password,
        first_name=data.first_name.strip(),
        last_name=data.last_name.strip(),
        mobile=mobile,
        email=email,
        national_id=national_id,
        gender=gender,
        role=role,
        must_change_password=True,
    )
    membership = await app_auth.membership_of(db, app_user)
    payload = app_auth.user_payload(app_user, int(membership.id) if membership else None)
    payload["default_credentials"] = {
        "username": mobile,
        "password": password,
        "is_default_password": password == app_auth.DEFAULT_PASSWORD,
    }
    await db.commit()
    return payload


@router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    data: UserUpdateIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ویرایش کاربر سازمان؛ مرز مستأجر با ``organization_id`` اجبار می‌شود."""
    result = await db.execute(
        select(App_users).where(
            App_users.id == user_id,
            App_users.organization_id == principal.organization_id,
        )
    )
    app_user = result.scalars().first()
    if app_user is None:
        raise app_auth.not_found("کاربر مورد نظر در این سازمان یافت نشد.")

    if data.first_name is not None:
        app_user.first_name = data.first_name.strip() or app_user.first_name
    if data.last_name is not None:
        app_user.last_name = data.last_name.strip() or app_user.last_name
    if data.mobile is not None and data.mobile.strip():
        new_mobile = app_auth.normalize_mobile(data.mobile)
        if new_mobile != (app_user.mobile or ""):
            app_user.mobile_verified = False
        app_user.mobile = new_mobile
    if data.email is not None:
        new_email = app_auth.normalize_email(data.email)
        if new_email != (app_user.email or ""):
            app_user.email_verified = False
        app_user.email = new_email
    if data.national_id is not None and data.national_id.strip():
        new_national_id = app_auth.normalize_national_id(data.national_id)
        if new_national_id != (app_user.national_id or ""):
            # یک کد ملی = یک هویت؛ نام و نام خانوادگی باید با سوابق همان کد ملی
            # در کل سامانه سازگار باشد.
            await app_auth.ensure_national_id_identity(
                db,
                new_national_id,
                app_user.first_name,
                app_user.last_name,
                exclude_id=int(app_user.id),
            )
            app_user.national_id = new_national_id
    if data.gender is not None and data.gender.strip():
        app_user.gender = app_auth.normalize_gender(data.gender)
    if data.role is not None and data.role.strip():
        new_role = app_auth.normalize_role(data.role)
        if app_user.id == principal.app_user_id and new_role != app_auth.ROLE_ADMIN:
            raise app_auth.bad_request("نمی‌توانید نقش مدیریت خودتان را تغییر دهید.")
        app_user.role = new_role
    if data.status is not None and data.status.strip():
        new_status = data.status.strip().lower()
        if new_status not in ("active", "disabled"):
            raise app_auth.bad_request("وضعیت کاربر باید «active» یا «disabled» باشد.")
        if app_user.id == principal.app_user_id and new_status != "active":
            raise app_auth.bad_request("نمی‌توانید حساب کاربری خودتان را غیرفعال کنید.")
        app_user.status = new_status
    if data.reset_password:
        app_user.password_hash = app_auth.hash_password(app_auth.DEFAULT_PASSWORD)
        app_user.must_change_password = True

    membership = await app_auth.membership_of(db, app_user)
    if membership is not None:
        membership.full_name = app_auth.full_name_of(app_user.first_name, app_user.last_name)
        membership.email = app_user.email or ""
        membership.role = app_user.role
        membership.status = app_user.status or "active"

    payload = app_auth.user_payload(app_user, int(membership.id) if membership else None)
    if data.reset_password:
        payload["temporary_password"] = app_auth.DEFAULT_PASSWORD
    await db.commit()
    return payload


@router.get("/members")
async def list_members(
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست خلاصهٔ اعضای سازمان برای انتخاب دبیر/شرکت‌کننده در فرم جلسه."""
    result = await db.execute(
        select(Memberships)
        .where(
            Memberships.organization_id == principal.organization_id,
            Memberships.status == "active",
        )
        .order_by(Memberships.id.asc())
    )
    items = [
        {
            "membership_id": int(row.id),
            "full_name": row.full_name or "",
            "role": row.role or app_auth.ROLE_MEMBER,
            "email": row.email or "",
        }
        for row in result.scalars().all()
    ]
    await db.commit()
    return {"items": items}
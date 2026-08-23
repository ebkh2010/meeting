"""روتر احراز هویت مستقل و مدیریت کاربران سازمان.

قراردادها:

* ``POST /api/v1/app-auth/register`` — ثبت‌نام مدیر + ساخت سازمان اختصاصی.
* ``POST /api/v1/app-auth/login`` — ورود با نام کاربری و رمز عبور، صدور توکن.
* ``GET  /api/v1/app-auth/me`` — پروفایل کاربر جاری.
* ``POST /api/v1/app-auth/change-password`` — تغییر رمز عبور توسط خود کاربر.
* ``GET/POST/PATCH /api/v1/app-auth/users`` — مدیریت کاربران توسط مدیر سازمان.

قاعدهٔ اعتبارنامهٔ پیش‌فرض کاربران ساخته‌شده توسط مدیر:
نام کاربری = شمارهٔ موبایل، رمز عبور = کد ملی، با الزام تغییر رمز در نخستین ورود.
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
    username: str
    password: str
    # اگر شخص در چند سازمان حساب داشته باشد، انتخاب سازمان اجباری است.
    organization_id: Optional[int] = None


class SwitchOrganizationIn(BaseModel):
    """تغییر سازمان فعال نشست؛ رمز عبور حساب سازمان مقصد تأیید می\u200cشود."""

    organization_id: int
    password: str


class ChangePasswordIn(BaseModel):
    current_password: str
    new_password: str


class UserIn(BaseModel):
    first_name: str = Field(..., min_length=1, max_length=100)
    last_name: str = Field(..., min_length=1, max_length=100)
    mobile: str
    national_id: str
    gender: str
    email: str = ""
    role: str = app_auth.ROLE_MEMBER


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

    # یکتایی نام کاربری در مرز سازمان است، نه سراسری؛ هر ثبت‌نام یک سازمان
    # مستقل می‌سازد، پس همین شخص می‌تواند در چند سازمان حساب داشته باشد و در
    # ورود، سازمان فعال نشست را انتخاب کند.
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
    payload = await _session_payload(db, app_user)
    await db.commit()
    return payload


async def _organization_brief(db: AsyncSession, app_user: App_users) -> Dict[str, Any]:
    """کارت کوتاه سازمان + نقش همان حساب، برای مرحلهٔ انتخاب سازمان در ورود."""
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
    """ورود با نام کاربری و رمز عبور + انتخاب سازمان در عضویت چندسازمانی.

    اگر یک شخص با همین اعتبارنامه در چند سازمان حساب فعال داشته باشد، پاسخ نخست
    بدون توکن و با ``needs_organization=true`` برمی‌گردد تا کاربر سازمان فعال
    نشست را انتخاب کند؛ نقش همیشه از حساب همان سازمان خوانده می‌شود.
    """
    username = app_auth.to_latin_digits((data.username or "").strip()).lower()
    if not username or not data.password:
        raise app_auth.bad_request("نام کاربری و رمز عبور را وارد کنید.")

    candidates = await app_auth.find_login_candidates(db, username)
    active = [row for row in candidates if (row.status or "active") == "active"]
    if not active:
        if candidates:
            raise app_auth.forbidden("حساب کاربری شما توسط مدیر سازمان غیرفعال شده است.")
        raise app_auth.unauthorized("نام کاربری یا رمز عبور نادرست است.")

    # مالکیت این نام کاربری باید با رمز عبور دست‌کم یکی از حساب‌های فعال اثبات شود؛
    # در غیر این صورت فهرست سازمان‌ها افشا نمی‌شود.
    matched = [
        row for row in active if app_auth.verify_password(data.password, row.password_hash or "")
    ]
    if not matched:
        raise app_auth.unauthorized("نام کاربری یا رمز عبور نادرست است.")

    if data.organization_id is not None:
        selected = next(
            (row for row in active if int(row.organization_id) == int(data.organization_id)),
            None,
        )
        if selected is None:
            raise app_auth.bad_request(
                "در سازمان انتخاب‌شده حساب فعالی با این اعتبارنامه وجود ندارد."
            )
        # رمز عبور هر سازمان مستقل است؛ ورود به سازمان مقصد باید با رمز همان سازمان
        # تأیید شود تا مرز مستأجر حفظ بماند.
        if not app_auth.verify_password(data.password, selected.password_hash or ""):
            raise app_auth.unauthorized(
                "رمز عبور شما در سازمان انتخاب‌شده متفاوت است؛ رمز عبور همان سازمان را وارد کنید."
            )
    elif len(active) > 1:
        organizations = [await _organization_brief(db, row) for row in active]
        await db.commit()
        return {
            "needs_organization": True,
            "organizations": organizations,
            "detail": "شما در چند سازمان عضو هستید؛ سازمان مورد نظر را انتخاب کنید.",
        }
    else:
        selected = active[0]

    selected.last_login_at = app_auth.utc_now()
    payload = await _session_payload(db, selected)
    payload["needs_organization"] = False
    payload["organizations"] = [await _organization_brief(db, row) for row in active]
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


@router.get("/organizations")
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
    """تغییر سازمان فعال نشست بدون خروج کامل از سامانه.

    توکن تازه برای حساب همان شخص در سازمان مقصد صادر می\u200cشود؛ بنابراین نقش و
    همهٔ گاردهای دسترسی از سازمان جدید خوانده می\u200cشوند. برای جلوگیری از ارتقای
    دسترسی، رمز عبور حساب سازمان مقصد الزاماً بررسی می\u200cگردد.
    """
    app_user = await app_auth.load_app_user(db, principal.app_user_id)
    siblings = await app_auth.find_sibling_accounts(db, app_user)
    target = next(
        (row for row in siblings if int(row.organization_id) == int(data.organization_id)),
        None,
    )
    if target is None:
        raise app_auth.not_found("در سازمان انتخاب\u200cشده حساب فعالی برای شما وجود ندارد.")

    if int(target.id) == int(app_user.id):
        payload = await _session_payload(db, app_user)
        payload["switched"] = False
        await db.commit()
        return payload

    if not app_auth.verify_password(data.password, target.password_hash or ""):
        raise app_auth.bad_request("رمز عبور حساب شما در سازمان انتخاب\u200cشده نادرست است.")

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
    """ساخت کاربر دبیر/عضو با اعتبارنامهٔ پیش‌فرض: نام کاربری=موبایل، رمز=کد ملی."""
    mobile = app_auth.normalize_mobile(data.mobile)
    national_id = app_auth.normalize_national_id(data.national_id)
    gender = app_auth.normalize_gender(data.gender)
    email = app_auth.normalize_email(data.email)
    role = app_auth.normalize_role(data.role)

    existing = await app_auth.find_existing_account(
        db, mobile, mobile, organization_id=principal.organization_id
    )
    if existing is not None:
        raise app_auth.conflict(
            "کاربری با این شمارهٔ موبایل در همین سازمان قبلاً ثبت شده است. "
            "برای ویرایش نقش او از فهرست کاربران سازمان استفاده کنید."
        )

    app_user = await app_auth.create_app_user(
        db,
        organization_id=principal.organization_id,
        username=mobile,
        password=national_id,
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
        "password_hint": "کد ملی کاربر",
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
        app_user.mobile = new_mobile
    if data.email is not None:
        app_user.email = app_auth.normalize_email(data.email)
    if data.national_id is not None and data.national_id.strip():
        app_user.national_id = app_auth.normalize_national_id(data.national_id)
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
        app_user.password_hash = app_auth.hash_password(app_user.national_id or app_user.mobile)
        app_user.must_change_password = True

    membership = await app_auth.membership_of(db, app_user)
    if membership is not None:
        membership.full_name = app_auth.full_name_of(app_user.first_name, app_user.last_name)
        membership.email = app_user.email or ""
        membership.role = app_user.role
        membership.status = app_user.status or "active"

    payload = app_auth.user_payload(app_user, int(membership.id) if membership else None)
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
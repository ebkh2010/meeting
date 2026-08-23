"""روتر تنظیمات اعلان سازمان: SMTP و پیامک قاصدک + ارسال آزمایشی و گزارش ارسال."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.app_auth import get_app_admin, get_app_principal
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.notify_deliveries import Notify_deliveries
from services import app_auth, notify_channels as channels
from services.meeting_invites import send_meeting_invites

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/notify", tags=["notify"])


class NotifySettingsIn(BaseModel):
    smtp_enabled: Optional[bool] = None
    smtp_host: Optional[str] = None
    smtp_port: Optional[int] = None
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None
    smtp_use_tls: Optional[bool] = None
    smtp_use_ssl: Optional[bool] = None
    smtp_from_email: Optional[str] = None
    smtp_from_name: Optional[str] = None
    sms_enabled: Optional[bool] = None
    sms_api_key: Optional[str] = None
    sms_line_number: Optional[str] = None


class TestEmailIn(BaseModel):
    to_email: str = ""


class TestSmsIn(BaseModel):
    to_mobile: str = ""


@router.get("/settings")
async def read_settings(
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    row = await channels.get_or_create_settings(db, principal.organization_id)
    payload = channels.settings_payload(row)
    await db.commit()
    return payload


@router.patch("/settings")
async def update_settings(
    data: NotifySettingsIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    row = await channels.get_or_create_settings(db, principal.organization_id)

    if data.smtp_host is not None:
        row.smtp_host = data.smtp_host.strip()
    if data.smtp_port is not None:
        port = int(data.smtp_port)
        if not 1 <= port <= 65535:
            raise app_auth.bad_request("پورت SMTP باید بین ۱ تا ۶۵۵۳۵ باشد.")
        row.smtp_port = port
    if data.smtp_username is not None:
        row.smtp_username = data.smtp_username.strip()
    if data.smtp_password:
        row.smtp_password_enc = app_auth.encrypt_secret(data.smtp_password)
    if data.smtp_use_tls is not None:
        row.smtp_use_tls = bool(data.smtp_use_tls)
    if data.smtp_use_ssl is not None:
        row.smtp_use_ssl = bool(data.smtp_use_ssl)
    if data.smtp_from_email is not None:
        row.smtp_from_email = app_auth.normalize_email(data.smtp_from_email) if data.smtp_from_email else ""
    if data.smtp_from_name is not None:
        row.smtp_from_name = data.smtp_from_name.strip()
    if data.smtp_enabled is not None:
        if data.smtp_enabled and not (row.smtp_host and row.smtp_from_email):
            raise app_auth.bad_request("برای فعال‌سازی ایمیل، میزبان SMTP و ایمیل فرستنده الزامی است.")
        row.smtp_enabled = bool(data.smtp_enabled)

    if data.sms_api_key:
        row.sms_api_key_enc = app_auth.encrypt_secret(data.sms_api_key.strip())
    if data.sms_line_number is not None:
        row.sms_line_number = app_auth.to_latin_digits(data.sms_line_number.strip())
    if data.sms_enabled is not None:
        if data.sms_enabled and not (row.sms_api_key_enc and row.sms_line_number):
            raise app_auth.bad_request("برای فعال‌سازی پیامک، کلید API قاصدک و شمارهٔ خط الزامی است.")
        row.sms_enabled = bool(data.sms_enabled)

    payload = channels.settings_payload(row)
    await db.commit()
    return payload


@router.post("/test-email")
async def test_email(
    data: TestEmailIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ارسال ایمیل آزمایشی با تنظیمات ذخیره‌شدهٔ سازمان."""
    row = await channels.get_or_create_settings(db, principal.organization_id)
    target = app_auth.normalize_email(data.to_email) if data.to_email else (principal.email or "")
    if not target:
        raise app_auth.bad_request("نشانی ایمیل مقصد را وارد کنید.")
    if not row.smtp_enabled:
        raise app_auth.bad_request("ابتدا ارسال ایمیل را فعال و ذخیره کنید.")
    await db.commit()

    now_label = channels.format_jalali_datetime(datetime.now(timezone.utc))
    result = await channels.send_email(
        row,
        to_email=target,
        subject="ایمیل آزمایشی — ویدارا - نسخه جلسات",
        text_body=(
            "این یک ایمیل آزمایشی از «ویدارا - نسخه جلسات» است.\n"
            f"زمان ارسال: {now_label}\n"
            "اگر این پیام را می‌بینید، تنظیمات SMTP سازمان درست است."
        ),
        html_body=(
            '<div dir="rtl" style="font-family:Tahoma,Arial,sans-serif;color:#0f172a">'
            "<h3>ایمیل آزمایشی ویدارا</h3>"
            f"<p>زمان ارسال: {now_label}</p>"
            "<p>تنظیمات SMTP سازمان شما درست کار می‌کند.</p></div>"
        ),
    )
    if not result.ok:
        raise app_auth.bad_request(f"ارسال ایمیل آزمایشی ناموفق بود: {result.error}")
    return {"ok": True, "recipient": target, "detail": "ایمیل آزمایشی ارسال شد."}


@router.post("/test-sms")
async def test_sms(
    data: TestSmsIn,
    principal: app_auth.AppPrincipal = Depends(get_app_admin),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ارسال پیامک آزمایشی از سرویس قاصدک."""
    row = await channels.get_or_create_settings(db, principal.organization_id)
    target = app_auth.normalize_mobile(data.to_mobile) if data.to_mobile else (principal.mobile or "")
    if not target:
        raise app_auth.bad_request("شماره موبایل مقصد را وارد کنید.")
    if not row.sms_enabled:
        raise app_auth.bad_request("ابتدا ارسال پیامک را فعال و ذخیره کنید.")
    await db.commit()

    now_label = channels.format_jalali_datetime(datetime.now(timezone.utc))
    result = await channels.send_sms(
        row,
        receptor=target,
        message=f"پیامک آزمایشی ویدارا - نسخه جلسات\nزمان: {now_label}",
        client_reference_id=f"test-{principal.organization_id}",
    )
    if not result.ok:
        raise app_auth.bad_request(f"ارسال پیامک آزمایشی ناموفق بود: {result.error}")
    return {
        "ok": True,
        "recipient": target,
        "provider_message_id": result.provider_message_id,
        "detail": "پیامک آزمایشی ارسال شد.",
    }


@router.get("/deliveries")
async def list_deliveries(
    meeting_id: Optional[int] = None,
    limit: int = 60,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """گزارش ارسال اعلان‌ها؛ فقط در مرز سازمان کاربر جاری."""
    stmt = select(Notify_deliveries).where(
        Notify_deliveries.organization_id == principal.organization_id
    )
    if meeting_id:
        stmt = stmt.where(Notify_deliveries.meeting_id == meeting_id)
    stmt = stmt.order_by(Notify_deliveries.id.desc()).limit(max(min(int(limit or 60), 200), 1))
    result = await db.execute(stmt)
    items: List[Dict[str, Any]] = [
        {
            "id": int(row.id),
            "meeting_id": int(row.meeting_id or 0),
            "membership_id": int(row.membership_id or 0),
            "channel": row.channel,
            "recipient": row.recipient or "",
            "recipient_name": row.recipient_name or "",
            "status": row.status,
            "provider_message_id": row.provider_message_id or "",
            "error_message": row.error_message or "",
            "body_preview": row.body_preview or "",
            "created_at": row.created_at.isoformat() if row.created_at else "",
        }
        for row in result.scalars().all()
    ]
    await db.commit()
    return {"items": items}


@router.post("/meetings/{meeting_id}/resend")
async def resend_meeting_invites(
    meeting_id: int,
    principal: app_auth.AppPrincipal = Depends(get_app_principal),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ارسال دوبارهٔ اعلان دعوت جلسه (مدیر سازمان یا دبیر)."""
    if principal.role not in (app_auth.ROLE_ADMIN, app_auth.ROLE_SECRETARY):
        raise app_auth.forbidden("ارسال دوبارهٔ اعلان فقط برای مدیر سازمان یا دبیر مجاز است.")
    summary = await send_meeting_invites(
        db,
        organization_id=principal.organization_id,
        meeting_id=meeting_id,
    )
    return summary


def _recent_window() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=30)
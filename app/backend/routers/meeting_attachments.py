"""روتر پیوست‌های دستور جلسه و ارسال دوبارهٔ دعوت.

قواعد کلیدی:

* هر عملیات ابتدا ``TenantContext`` را می‌سازد و همهٔ کوئری‌ها با
  ``organization_id`` محدود می‌شوند؛ رکورد سازمان دیگر «یافت نشد» است.
* ثبت/حذف پیوست و ارسال دوباره فقط برای مدیر سازمان یا دبیر همان جلسه مجاز است.
* الگوی بارگذاری همانند فایل صوتی است: ابتدا URL امضاشدهٔ آپلود گرفته می‌شود،
  مرورگر فایل را مستقیم در باکت خصوصی می‌گذارد و سپس فراداده ثبت می‌گردد.
* برای هر عملیات مؤثر یک رکورد Audit ثبت می‌شود.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from core.database import get_db
from dependencies.app_auth import get_workspace_user as get_current_user
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from schemas.auth import UserResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.meeting_attachments import Meeting_attachments
from models.meetings import Meetings
from services import meeting_files as files
from services import upload_limits as limits_service
from services.meeting_invites import send_meeting_invites
from services.mgmt_core import (
    audit,
    bad_request,
    get_owned,
    require_meeting_manager,
    resolve_context,
    secrets_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/workspace", tags=["meeting-attachments"])


class AttachmentUploadUrlIn(BaseModel):
    """درخواست URL امضاشده برای بارگذاری یک پیوست."""

    file_name: str
    size_bytes: int = 0
    content_type: Optional[str] = None


class AttachmentRegisterIn(BaseModel):
    """ثبت فراداده پس از بارگذاری موفق فایل در باکت."""

    object_key: str
    file_name: str
    size_bytes: int = 0
    content_type: Optional[str] = None


def _normalize_type(value: Optional[str]) -> str:
    return (value or "application/octet-stream").split(";")[0].strip().lower()


def _validate_upload(
    file_name: str,
    size_bytes: int,
    content_type: Optional[str],
    max_attachment_bytes: int,
) -> str:
    """اعتبارسنجی مشترک نام، حجم و نوع فایل؛ نوع نرمال‌شده را برمی‌گرداند.

    سقف حجم از تنظیمات سازمان می‌آید (نه مقدار ثابت کد) تا مدیر سازمان بتواند
    آن را در تنظیمات مدیریتی تغییر دهد.
    """
    if not (file_name or "").strip():
        raise bad_request("نام فایل پیوست معتبر نیست.")
    if int(size_bytes or 0) <= 0:
        raise bad_request("فایل پیوست خالی است.")
    if int(size_bytes) > int(max_attachment_bytes):
        max_mb = int(max_attachment_bytes) // (1024 * 1024)
        actual_mb = round(int(size_bytes) / (1024 * 1024), 1)
        raise bad_request(
            f"حجم فایل پیوست ({actual_mb} مگابایت) از سقف مجاز این سازمان "
            f"({max_mb} مگابایت) بیشتر است."
        )
    normalized = _normalize_type(content_type)
    if normalized not in files.ALLOWED_ATTACHMENT_TYPES:
        raise bad_request(
            "نوع فایل پیوست مجاز نیست. فایل‌های PDF، Word، Excel، PowerPoint، تصویر، متن و ZIP پذیرفته می‌شوند."
        )
    return normalized


def _dump(row: Meeting_attachments) -> Dict[str, Any]:
    return {
        "id": int(row.id),
        "meeting_id": int(row.meeting_id),
        "file_name": row.file_name,
        "content_type": row.content_type or "",
        "size_bytes": int(row.size_bytes or 0),
        "uploaded_by_name": row.uploaded_by_name or "",
        "created_at": row.created_at.isoformat() if row.created_at else "",
    }


async def _list_rows(
    db: AsyncSession, organization_id: int, meeting_id: int
) -> List[Meeting_attachments]:
    result = await db.execute(
        select(Meeting_attachments)
        .where(
            Meeting_attachments.organization_id == organization_id,
            Meeting_attachments.meeting_id == meeting_id,
        )
        .order_by(Meeting_attachments.id.asc())
    )
    return list(result.scalars().all())


@router.get("/meetings/{meeting_id}/attachments")
async def list_attachments(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست پیوست‌های یک جلسه برای همهٔ اعضای همان سازمان."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    rows = await _list_rows(db, ctx.organization_id, meeting_id)
    await db.commit()
    return {
        "items": [_dump(row) for row in rows],
        "total": len(rows),
        "can_manage": ctx.is_secretary_of(meeting),
    }


@router.post("/meetings/{meeting_id}/attachments/upload-url")
async def attachment_upload_url(
    meeting_id: int,
    payload: AttachmentUploadUrlIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """URL امضاشدهٔ بارگذاری پیوست در باکت خصوصی سازمان."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    limits = await limits_service.get_limits(db, ctx.organization_id)
    file_name = payload.file_name.strip()
    content_type = _validate_upload(
        file_name, payload.size_bytes, payload.content_type, limits["max_attachment_bytes"]
    )
    object_key = files.build_object_key(
        ctx.organization_id, meeting_id, secrets_token(12), file_name
    )
    upload_url = await files.create_attachment_upload_url(object_key)
    await db.commit()
    if not upload_url:
        raise bad_request("سرویس ذخیره‌سازی فایل در دسترس نیست؛ کمی بعد دوباره تلاش کنید.")
    return {
        "upload_url": upload_url,
        "object_key": object_key,
        "content_type": content_type,
    }


@router.post("/meetings/{meeting_id}/attachments")
async def register_attachment(
    meeting_id: int,
    payload: AttachmentRegisterIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ثبت فراداده پیوست پس از بارگذاری موفق در باکت."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    limits = await limits_service.get_limits(db, ctx.organization_id)
    file_name = payload.file_name.strip()
    content_type = _validate_upload(
        file_name, payload.size_bytes, payload.content_type, limits["max_attachment_bytes"]
    )
    object_key = payload.object_key.strip()
    expected_prefix = f"org-{ctx.organization_id}/meeting-{meeting_id}/"
    if not object_key.startswith(expected_prefix):
        raise bad_request("کلید فایل بارگذاری‌شده با این جلسه هم‌خوانی ندارد.")

    row = Meeting_attachments(
        organization_id=ctx.organization_id,
        meeting_id=meeting_id,
        object_key=object_key,
        file_name=file_name,
        content_type=content_type,
        size_bytes=int(payload.size_bytes),
        uploaded_by_user_id=ctx.user_id,
        uploaded_by_name=ctx.actor_name,
    )
    db.add(row)
    await db.flush()
    await audit(
        db,
        ctx,
        "meeting.attachment.added",
        "meeting_attachment",
        int(row.id),
        f"پیوست «{file_name}» به جلسهٔ «{meeting.title}» افزوده شد",
    )
    result = _dump(row)
    await db.commit()
    return result


@router.get("/attachments/{attachment_id}/download-url")
async def attachment_download_url(
    attachment_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """پیوند امضاشدهٔ دانلود برای اعضای همان سازمان."""
    ctx = await resolve_context(db, current_user)
    row = await get_owned(db, Meeting_attachments, attachment_id, ctx, "فایل پیوست")
    url = await files.create_attachment_download_url(row.object_key)
    await db.commit()
    if not url:
        raise bad_request("دریافت پیوند دانلود ناموفق بود؛ دوباره تلاش کنید.")
    return {"download_url": url, "file_name": row.file_name}


@router.delete("/attachments/{attachment_id}")
async def delete_attachment(
    attachment_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """حذف پیوست توسط مدیر سازمان یا دبیر همان جلسه."""
    ctx = await resolve_context(db, current_user)
    row = await get_owned(db, Meeting_attachments, attachment_id, ctx, "فایل پیوست")
    meeting = await get_owned(db, Meetings, int(row.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    object_key = row.object_key
    file_name = row.file_name
    await db.delete(row)
    await audit(
        db,
        ctx,
        "meeting.attachment.deleted",
        "meeting_attachment",
        attachment_id,
        f"پیوست «{file_name}» از جلسهٔ «{meeting.title}» حذف شد",
    )
    await db.commit()
    await files.delete_attachment_object(object_key)
    return {"success": True}


@router.post("/meetings/{meeting_id}/resend-agenda")
async def resend_agenda(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ارسال دوبارهٔ دستور جلسه و فایل‌های پیوست به همهٔ حاضران."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    organization_id = ctx.organization_id
    await audit(
        db,
        ctx,
        "meeting.agenda.resent",
        "meeting",
        meeting_id,
        f"ارسال دوبارهٔ دستور جلسه و پیوست‌های «{meeting.title}»",
    )
    await db.commit()

    return await send_meeting_invites(
        db, organization_id=organization_id, meeting_id=meeting_id
    )
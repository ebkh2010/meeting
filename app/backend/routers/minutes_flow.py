"""روتر چرخهٔ صورتجلسه، مصوبات، اقدامات، خروجی ICS و کنسول ادمین.

جریان تأیید مطابق سند معماری: ``draft → in_review → approved → locked``.
دبیر جلسه فقط تا مرحلهٔ ``in_review`` اختیار دارد؛ تأیید و قفل تنها با نقش
مدیر سازمان انجام می‌شود و هر گذار در Audit Log ثبت می‌گردد. پس از قفل شدن،
متن صورتجلسه غیرقابل تغییر است و فقط خروجی چاپ/ICS از آن گرفته می‌شود.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from core.database import get_db
from dependencies.app_auth import get_workspace_user as get_current_user
from fastapi import APIRouter, Depends, Response
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, Field
from schemas.auth import UserResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.action_items import Action_items
from models.agenda_items import Agenda_items
from models.audit_logs import Audit_logs
from models.decisions import Decisions
from models.jobs import Jobs
from models.meetings import Meetings
from models.memberships import Memberships
from models.minute_versions import Minute_versions
from models.minutes import Minutes
from models.organizations import Organizations
from models.participants import Participants
from models.recordings import Recordings
from models.transcripts import Transcripts
from services import mgmt_core as core
from services.ai_gateway import transcription_providers_status
from services.minutes_docx import build_minutes_docx, safe_file_name
from services.mgmt_core import (
    ACTION_FIELDS,
    ACTION_STATUSES,
    DECISION_FIELDS,
    MINUTES_APPROVED,
    MINUTES_DRAFT,
    MINUTES_FIELDS,
    MINUTES_IN_REVIEW,
    MINUTES_LOCKED,
    ROLE_ADMIN,
    ROLE_SECRETARY,
    audit,
    bad_request,
    conflict,
    dump,
    get_owned,
    list_owned,
    notify,
    notify_role,
    quota_snapshot,
    require_meeting_manager,
    require_role,
    resolve_context,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/minutes-flow", tags=["minutes-flow"])


# ---------------------------------------------------------------------------
# مدل‌های ورودی
# ---------------------------------------------------------------------------


class MinutesSaveIn(BaseModel):
    meeting_id: int
    body_markdown: str = Field(..., min_length=10)
    summary: str = ""
    change_note: str = ""


class MinutesActionIn(BaseModel):
    meeting_id: int
    note: str = ""


class DecisionIn(BaseModel):
    meeting_id: int
    title: str = Field(..., min_length=3, max_length=300)
    description: str = ""
    # منبع ثبت: «manual» برای ورود دستی و «ai» برای پذیرش پیشنهاد هوش مصنوعی.
    source: str = "manual"


class DecisionUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None


class ActionIn(BaseModel):
    meeting_id: int
    decision_id: Optional[int] = None
    title: str = Field(..., min_length=3, max_length=300)
    description: str = ""
    owner_membership_id: Optional[int] = None
    due_date: str = ""
    # منبع ثبت: «manual» برای ورود دستی و «ai» برای پذیرش پیشنهاد هوش مصنوعی.
    source: str = "manual"


class ActionUpdateIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    owner_membership_id: Optional[int] = None
    due_date: Optional[str] = None
    status: Optional[str] = None
    progress_note: Optional[str] = None


# ---------------------------------------------------------------------------
# صورتجلسه: ذخیره و گذارهای وضعیت
# ---------------------------------------------------------------------------


async def _get_minutes(db: AsyncSession, ctx, meeting_id: int) -> Optional[Minutes]:
    result = await db.execute(
        select(Minutes).where(
            Minutes.organization_id == ctx.organization_id, Minutes.meeting_id == meeting_id
        )
    )
    return result.scalars().first()


@router.post("/save")
async def save_minutes(
    payload: MinutesSaveIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """ذخیرهٔ ویرایش دستی صورتجلسه با ثبت نسخهٔ جدید (تاریخچهٔ تغییرات)."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is None:
        minutes = Minutes(
            organization_id=ctx.organization_id,
            meeting_id=payload.meeting_id,
            status=MINUTES_DRAFT,
            current_version=0,
            generated_by="manual",
            review_requested_at="",
            approved_by_name="",
            approved_at="",
            locked_at="",
        )
        db.add(minutes)
    if minutes.status == MINUTES_LOCKED:
        raise conflict("این صورتجلسه قفل شده و ویرایش آن مجاز نیست.")
    if minutes.status == MINUTES_APPROVED and not ctx.is_admin():
        raise conflict(
            "این صورتجلسه تأیید شده است؛ ویرایش دوبارهٔ آن فقط توسط مدیر سازمان مجاز است."
        )

    minutes.body_markdown = payload.body_markdown
    minutes.summary = (payload.summary or "").strip()[:1500]
    minutes.current_version = int(minutes.current_version or 0) + 1
    if minutes.status == MINUTES_APPROVED:
        minutes.status = MINUTES_DRAFT
        minutes.approved_by_name = ""
        minutes.approved_at = ""
    await db.flush()

    db.add(
        Minute_versions(
            organization_id=ctx.organization_id,
            minutes_id=int(minutes.id),
            meeting_id=payload.meeting_id,
            version=int(minutes.current_version),
            body_markdown=minutes.body_markdown,
            summary=minutes.summary,
            status_at_version=minutes.status,
            changed_by_name=ctx.actor_name,
            change_note=(payload.change_note or "ویرایش دستی صورتجلسه")[:300],
        )
    )
    await audit(db, ctx, "minutes.saved", "minutes", int(minutes.id), f"نسخهٔ {minutes.current_version}")
    await db.commit()
    return dump(minutes, MINUTES_FIELDS)


@router.post("/submit-review")
async def submit_for_review(
    payload: MinutesActionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is None or not (minutes.body_markdown or "").strip():
        raise bad_request("پیش از ارسال برای تأیید، متن صورتجلسه باید ثبت شده باشد.")
    if minutes.status == MINUTES_LOCKED:
        raise conflict("این صورتجلسه قفل شده است.")

    minutes.status = MINUTES_IN_REVIEW
    minutes.review_requested_at = core.now_iso()
    await notify_role(
        db,
        ctx.organization_id,
        [ROLE_ADMIN],
        kind="review_request",
        title=f"صورتجلسهٔ «{meeting.title}» در انتظار تأیید شماست",
        body=f"{ctx.actor_name} پیش‌نویس را برای بازبینی ارسال کرد.",
        link=f"/meetings/{payload.meeting_id}",
        dedupe_prefix=f"review-{payload.meeting_id}-{minutes.current_version}",
    )
    await audit(db, ctx, "minutes.submitted_for_review", "minutes", int(minutes.id), meeting.title)
    await db.commit()
    return dump(minutes, MINUTES_FIELDS)


@router.post("/approve")
async def approve_minutes(
    payload: MinutesActionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """تأیید صورتجلسه؛ فقط مدیر سازمان."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is None:
        raise bad_request("صورتجلسه‌ای برای این جلسه ثبت نشده است.")
    if minutes.status == MINUTES_LOCKED:
        raise conflict("این صورتجلسه قفل شده است.")
    if minutes.status != MINUTES_IN_REVIEW:
        raise conflict("تأیید فقط برای صورتجلسه‌ای که در انتظار بازبینی است انجام می‌شود.")

    minutes.status = MINUTES_APPROVED
    minutes.approved_by_name = ctx.actor_name
    minutes.approved_at = core.now_iso()
    await db.flush()
    db.add(
        Minute_versions(
            organization_id=ctx.organization_id,
            minutes_id=int(minutes.id),
            meeting_id=payload.meeting_id,
            version=int(minutes.current_version or 1),
            body_markdown=minutes.body_markdown,
            summary=minutes.summary,
            status_at_version=MINUTES_APPROVED,
            changed_by_name=ctx.actor_name,
            change_note=(payload.note or "تأیید صورتجلسه")[:300],
        )
    )
    if meeting.secretary_membership_id:
        await notify(
            db,
            ctx.organization_id,
            membership_id=int(meeting.secretary_membership_id),
            user_id=None,
            kind="minutes_approved",
            title=f"صورتجلسهٔ «{meeting.title}» تأیید شد",
            body=f"تأییدکننده: {ctx.actor_name}",
            link=f"/meetings/{payload.meeting_id}",
        )
    await audit(db, ctx, "minutes.approved", "minutes", int(minutes.id), meeting.title)
    await db.commit()
    return dump(minutes, MINUTES_FIELDS)


@router.post("/reject")
async def reject_minutes(
    payload: MinutesActionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """بازگرداندن صورتجلسه به دبیر با توضیح اصلاحات."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is None or minutes.status != MINUTES_IN_REVIEW:
        raise conflict("فقط صورتجلسهٔ در انتظار بازبینی را می‌توان برگرداند.")

    minutes.status = MINUTES_DRAFT
    minutes.review_requested_at = ""
    if meeting.secretary_membership_id:
        await notify(
            db,
            ctx.organization_id,
            membership_id=int(meeting.secretary_membership_id),
            user_id=None,
            kind="minutes_rejected",
            title=f"صورتجلسهٔ «{meeting.title}» نیازمند اصلاح است",
            body=(payload.note or "لطفاً متن را بازبینی و دوباره ارسال کنید."),
            link=f"/meetings/{payload.meeting_id}",
        )
    await audit(
        db, ctx, "minutes.rejected", "minutes", int(minutes.id), (payload.note or "بازگشت برای اصلاح")
    )
    await db.commit()
    return dump(minutes, MINUTES_FIELDS)


@router.post("/lock")
async def lock_minutes(
    payload: MinutesActionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """قفل نهایی؛ پس از این مرحله متن غیرقابل تغییر است."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is None or minutes.status != MINUTES_APPROVED:
        raise conflict("قفل کردن فقط پس از تأیید صورتجلسه امکان‌پذیر است.")

    minutes.status = MINUTES_LOCKED
    minutes.locked_at = core.now_iso()
    participants = await list_owned(
        db, Participants, ctx, Participants.meeting_id == payload.meeting_id
    )
    for participant in participants:
        if participant.membership_id:
            await notify(
                db,
                ctx.organization_id,
                membership_id=int(participant.membership_id),
                user_id=participant.member_user_id,
                kind="minutes_locked",
                title=f"صورتجلسهٔ نهایی «{meeting.title}» منتشر شد",
                body="نسخهٔ نهایی برای مطالعه و دریافت خروجی در دسترس است.",
                link=f"/meetings/{payload.meeting_id}",
                dedupe_key=f"locked-{payload.meeting_id}-{participant.id}",
            )
    await audit(db, ctx, "minutes.locked", "minutes", int(minutes.id), meeting.title)
    await db.commit()
    return dump(minutes, MINUTES_FIELDS)


@router.get("/versions/{meeting_id}")
async def minutes_versions(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    versions = await list_owned(
        db,
        Minute_versions,
        ctx,
        Minute_versions.meeting_id == meeting_id,
        order_by=Minute_versions.version.desc(),
        limit=30,
    )
    await db.commit()
    return {
        "items": [
            {
                "id": int(item.id),
                "version": int(item.version),
                "summary": item.summary,
                "body_markdown": item.body_markdown,
                "status_at_version": item.status_at_version,
                "changed_by_name": item.changed_by_name,
                "change_note": item.change_note,
                "created_at": core.iso_utc(item.created_at) if item.created_at else "",
            }
            for item in versions
        ]
    }


# ---------------------------------------------------------------------------
# مصوبات
# ---------------------------------------------------------------------------


@router.post("/decisions")
async def create_decision(
    payload: DecisionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    minutes = await _get_minutes(db, ctx, payload.meeting_id)
    if minutes is not None and minutes.status == MINUTES_LOCKED:
        raise conflict("صورتجلسه قفل شده و افزودن مصوبه مجاز نیست.")

    existing = await list_owned(db, Decisions, ctx, Decisions.meeting_id == payload.meeting_id)
    decision = Decisions(
        organization_id=ctx.organization_id,
        meeting_id=payload.meeting_id,
        minutes_id=int(minutes.id) if minutes is not None else None,
        position=len(existing) + 1,
        title=payload.title.strip(),
        description=(payload.description or "").strip(),
        source="ai" if payload.source == "ai" else "manual",
    )
    db.add(decision)
    await audit(db, ctx, "decision.created", "decision", None, decision.title)
    await db.commit()
    return dump(decision, DECISION_FIELDS)


@router.patch("/decisions/{decision_id}")
async def update_decision(
    decision_id: int,
    payload: DecisionUpdateIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    decision = await get_owned(db, Decisions, decision_id, ctx, "مصوبه")
    meeting = await get_owned(db, Meetings, int(decision.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    minutes = await _get_minutes(db, ctx, int(decision.meeting_id))
    if minutes is not None and minutes.status == MINUTES_LOCKED:
        raise conflict("صورتجلسه قفل شده و ویرایش مصوبه مجاز نیست.")

    if payload.title is not None and payload.title.strip():
        decision.title = payload.title.strip()
    if payload.description is not None:
        decision.description = payload.description.strip()
    await audit(db, ctx, "decision.updated", "decision", decision_id, decision.title)
    await db.commit()
    return dump(decision, DECISION_FIELDS)


@router.delete("/decisions/{decision_id}")
async def delete_decision(
    decision_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    decision = await get_owned(db, Decisions, decision_id, ctx, "مصوبه")
    meeting = await get_owned(db, Meetings, int(decision.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    minutes = await _get_minutes(db, ctx, int(decision.meeting_id))
    if minutes is not None and minutes.status == MINUTES_LOCKED:
        raise conflict("صورتجلسه قفل شده و حذف مصوبه مجاز نیست.")

    title = decision.title
    actions = await list_owned(db, Action_items, ctx, Action_items.decision_id == decision_id)
    for action in actions:
        action.decision_id = None
    await db.delete(decision)
    await audit(db, ctx, "decision.deleted", "decision", decision_id, title)
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# اقدامات
# ---------------------------------------------------------------------------


@router.get("/actions")
async def list_actions(
    scope: str = "all",
    status_filter: str = "all",
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """فهرست اقدامات با فیلتر «اقدامات من» و وضعیت."""
    ctx = await resolve_context(db, current_user)
    await core.refresh_overdue_actions(db, ctx.organization_id)
    actions = await list_owned(db, Action_items, ctx, order_by=Action_items.due_date)
    meetings = await list_owned(db, Meetings, ctx)
    titles = {int(meeting.id): meeting.title for meeting in meetings}

    items: List[Dict[str, Any]] = []
    for action in actions:
        if scope == "mine" and int(action.owner_membership_id or 0) != ctx.membership_id:
            continue
        if status_filter != "all" and action.status != status_filter:
            continue
        payload = dump(action, ACTION_FIELDS)
        payload["meeting_title"] = titles.get(int(action.meeting_id), "")
        items.append(payload)

    counts = {status: 0 for status in ACTION_STATUSES}
    for action in actions:
        key = action.status if action.status in counts else "open"
        counts[key] += 1
    await db.commit()
    return {"items": items, "counts": counts, "my_membership_id": ctx.membership_id}


@router.post("/actions")
async def create_action(
    payload: ActionIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, payload.meeting_id, ctx, "جلسه")
    require_meeting_manager(ctx, meeting)

    owner_name = ""
    owner_id: Optional[int] = None
    if payload.owner_membership_id:
        owner = await get_owned(db, Memberships, payload.owner_membership_id, ctx, "مسئول اقدام")
        owner_id = int(owner.id)
        owner_name = owner.full_name
    if payload.decision_id:
        await get_owned(db, Decisions, payload.decision_id, ctx, "مصوبه")

    due = core.normalize_iso(payload.due_date) or core.iso_utc(
        core.utc_now() + core.timedelta(days=14)
    )
    action = Action_items(
        organization_id=ctx.organization_id,
        meeting_id=payload.meeting_id,
        decision_id=payload.decision_id,
        title=payload.title.strip(),
        description=(payload.description or "").strip(),
        owner_membership_id=owner_id,
        owner_name=owner_name,
        due_date=due,
        status="open",
        progress_note="",
        source="ai" if payload.source == "ai" else "manual",
    )
    db.add(action)
    if owner_id:
        await notify(
            db,
            ctx.organization_id,
            membership_id=owner_id,
            user_id=None,
            kind="action_assigned",
            title=f"اقدام جدید: {action.title}",
            body=f"جلسه: {meeting.title}",
            link="/actions",
        )
    await audit(db, ctx, "action.created", "action_item", None, action.title)
    await db.commit()
    return dump(action, ACTION_FIELDS)


@router.patch("/actions/{action_id}")
async def update_action(
    action_id: int,
    payload: ActionUpdateIn,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """به‌روزرسانی اقدام؛ مسئول اقدام فقط وضعیت و یادداشت پیشرفت را تغییر می‌دهد."""
    ctx = await resolve_context(db, current_user)
    action = await get_owned(db, Action_items, action_id, ctx, "اقدام")
    meeting = await get_owned(db, Meetings, int(action.meeting_id), ctx, "جلسه")

    is_owner = int(action.owner_membership_id or 0) == ctx.membership_id
    can_manage = ctx.is_secretary_of(meeting)
    if not is_owner and not can_manage:
        raise core.forbidden(
            "دسترسی لازم را ندارید. ویرایش این اقدام فقط برای مسئول آن، دبیر جلسه یا مدیر سازمان مجاز است."
        )

    if payload.status is not None:
        if payload.status not in ACTION_STATUSES:
            raise bad_request("وضعیت اقدام معتبر نیست.")
        action.status = payload.status
    if payload.progress_note is not None:
        action.progress_note = payload.progress_note.strip()[:900]

    if can_manage:
        if payload.title is not None and payload.title.strip():
            action.title = payload.title.strip()
        if payload.description is not None:
            action.description = payload.description.strip()
        if payload.due_date is not None:
            normalized = core.normalize_iso(payload.due_date)
            if not normalized:
                raise bad_request("مهلت اقدام معتبر نیست.")
            action.due_date = normalized
        if payload.owner_membership_id is not None:
            owner = await get_owned(
                db, Memberships, payload.owner_membership_id, ctx, "مسئول اقدام"
            )
            action.owner_membership_id = int(owner.id)
            action.owner_name = owner.full_name
    elif any(
        value is not None
        for value in (payload.title, payload.description, payload.due_date, payload.owner_membership_id)
    ):
        raise core.forbidden(
            "دسترسی لازم را ندارید. تغییر عنوان، مهلت یا مسئول اقدام فقط برای دبیر جلسه یا مدیر سازمان مجاز است."
        )

    if action.status in ("open", "in_progress"):
        due = core.parse_iso(action.due_date)
        if due and due < core.utc_now():
            action.status = "overdue"

    await audit(db, ctx, "action.updated", "action_item", action_id, f"{action.title} / {action.status}")
    await db.commit()
    return dump(action, ACTION_FIELDS)


@router.delete("/actions/{action_id}")
async def delete_action(
    action_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    ctx = await resolve_context(db, current_user)
    action = await get_owned(db, Action_items, action_id, ctx, "اقدام")
    meeting = await get_owned(db, Meetings, int(action.meeting_id), ctx, "جلسه")
    require_meeting_manager(ctx, meeting)
    title = action.title
    await db.delete(action)
    await audit(db, ctx, "action.deleted", "action_item", action_id, title)
    await db.commit()
    return {"success": True}


# ---------------------------------------------------------------------------
# خروجی: بستهٔ چاپ و ICS
# ---------------------------------------------------------------------------


@router.get("/export/{meeting_id}")
async def export_package(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """دادهٔ کامل برای نمای چاپ فارسی/RTL (تبدیل به PDF در مرور‌گر انجام می‌شود)."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    minutes = await _get_minutes(db, ctx, meeting_id)
    agenda = await list_owned(
        db, Agenda_items, ctx, Agenda_items.meeting_id == meeting_id, order_by=Agenda_items.position
    )
    participants = await list_owned(
        db, Participants, ctx, Participants.meeting_id == meeting_id, order_by=Participants.id
    )
    decisions = await list_owned(
        db, Decisions, ctx, Decisions.meeting_id == meeting_id, order_by=Decisions.position
    )
    actions = await list_owned(
        db, Action_items, ctx, Action_items.meeting_id == meeting_id, order_by=Action_items.id
    )
    await db.commit()
    return {
        "organization": {"name": ctx.organization.name, "timezone": ctx.organization.timezone},
        "meeting": dump(meeting, core.MEETING_FIELDS),
        "minutes": dump(minutes, MINUTES_FIELDS) if minutes else None,
        "agenda": [dump(item, core.AGENDA_FIELDS) for item in agenda],
        "participants": [dump(item, core.PARTICIPANT_FIELDS) for item in participants],
        "decisions": [dump(item, DECISION_FIELDS) for item in decisions],
        "actions": [dump(item, ACTION_FIELDS) for item in actions],
    }


@router.get("/export/{meeting_id}/docx")
async def export_minutes_docx(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Response:
    """دانلود فایل Word صورتجلسه با چیدمان راست\u200cبه\u200cچپ و تاریخ شمسی."""
    package = await export_package(meeting_id, current_user, db)
    meeting = package.get("meeting") or {}
    organization = package.get("organization") or {}
    try:
        content = build_minutes_docx(package)
    except Exception as exc:  # noqa: BLE001 - خطای تولید فایل باید پیام فارسی بدهد
        logger.exception("تولید فایل Word صورتجلسه ناموفق بود")
        raise bad_request("تولید فایل Word صورتجلسه ناموفق بود. لطفاً دوباره تلاش کنید.") from exc

    file_name = safe_file_name(
        str(meeting.get("title") or ""),
        meeting.get("starts_at"),
        organization.get("timezone") or "Asia/Tehran",
    )
    quoted = quote(file_name)
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={
            "Content-Disposition": f"attachment; filename=\"minutes-{meeting_id}.docx\"; filename*=UTF-8''{quoted}",
        },
    )


def _ics_escape(text: str) -> str:
    return (
        (text or "")
        .replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def _ics_stamp(value: Optional[str]) -> str:
    parsed = core.parse_iso(value) or core.utc_now()
    return parsed.strftime("%Y%m%dT%H%M%SZ")


@router.get("/ics/{meeting_id}", response_class=PlainTextResponse)
async def meeting_ics(
    meeting_id: int,
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PlainTextResponse:
    """خروجی تقویم استاندارد برای افزودن جلسه به Outlook/Google Calendar."""
    ctx = await resolve_context(db, current_user)
    meeting = await get_owned(db, Meetings, meeting_id, ctx, "جلسه")
    agenda = await list_owned(
        db, Agenda_items, ctx, Agenda_items.meeting_id == meeting_id, order_by=Agenda_items.position
    )
    start = core.parse_iso(meeting.starts_at) or core.utc_now()
    end = start + core.timedelta(minutes=int(meeting.duration_minutes or 60))
    description_parts = [meeting.description or ""]
    if agenda:
        description_parts.append("دستور جلسه:")
        description_parts.extend(f"{index}. {item.title}" for index, item in enumerate(agenda, start=1))
    location = meeting.location or meeting.online_url or ""
    org_name = ctx.organization.name
    await db.commit()

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Meeting SaaS Demo//FA//",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:meeting-{meeting_id}-org-{ctx.organization_id}@meeting-saas.demo",
        f"DTSTAMP:{_ics_stamp(core.now_iso())}",
        f"DTSTART:{start.strftime('%Y%m%dT%H%M%SZ')}",
        f"DTEND:{end.strftime('%Y%m%dT%H%M%SZ')}",
        f"SUMMARY:{_ics_escape(meeting.title)}",
        f"DESCRIPTION:{_ics_escape(chr(10).join(part for part in description_parts if part))}",
        f"LOCATION:{_ics_escape(location)}",
        f"ORGANIZER;CN={_ics_escape(org_name)}:mailto:no-reply@meeting-saas.demo",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    content = "\r\n".join(lines)
    return PlainTextResponse(
        content=content,
        media_type="text/calendar; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="meeting-{meeting_id}.ics"'},
    )


# ---------------------------------------------------------------------------
# کنسول ادمین سازمان
# ---------------------------------------------------------------------------


@router.get("/admin/console")
async def admin_console(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """کنسول مدیر سازمان: سهمیه، وضعیت کارهای AI، تأمین‌کنندگان و سلامت داده."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)

    jobs = await list_owned(db, Jobs, ctx, order_by=Jobs.id.desc(), limit=40)
    usage = await list_owned(db, core.Ai_usage_events, ctx, order_by=core.Ai_usage_events.id.desc(), limit=30)
    recordings = await list_owned(db, Recordings, ctx, order_by=Recordings.id.desc())
    transcripts = await list_owned(db, Transcripts, ctx, order_by=Transcripts.id.desc(), limit=30)
    members = await list_owned(db, Memberships, ctx, order_by=Memberships.id)
    audit_rows = await list_owned(db, Audit_logs, ctx, order_by=Audit_logs.id.desc(), limit=20)

    job_counts: Dict[str, int] = {}
    for job in jobs:
        job_counts[job.status] = job_counts.get(job.status, 0) + 1

    storage_bytes = sum(int(item.size_bytes or 0) for item in recordings)
    low_quality = [
        {
            "meeting_id": int(item.meeting_id),
            "known_word_ratio": item.known_word_ratio,
        }
        for item in transcripts
        if item.known_word_ratio is not None and item.known_word_ratio < 0.8
    ]
    role_counts: Dict[str, int] = {}
    for member in members:
        role_counts[member.role] = role_counts.get(member.role, 0) + 1

    await db.commit()
    return {
        "organization": {
            "id": ctx.organization_id,
            "name": ctx.organization.name,
            "plan_code": ctx.organization.plan_code,
            "timezone": ctx.organization.timezone,
            "audio_retention_days": ctx.organization.audio_retention_days,
            "is_demo": bool(ctx.organization.is_demo),
        },
        "quota": quota_snapshot(ctx.organization),
        "job_counts": job_counts,
        "recent_jobs": [dump(job, core.JOB_FIELDS) for job in jobs[:12]],
        "usage_events": [
            {
                "id": int(item.id),
                "kind": item.kind,
                "provider": item.provider,
                "model": item.model,
                "minutes_charged": int(item.minutes_charged or 0),
                "detail": item.detail,
                "created_at": core.iso_utc(item.created_at) if item.created_at else "",
            }
            for item in usage
        ],
        "storage": {
            "files": len(recordings),
            "total_mb": round(storage_bytes / (1024 * 1024), 2),
            "retention_days": int(ctx.organization.audio_retention_days or core.DEMO_AUDIO_RETENTION_DAYS),
        },
        "transcription_providers": transcription_providers_status(),
        "low_quality_transcripts": low_quality,
        "role_counts": role_counts,
        "recent_audit": [dump(row, core.AUDIT_FIELDS) for row in audit_rows],
        "concurrency": {
            "org_limit": int(ctx.organization.max_concurrent_ai_jobs or core.DEMO_MAX_CONCURRENT_AI_JOBS),
            "system_limit": core.SYSTEM_MAX_CONCURRENT_AI_JOBS,
            "active": job_counts.get("running", 0) + job_counts.get("queued", 0),
        },
    }


@router.post("/admin/purge-expired-audio")
async def purge_expired_audio(
    current_user: UserResponse = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> Dict[str, Any]:
    """اجرای دستی سیاست نگه‌داری صوت؛ فایل‌های منقضی حذف می‌شوند."""
    ctx = await resolve_context(db, current_user)
    require_role(ctx, ROLE_ADMIN)
    recordings = await list_owned(db, Recordings, ctx)
    now = core.utc_now()
    removed = 0
    for recording in recordings:
        purge_at = core.parse_iso(recording.purge_after)
        if purge_at and purge_at < now:
            await db.delete(recording)
            removed += 1
    await audit(db, ctx, "recording.purged", "organization", ctx.organization_id, f"{removed} فایل")
    await db.commit()
    return {"success": True, "removed": removed}
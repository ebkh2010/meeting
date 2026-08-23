"""پیکربندی زمان اجرای فرانت‌اند برای استقرار مستقل.

فرانت‌اند پیش از هر تماسی `GET /api/config` را صدا می‌زند تا نشانی پایهٔ API را
بگیرد. در استقرار مستقل، فرانت و API روی همان دامنه (پشت یک reverse proxy)
هستند، پس مقدار درست «رشتهٔ خالی» است تا همهٔ تماس‌ها نسبی و same-origin بمانند.

این ماژول هیچ رفتار قابلیتی را تغییر نمی‌دهد؛ فقط مقدار پیکربندی را از متغیر
محیطی ``PUBLIC_API_BASE_URL`` می‌خواند و برمی‌گرداند تا نیازی به بازساخت ایمیج
فرانت هنگام تغییر دامنه نباشد.
"""

from __future__ import annotations

import os

from fastapi import APIRouter

router = APIRouter(tags=["runtime-config"])


@router.get("/api/config")
def read_runtime_config() -> dict:
    """نشانی پایهٔ API برای مرورگر؛ خالی یعنی «همین دامنه»."""
    return {"API_BASE_URL": (os.environ.get("PUBLIC_API_BASE_URL") or "").strip()}
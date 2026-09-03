"""کانال‌های اعلان بیرونی: ایمیل (SMTP) و پیامک (پارسااس‌ام‌اس).

قواعد اصلی:

* تنظیمات هر سازمان جدا نگه‌داری می‌شود (``org_notify_settings`` با ``organization_id``).
* رمز SMTP و کلید API پیامک رمزنگاری‌شده ذخیره می‌شوند و هرگز به فرانت‌اند بازنمی‌گردند.
* قرارداد پیامک از وب‌سرویس پارسااس‌ام‌اس پیروی می‌کند:
  ``POST https://api.parsasms.com/v2/sms/send/simple``
  با هدر ``apikey`` و بدنهٔ ``message`` / ``receptor`` / ``sender``.
* متن فارسی پیامک باید عبارت انصراف «لغو ۱۱» را داشته باشد؛ بدون آن اپراتور
  پیامک را فیلتر می‌کند و پنل وضعیت «۲۷» برمی‌گرداند و هزینه را پس می‌دهد.
* شکست ارسال هرگز جریان اصلی (ایجاد جلسه) را متوقف نمی‌کند؛ نتیجه در
  ``notify_deliveries`` ثبت می‌شود و امکان «ارسال دوباره» وجود دارد.
"""

from __future__ import annotations

import asyncio
import logging
import os
import smtplib
import ssl
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email import encoders
from email.header import Header
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.org_notify_settings import Org_notify_settings
from services.app_auth import (
    GENDER_FEMALE,
    GENDER_MALE,
    GENDER_SALUTATION,
    decrypt_secret,
    encrypt_secret,
)

logger = logging.getLogger(__name__)

PARSASMS_BASE_URL = os.environ.get("SMS_API_BASE_URL", "https://api.parsasms.com/v2")
SEND_SIMPLE_SMS_PATH = "/sms/send/simple"
SMS_TIMEOUT_SECONDS = 20.0
# برخی سرورهای ایمیل (مانند cPanel با recipient-verification) برای هر گیرنده
# تا ~۳۰ ثانیه معطل می‌کنند؛ تایماوت کوتاه باعث قطع جعلی اتصال می‌شد.
SMTP_TIMEOUT_SECONDS = 180.0

TEHRAN_OFFSET = timedelta(hours=3, minutes=30)

_PERSIAN_DIGITS = "۰۱۲۳۴۵۶۷۸۹"
_JALALI_MONTHS = [
    "فروردین",
    "اردیبهشت",
    "خرداد",
    "تیر",
    "مرداد",
    "شهریور",
    "مهر",
    "آبان",
    "آذر",
    "دی",
    "بهمن",
    "اسفند",
]
_WEEKDAYS = ["دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه", "شنبه", "یکشنبه"]


# ---------------------------------------------------------------------------
# تاریخ و ساعت شمسی
# ---------------------------------------------------------------------------


def to_persian_digits(value: str) -> str:
    return "".join(_PERSIAN_DIGITS[int(ch)] if ch.isdigit() else ch for ch in str(value))


def gregorian_to_jalali(year: int, month: int, day: int) -> Tuple[int, int, int]:
    """تبدیل تاریخ میلادی به هجری شمسی (الگوریتم استاندارد بدون وابستگی بیرونی)."""
    if year <= 1600:
        jy, gy = 0, 621
    else:
        jy, gy = 979, 1600
    gm = month - 1
    gd = day - 1

    g_day_no = 365 * (year - gy) + (year - gy + 3) // 4 - (year - gy + 99) // 100 + (year - gy + 399) // 400
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    for i in range(gm):
        g_day_no += g_days_in_month[i]
    if gm > 1 and ((year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)):
        g_day_no += 1
    g_day_no += gd

    j_day_no = g_day_no - 79
    j_np = j_day_no // 12053
    j_day_no %= 12053
    jy += 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461
    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    for i in range(11):
        month_length = 31 if i < 6 else 30
        if j_day_no < month_length:
            return jy, i + 1, j_day_no + 1
        j_day_no -= month_length
    return jy, 12, j_day_no + 1


def to_tehran(value: datetime) -> datetime:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc) + TEHRAN_OFFSET


def format_jalali_datetime(value: datetime, with_weekday: bool = True) -> str:
    """خروجی نمونه: «سه‌شنبه ۲۸ مرداد ۱۴۰۵ ساعت ۱۰:۳۰»."""
    local = to_tehran(value)
    jy, jm, jd = gregorian_to_jalali(local.year, local.month, local.day)
    weekday = _WEEKDAYS[local.weekday()]
    stamp = f"{jd} {_JALALI_MONTHS[jm - 1]} {jy} ساعت {local.hour:02d}:{local.minute:02d}"
    if with_weekday:
        stamp = f"{weekday} {stamp}"
    return to_persian_digits(stamp)


def parse_iso(value: Any) -> Optional[datetime]:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# تنظیمات سازمان
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# تنظیمات پیش‌فرض SMTP برای سازمان‌های تازه‌ثبت‌نام‌کرده
# ---------------------------------------------------------------------------
#
# هر سازمان به محض ثبت‌نام، بدون هیچ پیکربندی‌ای از این تنظیمات برای ارسال
# ایمیل استفاده می‌کند. مقادیر از متغیرهای محیطی خوانده می‌شوند تا در هر
# استقرار قابل تغییر باشند؛ در نبودشان از همین مقادیر پیش‌فرض استفاده می‌شود.


def _env_bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "t", "yes", "y", "on"}


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not str(raw).strip():
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("مقدار نامعتبر %s=%r؛ پیش‌فرض %d استفاده می‌شود.", name, raw, default)
        return default


DEFAULT_SMTP_ENABLED = _env_bool("DEFAULT_SMTP_ENABLED", True)
DEFAULT_SMTP_HOST = os.environ.get("DEFAULT_SMTP_HOST", "mail.samimsolutions.com")
DEFAULT_SMTP_PORT = _env_int("DEFAULT_SMTP_PORT", 465)
DEFAULT_SMTP_USERNAME = os.environ.get("DEFAULT_SMTP_USERNAME", "ebkh2010@samimsolutions.com")
DEFAULT_SMTP_PASSWORD = os.environ.get("DEFAULT_SMTP_PASSWORD", "O(q+-HGMTRha6k_n")
DEFAULT_SMTP_USE_TLS = _env_bool("DEFAULT_SMTP_USE_TLS", False)
DEFAULT_SMTP_USE_SSL = _env_bool("DEFAULT_SMTP_USE_SSL", True)
DEFAULT_SMTP_FROM_EMAIL = os.environ.get("DEFAULT_SMTP_FROM_EMAIL", "ebkh2010@samimsolutions.com")
DEFAULT_SMTP_FROM_NAME = os.environ.get("DEFAULT_SMTP_FROM_NAME", "ویدارا - نسخه جلسات")

# ---------------------------------------------------------------------------
# تنظیمات پیش‌فرض پیامک برای سازمان‌های تازه‌ثبت‌نام‌کرده
# ---------------------------------------------------------------------------
#
# سازمان‌های جدید بدون هیچ پیکربندی‌ای از این پنل (پارسااس‌ام‌اس) برای ارسال
# پیامک استفاده می‌کنند تا مدیر سازمان برای شروع کار نیازی به تنظیمات اولیه
# نداشته باشد. مقادیر از متغیرهای محیطی قابل بازنویسی هستند.

DEFAULT_SMS_ENABLED = _env_bool("DEFAULT_SMS_ENABLED", True)
DEFAULT_SMS_API_KEY = os.environ.get(
    "DEFAULT_SMS_API_KEY", "v6zgNiPwfm+GGlZymilBmSnsheRs2YPdFfMone6tC3c"
)
DEFAULT_SMS_LINE_NUMBER = os.environ.get("DEFAULT_SMS_LINE_NUMBER", "10002000100246")


def _apply_default_sms(row: Org_notify_settings) -> None:
    """پر کردن تنظیمات پیامک پیش‌فرض روی رکوردی که هنوز پیکربندی نشده است."""
    row.sms_enabled = DEFAULT_SMS_ENABLED
    row.sms_api_key_enc = encrypt_secret(DEFAULT_SMS_API_KEY)
    row.sms_line_number = DEFAULT_SMS_LINE_NUMBER


def _sms_configured(row: Org_notify_settings) -> bool:
    """آیا سازمان تنظیمات پیامک خودش را انجام داده است؟

    اگر مدیر تنظیمات را لمس کرده باشد (کلید یا شمارهٔ خط یا کلید فعال‌سازی ثبت
    شده باشد)، پیش‌فرض روی آن اعمال نمی‌شود.
    """
    return bool(
        row.sms_enabled
        or (row.sms_api_key_enc or "").strip()
        or (row.sms_line_number or "").strip()
    )


def _apply_default_smtp(row: Org_notify_settings) -> None:
    """پر کردن تنظیمات SMTP پیش‌فرض روی رکوردی که هنوز پیکربندی نشده است."""
    row.smtp_enabled = DEFAULT_SMTP_ENABLED
    row.smtp_host = DEFAULT_SMTP_HOST
    row.smtp_port = DEFAULT_SMTP_PORT
    row.smtp_username = DEFAULT_SMTP_USERNAME
    row.smtp_password_enc = encrypt_secret(DEFAULT_SMTP_PASSWORD)
    row.smtp_use_tls = DEFAULT_SMTP_USE_TLS
    row.smtp_use_ssl = DEFAULT_SMTP_USE_SSL
    row.smtp_from_email = DEFAULT_SMTP_FROM_EMAIL
    row.smtp_from_name = DEFAULT_SMTP_FROM_NAME


def _smtp_configured(row: Org_notify_settings) -> bool:
    """آیا سازمان تنظیمات SMTP خودش را انجام داده است؟

    اگر مدیر، حتی برای غیرفعال‌سازی، تنظیمات را لمس کرده باشد (مثلاً میزبان
    یا نام کاربری یا رمزی ثبت شده باشد)، پیش‌فرض روی آن اعمال نمی‌شود.
    """
    return bool(
        row.smtp_enabled
        or (row.smtp_host or "").strip()
        or (row.smtp_username or "").strip()
        or (row.smtp_password_enc or "").strip()
    )


async def get_or_create_settings(db: AsyncSession, organization_id: int) -> Org_notify_settings:
    """خواندن idempotent تنظیمات اعلان سازمان؛ در نبود رکورد، پیش‌فرض ساخته می‌شود.

    سازمان‌هایی که هنوز هیچ تنظیمی انجام نداده‌اند (اعم از تازه‌ثبت‌نام‌کرده و
    قدیمیِ دست‌نخورده) به‌صورت خودکار پیش‌فرض‌های SMTP و پیامک را دریافت
    می‌کنند تا ایمیل و پیامک بدون نیاز به پیکربندی ارسال شوند.
    """
    result = await db.execute(
        select(Org_notify_settings).where(Org_notify_settings.organization_id == organization_id)
    )
    row = result.scalars().first()
    if row is not None:
        if not _smtp_configured(row):
            _apply_default_smtp(row)
        if not _sms_configured(row):
            _apply_default_sms(row)
        await db.flush()
        return row
    row = Org_notify_settings(
        organization_id=organization_id,
        sms_enabled=False,
        sms_api_key_enc="",
        sms_line_number="",
    )
    _apply_default_smtp(row)
    _apply_default_sms(row)
    db.add(row)
    await db.flush()
    return row


def platform_default_sms_row(organization_id: int) -> Org_notify_settings:
    """ردیف پیامک پیش‌فرض پلتفرم (برای اطلاع‌رسانی‌های حساس که نباید به
    پیکربندی خود سازمان وابسته باشند). در نشست ثبت نمی‌شود."""
    return Org_notify_settings(
        organization_id=organization_id,
        sms_enabled=bool(DEFAULT_SMS_ENABLED),
        sms_api_key_enc=encrypt_secret(DEFAULT_SMS_API_KEY),
        sms_line_number=DEFAULT_SMS_LINE_NUMBER,
    )


def platform_default_email_row(organization_id: int) -> Org_notify_settings:
    """ردیف SMTP پیش‌فرض پلتفرم (برای تأیید ایمیل و اطلاع‌رسانی‌های حساس که
    نباید به پیکربندی خود سازمان وابسته باشند). در نشست ثبت نمی‌شود."""
    return Org_notify_settings(
        organization_id=organization_id,
        smtp_enabled=bool(DEFAULT_SMTP_ENABLED),
        smtp_host=DEFAULT_SMTP_HOST,
        smtp_port=DEFAULT_SMTP_PORT,
        smtp_username=DEFAULT_SMTP_USERNAME,
        smtp_password_enc=encrypt_secret(DEFAULT_SMTP_PASSWORD),
        smtp_use_tls=DEFAULT_SMTP_USE_TLS,
        smtp_use_ssl=DEFAULT_SMTP_USE_SSL,
        smtp_from_email=DEFAULT_SMTP_FROM_EMAIL,
        smtp_from_name=DEFAULT_SMTP_FROM_NAME,
    )


def settings_payload(row: Org_notify_settings) -> Dict[str, Any]:
    """خروجی امن برای فرانت‌اند: مقدار رمزها هرگز ارسال نمی‌شود."""
    return {
        "smtp_enabled": bool(row.smtp_enabled),
        "smtp_host": row.smtp_host or "",
        "smtp_port": int(row.smtp_port or 587),
        "smtp_username": row.smtp_username or "",
        "smtp_password_set": bool(row.smtp_password_enc),
        "smtp_use_tls": bool(row.smtp_use_tls),
        "smtp_use_ssl": bool(row.smtp_use_ssl),
        "smtp_from_email": row.smtp_from_email or "",
        "smtp_from_name": row.smtp_from_name or "",
        "sms_enabled": bool(row.sms_enabled),
        "sms_api_key_set": bool(row.sms_api_key_enc),
        "sms_line_number": row.sms_line_number or "",
    }


@dataclass
class SendResult:
    ok: bool
    provider_message_id: str = ""
    error: str = ""


@dataclass
class EmailAttachment:
    """پیوست ایمیل؛ محتوا به‌صورت بایت در حافظه و نام فارسی مجاز است."""

    file_name: str
    content: bytes
    content_type: str = "application/octet-stream"


# ---------------------------------------------------------------------------
# ایمیل
# ---------------------------------------------------------------------------


def _smtp_send_blocking(
    *,
    host: str,
    port: int,
    username: str,
    password: str,
    use_tls: bool,
    use_ssl: bool,
    from_email: str,
    from_name: str,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str,
    ics_content: str,
    attachments: Sequence[EmailAttachment] = (),
) -> None:
    message = MIMEMultipart("mixed")
    message["Subject"] = Header(subject, "utf-8")
    message["From"] = formataddr((str(Header(from_name or "", "utf-8")), from_email))
    message["To"] = to_email

    alternative = MIMEMultipart("alternative")
    alternative.attach(MIMEText(text_body, "plain", "utf-8"))
    if html_body:
        alternative.attach(MIMEText(html_body, "html", "utf-8"))
    message.attach(alternative)

    if ics_content:
        calendar_part = MIMEText(ics_content, "calendar", "utf-8")
        calendar_part.add_header("Content-Disposition", "attachment", filename="meeting.ics")
        message.attach(calendar_part)

    for attachment in attachments or ():
        if not attachment.content:
            continue
        main_type, _, sub_type = (attachment.content_type or "application/octet-stream").partition("/")
        part = MIMEBase(main_type or "application", sub_type or "octet-stream")
        part.set_payload(attachment.content)
        encoders.encode_base64(part)
        # نام فایل فارسی با RFC 2231 کدگذاری می‌شود تا در همهٔ کلاینت‌ها درست دیده شود.
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=("utf-8", "", attachment.file_name or "attachment"),
        )
        message.attach(part)

    if use_ssl:
        context = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=SMTP_TIMEOUT_SECONDS, context=context) as server:
            if username:
                server.login(username, password)
            server.sendmail(from_email, [to_email], message.as_string())
        return

    with smtplib.SMTP(host, port, timeout=SMTP_TIMEOUT_SECONDS) as server:
        server.ehlo()
        if use_tls:
            server.starttls(context=ssl.create_default_context())
            server.ehlo()
        if username:
            server.login(username, password)
        server.sendmail(from_email, [to_email], message.as_string())


async def send_email(
    row: Org_notify_settings,
    *,
    to_email: str,
    subject: str,
    text_body: str,
    html_body: str = "",
    ics_content: str = "",
    attachments: Sequence[EmailAttachment] = (),
) -> SendResult:
    """ارسال ایمیل با تنظیمات SMTP سازمان؛ خطا فقط برگردانده می‌شود، پرتاب نمی‌شود."""
    if not row.smtp_enabled:
        return SendResult(ok=False, error="ارسال ایمیل برای این سازمان فعال نیست.")
    if not (row.smtp_host and row.smtp_from_email):
        return SendResult(ok=False, error="تنظیمات SMTP کامل نیست (میزبان یا ایمیل فرستانده خالی است).")
    if not to_email:
        return SendResult(ok=False, error="نشانی ایمیل گیرنده ثبت نشده است.")

    password = decrypt_secret(row.smtp_password_enc or "")
    try:
        await asyncio.to_thread(
            _smtp_send_blocking,
            host=row.smtp_host,
            port=int(row.smtp_port or 587),
            username=row.smtp_username or "",
            password=password,
            use_tls=bool(row.smtp_use_tls),
            use_ssl=bool(row.smtp_use_ssl),
            from_email=row.smtp_from_email,
            from_name=row.smtp_from_name or "",
            to_email=to_email,
            subject=subject,
            text_body=text_body,
            html_body=html_body,
            ics_content=ics_content,
            attachments=list(attachments or ()),
        )
    except smtplib.SMTPAuthenticationError:
        return SendResult(ok=False, error="نام کاربری یا رمز SMTP پذیرفته نشد.")
    except smtplib.SMTPException as exc:
        return SendResult(ok=False, error=f"خطای سرور ایمیل: {exc.__class__.__name__}")
    except (OSError, ssl.SSLError) as exc:
        return SendResult(ok=False, error=f"اتصال به سرور ایمیل برقرار نشد: {exc.__class__.__name__}")
    return SendResult(ok=True)


# ---------------------------------------------------------------------------
# پیامک پارسااس‌ام‌اس
# ---------------------------------------------------------------------------

_SMS_ERROR_CODES: Dict[str, str] = {
    "1": "نام کاربری یا رمز عبور معتبر نیست.",
    "6": "حساب کاربری غیرفعال است.",
    "7": "دسترسی به خط فرستنده وجود ندارد.",
    "8": "شماره گیرنده نامعتبر است.",
    "9": "اعتبار حساب کافی نیست.",
    "11": "آدرس IP مجاز نیست.",
    "20": "شماره مخاطب فیلتر شده است.",
    "21": "ارتباط با سرویس‌دهنده قطع است.",
    "29": "شماره فرستنده معتبر نیست.",
}


def _sms_error_detail(code: Any) -> str:
    return _SMS_ERROR_CODES.get(str(code), f"کد خطای {code} از سرویس پیامک")


async def send_sms(
    row: Org_notify_settings,
    *,
    receptor: str,
    message: str,
    client_reference_id: str = "",
) -> SendResult:
    """ارسال پیامک تکی از طریق وب‌سرویس پارسااس‌ام‌اس (``POST /v2/sms/send/simple``)."""
    if not row.sms_enabled:
        return SendResult(ok=False, error="ارسال پیامک برای این سازمان فعال نیست.")
    api_key = decrypt_secret(row.sms_api_key_enc or "")
    if not api_key:
        return SendResult(ok=False, error="کلید API پیامک ثبت نشده است.")
    if not row.sms_line_number:
        return SendResult(ok=False, error="شماره خط فرستندهٔ پیامک ثبت نشده است.")
    if not receptor:
        return SendResult(ok=False, error="شماره موبایل گیرنده ثبت نشده است.")

    payload: Dict[str, Any] = {
        "message": message,
        "receptor": receptor,
        "sender": row.sms_line_number,
    }
    # شناسهٔ پیگیری یکتا از طرف کاربر؛ پنل فقط مقدار عددی می‌پذیرد.
    if client_reference_id and str(client_reference_id).isdigit():
        payload["checkmessageids"] = str(client_reference_id)

    headers = {"apikey": api_key, "Content-Type": "application/json"}
    url = f"{PARSASMS_BASE_URL}{SEND_SIMPLE_SMS_PATH}"

    try:
        async with httpx.AsyncClient(timeout=SMS_TIMEOUT_SECONDS) as http_client:
            response = await http_client.post(url, json=payload, headers=headers)
    except httpx.TimeoutException:
        return SendResult(ok=False, error="سرویس پیامک در زمان مجاز پاسخ نداد.")
    except httpx.HTTPError as exc:
        return SendResult(ok=False, error=f"اتصال به سرویس پیامک برقرار نشد: {exc.__class__.__name__}")

    try:
        body = response.json()
    except ValueError:
        body = {}

    if response.status_code >= 400:
        detail = body.get("Message") or body.get("message") or f"کد وضعیت {response.status_code}"
        return SendResult(ok=False, error=f"سرویس پیامک درخواست را نپذیرفت ({detail}).")

    result = body.get("result")
    if result == "success":
        raw_ids = body.get("messageids")
        try:
            numeric_ids = int(raw_ids)
        except (TypeError, ValueError):
            numeric_ids = 0
        # طبق مستند: مقدار بزرگ‌تر از ۱۰۰۰ یعنی ارسال موفق؛ وگرنه کد خطا است.
        if numeric_ids > 1000:
            return SendResult(ok=True, provider_message_id=str(numeric_ids))
        return SendResult(ok=False, error=_sms_error_detail(raw_ids))
    if result == "error":
        detail = body.get("message") or _sms_error_detail(body.get("messageids"))
        return SendResult(ok=False, error=f"سرویس پیامک درخواست را نپذیرفت ({detail}).")

    return SendResult(ok=False, error="پاسخ نامعتبر از سرویس پیامک.")


# ---------------------------------------------------------------------------
# متن اعلان دعوت جلسه
# ---------------------------------------------------------------------------


def salutation(gender: str, full_name: str) -> str:
    prefix = GENDER_SALUTATION.get((gender or "").lower(), "")
    return f"{prefix} {full_name}".strip() if prefix else full_name


def sms_addressee(gender: str, full_name: str) -> str:
    """خطاب گیرنده در پیامک: «آقای …» یا «خانم …» بر اساس جنسیت."""
    name = (full_name or "").strip()
    lowered = (gender or "").lower()
    if lowered == GENDER_MALE:
        return f"آقای {name}" if name else "کاربر گرامی"
    if lowered == GENDER_FEMALE:
        return f"خانم {name}" if name else "کاربر گرامی"
    return name or "کاربر گرامی"


def format_jalali_date_and_time(value: datetime) -> Tuple[str, str]:
    """خروجی: (تاریخ شمسی با ارقام فارسی، ساعت با ارقام فارسی).

    نمونه: ``("۲۸ مرداد ۱۴۰۵", "۱۰:۳۰")``.
    """
    local = to_tehran(value)
    jy, jm, jd = gregorian_to_jalali(local.year, local.month, local.day)
    date_str = f"{jd} {_JALALI_MONTHS[jm - 1]} {jy}"
    time_str = f"{local.hour:02d}:{local.minute:02d}"
    return to_persian_digits(date_str), to_persian_digits(time_str)


def build_invite_sms(
    *,
    recipient_name: str,
    gender: str,
    starts_at: datetime,
) -> str:
    """متن پیامک دعوت به جلسه.

    قالب ثابت (مطابق الگوی مصوب):
    «کاربر گرامی / آقای|خانم … / شما به یک جلسه در تاریخ … ساعت … دعوت شده‌اید /
    برای اطلاع از جزئیات به ایمیل یا حساب کاربری در ویدارا نسخه جلسات مراجعه
    بفرمایید. / لغو ۱۱»
    عبارت «لغو ۱۱» الزامی است؛ بدون آن اپراتور پیامک را فیلتر می‌کند.
    """
    date_str, time_str = format_jalali_date_and_time(starts_at)
    lines = ["کاربر گرامی"]
    addressee = sms_addressee(gender, recipient_name)
    if addressee and addressee != "کاربر گرامی":
        lines.append(addressee)
    lines.append(f"شما به یک جلسه در تاریخ {date_str} ساعت {time_str} دعوت شده اید")
    lines.append("برای اطلاع از جزییات به ایمیل یا حساب کاربری در ویدارا نسخه جلسات مراجعه بفرمایید.")
    lines.append("لغو ۱۱")
    return "\n".join(lines)


def build_invite_email(
    *,
    recipient_name: str,
    gender: str,
    organization_name: str,
    meeting_title: str,
    description: str,
    starts_at: datetime,
    duration_minutes: int,
    location: str,
    online_url: str,
    secretary_name: str,
    agenda_items: Sequence[Dict[str, Any]] = (),
    attachment_names: Sequence[str] = (),
) -> Tuple[str, str, str]:
    """خروجی: (موضوع، متن ساده، متن HTML).

    ``agenda_items`` بندهای دستور جلسه است (``title`` / ``planned_minutes`` /
    ``owner_name`` / ``notes``) و ``attachment_names`` نام فایل‌های پیوست\u200cشده به
    ایمیل است تا گیرنده بداند چه فایل\u200cهایی همراه دعوت ارسال شده است.
    """
    when = format_jalali_datetime(starts_at)
    subject = f"دعوت به جلسهٔ «{meeting_title}» — {when}"

    rows = [
        ("عنوان جلسه", meeting_title),
        ("سازمان", organization_name),
        ("زمان برگزاری", when),
        ("مدت", f"{to_persian_digits(duration_minutes)} دقیقه"),
    ]
    if location:
        rows.append(("محل برگزاری", location))
    if online_url:
        rows.append(("پیوند جلسهٔ برخط", online_url))
    if secretary_name:
        rows.append(("دبیر جلسه", secretary_name))

    text_lines = [f"{salutation(gender, recipient_name)}؛", "", "با احترام، حضور شما در جلسهٔ زیر درخواست می‌شود:", ""]
    text_lines += [f"{label}: {value}" for label, value in rows]
    if description:
        text_lines += ["", "توضیحات:", description]

    agenda_rows = [item for item in (agenda_items or ()) if (item.get("title") or "").strip()]
    if agenda_rows:
        text_lines += ["", "دستور جلسه:"]
        for index, item in enumerate(agenda_rows, start=1):
            parts = [f"{to_persian_digits(index)}. {item.get('title')}"]
            if item.get("planned_minutes"):
                parts.append(f"({to_persian_digits(int(item['planned_minutes']))} دقیقه)")
            if item.get("owner_name"):
                parts.append(f"— مسئول: {item['owner_name']}")
            text_lines.append(" ".join(parts))
            if item.get("notes"):
                text_lines.append(f"   یادداشت: {item['notes']}")

    file_names = [name for name in (attachment_names or ()) if name]
    if file_names:
        text_lines += ["", "فایل‌های پیوست:"]
        text_lines += [f"- {name}" for name in file_names]

    text_lines += ["", "این پیام به‌صورت خودکار از «ویدارا - نسخه جلسات» ارسال شده است."]
    text_body = "\n".join(text_lines)

    table_rows = "".join(
        f'<tr><td style="padding:6px 12px;color:#64748b;white-space:nowrap">{label}</td>'
        f'<td style="padding:6px 12px;font-weight:600;color:#0f172a">{value}</td></tr>'
        for label, value in rows
    )
    description_html = (
        f'<p style="margin:16px 0 0;color:#334155;line-height:1.9">{description}</p>' if description else ""
    )

    agenda_html = ""
    if agenda_rows:
        agenda_list = "".join(
            '<li style="margin:0 0 8px;color:#0f172a;line-height:1.9">'
            f"<span style=\"font-weight:600\">{item.get('title')}</span>"
            + (
                f'<span style="color:#64748b"> — {to_persian_digits(int(item["planned_minutes"]))} دقیقه</span>'
                if item.get("planned_minutes")
                else ""
            )
            + (
                f'<span style="color:#64748b"> — مسئول: {item["owner_name"]}</span>'
                if item.get("owner_name")
                else ""
            )
            + (
                f'<div style="color:#475569;font-size:13px">{item["notes"]}</div>'
                if item.get("notes")
                else ""
            )
            + "</li>"
            for item in agenda_rows
        )
        agenda_html = (
            '<h3 style="margin:24px 0 8px;font-size:15px;color:#0f172a">دستور جلسه</h3>'
            f'<ol style="margin:0;padding-inline-start:20px;font-size:14px">{agenda_list}</ol>'
        )

    attachments_html = ""
    if file_names:
        items_html = "".join(
            f'<li style="margin:0 0 6px;color:#0f172a">{name}</li>' for name in file_names
        )
        attachments_html = (
            '<h3 style="margin:24px 0 8px;font-size:15px;color:#0f172a">فایل‌های پیوست</h3>'
            f'<ul style="margin:0;padding-inline-start:20px;font-size:14px">{items_html}</ul>'
        )
    html_body = f"""<!DOCTYPE html>
<html dir="rtl" lang="fa"><body style="margin:0;background:#f8fafc;padding:24px;font-family:Tahoma,Arial,sans-serif">
  <div style="max-width:600px;margin:0 auto;background:#ffffff;border:1px solid #e2e8f0;border-radius:14px;padding:24px">
    <h2 style="margin:0 0 4px;font-size:18px;color:#0f172a">دعوت به جلسه</h2>
    <p style="margin:0 0 16px;color:#475569">{salutation(gender, recipient_name)}؛ حضور شما در جلسهٔ زیر درخواست می‌شود.</p>
    <table style="width:100%;border-collapse:collapse;font-size:14px">{table_rows}</table>
    {description_html}
    {agenda_html}
    {attachments_html}
    <p style="margin:24px 0 0;font-size:12px;color:#6b7280">این پیام به‌صورت خودکار از «ویدارا - نسخه جلسات» ارسال شده است.</p>
  </div>
</body></html>"""
    return subject, text_body, html_body


def build_ics(
    *,
    meeting_id: int,
    meeting_title: str,
    description: str,
    starts_at: datetime,
    duration_minutes: int,
    location: str,
    organizer_email: str,
) -> str:
    start_utc = starts_at.astimezone(timezone.utc) if starts_at.tzinfo else starts_at.replace(tzinfo=timezone.utc)
    end_utc = start_utc + timedelta(minutes=max(int(duration_minutes or 60), 5))
    stamp = datetime.now(timezone.utc)

    def fmt(value: datetime) -> str:
        return value.strftime("%Y%m%dT%H%M%SZ")

    def escape(value: str) -> str:
        return (value or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Vidara//Meetings//FA",
        "CALSCALE:GREGORIAN",
        "METHOD:REQUEST",
        "BEGIN:VEVENT",
        f"UID:vidara-meeting-{meeting_id}@vidara",
        f"DTSTAMP:{fmt(stamp)}",
        f"DTSTART:{fmt(start_utc)}",
        f"DTEND:{fmt(end_utc)}",
        f"SUMMARY:{escape(meeting_title)}",
    ]
    if description:
        lines.append(f"DESCRIPTION:{escape(description)}")
    if location:
        lines.append(f"LOCATION:{escape(location)}")
    if organizer_email:
        lines.append(f"ORGANIZER:mailto:{organizer_email}")
    lines += ["END:VEVENT", "END:VCALENDAR"]
    return "\r\n".join(lines)
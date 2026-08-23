"""آداپتر فضای ذخیره‌سازی خارجی سازمان (سازگار با S3 و WebDAV).

این ماژول تنها جایی است که با مقصد خارجی حرف می‌زند و سه قاعدهٔ سخت دارد:

* **جریانی بودن**: هیچ فایلی به‌طور کامل در حافظه بار نمی‌شود؛ انتقال با قطعه‌های
  یک مگابایتی و از طریق فایل موقت روی دیسک انجام می‌گیرد (``spooled_file``)
  تا هم ``Content-Length`` دقیق داشته باشیم و هم مصرف حافظه ثابت بماند.
* **بدون وابستگی اضافه**: امضای SigV4 مستقیماً با ``hmac``/``hashlib`` ساخته
  می‌شود، پس نیازی به SDK اختصاصی نیست و همان یک کلاینت ``httpx`` پروژه کافی است.
* **خطای فارسی و دقیق**: هر شکست به ``ExternalStorageError`` با پیام قابل نمایش
  به مدیر تبدیل می‌شود؛ کد وضعیت HTTP هرگز خام به کاربر نمی‌رسد.

دو تأمین‌کننده پشتیبانی می‌شود، هر دو واقعاً قابل تست:

* ``s3`` — هر سرویس سازگار با S3 (MinIO خارجی، آروان، لیارا، Backblaze، Wasabi، AWS).
* ``webdav`` — Nextcloud و ownCloud و هر سرور WebDAV استاندارد.

Dropbox آگاهانه اضافه نشده است؛ جریان OAuth آن نیازمند ثبت اپلیکیشن، آدرس
بازگشت پایدار و توکن تازه‌شونده است و بدون آن قابل تست واقعی نیست.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Dict, Optional, Tuple
from urllib.parse import quote, urlparse

import httpx

logger = logging.getLogger(__name__)

CHUNK_SIZE = 1024 * 1024
SPOOL_MAX_MEMORY = 8 * 1024 * 1024
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

PROVIDER_S3 = "s3"
PROVIDER_WEBDAV = "webdav"
ALL_PROVIDERS = (PROVIDER_S3, PROVIDER_WEBDAV)

_TIMEOUT = httpx.Timeout(connect=20.0, read=600.0, write=600.0, pool=20.0)


class ExternalStorageError(Exception):
    """خطای قابل نمایش به مدیر در ارتباط با فضای ذخیره‌سازی خارجی."""


@dataclass
class TargetConfig:
    """پیکربندی رمزگشایی‌شدهٔ مقصد؛ فقط در حافظهٔ فرایند ساخته می‌شود."""

    provider: str
    endpoint: str = ""
    bucket: str = ""
    region: str = "us-east-1"
    path_prefix: str = ""
    access_key: str = ""
    secret_key: str = ""
    force_path_style: bool = True
    webdav_base_url: str = ""
    webdav_username: str = ""
    webdav_password: str = ""
    extra: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """بررسی کامل بودن پیکربندی پیش از هر تماس شبکه‌ای."""
        if self.provider == PROVIDER_S3:
            missing = [
                label
                for value, label in (
                    (self.endpoint, "نشانی سرویس (endpoint)"),
                    (self.bucket, "نام باکت"),
                    (self.access_key, "کلید دسترسی"),
                    (self.secret_key, "کلید محرمانه"),
                )
                if not (value or "").strip()
            ]
            if missing:
                raise ExternalStorageError(
                    "پیکربندی مقصد S3 کامل نیست؛ این مقادیر لازم است: " + "، ".join(missing)
                )
        elif self.provider == PROVIDER_WEBDAV:
            missing = [
                label
                for value, label in (
                    (self.webdav_base_url, "نشانی پایهٔ WebDAV"),
                    (self.webdav_username, "نام کاربری"),
                    (self.webdav_password, "رمز عبور"),
                )
                if not (value or "").strip()
            ]
            if missing:
                raise ExternalStorageError(
                    "پیکربندی مقصد WebDAV کامل نیست؛ این مقادیر لازم است: "
                    + "، ".join(missing)
                )
        else:
            raise ExternalStorageError("نوع مقصد ذخیره‌سازی پشتیبانی نمی‌شود.")


# ---------------------------------------------------------------------------
# ابزارهای مشترک
# ---------------------------------------------------------------------------


def spooled_file() -> tempfile.SpooledTemporaryFile:
    """فایل موقت: تا ۸ مگابایت در حافظه، بیشتر از آن روی دیسک."""
    return tempfile.SpooledTemporaryFile(max_size=SPOOL_MAX_MEMORY)


def join_path(*parts: str) -> str:
    """چسباندن بخش‌های مسیر با حذف اسلش‌های اضافه."""
    cleaned = [str(part).strip("/") for part in parts if str(part or "").strip("/")]
    return "/".join(cleaned)


async def _aiter_file(fileobj: Any) -> AsyncIterator[bytes]:
    """خواندن قطعه‌قطعهٔ فایل موقت برای ارسال جریانی."""
    fileobj.seek(0)
    while True:
        chunk = fileobj.read(CHUNK_SIZE)
        if not chunk:
            break
        yield chunk


def _http_error(action: str, status_code: int, body: str = "") -> ExternalStorageError:
    """تبدیل کد وضعیت به پیام فارسی روشن."""
    if status_code in (401, 403):
        detail = "اعتبارنامهٔ مقصد پذیرفته نشد (کلید دسترسی، کلید محرمانه یا رمز عبور را بررسی کنید)."
    elif status_code == 404:
        detail = "مسیر یا باکت مقصد یافت نشد؛ نام باکت و پیشوند مسیر را بررسی کنید."
    elif status_code == 405:
        detail = "سرویس مقصد این عملیات را نمی‌پذیرد؛ نوع مقصد یا نشانی را بررسی کنید."
    elif status_code == 409:
        detail = "تضاد در مقصد؛ ممکن است باکت یا پوشهٔ مقصد وجود نداشته باشد."
    elif status_code >= 500:
        detail = "سرویس مقصد با خطای داخلی پاسخ داد؛ کمی بعد دوباره تلاش کنید."
    else:
        detail = "سرویس مقصد درخواست را نپذیرفت."
    snippet = (body or "").strip().replace("\n", " ")[:200]
    suffix = f" جزئیات سرویس: {snippet}" if snippet else ""
    return ExternalStorageError(f"{action} ناموفق بود (کد {status_code}). {detail}{suffix}")


# ---------------------------------------------------------------------------
# امضای SigV4 برای سرویس‌های سازگار با S3
# ---------------------------------------------------------------------------


def _amz_dates() -> Tuple[str, str]:
    now = datetime.now(timezone.utc)
    return now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")


def _encode_key(key: str) -> str:
    return "/".join(quote(part, safe="") for part in key.split("/"))


def _signing_key(secret: str, date_stamp: str, region: str) -> bytes:
    def sign(key: bytes, message: str) -> bytes:
        return hmac.new(key, message.encode("utf-8"), hashlib.sha256).digest()

    k_date = sign(f"AWS4{secret}".encode("utf-8"), date_stamp)
    k_region = sign(k_date, region)
    k_service = sign(k_region, "s3")
    return sign(k_service, "aws4_request")


def _s3_url_parts(cfg: TargetConfig, object_path: str) -> Tuple[str, str, str]:
    raw = cfg.endpoint.strip()
    parsed = urlparse(raw if "://" in raw else f"https://{raw}")
    scheme = parsed.scheme or "https"
    host = parsed.netloc
    base = parsed.path.rstrip("/")
    encoded = _encode_key(object_path.lstrip("/"))
    if cfg.force_path_style:
        canonical = f"{base}/{quote(cfg.bucket, safe='')}/{encoded}"
    else:
        host = f"{cfg.bucket}.{host}"
        canonical = f"{base}/{encoded}"
    return scheme, host, canonical or "/"


def _sign_s3(
    cfg: TargetConfig,
    method: str,
    object_path: str,
    *,
    payload_hash: str,
    extra_headers: Optional[Dict[str, str]] = None,
) -> Tuple[str, Dict[str, str]]:
    """ساخت نشانی و هدرهای امضاشدهٔ SigV4 برای یک درخواست S3."""
    scheme, host, canonical_uri = _s3_url_parts(cfg, object_path)
    amz_date, date_stamp = _amz_dates()
    region = (cfg.region or "us-east-1").strip() or "us-east-1"

    headers: Dict[str, str] = {
        "host": host,
        "x-amz-content-sha256": payload_hash,
        "x-amz-date": amz_date,
    }
    for key, value in (extra_headers or {}).items():
        if value:
            headers[key.lower()] = str(value)

    signed_keys = sorted(headers)
    canonical_headers = "".join(f"{key}:{headers[key].strip()}\n" for key in signed_keys)
    signed_headers = ";".join(signed_keys)
    canonical_request = "\n".join(
        [method, canonical_uri, "", canonical_headers, signed_headers, payload_hash]
    )
    scope = f"{date_stamp}/{region}/s3/aws4_request"
    string_to_sign = "\n".join(
        [
            "AWS4-HMAC-SHA256",
            amz_date,
            scope,
            hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
        ]
    )
    signature = hmac.new(
        _signing_key(cfg.secret_key, date_stamp, region),
        string_to_sign.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
    headers["authorization"] = (
        f"AWS4-HMAC-SHA256 Credential={cfg.access_key}/{scope}, "
        f"SignedHeaders={signed_headers}, Signature={signature}"
    )
    return f"{scheme}://{host}{canonical_uri}", headers


# ---------------------------------------------------------------------------
# WebDAV
# ---------------------------------------------------------------------------


def _webdav_url(cfg: TargetConfig, object_path: str) -> str:
    raw = cfg.webdav_base_url.strip().rstrip("/")
    if "://" not in raw:
        raw = f"https://{raw}"
    return f"{raw}/{_encode_key(object_path.lstrip('/'))}"


def _webdav_auth(cfg: TargetConfig) -> Tuple[str, str]:
    return cfg.webdav_username, cfg.webdav_password


async def _webdav_ensure_dirs(client: httpx.AsyncClient, cfg: TargetConfig, object_path: str) -> None:
    """ساخت پوشه‌های میانی WebDAV (idempotent؛ ۴۰۵ یعنی از قبل هست)."""
    segments = [part for part in object_path.split("/")[:-1] if part]
    current = ""
    for segment in segments:
        current = f"{current}/{segment}" if current else segment
        response = await client.request(
            "MKCOL", _webdav_url(cfg, current), auth=_webdav_auth(cfg)
        )
        if response.status_code in (201, 301, 405, 409):
            continue
        if response.status_code in (401, 403):
            raise _http_error("ساخت پوشه در مقصد WebDAV", response.status_code, response.text)


# ---------------------------------------------------------------------------
# عملیات عمومی: آپلود، دانلود، حذف، اندازه
# ---------------------------------------------------------------------------


async def upload_file(
    cfg: TargetConfig,
    remote_path: str,
    fileobj: Any,
    *,
    size: int,
    sha256_hex: str,
    content_type: str = "application/octet-stream",
) -> None:
    """آپلود جریانی فایل موقت به مقصد خارجی (بازنویسی همان مسیر = idempotent)."""
    cfg.validate()
    headers = {"content-length": str(int(size)), "content-type": content_type or "application/octet-stream"}
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if cfg.provider == PROVIDER_S3:
                url, signed = _sign_s3(
                    cfg,
                    "PUT",
                    remote_path,
                    payload_hash=sha256_hex or EMPTY_SHA256,
                    extra_headers={"content-type": headers["content-type"]},
                )
                signed["content-length"] = headers["content-length"]
                response = await client.put(url, headers=signed, content=_aiter_file(fileobj))
            else:
                await _webdav_ensure_dirs(client, cfg, remote_path)
                response = await client.put(
                    _webdav_url(cfg, remote_path),
                    headers=headers,
                    auth=_webdav_auth(cfg),
                    content=_aiter_file(fileobj),
                )
            if response.status_code >= 400:
                raise _http_error("بارگذاری فایل در مقصد خارجی", response.status_code, response.text)
    except httpx.HTTPError as exc:
        raise ExternalStorageError(
            "ارتباط با مقصد ذخیره‌سازی خارجی برقرار نشد؛ نشانی سرویس و دسترسی شبکه را بررسی کنید."
        ) from exc


async def download_file(cfg: TargetConfig, remote_path: str, sink: Any) -> Tuple[int, str]:
    """دانلود جریانی از مقصد خارجی؛ (حجم، چکسام SHA-256) برمی‌گرداند."""
    cfg.validate()
    digest = hashlib.sha256()
    total = 0
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if cfg.provider == PROVIDER_S3:
                url, signed = _sign_s3(cfg, "GET", remote_path, payload_hash=EMPTY_SHA256)
                request = client.build_request("GET", url, headers=signed)
            else:
                request = client.build_request("GET", _webdav_url(cfg, remote_path))
                request.headers["authorization"] = httpx.BasicAuth(
                    *_webdav_auth(cfg)
                )._auth_header
            response = await client.send(request, stream=True)
            async with response:
                if response.status_code >= 400:
                    body = (await response.aread()).decode("utf-8", "ignore")
                    raise _http_error("دریافت فایل از مقصد خارجی", response.status_code, body)
                async for chunk in response.aiter_bytes(CHUNK_SIZE):
                    if not chunk:
                        continue
                    digest.update(chunk)
                    total += len(chunk)
                    sink.write(chunk)
    except httpx.HTTPError as exc:
        raise ExternalStorageError(
            "دریافت فایل از مقصد ذخیره‌سازی خارجی ناموفق بود؛ دسترسی شبکه را بررسی کنید."
        ) from exc
    sink.flush()
    return total, digest.hexdigest()


async def stat_file(cfg: TargetConfig, remote_path: str) -> int:
    """حجم فایل در مقصد؛ ``-1`` یعنی سرویس اندازه را اعلام نکرد."""
    cfg.validate()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if cfg.provider == PROVIDER_S3:
                url, signed = _sign_s3(cfg, "HEAD", remote_path, payload_hash=EMPTY_SHA256)
                response = await client.head(url, headers=signed)
            else:
                response = await client.head(
                    _webdav_url(cfg, remote_path), auth=_webdav_auth(cfg)
                )
            if response.status_code >= 400:
                raise _http_error("بررسی فایل در مقصد خارجی", response.status_code, response.text)
            raw = response.headers.get("content-length")
            return int(raw) if raw and raw.isdigit() else -1
    except httpx.HTTPError as exc:
        raise ExternalStorageError("بررسی فایل در مقصد خارجی ناموفق بود.") from exc


async def delete_file(cfg: TargetConfig, remote_path: str) -> bool:
    """حذف فایل از مقصد خارجی؛ نبودن فایل هم موفق شمرده می‌شود."""
    cfg.validate()
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT, follow_redirects=True) as client:
            if cfg.provider == PROVIDER_S3:
                url, signed = _sign_s3(cfg, "DELETE", remote_path, payload_hash=EMPTY_SHA256)
                response = await client.delete(url, headers=signed)
            else:
                response = await client.delete(
                    _webdav_url(cfg, remote_path), auth=_webdav_auth(cfg)
                )
            if response.status_code in (200, 202, 204, 404):
                return True
            raise _http_error("حذف فایل از مقصد خارجی", response.status_code, response.text)
    except httpx.HTTPError as exc:
        raise ExternalStorageError("حذف فایل از مقصد خارجی ناموفق بود.") from exc


# ---------------------------------------------------------------------------
# تست اتصال واقعی: نوشتن، خواندن، مقایسه، حذف
# ---------------------------------------------------------------------------


async def test_connection(cfg: TargetConfig, *, probe_prefix: str) -> str:
    """چرخهٔ کامل نوشتن/خواندن/حذف یک فایل آزمایشی کوچک.

    تنها راه اطمینان واقعی از مقصد این است که هر سه عملیات انجام شود؛ فقط
    بررسی دسترسی خواندن، خطاهای مجوز نوشتن را پنهان می‌کند.
    """
    cfg.validate()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    payload = f"vidara-connection-test-{stamp}".encode("utf-8")
    remote_path = join_path(probe_prefix, "_connection-test", f"test-{stamp}.txt")

    buffer = spooled_file()
    buffer.write(payload)
    buffer.flush()
    checksum = hashlib.sha256(payload).hexdigest()

    try:
        await upload_file(
            cfg,
            remote_path,
            buffer,
            size=len(payload),
            sha256_hex=checksum,
            content_type="text/plain",
        )
    finally:
        buffer.close()

    verify = spooled_file()
    try:
        size, digest = await download_file(cfg, remote_path, verify)
    finally:
        verify.close()

    if size != len(payload) or digest != checksum:
        await delete_file(cfg, remote_path)
        raise ExternalStorageError(
            "فایل آزمایشی نوشته شد اما محتوای خوانده‌شده با اصل یکسان نبود؛ "
            "پیشوند مسیر یا تنظیمات باکت را بررسی کنید."
        )

    await delete_file(cfg, remote_path)
    return (
        "اتصال برقرار است: نوشتن، خواندن و حذف فایل آزمایشی با موفقیت انجام شد "
        f"(مسیر آزمایش: {remote_path})."
    )
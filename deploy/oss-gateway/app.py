"""دروازهٔ ذخیره‌سازی مستقل (سازگار با قرارداد ObjectStorage پروژه) روی MinIO.

چرا این سرویس لازم است؟ کد قابلیت‌های بک‌اند (`services/storage.py`) با یک سرویس
ObjectStorage از طریق مسیرهای `/api/v1/infra/client/oss/...` حرف می‌زند. برای اجرای
پروژه روی سرور مستقل، بدون هیچ تغییری در کد قابلیت‌ها، همان قرارداد را اینجا
پیاده می‌کنیم و پشت آن MinIO محلی می‌نشیند.

قواعد سخت این ماژول:

* **قرارداد پاسخ عیناً حفظ می‌شود**: هر پاسخ در پوشش ``{"code": 0, "message":
  "SUCCESS", "data": {...}}`` برگردانده می‌شود، چون کلاینت پروژه دقیقاً همین را
  بررسی می‌کند.
* **دو نشانی مجزا**: عملیات سمت سرور با نشانی داخلی شبکهٔ داکر انجام می‌شود، اما
  نشانی‌های امضاشده (upload/download) با نشانی عمومی امضا می‌شوند تا میزبان
  امضا با میزبانی که مرورگر صدا می‌زند یکی باشد.
* **کلید اجباری**: بدون ``OSS_API_KEY`` سرویس بالا نمی‌آید؛ هیچ مقدار پیش‌فرض
  قابل حدسی وجود ندارد.
"""

from __future__ import annotations

import json
import logging
import mimetypes
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.client import Config as BotoConfig
from botocore.exceptions import ClientError
from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("oss-gateway")

API_PREFIX = "/api/v1/infra/client/oss"
DEFAULT_PRESIGN_EXPIRES = int(os.environ.get("PRESIGN_EXPIRES", "3600"))


def _required_env(name: str) -> str:
    value = (os.environ.get(name) or "").strip()
    if not value:
        raise RuntimeError(
            f"متغیر محیطی «{name}» تنظیم نشده است. سرویس ذخیره‌سازی بدون آن اجرا نمی‌شود."
        )
    return value


OSS_API_KEY = _required_env("OSS_API_KEY")
MINIO_ACCESS_KEY = _required_env("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = _required_env("MINIO_SECRET_KEY")
MINIO_INTERNAL_URL = _required_env("MINIO_INTERNAL_URL").rstrip("/")
MINIO_PUBLIC_URL = _required_env("MINIO_PUBLIC_URL").rstrip("/")
MINIO_REGION = (os.environ.get("MINIO_REGION") or "us-east-1").strip() or "us-east-1"

_BOTO_CONFIG = BotoConfig(
    signature_version="s3v4",
    s3={"addressing_style": "path"},
    retries={"max_attempts": 3, "mode": "standard"},
)


def _client(endpoint: str):
    return boto3.client(
        "s3",
        endpoint_url=endpoint,
        aws_access_key_id=MINIO_ACCESS_KEY,
        aws_secret_access_key=MINIO_SECRET_KEY,
        region_name=MINIO_REGION,
        config=_BOTO_CONFIG,
    )


internal_s3 = _client(MINIO_INTERNAL_URL)
public_s3 = _client(MINIO_PUBLIC_URL)

app = FastAPI(title="Vidara Storage Gateway", version="1.0.0", docs_url=None, redoc_url=None)


# ---------------------------------------------------------------------------
# ابزارهای مشترک
# ---------------------------------------------------------------------------


def require_token(authorization: str = Header(default="")) -> None:
    """بررسی توکن Bearer؛ مقایسه ساده اما اجباری است."""
    expected = f"Bearer {OSS_API_KEY}"
    if (authorization or "").strip() != expected:
        raise HTTPException(status_code=401, detail="کلید دسترسی سرویس ذخیره‌سازی معتبر نیست.")


def ok(data: Any) -> JSONResponse:
    return JSONResponse({"code": 0, "message": "SUCCESS", "data": data})


def fail(message: str, status_code: int = 400) -> JSONResponse:
    return JSONResponse({"code": 1, "message": message, "error": message}, status_code=status_code)


def _iso(value: Optional[datetime]) -> str:
    if not value:
        return datetime.now(timezone.utc).isoformat()
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


def _expires_at(expires_in: int) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=expires_in)).isoformat()


def _normalize_expires(raw: Optional[int]) -> int:
    """صفر یا مقدار نامعتبر به بازهٔ پیش‌فرض تبدیل می‌شود (کلاینت پروژه صفر می‌فرستد)."""
    try:
        value = int(raw or 0)
    except (TypeError, ValueError):
        value = 0
    if value <= 0:
        return DEFAULT_PRESIGN_EXPIRES
    return min(value, 7 * 24 * 3600)


def _public_read_policy(bucket: str) -> str:
    return json.dumps(
        {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {"AWS": ["*"]},
                    "Action": ["s3:GetObject"],
                    "Resource": [f"arn:aws:s3:::{bucket}/*"],
                }
            ],
        }
    )


def _bucket_visibility(bucket: str) -> str:
    try:
        internal_s3.get_bucket_policy(Bucket=bucket)
        return "public"
    except ClientError:
        return "private"


def _guess_content_type(object_key: str) -> str:
    guessed, _ = mimetypes.guess_type(object_key)
    return guessed or "application/octet-stream"


def _client_error_message(exc: ClientError, action: str) -> str:
    code = (exc.response or {}).get("Error", {}).get("Code", "")
    if code in ("NoSuchBucket",):
        return f"{action} ناموفق بود: باکت مقصد وجود ندارد."
    if code in ("NoSuchKey", "404"):
        return f"{action} ناموفق بود: فایل در فضای ذخیره‌سازی یافت نشد."
    if code in ("AccessDenied", "403", "InvalidAccessKeyId", "SignatureDoesNotMatch"):
        return f"{action} ناموفق بود: دسترسی به فضای ذخیره‌سازی پذیرفته نشد."
    return f"{action} ناموفق بود ({code or 'خطای نامشخص'})."


# ---------------------------------------------------------------------------
# مدل‌های ورودی (هم‌شکل با کلاینت پروژه)
# ---------------------------------------------------------------------------


class BucketBody(BaseModel):
    bucket_name: str
    visibility: str = "private"


class DeleteBody(BaseModel):
    object_keys: List[str] = Field(default_factory=list)


class RenameBody(BaseModel):
    source_key: str
    target_key: str
    overwrite_key: bool = True


class PresignBody(BaseModel):
    object_key: str
    expires_in: int = 0
    content_type: Optional[str] = None


# ---------------------------------------------------------------------------
# باکت‌ها
# ---------------------------------------------------------------------------


@app.get("/healthz")
def healthz() -> JSONResponse:
    try:
        internal_s3.list_buckets()
    except Exception as exc:  # pragma: no cover - وابسته به وضعیت MinIO
        logger.warning("بررسی سلامت ناموفق بود: %s", exc)
        return JSONResponse({"status": "unhealthy"}, status_code=503)
    return JSONResponse({"status": "ok"})


@app.post(f"{API_PREFIX}/buckets", dependencies=[Depends(require_token)])
def create_bucket(body: BucketBody) -> JSONResponse:
    bucket = body.bucket_name.strip()
    if not bucket:
        return fail("نام باکت خالی است.")
    try:
        try:
            internal_s3.create_bucket(Bucket=bucket)
        except ClientError as exc:
            code = (exc.response or {}).get("Error", {}).get("Code", "")
            if code not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise
        if body.visibility == "public":
            internal_s3.put_bucket_policy(Bucket=bucket, Policy=_public_read_policy(bucket))
    except ClientError as exc:
        return fail(_client_error_message(exc, "ساخت باکت"), 502)
    return ok({"bucket_name": bucket, "created_at": _iso(None)})


@app.get(f"{API_PREFIX}/buckets", dependencies=[Depends(require_token)])
def list_buckets() -> JSONResponse:
    try:
        result = internal_s3.list_buckets()
    except ClientError as exc:
        return fail(_client_error_message(exc, "فهرست باکت‌ها"), 502)
    buckets = [
        {"bucket_name": item["Name"], "visibility": _bucket_visibility(item["Name"])}
        for item in result.get("Buckets", [])
    ]
    return ok({"buckets": buckets})


# ---------------------------------------------------------------------------
# اشیاء
# ---------------------------------------------------------------------------


@app.get(f"{API_PREFIX}/buckets/{{bucket}}/objects/metadata", dependencies=[Depends(require_token)])
def object_metadata(bucket: str, object_key: str = Query(...)) -> JSONResponse:
    try:
        head = internal_s3.head_object(Bucket=bucket, Key=object_key)
    except ClientError as exc:
        return fail(_client_error_message(exc, "دریافت مشخصات فایل"), 404)
    return ok(
        {
            "key": object_key,
            "size": int(head.get("ContentLength") or 0),
            "last_modified": _iso(head.get("LastModified")),
            "etag": (head.get("ETag") or "").strip('"'),
        }
    )


@app.get(f"{API_PREFIX}/buckets/{{bucket}}/objects", dependencies=[Depends(require_token)])
def list_objects(bucket: str, prefix: str = Query(default="")) -> JSONResponse:
    objects: List[Dict[str, Any]] = []
    try:
        token: Optional[str] = None
        while True:
            kwargs: Dict[str, Any] = {"Bucket": bucket, "MaxKeys": 1000}
            if prefix:
                kwargs["Prefix"] = prefix
            if token:
                kwargs["ContinuationToken"] = token
            page = internal_s3.list_objects_v2(**kwargs)
            for item in page.get("Contents", []):
                objects.append(
                    {
                        "key": item["Key"],
                        "size": int(item.get("Size") or 0),
                        "last_modified": _iso(item.get("LastModified")),
                        "etag": (item.get("ETag") or "").strip('"'),
                    }
                )
            if not page.get("IsTruncated"):
                break
            token = page.get("NextContinuationToken")
            if not token:
                break
    except ClientError as exc:
        return fail(_client_error_message(exc, "فهرست فایل‌ها"), 502)
    return ok({"objects": objects})


@app.delete(f"{API_PREFIX}/buckets/{{bucket}}/objects", dependencies=[Depends(require_token)])
def delete_objects(bucket: str, body: DeleteBody) -> JSONResponse:
    keys = [key for key in (body.object_keys or []) if key]
    if not keys:
        return ok({"deleted": 0})
    try:
        internal_s3.delete_objects(
            Bucket=bucket, Delete={"Objects": [{"Key": key} for key in keys], "Quiet": True}
        )
    except ClientError as exc:
        return fail(_client_error_message(exc, "حذف فایل"), 502)
    return ok({"deleted": len(keys)})


@app.post(f"{API_PREFIX}/buckets/{{bucket}}/objects/rename", dependencies=[Depends(require_token)])
def rename_object(bucket: str, body: RenameBody) -> JSONResponse:
    if not body.source_key or not body.target_key:
        return fail("مسیر مبدأ و مقصد لازم است.")
    try:
        if not body.overwrite_key:
            try:
                internal_s3.head_object(Bucket=bucket, Key=body.target_key)
                return fail("فایل مقصد از قبل وجود دارد.", 409)
            except ClientError:
                pass
        internal_s3.copy_object(
            Bucket=bucket,
            Key=body.target_key,
            CopySource={"Bucket": bucket, "Key": body.source_key},
        )
        internal_s3.delete_object(Bucket=bucket, Key=body.source_key)
    except ClientError as exc:
        return fail(_client_error_message(exc, "تغییر نام فایل"), 502)
    return ok({"success": True})


@app.post(f"{API_PREFIX}/buckets/{{bucket}}/objects/upload_url", dependencies=[Depends(require_token)])
def upload_url(bucket: str, body: PresignBody) -> JSONResponse:
    expires_in = _normalize_expires(body.expires_in)
    try:
        try:
            internal_s3.head_bucket(Bucket=bucket)
        except ClientError:
            internal_s3.create_bucket(Bucket=bucket)
        url = public_s3.generate_presigned_url(
            "put_object",
            Params={"Bucket": bucket, "Key": body.object_key},
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        return fail(_client_error_message(exc, "ساخت نشانی بارگذاری"), 502)
    return ok({"upload_url": url, "expires_at": _expires_at(expires_in)})


@app.post(f"{API_PREFIX}/buckets/{{bucket}}/objects/download_url", dependencies=[Depends(require_token)])
def download_url(bucket: str, body: PresignBody) -> JSONResponse:
    expires_in = _normalize_expires(body.expires_in)
    content_type = (body.content_type or "").strip() or _guess_content_type(body.object_key)
    try:
        url = public_s3.generate_presigned_url(
            "get_object",
            Params={
                "Bucket": bucket,
                "Key": body.object_key,
                "ResponseContentType": content_type,
            },
            ExpiresIn=expires_in,
        )
    except ClientError as exc:
        return fail(_client_error_message(exc, "ساخت نشانی دریافت"), 502)
    return ok({"download_url": url, "expires_at": _expires_at(expires_in)})
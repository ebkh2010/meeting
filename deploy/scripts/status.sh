#!/usr/bin/env bash
# نمایش وضعیت سرویس‌ها و نتیجهٔ بررسی‌های سلامت.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"

[ -f "${ENV_FILE}" ] || { echo "[خطا] فایل .env یافت نشد." >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

# پورت منتشرشدهٔ سامانه روی میزبان (همان APP_PORT در docker-compose.yml)
APP_PORT="${APP_PORT:-7080}"

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

echo "=== وضعیت سرویس‌ها ==="
compose ps

echo ""
echo "=== بررسی سلامت ==="
if compose exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
    echo "پایگاه داده:        سالم"
else
    echo "پایگاه داده:        ناسالم"
fi

# ایمیج‌های oss-gateway و backend (python:3.11-slim) شامل curl نیستند؛
# بررسی سلامت با خودِ پایتون انجام می‌شود تا همیشه درست گزارش شود.
if compose exec -T oss-gateway python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:9000/healthz', timeout=5).status==200 else 1)" >/dev/null 2>&1; then
    echo "ذخیره‌سازی:         سالم"
else
    echo "ذخیره‌سازی:         ناسالم"
fi

if compose exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)" >/dev/null 2>&1; then
    echo "بک‌اند:              سالم"
else
    echo "بک‌اند:              ناسالم"
fi

# سامانه روی پورت میزبان APP_PORT منتشر شده است (پیش‌فرض ۷۰۸۰). این بررسی
# خودِ کانتینر پروکسی را می‌سنجد و مستقل از لایهٔ TLS لبه است.
if curl -fsS -m 10 -H "Host: ${APP_DOMAIN}" "http://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    echo "پروکسی (HTTP):      سالم"
else
    echo "پروکسی (HTTP):      پاسخ نداد"
fi

# HTTPS ممکن است در لبه (nginx میزبان/CDN) یا داخل کانتینر (گواهی دستی در
# deploy/nginx/certs) خاتمه یابد؛ هر دو مسیر بررسی می‌شود.
HTTPS_OK=0
if curl -fsSk -m 10 "https://${APP_DOMAIN}/health" >/dev/null 2>&1; then
    HTTPS_OK=1
elif curl -fsSk -m 10 "https://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
    HTTPS_OK=1
fi
if [ "${HTTPS_OK}" = "1" ]; then
    echo "HTTPS:              فعال"
else
    echo "HTTPS:              غیرفعال (گواهی دستی در deploy/nginx/certs نیست یا لبهٔ TLS تنظیم نشده)"
fi

echo ""
echo "=== مصرف فضای دیسک ==="
docker system df 2>/dev/null || true

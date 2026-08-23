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

if compose exec -T oss-gateway curl -fsS http://127.0.0.1:9000/healthz >/dev/null 2>&1; then
    echo "ذخیره‌سازی:         سالم"
else
    echo "ذخیره‌سازی:         ناسالم"
fi

if compose exec -T backend curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
    echo "بک‌اند:              سالم"
else
    echo "بک‌اند:              ناسالم"
fi

if curl -fsS -m 10 -H "Host: ${APP_DOMAIN}" http://127.0.0.1/health >/dev/null 2>&1; then
    echo "پروکسی (HTTP):      سالم"
else
    echo "پروکسی (HTTP):      پاسخ نداد"
fi

if curl -fsSk -m 10 "https://${APP_DOMAIN}/health" >/dev/null 2>&1; then
    echo "HTTPS:              فعال"
else
    echo "HTTPS:              غیرفعال یا گواهی صادر نشده"
fi

echo ""
echo "=== مصرف فضای دیسک ==="
docker system df 2>/dev/null || true
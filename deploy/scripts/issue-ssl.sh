#!/usr/bin/env bash
# فعال‌سازی گواهی SSL دستی برای دامنهٔ سامانه و دامنهٔ فایل‌ها.
#
# در این بسته سرویس certbot وجود ندارد (آگاهانه حذف شد)؛ گواهی به‌صورت دستی در
# پوشهٔ deploy/nginx/certs/ قرار می‌گیرد:
#   fullchain.pem  ← زنجیرهٔ کامل گواهی (leaf + intermediate)
#   privkey.pem    ← کلید خصوصی
#
# دو حالت استقرار پشتیبانی می‌شود:
#   ۱) TLS در لبه (nginx میزبان یا CDN): گواهی در لبه نصب می‌شود و لبه به
#      پورت‌های منتشرشدهٔ این بسته پراکسی می‌کند؛ در این حالت فایل گواهی در
#      certs لازم نیست و فقط بررسی HTTPS انجام می‌شود.
#   ۲) TLS داخل کانتینر: گواهی را در deploy/nginx/certs بگذارید و این اسکریپت
#      را اجرا کنید تا پروکسی با پیکربندی HTTPS دوباره ساخته شود.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
CERTS_DIR="${DEPLOY_DIR}/nginx/certs"

[ -f "${ENV_FILE}" ] || { echo "[خطا] فایل .env یافت نشد." >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

APP_PORT="${APP_PORT:-7080}"
STORAGE_HOST_PORT="${STORAGE_HOST_PORT:-7443}"

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

FULLCHAIN="${CERTS_DIR}/fullchain.pem"
PRIVKEY="${CERTS_DIR}/privkey.pem"

if [ -s "${FULLCHAIN}" ] && [ -s "${PRIVKEY}" ]; then
    echo "[اطلاع] گواهی دستی یافت شد؛ راه‌اندازی دوبارهٔ پروکسی برای فعال شدن HTTPS..."
    compose up -d --force-recreate proxy
else
    echo "[خطا] گواهی دستی یافت نشد:" >&2
    echo "        ${FULLCHAIN}" >&2
    echo "        ${PRIVKEY}" >&2
    echo "" >&2
    echo "  در این بسته سرویس certbot وجود ندارد؛ گواهی را از یکی از این راه‌ها تهیه کنید:" >&2
    echo "  ۱) صدور از پنل CDN (مثلاً ابر آروان) و دانلود fullchain و privkey؛" >&2
    echo "  ۲) certbot روی خودِ میزبان (بیرون از داکر) و کپی دو فایل به مسیر بالا؛" >&2
    echo "  ۳) هر گواهی معتبر دیگر." >&2
    echo "" >&2
    echo "  سپس اجرا کنید:" >&2
    echo "        bash scripts/issue-ssl.sh" >&2
    echo "" >&2
    echo "  اگر TLS را در لبه (nginx میزبان/CDN) خاتمه می‌دهید، این اسکریپت لازم نیست؛" >&2
    echo "  لبه باید به 127.0.0.1:${APP_PORT} (سامانه) و 127.0.0.1:${STORAGE_HOST_PORT} (فایل‌ها)" >&2
    echo "  پراکسی کند و هدر Host را حفظ نماید." >&2
    exit 1
fi

echo "[اطلاع] بررسی HTTPS روی ${APP_DOMAIN}..."
HTTPS_OK=0
for _ in $(seq 1 20); do
    # مسیر اصلی کاربر (در حالت لبه هم همین نشانی است)؛ در حالت مستقیم،
    # پورت منتشرشدهٔ میزبان هم به‌عنوان جایگزین بررسی می‌شود.
    if curl -fsSk -m 15 "https://${APP_DOMAIN}/health" >/dev/null 2>&1; then
        HTTPS_OK=1
        break
    fi
    if curl -fsSk -m 15 "https://127.0.0.1:${APP_PORT}/health" >/dev/null 2>&1; then
        HTTPS_OK=1
        break
    fi
    sleep 3
done
if [ "${HTTPS_OK}" = "1" ]; then
    echo "[موفق] HTTPS فعال است و سامانه پاسخ می‌دهد: https://${APP_DOMAIN}"
else
    echo "[هشدار] پاسخ HTTPS دریافت نشد؛ بررسی کنید:"
    echo "         - حالت لبه: تنظیمات nginx میزبان/CDN؛"
    echo "         - حالت مستقیم: curl -k https://127.0.0.1:${APP_PORT}/health"
    echo "         و لاگ پروکسی: bash scripts/logs.sh proxy"
fi

echo "[اطلاع] بررسی HTTPS مسیر فایل‌ها..."
STORAGE_OK=0
if curl -fsSk -m 15 "https://${STORAGE_DOMAIN}/minio/health/live" >/dev/null 2>&1; then
    STORAGE_OK=1
elif curl -fsSk -m 15 "https://127.0.0.1:${STORAGE_HOST_PORT}/minio/health/live" >/dev/null 2>&1; then
    STORAGE_OK=1
fi
if [ "${STORAGE_OK}" = "1" ]; then
    echo "[موفق] مسیر فایل‌ها با HTTPS پاسخ می‌دهد."
else
    echo "[هشدار] مسیر فایل‌ها پاسخ HTTPS نداد؛ در حالت لبه، پورت ${STORAGE_HOST_PORT}"
    echo "         باید با TLS پوشانده شود؛ در حالت مستقیم گواهی کانتینر را بررسی کنید."
fi

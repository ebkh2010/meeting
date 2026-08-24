#!/usr/bin/env bash
# صدور گواهی Let's Encrypt برای دامنهٔ سامانه و دامنهٔ فایل‌ها.
#
# روش webroot استفاده می‌شود تا سرویس در حال اجرا قطع نشود. پس از صدور موفق،
# سرویس پروکسی دوباره راه‌اندازی می‌شود و به‌طور خودکار پیکربندی HTTPS را
# برمی‌دارد. تمدید خودکار توسط سرویس `certbot` انجام می‌شود.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"

[ -f "${ENV_FILE}" ] || { echo "[خطا] فایل .env یافت نشد." >&2; exit 1; }

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

for key in APP_DOMAIN STORAGE_DOMAIN LETSENCRYPT_EMAIL; do
    if [ -z "${!key:-}" ]; then
        echo "[خطا] متغیر «${key}» تنظیم نشده است." >&2
        exit 1
    fi
done

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

echo "[اطلاع] بررسی دسترس‌پذیری مسیر چالش ACME روی ${APP_DOMAIN}..."
if ! curl -fsS -m 15 "http://${APP_DOMAIN}/.well-known/acme-challenge/" >/dev/null 2>&1; then
    echo "[هشدار] مسیر چالش پاسخ استاندارد نداد؛ اگر صدور شکست خورد، DNS و باز بودن پورت ۸۰ را بررسی کنید."
fi

STAGING_FLAG=""
if [ "${LETSENCRYPT_STAGING:-0}" = "1" ]; then
    STAGING_FLAG="--staging"
    echo "[اطلاع] حالت آزمایشی Let's Encrypt فعال است (گواهی مورد اعتماد مرورگر نیست)."
fi

echo "[اطلاع] درخواست گواهی..."
# دامنه‌ها: اصلی + www + (دامنهٔ فایل‌ها فقط اگر متفاوت باشد)
CERT_DOMAINS=(-d "${APP_DOMAIN}" -d "www.${APP_DOMAIN}")
if [ "${STORAGE_DOMAIN}" != "${APP_DOMAIN}" ] && [ "${STORAGE_DOMAIN}" != "www.${APP_DOMAIN}" ]; then
    CERT_DOMAINS+=(-d "${STORAGE_DOMAIN}")
fi
compose run --rm --entrypoint certbot certbot certonly \
    --webroot --webroot-path /var/www/certbot \
    --email "${LETSENCRYPT_EMAIL}" \
    --agree-tos --no-eff-email \
    --non-interactive \
    ${STAGING_FLAG} \
    "${CERT_DOMAINS[@]}"

echo "[اطلاع] راه‌اندازی دوبارهٔ پروکسی برای فعال شدن HTTPS..."
compose up -d --force-recreate proxy

sleep 5
if curl -fsSk -m 15 "https://${APP_DOMAIN}/health" >/dev/null 2>&1; then
    echo "[موفق] HTTPS فعال است و سامانه روی https://${APP_DOMAIN} پاسخ می‌دهد."
else
    echo "[هشدار] پاسخ HTTPS دریافت نشد؛ لاگ پروکسی را بررسی کنید: bash scripts/logs.sh proxy"
fi
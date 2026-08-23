#!/bin/sh
# انتخاب پیکربندی nginx بر پایهٔ وجود گواهی SSL.
#
# پیش از صدور گواهی، پیکربندی HTTP بالا می‌آید تا هم سامانه قابل استفاده باشد و هم
# مسیر چالش ACME پاسخ بدهد. پس از صدور گواهی، با یک بار راه‌اندازی دوبارهٔ سرویس،
# پیکربندی HTTPS فعال می‌شود.
set -eu

if [ -z "${APP_DOMAIN:-}" ]; then
    echo "[خطا] متغیر APP_DOMAIN تنظیم نشده است؛ سرویس پروکسی اجرا نمی‌شود." >&2
    exit 1
fi
if [ -z "${STORAGE_DOMAIN:-}" ]; then
    echo "[خطا] متغیر STORAGE_DOMAIN تنظیم نشده است؛ سرویس پروکسی اجرا نمی‌شود." >&2
    exit 1
fi

MAX_UPLOAD_SIZE="${MAX_UPLOAD_SIZE:-2048m}"
# پورت جداگانهٔ storage: در حالت بدون دامنه (دسترسی با IP) روی ۸۴۴۳ می‌نشیند؛
# در حالت دامنه‌دار با SSL می‌توان آن را ۴۴۳ گذاشت تا مثل قبل روی همان پورت باشد.
STORAGE_PORT="${STORAGE_PORT:-8443}"
export APP_DOMAIN STORAGE_DOMAIN MAX_UPLOAD_SIZE STORAGE_PORT

CERT_DIR="/etc/letsencrypt/live/${APP_DOMAIN}"
if [ -s "${CERT_DIR}/fullchain.pem" ] && [ -s "${CERT_DIR}/privkey.pem" ]; then
    TEMPLATE="/etc/nginx/templates/https.conf.template"
    echo "[اطلاع] گواهی SSL برای ${APP_DOMAIN} یافت شد؛ پیکربندی HTTPS فعال می‌شود."
else
    TEMPLATE="/etc/nginx/templates/http.conf.template"
    echo "[هشدار] گواهی SSL یافت نشد؛ فعلاً فقط HTTP فعال است. پس از صدور گواهی، سرویس پروکسی را دوباره راه‌اندازی کنید."
fi

mkdir -p /var/www/certbot
envsubst '${APP_DOMAIN} ${STORAGE_DOMAIN} ${MAX_UPLOAD_SIZE} ${STORAGE_PORT}' \
    < "${TEMPLATE}" > /etc/nginx/conf.d/default.conf

nginx -t
exec nginx -g 'daemon off;'
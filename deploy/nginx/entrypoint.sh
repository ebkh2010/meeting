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

# گواهی دستی (تأمین‌شده توسط مدیر) اولویت دارد؛ در نبودش به مسیر Let's Encrypt
# نگاه می‌کنیم و اگر هیچ گواهی‌ای نبود فقط HTTP بالا می‌آید.
CERT_FULLCHAIN=""
CERT_PRIVKEY=""
if [ -s "/etc/nginx/certs/fullchain.pem" ] && [ -s "/etc/nginx/certs/privkey.pem" ]; then
    CERT_FULLCHAIN="/etc/nginx/certs/fullchain.pem"
    CERT_PRIVKEY="/etc/nginx/certs/privkey.pem"
    echo "[اطلاع] گواهی دستی یافت شد؛ پیکربندی HTTPS فعال می‌شود."
elif [ -s "/etc/letsencrypt/live/${APP_DOMAIN}/fullchain.pem" ] && [ -s "/etc/letsencrypt/live/${APP_DOMAIN}/privkey.pem" ]; then
    CERT_FULLCHAIN="/etc/letsencrypt/live/${APP_DOMAIN}/fullchain.pem"
    CERT_PRIVKEY="/etc/letsencrypt/live/${APP_DOMAIN}/privkey.pem"
    echo "[اطلاع] گواهی Let's Encrypt یافت شد؛ پیکربندی HTTPS فعال می‌شود."
else
    echo "[هشدار] گواهی SSL یافت نشد؛ فعلاً فقط HTTP فعال است."
fi
export CERT_FULLCHAIN CERT_PRIVKEY

if [ -n "${CERT_FULLCHAIN}" ]; then
    TEMPLATE="/etc/nginx/templates/https.conf.template"
else
    TEMPLATE="/etc/nginx/templates/http.conf.template"
fi

mkdir -p /var/www/certbot
envsubst '${APP_DOMAIN} ${STORAGE_DOMAIN} ${MAX_UPLOAD_SIZE} ${STORAGE_PORT} ${CERT_FULLCHAIN} ${CERT_PRIVKEY}' \
    < "${TEMPLATE}" > /etc/nginx/conf.d/default.conf

nginx -t
exec nginx -g 'daemon off;'
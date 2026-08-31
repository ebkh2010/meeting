#!/bin/sh
# انتخاب پیکربندی nginx بر پایهٔ وجود گواهی دستی SSL.
#
# گواهی دستی از پوشهٔ deploy/nginx/certs خوانده می‌شود (fullchain.pem و privkey.pem).
# در نبود گواهی، پیکربندی فقط-HTTP بالا می‌آید تا سامانه با HTTP کار کند و TLS در
# لبه (nginx میزبان یا CDN) خاتمه یابد. پس از قرار دادن گواهی و راه‌اندازی دوبارهٔ
# سرویس پروکسی، خودِ کانتینر هم TLS را روی پورت‌های منتشرشده خاتمه می‌دهد.
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
# پورت گوش‌دادن مسیر فایل‌ها داخل کانتینر؛ روی میزبان با STORAGE_HOST_PORT منتشر
# می‌شود (پیش‌فرض ۷۴۴۳). در حالت با دامنهٔ مجزا و TLS در لبه، مقدار پیش‌فرض
# مناسب است و معمولاً تغییر لازم نیست.
STORAGE_PORT="${STORAGE_PORT:-8443}"
export APP_DOMAIN STORAGE_DOMAIN MAX_UPLOAD_SIZE STORAGE_PORT

# گواهی دستی (تأمین‌شده توسط مدیر)؛ در نبودش فقط HTTP بالا می‌آید.
CERT_FULLCHAIN=""
CERT_PRIVKEY=""
if [ -s "/etc/nginx/certs/fullchain.pem" ] && [ -s "/etc/nginx/certs/privkey.pem" ]; then
    CERT_FULLCHAIN="/etc/nginx/certs/fullchain.pem"
    CERT_PRIVKEY="/etc/nginx/certs/privkey.pem"
    echo "[اطلاع] گواهی دستی یافت شد؛ پیکربندی HTTPS فعال می‌شود."
else
    echo "[هشدار] گواهی SSL یافت نشد؛ فعلاً فقط HTTP فعال است (TLS باید در لبه خاتمه یابد یا گواهی دستی اضافه شود)."
fi
export CERT_FULLCHAIN CERT_PRIVKEY

if [ -n "${CERT_FULLCHAIN}" ]; then
    TEMPLATE="/etc/nginx/templates/https.conf.template"
else
    TEMPLATE="/etc/nginx/templates/http.conf.template"
fi

envsubst '${APP_DOMAIN} ${STORAGE_DOMAIN} ${MAX_UPLOAD_SIZE} ${STORAGE_PORT} ${CERT_FULLCHAIN} ${CERT_PRIVKEY}' \
    < "${TEMPLATE}" > /etc/nginx/conf.d/default.conf

nginx -t
exec nginx -g 'daemon off;'
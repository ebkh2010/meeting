#!/usr/bin/env bash
# ساخت فایل `.env` با کلیدهای تصادفی امن.
#
# این اسکریپت هیچ مقدار حساسی را حدس‌زدنی نمی‌گذارد: هر کلید با openssl تولید
# می‌شود. اگر `.env` از قبل وجود داشته باشد، بازنویسی نمی‌شود تا کلیدهای فعلی
# (که اعتبارنامه‌های رمزشده به آن‌ها وابسته‌اند) از دست نروند.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
EXAMPLE_FILE="${DEPLOY_DIR}/.env.example"

if [ -f "${ENV_FILE}" ]; then
    echo "[اطلاع] فایل .env از قبل وجود دارد و دست‌نخورده می‌ماند: ${ENV_FILE}"
    echo "        اگر می‌خواهید از نو بسازید، ابتدا از آن نسخهٔ پشتیبان بگیرید."
    exit 0
fi

if ! command -v openssl >/dev/null 2>&1; then
    echo "[خطا] برنامهٔ openssl نصب نیست؛ برای ساخت کلیدهای امن لازم است." >&2
    exit 1
fi

random_secret() {
    openssl rand -base64 36 | tr -d '\n/+=' | cut -c1-40
}

APP_DOMAIN_INPUT="${APP_DOMAIN:-}"
STORAGE_DOMAIN_INPUT="${STORAGE_DOMAIN:-}"
LETSENCRYPT_EMAIL_INPUT="${LETSENCRYPT_EMAIL:-}"

if [ -z "${APP_DOMAIN_INPUT}" ]; then
    read -r -p "دامنهٔ اصلی سامانه (مثال: meetings.example.com): " APP_DOMAIN_INPUT
fi
if [ -z "${STORAGE_DOMAIN_INPUT}" ]; then
    read -r -p "دامنهٔ فایل‌ها (پیشنهاد: storage.${APP_DOMAIN_INPUT}): " STORAGE_DOMAIN_INPUT
    STORAGE_DOMAIN_INPUT="${STORAGE_DOMAIN_INPUT:-storage.${APP_DOMAIN_INPUT}}"
fi
if [ -z "${LETSENCRYPT_EMAIL_INPUT}" ]; then
    read -r -p "ایمیل برای گواهی SSL (اختیاری؛ در حالت گواهی دستی لازم نیست): " LETSENCRYPT_EMAIL_INPUT
fi

for pair in "APP_DOMAIN:${APP_DOMAIN_INPUT}" "STORAGE_DOMAIN:${STORAGE_DOMAIN_INPUT}"; do
    name="${pair%%:*}"
    value="${pair#*:}"
    if [ -z "${value}" ]; then
        echo "[خطا] مقدار «${name}» خالی است؛ نصب بدون آن ممکن نیست." >&2
        exit 1
    fi
done

cp "${EXAMPLE_FILE}" "${ENV_FILE}"

set_value() {
    local key="$1"
    local value="$2"
    python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import sys

path, key, value = sys.argv[1], sys.argv[2], sys.argv[3]
with open(path, "r", encoding="utf-8") as handle:
    lines = handle.readlines()

found = False
for index, line in enumerate(lines):
    if line.startswith(f"{key}="):
        lines[index] = f"{key}={value}\n"
        found = True
        break
if not found:
    lines.append(f"{key}={value}\n")

with open(path, "w", encoding="utf-8") as handle:
    handle.writelines(lines)
PY
}

set_value APP_DOMAIN "${APP_DOMAIN_INPUT}"
set_value STORAGE_DOMAIN "${STORAGE_DOMAIN_INPUT}"
set_value LETSENCRYPT_EMAIL "${LETSENCRYPT_EMAIL_INPUT}"
set_value APP_PUBLIC_URL "https://${APP_DOMAIN_INPUT}"
set_value STORAGE_PUBLIC_URL "https://${STORAGE_DOMAIN_INPUT}"
set_value PUBLIC_API_BASE_URL ""
set_value POSTGRES_PASSWORD "$(random_secret)"
set_value JWT_SECRET_KEY "$(random_secret)"
set_value MINIO_ROOT_PASSWORD "$(random_secret)"
set_value OSS_API_KEY "$(random_secret)"

chmod 600 "${ENV_FILE}"

echo "[موفق] فایل .env ساخته شد: ${ENV_FILE}"
echo "        دسترسی فایل روی 600 تنظیم شد."
echo "        هشدار: از این فایل نسخهٔ پشتیبان امن بگیرید؛ با گم شدن JWT_SECRET_KEY"
echo "        اعتبارنامه‌های رمزشده (SMTP، پیامک، کلید AI، مقصد آرشیو) قابل بازیابی نیستند."
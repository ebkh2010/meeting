#!/usr/bin/env bash
# بازیابی از فایل پشتیبان.
#
# ترتیب امن: تأیید صریح کاربر ← استخراج و بررسی سالم بودن پشتیبان ←
# بازیابی پایگاه داده ← بازگرداندن فایل‌ها ← راه‌اندازی دوبارهٔ بک‌اند.
#
# نکتهٔ مهم: اگر `JWT_SECRET_KEY` فعلی با کلید زمان پشتیبان‌گیری متفاوت باشد،
# اعتبارنامه‌های رمزشده (SMTP، پیامک، کلید AI، مقصد آرشیو) قابل رمزگشایی
# نخواهند بود؛ اسکریپت این وضعیت را تشخیص می‌دهد و هشدار می‌دهد.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
ARCHIVE="${1:-}"

if [ -z "${ARCHIVE}" ]; then
    echo "روش استفاده: bash scripts/restore.sh <مسیر فایل پشتیبان .tar.gz>" >&2
    exit 1
fi
[ -s "${ARCHIVE}" ] || { echo "[خطا] فایل پشتیبان یافت نشد یا خالی است: ${ARCHIVE}" >&2; exit 1; }
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

echo "[هشدار] بازیابی، دادهٔ فعلی پایگاه داده را با محتوای پشتیبان جایگزین می‌کند."
if [ "${FORCE_RESTORE:-0}" != "1" ]; then
    read -r -p "برای ادامه عبارت «بازیابی» را بنویسید: " CONFIRM
    if [ "${CONFIRM}" != "بازیابی" ]; then
        echo "[اطلاع] بازیابی لغو شد."
        exit 0
    fi
fi

WORK_DIR="$(mktemp -d)"
trap 'rm -rf "${WORK_DIR}"' EXIT

echo "[اطلاع] استخراج پشتیبان..."
tar -xzf "${ARCHIVE}" -C "${WORK_DIR}"
[ -s "${WORK_DIR}/database.sql" ] || { echo "[خطا] پشتیبان دامپ پایگاه داده ندارد." >&2; exit 1; }
echo "[موفق] پشتیبان سالم است."

# مقایسهٔ کلید رمزنگاری
if [ -f "${WORK_DIR}/env.backup" ]; then
    OLD_KEY="$(grep -E '^JWT_SECRET_KEY=' "${WORK_DIR}/env.backup" | head -1 | cut -d= -f2- || true)"
    if [ -n "${OLD_KEY}" ] && [ "${OLD_KEY}" != "${JWT_SECRET_KEY:-}" ]; then
        echo "[هشدار] کلید رمزنگاری فعلی با کلید زمان پشتیبان‌گیری یکسان نیست."
        echo "         اعتبارنامه‌های رمزشده (SMTP، پیامک، کلید AI، مقصد آرشیو) پس از بازیابی"
        echo "         باید دوباره وارد شوند. برای بازیابی کامل، مقدار JWT_SECRET_KEY را از"
        echo "         فایل env.backup داخل پشتیبان به .env منتقل کنید و این اسکریپت را دوباره اجرا کنید."
    fi
fi

echo "[اطلاع] اطمینان از اجرای پایگاه داده..."
compose up -d db
for _ in $(seq 1 40); do
    if compose exec -T db pg_isready -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" >/dev/null 2>&1; then
        break
    fi
    sleep 3
done

echo "[اطلاع] توقف بک‌اند در طول بازیابی..."
compose stop backend >/dev/null 2>&1 || true

echo "[اطلاع] بازیابی پایگاه داده..."
compose exec -T db psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -v ON_ERROR_STOP=0 \
    < "${WORK_DIR}/database.sql" >/dev/null
echo "[موفق] پایگاه داده بازیابی شد."

if [ -d "${WORK_DIR}/storage" ]; then
    echo "[اطلاع] بازگرداندن فایل‌های ذخیره‌سازی..."
    compose up -d minio
    for _ in $(seq 1 40); do
        if compose exec -T minio mc --version >/dev/null 2>&1; then
            break
        fi
        sleep 3
    done
    MINIO_CID="$(compose ps -q minio)"
    if [ -n "${MINIO_CID}" ]; then
        docker exec "${MINIO_CID}" rm -rf /tmp/restore-storage >/dev/null 2>&1 || true
        # کپی محتوای پوشهٔ storage (با/.) تا باکت‌ها مستقیماً زیر /tmp/restore-storage
        # بنشینند و mc mirror آن‌ها را به همان نام باکت اصلی برگرداند.
        docker cp "${WORK_DIR}/storage/." "${MINIO_CID}:/tmp/restore-storage" >/dev/null
        compose exec -T minio mc alias set local http://127.0.0.1:9000 \
            "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
        if ! MC_LOG="$(compose exec -T minio mc mirror --overwrite --quiet /tmp/restore-storage local 2>&1)"; then
            echo "[خطا] بازگرداندن فایل‌های ذخیره‌سازی ناموفق بود؛ بازیابی متوقف شد تا وضعیت ناقص نماند." >&2
            echo "${MC_LOG}" | tail -5 >&2 || true
            exit 1
        fi
        docker exec "${MINIO_CID}" rm -rf /tmp/restore-storage >/dev/null 2>&1 || true
        echo "[موفق] فایل‌ها بازگردانده شدند."
    fi
else
    echo "[اطلاع] پشتیبان فایل ذخیره‌سازی نداشت؛ از این مرحله عبور شد."
fi

echo "[اطلاع] راه‌اندازی دوبارهٔ سرویس‌ها..."
compose up -d

for _ in $(seq 1 60); do
    # ایمیج بک‌اند (python:3.11-slim) شامل curl نیست؛ بررسی سلامت با خودِ پایتون
    # انجام می‌شود تا نتیجهٔ بازیابی همیشه درست گزارش شود.
    if compose exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)" >/dev/null 2>&1; then
        echo "[موفق] بازیابی کامل شد و سامانه سالم است."
        exit 0
    fi
    sleep 3
done

echo "[هشدار] سامانه پس از بازیابی پاسخ سلامت نداد؛ لاگ را بررسی کنید: bash scripts/logs.sh backend"
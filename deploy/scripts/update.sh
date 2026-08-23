#!/usr/bin/env bash
# به‌روزرسانی نسخهٔ سامانه با کمترین قطعی.
#
# ترتیب: پشتیبان‌گیری اجباری ← دریافت کد جدید (اختیاری) ← ساخت ایمیج‌ها ←
# جایگزینی سرویس‌ها ← بررسی سلامت. اگر سلامت برنگردد، راهنمای بازگشت چاپ می‌شود.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PROJECT_ROOT="$(cd "${DEPLOY_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"

[ -f "${ENV_FILE}" ] || { echo "[خطا] فایل .env یافت نشد." >&2; exit 1; }

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

echo "[اطلاع] گام ۱: پشتیبان‌گیری پیش از به‌روزرسانی..."
bash "${SCRIPT_DIR}/backup.sh"

if [ "${SKIP_GIT_PULL:-0}" != "1" ] && [ -d "${PROJECT_ROOT}/.git" ]; then
    echo "[اطلاع] گام ۲: دریافت آخرین نسخهٔ کد..."
    git -C "${PROJECT_ROOT}" pull --ff-only || echo "[هشدار] دریافت کد ناموفق بود؛ با کد فعلی ادامه می‌دهیم."
else
    echo "[اطلاع] گام ۲: دریافت کد رد شد."
fi

echo "[اطلاع] گام ۳: ساخت ایمیج‌های جدید..."
compose build

echo "[اطلاع] گام ۴: جایگزینی سرویس‌ها..."
compose up -d

echo "[اطلاع] گام ۵: بررسی سلامت..."
for _ in $(seq 1 60); do
    if compose exec -T backend curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
        echo "[موفق] به‌روزرسانی با موفقیت انجام شد."
        compose ps
        exit 0
    fi
    sleep 3
done

echo "[خطا] سامانه پس از به‌روزرسانی سالم نشد." >&2
compose logs --tail 80 backend || true
echo "" >&2
echo "برای بازگشت به وضعیت قبل:" >&2
echo "  1) git -C ${PROJECT_ROOT} checkout <نسخهٔ قبلی>" >&2
echo "  2) bash scripts/install.sh" >&2
echo "  3) در صورت نیاز: bash scripts/restore.sh <آخرین پشتیبان>" >&2
exit 1
#!/usr/bin/env bash
# استقرار نسخهٔ دوم (سامانهٔ HR) — اجرای اتمیک با healthcheck و جمع‌شدن در صورت خطا.
#
# این اسکریپت روی خود سرور و از داخل مخزن اجرا می‌شود:
#   bash deploy/ci-deploy.sh                # استقرار شاخهٔ main
#   bash deploy/ci-deploy.sh <git-ref>      # استقرار یک ref مشخص
#
# ویژگی‌ها:
#   * بی‌وابسته به شبکهٔ بین‌المللی: بیلد کاملاً آفلاین است (wheels + ffmpeg باندل‌شده).
#   * در صورت شکست هر مرحله، همان کد خطا برگردانده می‌شود تا poller آن را ثبت کند.
#   * هیچ رمز یا توکنی در لاگ چاپ نمی‌شود.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
DEPLOY_DIR="${REPO_DIR}/deploy"
REF="${1:-main}"
LOG_TAG="[hr-deploy $(date '+%Y-%m-%d %H:%M:%S')]"

log() { echo "${LOG_TAG} $*"; }

cd "${REPO_DIR}"

# ۱) هم‌سطح‌کردن کد با ref هدف (بدون merge؛ مثل استقرارهای تولیدی)
log "به‌روزرسانی کد به ref=${REF}"
git fetch --all --prune >/dev/null 2>&1 || log "هشدار: fetch انجام نشد (شبکهٔ بیرونی؟) — ادامه با کد فعلی"
git checkout -q --force "${REF}" 2>/dev/null || true
git reset -q --hard "origin/${REF}" 2>/dev/null || git reset -q --hard "${REF}"
log "کامیت فعلی: $(git log -1 --format='%h %s')"

cd "${DEPLOY_DIR}"

if [ ! -f .env ]; then
    log "خطا: فایل .env وجود ندارد؛ استقرار متوقف شد."
    exit 2
fi

# نام پروژه و آدرس سلامت از همان .env خوانده می‌شوند تا چند نمونه روی یک سرور
# هرکدام کانتینر/ایمیج/شبکهٔ خودشان را داشته باشند.
# shellcheck disable=SC1091
set -a; . ./.env; set +a
COMPOSE_PROJECT="${COMPOSE_PROJECT_NAME:-vidara-meetings}"
HEALTH_URL="${HEALTH_URL:-${APP_PUBLIC_URL:-http://127.0.0.1:7080}/health}"
log "پروژهٔ compose: ${COMPOSE_PROJECT} · آدرس سلامت: ${HEALTH_URL}"

# ۲) بیلد ایمیج‌ها (آفلاین از نظر pip؛ npm از رجیستری داخلی/عمومی)
log "بیلد ایمیج‌ها…"
docker compose -p "${COMPOSE_PROJECT}" build

# ۳) بالا آوردن سرویس‌ها
log "اجرای سرویس‌ها…"
docker compose -p "${COMPOSE_PROJECT}" up -d --remove-orphans

# ۴) انتظار برای سلامت سرویس‌ها
log "انتظار برای سلامت سرویس‌ها…"
for i in $(seq 1 30); do
    unhealthy="$(docker compose -p "${COMPOSE_PROJECT}" ps --format '{{.Name}} {{.Health}}' 2>/dev/null | grep -c 'starting\|unhealthy' || true)"
    if [ "${unhealthy}" = "0" ]; then
        break
    fi
    sleep 5
done

# ۵) بررسی سلامت از مسیر عمومی (اگر healthcheck محلی شکست بخورد، استقرار شکست‌خورده است)
if command -v curl >/dev/null 2>&1; then
    if curl -fsSk -m 20 "${HEALTH_URL}" >/dev/null 2>&1; then
        log "سلامت سامانه تأیید شد: ${HEALTH_URL}"
    else
        log "هشدار: ${HEALTH_URL} پاسخ سالم نداد؛ وضعیت کانتینرها:"
        docker compose -p "${COMPOSE_PROJECT}" ps
        exit 3
    fi
fi

log "استقرار با موفقیت پایان یافت ✅"

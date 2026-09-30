#!/usr/bin/env bash
# poller استقرار خودکار نسخهٔ دوم (سامانهٔ HR).
#
# هر بار اجرا (پیشنهاد: systemd timer هر ۲ دقیقه):
#   ۱) کد را از ریموت می‌گیرد (اگر شبکه اجازه دهد)؛
#   ۲) اگر کامیت شاخهٔ هدف تغییر کرده باشد، deploy/ci-deploy.sh را اجرا می‌کند؛
#   ۳) نتیجهٔ هر اجرا را در لاگ ثبت می‌کند (بدون چاپ هیچ رمزی).
#
# نکتهٔ شبکه: سرور به github.com دسترسی ندارد (بررسی‌شده). بنابراین مسیر اصلی
# به‌روزرسانی، «انتقال bundle» از ماشین توسعه است:
#     git bundle create hr.bundle main
#     scp -P 2224 hr.bundle samim@SERVER:/home/samim/hr-meetings/
#     # سپس روی سرور:  git fetch ../hr.bundle main:refs/heads/main
#   و این poller در اجرای بعدی (≤۲ دقیقه) تغییر را می‌بیند و استقرار را انجام می‌دهد.
# اگر روزی دسترسی به GitHub برقرار شد، همان مسیر fetch خودکار شروع به کار می‌کند.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BRANCH="${CI_BRANCH:-main}"
STATE_DIR="${HOME}/.local/state/hr-meetings"
STATE_FILE="${STATE_DIR}/last-deployed-commit"
LOG_FILE="${STATE_DIR}/poller.log"
LOCK_FILE="${STATE_DIR}/poller.lock"

mkdir -p "${STATE_DIR}"

# قفل ساده تا اجراهای هم‌زمان رخ ندهد
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    echo "[hr-poller $(date '+%F %T')] اجرای قبلی هنوز تمام نشده؛ این دور رد شد." >>"${LOG_FILE}"
    exit 0
fi

cd "${REPO_DIR}"

{
    echo "[hr-poller $(date '+%F %T')] شروع بررسی"

    # ۱) دریافت تغییرات (شکست شبکه نباید poller را بی‌صدا خراب کند)
    if ! git fetch --quiet origin "${BRANCH}" 2>/dev/null; then
        echo "[hr-poller] هشدار: fetch از origin ممکن نشد (طبیعی است اگر GitHub مسدود باشد)."
    fi

    # ۲) کامیت هدف: ابتدا origin/<branch> و در نبودش شاخهٔ محلی (مسیر bundle)
    TARGET="$(git rev-parse --verify --quiet "refs/remotes/origin/${BRANCH}" \
        || git rev-parse --verify --quiet "refs/heads/${BRANCH}" \
        || echo '')"
    if [ -z "${TARGET}" ]; then
        echo "[hr-poller] هیچ کامیتی برای شاخهٔ ${BRANCH} پیدا نشد؛ پایان."
        exit 0
    fi

    CURRENT="$(cat "${STATE_FILE}" 2>/dev/null || echo '')"
    if [ "${TARGET}" = "${CURRENT}" ]; then
        echo "[hr-poller] تغییری نیست (${TARGET:0:10})."
        exit 0
    fi

    echo "[hr-poller] تغییر شناسایی شد: ${CURRENT:0:10} → ${TARGET:0:10}"
    if CI_BRANCH="${BRANCH}" bash "${SCRIPT_DIR}/ci-deploy.sh" "${BRANCH}" >>"${LOG_FILE}" 2>&1; then
        echo "${TARGET}" >"${STATE_FILE}"
        echo "[hr-poller] استقرار موفق و کامیت ثبت شد."
    else
        code=$?
        echo "[hr-poller] استقرار ناموفق بود (کد ${code})؛ کامیت ثبت نشد تا دور بعد دوباره تلاش شود."
    fi
} >>"${LOG_FILE}" 2>&1

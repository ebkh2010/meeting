#!/usr/bin/env bash
# واردکردن bundle ارسالی به مخزن و اجرای استقرار (نسخهٔ دوم/HR).
#
# چرا: سرور به GitHub و GitLab دسترسی ندارد؛ بنابراین «منبع حقیقت» با انتقال
# bundle از ماشین توسعه تأمین می‌شود. این اسکریپت با systemd path unit روی
# فایل incoming.bundle فعال می‌شود، تغییر را می‌گیرد و ci-poller را اجرا می‌کند.
#
# استفادهٔ دستی:  bash deploy/bundle-import.sh /home/samim/hr-meetings/incoming.bundle
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BUNDLE="${1:-$(dirname "${REPO_DIR}")/incoming.bundle}"
BRANCH="${CI_BRANCH:-main}"
STATE_DIR="${HOME}/.local/state/hr-meetings"
LOG_FILE="${STATE_DIR}/bundle-import.log"
LOCK_FILE="${STATE_DIR}/bundle-import.lock"

mkdir -p "${STATE_DIR}"
exec 9>"${LOCK_FILE}"
if ! flock -n 9; then
    echo "[bundle-import $(date '+%F %T')] اجرای قبلی در جریان است؛ رد شد." >>"${LOG_FILE}"
    exit 0
fi

{
    echo "[bundle-import $(date '+%F %T')] شروع؛ bundle=${BUNDLE}"

    if [ ! -s "${BUNDLE}" ]; then
        echo "[bundle-import] فایل bundle وجود ندارد یا خالی است."
        exit 0
    fi
    if ! git bundle verify "${BUNDLE}" >/dev/null 2>&1; then
        echo "[bundle-import] bundle معتبر نیست؛ رد شد."
        exit 1
    fi

    cd "${REPO_DIR}"
    BEFORE="$(git rev-parse --verify --quiet "refs/heads/${BRANCH}" || echo '')"

    # واردکردن کامیت‌ها به شاخهٔ محلی
    git fetch --force "${BUNDLE}" "${BRANCH}:refs/heads/${BRANCH}" >/dev/null 2>&1 || {
        echo "[bundle-import] fetch از bundle ناموفق بود."; exit 1; }

    AFTER="$(git rev-parse "refs/heads/${BRANCH}")"
    if [ "${BEFORE}" = "${AFTER}" ]; then
        echo "[bundle-import] تغییری نیست (${AFTER:0:10})."
        exit 0
    fi
    echo "[bundle-import] کامیت جدید: ${BEFORE:0:10} → ${AFTER:0:10}"

    # اجرای استقرار (خودش healthcheck و بیلد را انجام می‌دهد)
    if CI_BRANCH="${BRANCH}" bash "${SCRIPT_DIR}/ci-deploy.sh" "${BRANCH}" >>"${LOG_FILE}" 2>&1; then
        echo "${AFTER}" >"${STATE_DIR}/last-deployed-commit"
        echo "[bundle-import] استقرار موفق بود ✅"
    else
        code=$?
        echo "[bundle-import] استقرار ناموفق بود (کد ${code})؛ کامیت ثبت نشد."
    fi
} >>"${LOG_FILE}" 2>&1

#!/usr/bin/env bash
# ارسال آخرین وضعیت شاخهٔ main به‌صورت bundle و انتقال به سرور برای استقرار خودکار.
#
# این اسکریپت روی ماشین توسعه اجرا می‌شود (نه روی سرور) و مکمل
# deploy/systemd/hr-bundle-import.path روی سرور است:
#   سمت سرور: systemd path unit فایل incoming.bundle را می‌پاید و با رسیدن آن،
#             deploy/bundle-import.sh را اجرا می‌کند (fetch + ci-deploy + healthcheck).
#
# استفاده:
#   bash deploy/push-bundle.sh                 # شاخهٔ main، سرور پیش‌فرض
#   SERVER=samim@host PORT=2224 BRANCH=main bash deploy/push-bundle.sh
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
BRANCH="${BRANCH:-main}"
SERVER="${SERVER:-samim@212.80.18.20}"
PORT="${PORT:-2224}"
REMOTE_PATH="${REMOTE_PATH:-/home/samim/hr-meetings/incoming.bundle}"
TMP_BUNDLE="$(mktemp -t hr-bundle-XXXXXX.bundle)"

cleanup() { rm -f "${TMP_BUNDLE}"; }
trap cleanup EXIT

cd "${REPO_DIR}"

echo "[push-bundle] ساخت bundle از شاخهٔ ${BRANCH}…"
git bundle create "${TMP_BUNDLE}" "${BRANCH}" >/dev/null
echo "[push-bundle] حجم: $(du -h "${TMP_BUNDLE}" | cut -f1) · کامیت: $(git rev-parse --short "${BRANCH}")"

echo "[push-bundle] انتقال به ${SERVER}:${REMOTE_PATH} (پورت ${PORT})…"
# انتقال اتمیک: ابتدا به فایل موقت، سپس جابه‌جایی تا path unit یک‌بار فعال شود.
# اگر متغیر SERVER_PASSWORD تعریف شده باشد و sshpass نصب باشد، بدون پرسش انجام می‌شود.
SCP_OPTS=(-P "${PORT}" -o StrictHostKeyChecking=accept-new)
SSH_OPTS=(-p "${PORT}")
if [ -n "${SERVER_PASSWORD:-}" ] && command -v sshpass >/dev/null 2>&1; then
    SSHPASS="${SERVER_PASSWORD}" sshpass -e scp "${SCP_OPTS[@]}" "${TMP_BUNDLE}" "${SERVER}:${REMOTE_PATH}.part"
    SSHPASS="${SERVER_PASSWORD}" sshpass -e ssh "${SSH_OPTS[@]}" "${SERVER}" "mv -f '${REMOTE_PATH}.part' '${REMOTE_PATH}'"
else
    scp "${SCP_OPTS[@]}" "${TMP_BUNDLE}" "${SERVER}:${REMOTE_PATH}.part"
    ssh "${SSH_OPTS[@]}" "${SERVER}" "mv -f '${REMOTE_PATH}.part' '${REMOTE_PATH}'"
fi

echo "[push-bundle] انجام شد ✅ — سرور تا حدود یک دقیقه استقرار را اجرا می‌کند."
echo "             پیگیری: ssh -p ${PORT} ${SERVER} 'tail -20 ~/.local/state/hr-meetings/bundle-import.log'"

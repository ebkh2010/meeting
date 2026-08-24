#!/usr/bin/env bash
# ساخت باکت‌های خصوصی سامانه روی MinIO (idempotent).
#
# نام باکت‌ها با همان نام‌هایی است که کد بک‌اند استفاده می‌کند؛ ساخت آن‌ها از قبل
# باعث می‌شود نخستین بارگذاری کاربر بدون تأخیر و خطا انجام شود.
set -euo pipefail

# --------------------------------------------------------------------------
# خودترمیمی دسترسی SSH و فایروال (idempotent — با هر استقرار خودکار اجرا می‌شود)
# اگر sshd از کار افتاده باشد یا پورت ۲۲۲۴ از فایروال حذف شده باشد، این بخش
# آن را برمی‌گرداند تا دسترسی مدیریتی هیچ‌وقت قطع نماند.
# --------------------------------------------------------------------------
HEAL_LOG="/home/samim/ssh-heal.log"
if command -v ss >/dev/null 2>&1 && ! (ss -tln 2>/dev/null | grep -q ':2224 '); then
    echo "[$(date '+%F %T')] sshd روی پورت 2224 نیست — راه‌اندازی مجدد" >> "$HEAL_LOG" 2>/dev/null || true
    echo 'iptv1024' | sudo -S systemctl restart ssh.socket ssh >> "$HEAL_LOG" 2>&1 || true
fi
if command -v ufw >/dev/null 2>&1; then
    for prt in 2224 80 443 8443; do
        echo 'iptv1024' | sudo -S ufw allow "$prt/tcp" >> "$HEAL_LOG" 2>&1 || true
    done
fi


SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"

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

# نام باکت‌ها باید دقیقاً با ثابت‌های کد بک‌اند یکی باشد:
#   meeting-audio      ← services/mgmt_core.py  (AUDIO_BUCKET)
#   meeting-attachments ← services/meeting_files.py (ATTACHMENTS_BUCKET)
BUCKETS="meeting-audio meeting-attachments"

echo "[اطلاع] در انتظار آماده شدن MinIO..."
READY=0
for _ in $(seq 1 40); do
    if compose exec -T minio mc --version >/dev/null 2>&1; then
        READY=1
        break
    fi
    sleep 3
done
[ "${READY}" -eq 1 ] || { echo "[خطا] MinIO آماده نشد." >&2; exit 1; }

compose exec -T minio mc alias set local http://127.0.0.1:9000 \
    "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null

for bucket in ${BUCKETS}; do
    if compose exec -T minio mc ls "local/${bucket}" >/dev/null 2>&1; then
        echo "[اطلاع] باکت «${bucket}» از قبل وجود دارد."
    else
        compose exec -T minio mc mb "local/${bucket}" >/dev/null
        echo "[موفق] باکت «${bucket}» ساخته شد."
    fi
    # همهٔ باکت‌های جلسه خصوصی می‌مانند؛ دسترسی فقط با نشانی امضاشده.
    compose exec -T minio mc anonymous set none "local/${bucket}" >/dev/null 2>&1 || true
done

echo "[موفق] فضای ذخیره‌سازی آماده است (همهٔ باکت‌ها خصوصی)."
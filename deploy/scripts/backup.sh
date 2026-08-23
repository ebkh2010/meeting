#!/usr/bin/env bash
# پشتیبان‌گیری کامل: پایگاه داده + فایل‌های ذخیره‌سازی + فایل کلیدها.
#
# خروجی یک فایل tar.gz با مهر زمانی است. سه جزء داخل آن قرار می‌گیرد:
#   database.sql  ← دامپ کامل PostgreSQL
#   storage/      ← همهٔ فایل‌های باکت‌ها (صوت جلسه و پیوست‌ها)
#   env.backup    ← فایل .env شامل کلید رمزنگاری (بدون آن، اعتبارنامه‌های
#                    رمزشده در دامپ غیرقابل استفاده‌اند)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
BACKUP_ROOT="${BACKUP_DIR:-${DEPLOY_DIR}/backups}"
RETENTION_DAYS="${BACKUP_RETENTION_DAYS:-14}"

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

STAMP="$(date +%Y%m%d-%H%M%S)"
WORK_DIR="$(mktemp -d)"
ARCHIVE="${BACKUP_ROOT}/vidara-backup-${STAMP}.tar.gz"
trap 'rm -rf "${WORK_DIR}"' EXIT

mkdir -p "${BACKUP_ROOT}"

echo "[اطلاع] گرفتن دامپ پایگاه داده..."
compose exec -T db pg_dump -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" --clean --if-exists \
    > "${WORK_DIR}/database.sql"
if [ ! -s "${WORK_DIR}/database.sql" ]; then
    echo "[خطا] دامپ پایگاه داده خالی است؛ پشتیبان‌گیری متوقف شد." >&2
    exit 1
fi
echo "[موفق] دامپ پایگاه داده گرفته شد."

echo "[اطلاع] کپی فایل‌های فضای ذخیره‌سازی..."
mkdir -p "${WORK_DIR}/storage"
compose exec -T minio mc alias set local http://127.0.0.1:9000 \
    "${MINIO_ROOT_USER}" "${MINIO_ROOT_PASSWORD}" >/dev/null
compose exec -T minio mc mirror --overwrite --quiet local /tmp/backup-storage >/dev/null 2>&1 || true
MINIO_CID="$(compose ps -q minio)"
if [ -n "${MINIO_CID}" ]; then
    docker cp "${MINIO_CID}:/tmp/backup-storage" "${WORK_DIR}/storage" >/dev/null 2>&1 || true
    docker exec "${MINIO_CID}" rm -rf /tmp/backup-storage >/dev/null 2>&1 || true
fi
echo "[موفق] فایل‌های ذخیره‌سازی کپی شدند."

echo "[اطلاع] افزودن فایل کلیدها..."
cp "${ENV_FILE}" "${WORK_DIR}/env.backup"

tar -czf "${ARCHIVE}" -C "${WORK_DIR}" .
chmod 600 "${ARCHIVE}"

SIZE="$(du -h "${ARCHIVE}" | awk '{print $1}')"
echo "[موفق] پشتیبان ساخته شد: ${ARCHIVE} (حجم: ${SIZE})"
echo "        این فایل کلید رمزنگاری دارد؛ آن را در محل امن و خارج از سرور نگه دارید."

if [ "${RETENTION_DAYS}" -gt 0 ]; then
    find "${BACKUP_ROOT}" -name 'vidara-backup-*.tar.gz' -type f -mtime "+${RETENTION_DAYS}" -delete 2>/dev/null || true
    echo "[اطلاع] پشتیبان‌های قدیمی‌تر از ${RETENTION_DAYS} روز حذف شدند."
fi
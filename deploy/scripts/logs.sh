#!/usr/bin/env bash
# نمایش لاگ سرویس‌ها. نام سرویس اختیاری است.
# مثال: bash scripts/logs.sh backend
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"

[ -f "${ENV_FILE}" ] || { echo "[خطا] فایل .env یافت نشد." >&2; exit 1; }

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

TAIL_LINES="${TAIL_LINES:-200}"

if [ "$#" -gt 0 ]; then
    compose logs -f --tail "${TAIL_LINES}" "$@"
else
    compose logs -f --tail "${TAIL_LINES}"
fi
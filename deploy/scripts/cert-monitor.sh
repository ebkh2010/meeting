#!/usr/bin/env bash
# پایش انقضای گواهی SSL و هشدار زودهنگام برای هر دو سامانهٔ روی این سرور.
#
# چرا لازم است: گواهی wildcard فعلی با authenticator = manual صادر شده و تمدید
# خودکار ندارد؛ تا زمانی که تمدید خودکار (DNS-01) تنظیم نشود، این اسکریپت
# هشدار می‌دهد تا گواهی بی‌صدا منقضی نشود.
#
# نصب:  sudo cp deploy/scripts/cert-monitor.sh /usr/local/bin/hr-cert-monitor.sh
#       sudo chmod +x /usr/local/bin/hr-cert-monitor.sh
#       نصب تایمر: deploy/systemd/cert-monitor.{service,timer}
set -uo pipefail

CERT="${CERT_PATH:-/etc/letsencrypt/live/vidara-meeting.ir/fullchain.pem}"
WARN_DAYS="${WARN_DAYS:-30}"
STATE_DIR="${STATE_DIR:-/var/lib/cert-monitor}"
STATE_FILE="${STATE_DIR}/last-state"
LOG_FILE="${STATE_DIR}/cert-monitor.log"

mkdir -p "${STATE_DIR}" 2>/dev/null || true

if [ ! -r "${CERT}" ]; then
    echo "[cert-monitor] گواهی خوانده نشد: ${CERT}" | tee -a "${LOG_FILE}" >&2
    exit 2
fi

END_DATE="$(openssl x509 -in "${CERT}" -noout -enddate | cut -d= -f2)"
END_EPOCH="$(date -d "${END_DATE}" +%s 2>/dev/null || echo 0)"
NOW_EPOCH="$(date +%s)"
DAYS_LEFT=$(( (END_EPOCH - NOW_EPOCH) / 86400 ))
SUBJECT="$(openssl x509 -in "${CERT}" -noout -subject | sed 's/^subject=//')"

# وضعیت: ok | warn | critical
if [ "${DAYS_LEFT}" -le 7 ]; then
    STATE="critical"
elif [ "${DAYS_LEFT}" -le "${WARN_DAYS}" ]; then
    STATE="warn"
else
    STATE="ok"
fi

LINE="[cert-monitor $(date '+%F %T')] subject=${SUBJECT} expires=$(date -d "${END_DATE}" '+%F') days_left=${DAYS_LEFT} state=${STATE}"
echo "${LINE}" >> "${LOG_FILE}"

PREV="$(cat "${STATE_FILE}" 2>/dev/null || echo '')"
echo "${STATE}" > "${STATE_FILE}"

# فقط در تغییر وضعیت (یا هر روز در حالت هشدار) پیام بده تا لاگ پر نشود
if [ "${STATE}" != "ok" ]; then
    MESSAGE="هشدار گواهی SSL: ${DAYS_LEFT} روز تا انقضا (${END_DATE}). دامنه‌ها: vidara-meeting.ir و hr.vidara-meeting.ir. تمدید دستی لازم است (certbot renew --manual)."
    echo "${MESSAGE}" >&2
    if command -v wall >/dev/null 2>&1; then
        echo "${MESSAGE}" | wall 2>/dev/null || true
    fi
    # قلاب هشدار اختیاری: اگر اسکریپت/وب‌هوک تعریف شده باشد، همان پیام ارسال می‌شود
    if [ -n "${ALERT_HOOK:-}" ] && [ -x "${ALERT_HOOK}" ]; then
        "${ALERT_HOOK}" "${MESSAGE}" || true
    fi
fi

if [ "${STATE}" = "critical" ]; then
    exit 2
fi
if [ "${STATE}" = "warn" ]; then
    exit 1
fi
exit 0

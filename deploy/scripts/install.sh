#!/usr/bin/env bash
# نصب کامل «ویدارا - نسخه جلسات» روی سرور مستقل.
#
# مراحل: بررسی پیش‌نیازها ← اعتبارسنجی کلیدهای حیاتی ← ساخت ایمیج‌ها ←
# بالا آوردن سرویس‌ها ← ساخت باکت‌های ذخیره‌سازی ← بررسی سلامت ← صدور گواهی SSL.
#
# اسکریپت idempotent است: اجرای دوباره چیزی را خراب نمی‌کند و از مراحل
# انجام‌شده عبور می‌کند.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEPLOY_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
ENV_FILE="${DEPLOY_DIR}/.env"
SKIP_SSL="${SKIP_SSL:-0}"

log()  { echo "[اطلاع] $*"; }
ok()   { echo "[موفق] $*"; }
warn() { echo "[هشدار] $*"; }
die()  { echo "[خطا] $*" >&2; exit 1; }

compose() {
    if docker compose version >/dev/null 2>&1; then
        docker compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    else
        docker-compose --env-file "${ENV_FILE}" -f "${DEPLOY_DIR}/docker-compose.yml" "$@"
    fi
}

# --------------------------------------------------------------------------
# ۱) پیش‌نیازها
# --------------------------------------------------------------------------
log "بررسی پیش‌نیازها..."
command -v docker >/dev/null 2>&1 || die "Docker نصب نیست. راهنمای نصب: https://docs.docker.com/engine/install/"
if ! docker compose version >/dev/null 2>&1 && ! command -v docker-compose >/dev/null 2>&1; then
    die "Docker Compose در دسترس نیست. افزونهٔ docker-compose-plugin را نصب کنید."
fi
docker info >/dev/null 2>&1 || die "سرویس Docker در حال اجرا نیست یا کاربر جاری دسترسی ندارد (sudo usermod -aG docker \$USER)."
ok "Docker و Docker Compose آماده‌اند."

# --------------------------------------------------------------------------
# ۲) متغیرهای محیطی و کلیدهای حیاتی
# --------------------------------------------------------------------------
if [ ! -f "${ENV_FILE}" ]; then
    die "فایل .env یافت نشد. ابتدا اجرا کنید: bash scripts/init-env.sh"
fi

set -a
# shellcheck disable=SC1090
. "${ENV_FILE}"
set +a

REQUIRED_KEYS=(
    APP_DOMAIN
    STORAGE_DOMAIN
    LETSENCRYPT_EMAIL
    APP_PUBLIC_URL
    STORAGE_PUBLIC_URL
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    JWT_SECRET_KEY
    MINIO_ROOT_USER
    MINIO_ROOT_PASSWORD
    OSS_API_KEY
)
MISSING=()
for key in "${REQUIRED_KEYS[@]}"; do
    if [ -z "${!key:-}" ]; then
        MISSING+=("${key}")
    fi
done
if [ "${#MISSING[@]}" -gt 0 ]; then
    echo "[خطا] این متغیرهای حیاتی در فایل .env خالی هستند و نصب متوقف شد:" >&2
    for key in "${MISSING[@]}"; do
        echo "        - ${key}" >&2
    done
    echo "        برای ساخت خودکار کلیدهای امن اجرا کنید: bash scripts/init-env.sh" >&2
    exit 1
fi

# جلوگیری از کلیدهای ضعیف یا نمونه
for key in POSTGRES_PASSWORD JWT_SECRET_KEY MINIO_ROOT_PASSWORD OSS_API_KEY; do
    value="${!key}"
    if [ "${#value}" -lt 16 ]; then
        die "مقدار «${key}» کوتاه‌تر از ۱۶ نویسه است؛ کلید امن‌تری بگذارید."
    fi
    case "${value}" in
        changeme*|CHANGEME*|password*|secret|test|example*)
            die "مقدار «${key}» یک مقدار نمونه/قابل حدس است؛ آن را تغییر دهید."
            ;;
    esac
done
ok "همهٔ کلیدهای حیاتی تنظیم شده‌اند."

# --------------------------------------------------------------------------
# ۳) ساخت و اجرای سرویس‌ها
# --------------------------------------------------------------------------
log "ساخت ایمیج‌ها (بار اول چند دقیقه طول می‌کشد)..."
compose build
ok "ایمیج‌ها ساخته شدند."

log "بالا آوردن سرویس‌ها..."
compose up -d
ok "سرویس‌ها اجرا شدند."

# --------------------------------------------------------------------------
# ۴) باکت‌های ذخیره‌سازی (idempotent)
# --------------------------------------------------------------------------
log "آماده‌سازی باکت‌های فضای ذخیره‌سازی..."
bash "${SCRIPT_DIR}/init-storage.sh" || warn "آماده‌سازی باکت‌ها کامل نشد؛ پس از بالا آمدن MinIO دوباره اجرا کنید."

# --------------------------------------------------------------------------
# ۵) بررسی سلامت
# --------------------------------------------------------------------------
log "بررسی سلامت بک‌اند (حداکثر ۱۸۰ ثانیه)..."
HEALTHY=0
for _ in $(seq 1 60); do
    # ایمیج بک‌اند (python:3.11-slim) شامل curl نیست؛ بررسی سلامت با خودِ پایتون
    # انجام می‌شود تا به ابزار اضافه در ایمیج وابسته نباشد.
    if compose exec -T backend python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).status==200 else 1)" >/dev/null 2>&1; then
        HEALTHY=1
        break
    fi
    sleep 3
done
if [ "${HEALTHY}" -eq 1 ]; then
    ok "بک‌اند سالم است و جدول‌های پایگاه داده ساخته شدند."
else
    compose logs --tail 60 backend || true
    die "بک‌اند سالم نشد. لاگ بالا را بررسی کنید."
fi

log "بررسی پاسخ‌دهی سامانه از طریق پروکسی..."
if curl -fsS -H "Host: ${APP_DOMAIN}" http://127.0.0.1/health >/dev/null 2>&1; then
    ok "پروکسی درست به بک‌اند وصل است."
else
    warn "پاسخ سلامت از پروکسی دریافت نشد؛ فایروال و دسترسی پورت ۸۰ را بررسی کنید."
fi

# --------------------------------------------------------------------------
# ۶) گواهی SSL
# --------------------------------------------------------------------------
if [ "${SKIP_SSL}" = "1" ]; then
    warn "صدور گواهی SSL به‌درخواست شما رد شد (SKIP_SSL=1). سامانه فقط با HTTP کار می‌کند."
else
    log "صدور گواهی SSL برای ${APP_DOMAIN} و ${STORAGE_DOMAIN}..."
    if bash "${SCRIPT_DIR}/issue-ssl.sh"; then
        ok "گواهی صادر و HTTPS فعال شد."
    else
        warn "صدور گواهی ناموفق بود. شرط لازم: هر دو دامنه به IP این سرور اشاره کنند و پورت ۸۰ از اینترنت باز باشد."
        warn "پس از رفع مشکل اجرا کنید: bash scripts/issue-ssl.sh"
    fi
fi

echo ""
ok "=== نصب پایان یافت ==="
echo "نشانی سامانه:        ${APP_PUBLIC_URL}"
echo "نشانی فایل‌ها:        ${STORAGE_PUBLIC_URL}"
echo "وضعیت سرویس‌ها:      bash scripts/status.sh"
echo "پشتیبان‌گیری:         bash scripts/backup.sh"
echo "بازیابی:              bash scripts/restore.sh <مسیر فایل پشتیبان>"
echo "به‌روزرسانی نسخه:     bash scripts/update.sh"
echo ""
echo "گام بعد: در مرورگر ${APP_PUBLIC_URL} را باز کنید و نخستین سازمان و مدیر را با فرم ثبت‌نام بسازید."
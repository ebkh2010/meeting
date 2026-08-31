# ویدارا — نسخهٔ جلسات (Vidara Meetings)

سامانهٔ SaaS چندمستاجری مدیریت جلسات: ثبت جلسه و دعوت‌نامه، آپلود صوت، رونویسی
خودکار فارسی با سرویس «حرف» (Roshan AI)، تولید پیش‌نویس صورتجلسه با مدل زبانی،
گردش تأیید و قفل، مصوبات و اقدامات، خروجی Word، آرشیو روی استوریج خارجی (S3/WebDAV)
و اعلان‌های ایمیل/پیامک.

## پشتهٔ فنی

- **Backend:** FastAPI (async) + SQLAlchemy 2 + PostgreSQL 16 + Alembic
- **Frontend:** React 18 + TypeScript + Vite 5 + shadcn/ui + Tailwind (RTL فارسی)
- **Storage:** MinIO (S3-compatible) از طریق دروازهٔ `oss-gateway` با نشانی‌های امضاشده
- **Proxy/TLS:** nginx — گواهی به‌صورت دستی در `deploy/nginx/certs` قرار می‌گیرد، یا TLS در لبهٔ شبکه (nginx میزبان/CDN) خاتمه می‌یابد
- **اجرا:** Docker + Docker Compose — فقط سرویس proxy پورت منتشر می‌کند (پیش‌فرض: ۷۰۸۰ سامانه و ۷۴۴۳ فایل‌ها؛ با متغیرهای `APP_PORT`/`STORAGE_HOST_PORT` قابل تغییر)

## استقرار سریع

```bash
cd deploy
bash scripts/init-env.sh     # ساخت .env با کلیدهای تصادفی امن
bash scripts/install.sh      # بیلد ایمیج‌ها + اجرا + باکت‌ها + healthcheck + SSL
```

راهنمای کامل در [`docs/deployment.md`](docs/deployment.md) و [`docs/quickstart.md`](docs/quickstart.md).

## نکات مهم

- **ساخت ایمیج‌ها بدون وابستگی به PyPI/apt:** بسته‌های pip از آینهٔ در دسترس
  (`mirror-pypi.runflare.com`) نصب می‌شوند و ffmpeg/فونت‌ها به‌صورت استاتیک در
  `app/backend/bundle/` باندل شده‌اند — مناسب سرورهای دارای شبکهٔ فیلترشده.
- **حالت بدون دامنه:** مسیر فایل‌ها از پورت جداگانهٔ میزبان سرو می‌شود
  (پیش‌فرض `STORAGE_HOST_PORT=7443`) تا سامانه با IP هم کامل کار کند؛ اگر TLS را
  در لبه خاتمه می‌دهید، لبه باید به پورت‌های ۷۰۸۰/۷۴۴۳ پراکسی کند (جزئیات در `.env.example`).
- **سرویس رونویسی «حرف»** فقط با نام کاربری/رمز عبور (`/auth/glogin/`) کار
  می‌کند و فایل به‌صورت مستقیم multipart ارسال می‌شود.
- فایل‌های محلی توسعه (کلیدهای SSH، فایل‌های تست و …) در `.gitignore` هستند و
  هرگز وارد مخزن نمی‌شوند.

## استقرار خودکار (CI/CD)

با هر push به شاخهٔ `main` (تغییرات `app/` یا `deploy/`)، سرور تولید خودکار
به‌روز می‌شود:

| مسیر | توضیح |
|---|---|
| **poller سرور (اصلی)** | cron هر ۲ دقیقه `deploy/ci-poller.sh` را اجرا می‌کند؛ کد را از همین ریپو (HTTPS) می‌گیرد و در صورت تغییر `deploy/ci-deploy.sh` را اجرا می‌کند (بیلد آفلاین ایمیج‌ها + healthcheck). وابسته به هیچ ترافیک ورودی بین‌المللی نیست. |

اسرار اتصال به سرور روی خود سرور (دسترسی poller) ذخیره شده‌اند. کلید CI روی
سرور فقط اجازهٔ اجرای اسکریپت استقرار را دارد (دستور اجباری SSH — بدون شل).

## عملیات روزمره

```bash
bash scripts/status.sh        # وضعیت و سلامت
bash scripts/logs.sh backend  # لاگ زنده
bash scripts/backup.sh        # بکاپ کامل (DB + فایل‌ها + کلیدها)
bash scripts/restore.sh <f>   # بازیابی
bash scripts/update.sh        # به‌روزرسانی
```

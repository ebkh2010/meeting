# ویدارا — نسخهٔ جلسات (Vidara Meetings)

سامانهٔ SaaS چندمستاجری مدیریت جلسات: ثبت جلسه و دعوت‌نامه، آپلود صوت، رونویسی
خودکار فارسی با سرویس «حرف» (Roshan AI)، تولید پیش‌نویس صورتجلسه با مدل زبانی،
گردش تأیید و قفل، مصوبات و اقدامات، خروجی Word، آرشیو روی استوریج خارجی (S3/WebDAV)
و اعلان‌های ایمیل/پیامک.

## پشتهٔ فنی

- **Backend:** FastAPI (async) + SQLAlchemy 2 + PostgreSQL 16 + Alembic
- **Frontend:** React 18 + TypeScript + Vite 5 + shadcn/ui + Tailwind (RTL فارسی)
- **Storage:** MinIO (S3-compatible) از طریق دروازهٔ `oss-gateway` با نشانی‌های امضاشده
- **Proxy/TLS:** nginx + certbot (Let's Encrypt)
- **اجرا:** Docker + Docker Compose — تنها پورت‌های ۸۰/۴۴۳ منتشر می‌شوند

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
- **حالت بدون دامنه:** با `STORAGE_PORT=8443` فایل‌ها از پورت جداگانه سرو
  می‌شوند تا سامانه با IP هم کامل کار کند (جزئیات در `.env.example`).
- **سرویس رونویسی «حرف»** فقط با نام کاربری/رمز عبور (`/auth/glogin/`) کار
  می‌کند و فایل به‌صورت مستقیم multipart ارسال می‌شود.
- فایل‌های محلی توسعه (کلیدهای SSH، فایل‌های تست و …) در `.gitignore` هستند و
  هرگز وارد مخزن نمی‌شوند.

## عملیات روزمره

```bash
bash scripts/status.sh        # وضعیت و سلامت
bash scripts/logs.sh backend  # لاگ زنده
bash scripts/backup.sh        # بکاپ کامل (DB + فایل‌ها + کلیدها)
bash scripts/restore.sh <f>   # بازیابی
bash scripts/update.sh        # به‌روزرسانی
```

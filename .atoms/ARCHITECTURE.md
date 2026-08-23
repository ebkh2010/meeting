# Architecture Design

## System Overview

سرویس SaaS چندمستأجری مدیریت جلسات با جریان اصلی «ایجاد جلسه → دستور جلسه → دعوت → آپلود صوت → رونویسی → پیش‌نویس صورتجلسه با AI → تأیید و قفل → مصوبات و پیگیری اقدامات».

- **الگو:** مونولیت ماژولار (SPA + REST API) با جداسازی فرایند **API** و **Worker**؛ همهٔ کارهای وابسته به سرویس بیرونی روی صف پایدار.
- **چندمستأجری:** `organization_id` در همهٔ جداول دامنه + اجبار دو لایه (Repository اجباری در کد و RLS در PostgreSQL).
- **AI:** پشت لایهٔ Gateway با درگاه‌های `TranscriptionPort` و `TextPort` — رونویسی با **«حرف» (Roshan AI)** و پیش‌نویس صورتجلسه/مصوبات با **DeepSeek** (یک فراخوان با خروجی JSON).
- **الگوی رونویسی:** همیشه `wait=false` + پایدارسازی `task_ids` + **polling** (سرویس webhook ندارد)؛ ارسال فایل به‌صورت multipart جریانی از MinIO تا Storage خصوصی بماند.
- **ظرفیت هدف:** ۱۰۰ کاربر همزمان، ۲۰–۳۰ RPS خواندن، ۵ آپلود همزمان، ۱۰ کار AI همزمان (۳ در هر سازمان) با سقف مؤثر ۴ درخواست همزمان به «حرف».
- **زمان:** ذخیره و محاسبه UTC، نمایش شمسی در منطقهٔ زمانی سازمان.
- سند کامل: `docs/architecture.md` (نمای اجزا، ERD، API، RBAC، صف، امنیت، ظرفیت، استقرار، ۱۵ ADR).

## Tech Stack

| لایه | انتخاب |
|---|---|
| Frontend | React 18 + TypeScript + Vite + shadcn/ui + Tailwind + TanStack Query + react-hook-form/zod + dayjs/jalaliday |
| Backend | FastAPI + SQLModel + Pydantic v2 + Alembic |
| پایگاه داده | PostgreSQL 16 خودمدیریت (FTS فارسی، RLS، پارتیشن Audit) |
| صف و کش | Celery 5 + Redis 7 (broker، کش، rate limit، کش توکن حرف)؛ منبع حقیقت وضعیت کار در جدول `jobs` |
| Storage | MinIO سازگار با S3 (presigned multipart، SSE-S3) — خصوصی، بدون انتشار عمومی |
| **رونویسی فارسی** | **«حرف» (Roshan AI)** — `POST /api/transcribe_files/` با `wait=false` + polling؛ ورود با `/auth/glogin/` و توکن Bearer |
| **تولید متن** | **DeepSeek** (`deepseek-chat`) با خروجی JSON ساختاریافته |
| پردازش صوت | `ffmpeg` / `ffprobe` **فقط در ایمیج Worker** (اندازه‌گیری مدت، استخراج صوت از ویدیو، قطعه‌قطعه‌سازی روی مرز سکوت) |
| اسناد | WeasyPrint + فونت Vazirmatn برای PDF فارسی/RTL؛ `icalendar` برای ICS |
| ایمیل | SMTP relay تأمین‌کننده + قالب Jinja2 |
| امنیت | Argon2id، JWT ۱۵ دقیقه‌ای + Refresh چرخشی در DB + فهرست ابطال Redis |
| Proxy/TLS | Caddy 2 |
| پایش | Prometheus + Grafana + Loki + structlog (شامل متریک‌های اختصاصی `harf_*`) |
| آزمون | pytest + httpx + testcontainers؛ Vitest + Playwright؛ k6 برای آزمون بار |

## Module Design

| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| core | RequestContext، امنیت، RBAC، rate limit، Audit، لاگ ساخت‌یافته، خطاها | `backend/app/core/` |
| db | session، RLS (`SET LOCAL app.current_org`)، مهاجرت‌ها | `backend/app/db/` |
| auth | ثبت‌نام + ایجاد خودکار سازمان، ورود، refresh چرخشی، بازیابی رمز | `backend/app/modules/auth/` |
| org | تنظیمات سازمان، اعضا، دعوت با توکن، سهمیه و مصرف، Audit، خروجی داده | `backend/app/modules/org/` |
| meetings / agenda / participants | جلسه، سری تکرارشونده (≤۱۲ نمونه)، دستور جلسه، پیوست، RSVP، حضور و حد نصاب | `backend/app/modules/meetings/`, `agenda/`, `participants/` |
| recordings / transcripts | آپلود مستقیم با presigned URL، `ffprobe` برای مدت، چرخهٔ عمر و حذف صوت، رونویسی و قطعات زمان‌دار | `backend/app/modules/recordings/`, `transcripts/` |
| minutes / actions | ماشین وضعیت `draft→in_review→approved→locked`، نسخه‌بندی و diff، مصوبات، اقدامات | `backend/app/modules/minutes/`, `actions/` |
| jobs | ایجاد کار idempotent، وضعیت، نوبت صف، retry دستی (با استفاده از `task_ids` ذخیره‌شده)، نمای DLQ | `backend/app/modules/jobs/` |
| notifications | رخدادمحور: اعلان درون‌برنامه‌ای + ایمیل بر پایهٔ `notification_prefs` | `backend/app/modules/notifications/` |
| search / dashboard | FTS با `fa_normalize`، کوئری تجمیعی سبک + کش ۶۰ ثانیه | `backend/app/modules/search/`, `dashboard/` |
| admin (platform) | کنسول پلتفرم با هویت و نقش DB جدا، فقط متادیتا و شمارنده | `backend/app/modules/admin/` |
| integrations | AI Gateway: `ports.py`، `roshan_harf.py` (ورود/کش توکن/ارسال جریانی/polling/پارس زمان/chunking)، `deepseek.py`، `fake.py`؛ StorageClient؛ MailSender | `backend/app/integrations/` |
| workers | تسک‌های `transcribe`, `draft_minutes`, `send_email`, `render_pdf`, `purge_audio`, `org_export` + beat | `backend/app/workers/` |
| documents | قالب PDF فارسی/RTL و تولید ICS | `backend/app/documents/` |
| frontend features | auth, meetings, agenda, recordings, minutes, actions, notifications, admin | `frontend/src/features/` |

## Tech Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| سبک معماری | مونولیت ماژولار + جداسازی API/Worker | تیم کوچک، بار متوسط، انسجام تراکنشی؛ هزینهٔ عملیاتی میکروسرویس توجیه ندارد |
| چندمستأجری | ستون `organization_id` + RLS به‌عنوان دفاع عمقی | مهاجرت واحد و عملیات ساده، با تضمین «صفر نشت» حتی در خطای کد |
| کارهای بیرونی | Celery + Redis، وضعیت در جدول `jobs` | پایداری در ری‌استارت، retry نمایی، سقف همزمانی، DLQ پرس‌وجوپذیر |
| آپلود صوت | مستقیم به MinIO با presigned multipart | جلوگیری از اشباع حافظه و پهنای باند نمونهٔ برنامه در ۵ آپلود همزمان |
| **حالت رونویسی** | **`wait=false` + پایدارسازی `task_ids` + polling** | `wait=true` اتصال HTTP را برای ده‌ها دقیقه باز نگه می‌دارد و با هر قطعی، نتیجهٔ **پرداخت‌شده** از دست می‌رود؛ سرویس webhook ندارد پس polling تنها الگوی قابل اتکاست |
| **retry رونویسی** | اگر `task_ids` موجود باشد فقط polling ادامه می‌یابد، فایل دوباره ارسال نمی‌شود | مهم‌ترین محافظ در برابر پرداخت دوبارهٔ هزینهٔ یک رونویسی |
| **نحوهٔ ارسال فایل** | multipart جریانی از MinIO (پیش‌فرض)، `HARF_SEND_MODE=url` اختیاری | `media_urls` مستلزم قابل‌واکشی بودن صوت جلسه از اینترنت است و با تصمیم «Storage کاملاً خصوصی» تناقض دارد |
| **سنجش کیفیت** | `known_word_ratio` (= `known_words/words`) به‌جای امتیاز اطمینان | «حرف» `confidence` نمی‌دهد؛ تنها سیگنال‌ها `stats` و کروشهٔ واژهٔ مشکوک است؛ آستانهٔ ۰٫۸ برای هشدار بازبینی |
| **انتساب گوینده** | خارج از دامنهٔ MVP | سرویس برچسب‌گذاری گوینده به نمونهٔ صدای از پیش ثبت‌شدهٔ هر فرد نیاز دارد (دادهٔ بیومتریک + رضایت)؛ هزینهٔ حقوقی بر ارزش MVP می‌چربد |
| **واحد مصرف** | دقیقهٔ صوت با گرد کردن بالا، بر پایهٔ `duration` بازگشتی سرویس | منبع حقیقت مصرف باید پاسخ تأمین‌کننده باشد نه تخمین محلی؛ تغییر واحد صورت‌حساب فقط ضریب `QuotaService` را عوض می‌کند |
| **فایل‌های بلند** | chunking با `ffmpeg` روی مرز سکوت + جابه‌جایی زمانی (`offset`) در ادغام | مستندات سقف حجم/مدت را اعلام نکرده؛ آستانهٔ محافظه‌کارانهٔ داخلی از رد شدن درخواست و هزینهٔ ناگهانی جلوگیری می‌کند |
| اعتبارنامهٔ AI | `HARF_USERNAME`/`HARF_PASSWORD` و `DEEPSEEK_API_KEY` **فقط در Worker**، توکن در Redis کش می‌شود | سطح حملهٔ کمینه؛ نمونهٔ API عمومی هیچ اعتبارنامهٔ تأمین‌کننده ندارد |
| جست‌وجو | Postgres FTS + تابع `fa_normalize` | یکسان‌سازی ی/ک/نیم‌فاصله/اعراب بدون افزودن سرویس جدید |
| نشست | JWT کوتاه‌عمر + Refresh در DB + فهرست ابطال Redis | تحقق الزام ابطال دسترسی زیر ۶۰ ثانیه |
| سهمیه (M4) | اعمال در سه نقطه: پیش از آپلود، پیش از کار AI (شامل مجموع قطعات)، پس از پایان کار | تنها سد قابل اتکا در برابر هزینهٔ کنترل‌نشدهٔ AI |
| کنسول پلتفرم | مسیر، هویت و نقش DB جدا؛ **بدون دسترسی به محتوا** | حذف کلاس ریسک نشت بین‌مستأجری و ریسک حقوقی |
| PDF | WeasyPrint + Vazirmatn | RTL و شکل‌دهی صحیح فارسی با مصرف منابع کم |
| زمان | ذخیره UTC، نمایش شمسی در مرز UI؛ زمان قطعات از رشتهٔ `H:MM:SS[.ffffff]` به میلی‌ثانیه | هیچ رشتهٔ زمانی خام در پایگاه داده ذخیره نمی‌شود |
| استقرار | Docker Compose روی VPS با Caddy (TLS خودکار) | سادگی عملیاتی متناسب با MVP؛ لایهٔ برنامه بی‌حالت و آمادهٔ مقیاس افقی |

## File Tree Plan

```
backend/
  app/main.py, config.py, deps.py
  app/core/            # context, security, rbac, ratelimit, audit, logging, errors
  app/db/              # session, base, rls, migrations/
  app/models/          # organization, plan, user, invitation, meeting, minutes, job, audit ...
  app/schemas/
  app/repositories/    # TenantRepository و مشتقات
  app/modules/         # auth, org, meetings, agenda, participants, recordings,
                       # transcripts, minutes, actions, jobs, notifications,
                       # search, dashboard, admin
  app/integrations/    # ai_gateway/{ports,roshan_harf,deepseek,fake}, storage, mail, media (ffmpeg)
  app/workers/         # celery_app, tasks_ai, tasks_mail, tasks_doc, tasks_maintenance, beat_schedule
  app/documents/       # قالب PDF (Jinja2 + RTL) و ICS
  tests/               # unit, api, tenant_isolation, harf_adapter (با پاسخ نمونهٔ مستندات), load (k6)
frontend/
  src/app/             # router, providers, layout RTL
  src/features/        # auth, meetings, agenda, recordings, minutes, actions, admin, notifications
  src/components/ui/   # shadcn
  src/lib/             # api client, jalali, formatters, jobPolling
deploy/
  compose.yml, Caddyfile, .env.example, backup/, grafana/, prometheus/
docs/
  mvp_feature_review.md, architecture.md
uploads/
  harf                 # مستندات مرجع سرویس رونویسی
```

## Implementation Guide

ترتیب پیاده‌سازی مطابق چهار برش سند محصول، با این قواعد الزامی برای مهندسان:

۱. **برش ۱ (پایه و SaaS):** ابتدا `core` + `db` + RLS + `TenantRepository`، سپس auth و سازمان و دعوت و RBAC و Audit. هیچ جدول دامنه‌ای بدون `organization_id` و بدون policy RLS ساخته نشود. آزمون نشت بین دو سازمان از همین برش در CI فعال شود.
۲. **برش ۲ (چرخهٔ جلسه):** انواع جلسه، جلسه، دستور جلسه، RSVP، ایمیل و ICS. ایمیل از ابتدا روی صف باشد، نه در چرخهٔ درخواست.
۳. **برش ۳ (هستهٔ AI):** **ابتدا زیرساخت کار (`jobs` + Celery + وضعیت + retry + سقف همزمانی)**، سپس آپلود مستقیم و سیاست صوت، بعد آداپتر «حرف»، پیش‌نویس صورتجلسه با DeepSeek، جریان تأیید و سهمیه. پیاده‌سازی رونویسی به‌صورت همزمان (`wait=true`) ممنوع است.
۴. **برش ۴ (تکمیل و عرضه):** اقدامات، PDF، جست‌وجو، داشبورد، پایش، rate limit و صفحات حقوقی. سپس آزمون‌های پذیرش ظرفیت بخش ۱۱.۵ سند معماری.

قواعد ثابت برای آداپتر «حرف»: توکن از `/auth/glogin/` گرفته و در Redis کش شود؛ در `401` یک‌بار ورود مجدد بدون سوزاندن تلاش کار؛ همیشه **یک فایل در هر درخواست** با `wait=false`؛ `task_ids` پیش از هر polling در `jobs.payload` ذخیره شود؛ زمان‌های رشته‌ای به میلی‌ثانیه تبدیل شوند؛ کروشه‌های واژهٔ مشکوک در متن حفظ شوند و به DeepSeek هم پاس داده شوند؛ مصرف از `duration` پاسخ ثبت شود؛ و آزمون آداپتر با پاسخ‌های نمونهٔ مستندات (`uploads/harf`) نوشته شود.

قواعد عمومی: هر endpoint نوشتنی باید RBAC از dependency مشترک، `If-Match` در منابع نسخه‌دار، و رخداد Audit در عملیات حساس داشته باشد؛ هیچ اعتبارنامهٔ تأمین‌کنندهٔ AI در سرویس API یا کلاینت قرار نمی‌گیرد (فقط Worker)؛ آداپتر جعلی AI برای تست‌ها همیشه نگه‌داری شود؛ و تبدیل تاریخ شمسی فقط در مرز UI و قالب‌ها انجام شود.

**ابهامات باز که باید از تأمین‌کننده پرسیده شود (A8–A13 در سند معماری):** سقف حجم/مدت فایل، سقف نرخ و همزمانی، مدل قیمت‌گذاری و واحد صورت‌حساب، سیاست نگه‌داری و عدم استفادهٔ آموزشی داده، پذیرش ویدیو، و فهرست کدهای خطا. تا پاسخ رسمی، آستانه‌های محافظه‌کارانهٔ تنظیم‌پذیر اعمال است.
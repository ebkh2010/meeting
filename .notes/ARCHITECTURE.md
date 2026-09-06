# Architecture Design

## System Overview

سرویس SaaS چندمستأجری مدیریت جلسات با جریان اصلی «ایجاد جلسه → دستور جلسه → دعوت → آپلود صوت/ویدیو → رونویسی → پیش‌نویس صورت‌جلسه با AI → تأیید و قفل → مصوبات و پیگیری اقدامات».

> **این سند با ساختار فعلی کد (v1.0.26) هماهنگ شده است**؛ سند مرجع طراحی در
> `docs/architecture.md` و وضعیت تفاوت‌ها در بخش ۰ همان سند است.

- **الگو:** مونولیت ماژولار (SPA + REST API) — یک پروسهٔ FastAPI که کارهای پس‌زمینه را با `asyncio.create_task` اجرا می‌کند و وضعیت هر کار در جدول پایدار `jobs` نگه داشته می‌شود (بدون Celery/Redis؛ بازیابی کارهای نیمه‌کاره با `RECOVER_ORPHAN_JOBS` هنگام بالا آمدن).
- **چندمستأجری:** `organization_id` در همهٔ جداول دامنه + اجبار در لایهٔ کد (`resolve_context` / `list_owned` / `get_owned` در `services/mgmt_core.py`). RLS در پایگاه داده فعال نیست.
- **AI:** لایهٔ Port/Adapter در `services/ai_providers.py` — رونویسی با **«حرف» (Roshan AI)** و تولید متن با **DeepSeek**؛ زنجیرهٔ اولویت/fallback به‌ازای هر سازمان با اعتبار پیش‌فرض از متغیرهای محیطی (`DEFAULT_HARF_*`، `DEFAULT_DEEPSEEK_API_KEY`).
- **واحد مصرف:** «توکن ویدارا» — ۱ دقیقه رونویسی = ۱ توکن، ۱ سنت مدل زبانی = ۱ توکن (`services/ai_usage.py`)؛ سقف ماهانهٔ هر کاربر + سقف سازمان؛ نمایش در داشبورد و پنل پلتفرم.
- **زمان:** ذخیره و محاسبه UTC، نمایش شمسی در مرز UI.

## Tech Stack (پیاده‌سازی‌شده)

| لایه | انتخاب |
|---|---|
| Frontend | React 18 + TypeScript + Vite 5 + shadcn/ui + Tailwind (RTL) |
| Backend | FastAPI (async) + SQLAlchemy 2 + Pydantic v2 |
| پایگاه داده | PostgreSQL 16؛ جدول‌ها با `create_all` و ستون‌های جدید با `ALTER TABLE` دستی |
| صف کار | جدول `jobs` + اجرای in-process (وضعیت/پیشرفت/retry در DB) |
| Storage | MinIO خصوصی از طریق `oss-gateway` (presigned upload/download) |
| رونویسی فارسی | «حرف» (Roshan AI) — ورود `/auth/glogin/`، ارسال multipart، polling با `task_ids` |
| تولید متن | DeepSeek (`deepseek-chat`) با خروجی JSON ساختاریافته |
| پردازش صوت/ویدیو | ffmpeg/ffprobe استاتیک در ایمیج بک‌اند (مدت صوت، جداسازی صدای ویدیو، کلیپ گوینده) |
| اسناد | `python-docx` برای Word راست‌به‌چپ + نمای چاپ/PDF مرورگر؛ `icalendar` برای ICS |
| ایمیل/پیامک | SMTP + ParsaSMS (`services/notify_channels.py`) با پیش‌فرض پلتفرم در نبود تنظیمات سازمان |
| امنیت | هش رمز، JWT (`typ=vidara_app` / `typ=vidara_platform`)، رمزنگاری اعتبارنامه‌ها با `JWT_SECRET_KEY`، مرز مستأجر در همهٔ کوئری‌ها |
| Proxy/TLS | nginx — گواهی دستی در `deploy/nginx/certs` یا خاتمهٔ TLS در لبه |
| آزمون | هارنس E2E `.deploy-tools/e2e-final.py` روی سرور تولید (۲۱۰ PASS / ۶ FAIL شناخته‌شده) + Playwright برای بررسی UI |

## Module Design (ساختار فعلی)

| Module | Responsibility | Key Files |
|--------|---------------|-----------|
| core | تنظیمات، دیتابیس، خطاها | `core/config.py`, `core/database.py` |
| auth | ثبت‌نام/ورود/کاربران/تکمیل مشخصات/سوییچ فضا/حذف سازمان | `routers/app_auth.py`, `services/app_auth.py` |
| platform admin | مدیر پلتفرم: سازمان‌ها، مدیران، تنظیمات/سقف هر سازمان، مصرف AI، سطل آشغال | `routers/platform.py`, `services/platform_admin.py` |
| workspace | جلسه، دستور جلسه، RSVP/حضور، صورت‌جلسه، مصوبات/اقدامات، داشبورد، جست‌وجوی تمام‌متن | `routers/workspace.py`, `services/mgmt_core.py` |
| meeting-ai | آپلود صوت/ویدیو، ترتیب فایل‌ها، کارهای رونویسی/پیش‌نویس/جداسازی صدا، گوینده‌ها | `routers/meeting_ai.py`, `services/ai_providers.py`, `services/meeting_speakers.py` |
| minutes flow | گردش draft→in_review→approved→locked، نسخه‌ها، خروجی Word/JSON | `routers/minutes_flow.py`, `services/minutes_docx.py`, `services/minutes_settings.py` |
| assistant | دستیار هوشمند با بازیابی محتوای واقعی سازمان | `routers/assistant.py`, `services/assistant.py` |
| archive | آرشیو/بازیابی روی استوریج خارجی S3/WebDAV | `routers/archive.py`, `services/meeting_archive.py`, `services/external_storage.py` |
| notifications | SMTP + پیامک + دعوت‌نامه با ICS و پیوست | `services/notify_channels.py`, `services/meeting_invites.py` |
| upload limits | سقف‌های بارگذاری هر سازمان + سقف ویدیو | `services/upload_limits.py` |
| ai usage | توکن ویدارا، سهمیهٔ کاربر/سازمان، تعرفهٔ روز دیپ‌سیک | `services/ai_usage.py` |
| frontend | pages/، components/، lib/ | `app/frontend/src/*` |

## Tech Decisions (پیاده‌سازی‌شده)

| Decision | Choice | Rationale |
|----------|--------|-----------|
| سبک معماری | مونولیت ماژولار با کارهای in-process روی جدول `jobs` | تیم کوچک، بار متوسط، انسجام تراکنشی؛ بدون هزینهٔ عملیاتی Celery/Redis |
| چندمستأجری | ستون `organization_id` + اجبار در لایهٔ کد | مهاجرت واحد و عملیات ساده؛ همهٔ کوئری‌ها از `list_owned`/`get_owned` عبور می‌کنند |
| آپلود صوت/ویدیو | مستقیم به MinIO با presigned PUT + ثبت فراداده | جلوگیری از اشباع حافظهٔ API؛ نوار پیشرفت واقعی با XHR |
| ویدیو | کار `audio_extract` با ffmpeg (MP3 16kHz تک‌کاناله)؛ `object_key` بعد از جداسازی به صوت تغییر می‌کند و ویدیو در `video_*` می‌ماند | همان مسیر رونویسی بدون تغییر ادامه می‌یابد؛ «حذف ویدیو با نگه‌داری صدا» جداگانه ممکن است |
| چند فایل صوتی | ستون `position` در recordings + `PUT /recordings/order`؛ متن نهایی = ترکیب فایل‌های رونویسی‌شده به ترتیب کاربر | متن و صورت‌جلسه دقیقاً از ترتیب جلسه پیروی می‌کنند؛ فایل‌های رونویسی‌نشده نادیده گرفته می‌شوند |
| رونویسی | `wait=false` + پایدارسازی `task_ids` + polling؛ در retry فایل دوباره ارسال نمی‌شود | جلوگیری از پرداخت دوبارهٔ هزینه |
| سنجش کیفیت | `known_word_ratio` (آستانهٔ هشدار ۰٫۸) | «حرف» `confidence` نمی‌دهد |
| گوینده‌ها | برچسب `SPEAKER_x` از diarization + نام‌گذاری مدیر جلسه + کلیپ نمونهٔ صدا (ffmpeg) | بدون نیاز به دادهٔ بیومتریک |
| جست‌وجو | `fa_normalize` پایتونی + جست‌وجو روی متن‌های جمع‌شده با `search_scope` + بندهای یافت‌شده و پرش به بخش | نرمال‌سازی ی/ک/نیم‌فاصله/اعراب؛ بدون سرویس جدید |
| واحد مصرف | «توکن ویدارا» (۱ دقیقه STT = ۱ سنت LLM = ۱ توکن) | نمایش یکپارچه برای کاربر؛ پنل پلتفرم دلار نرخ روز دیپ‌سیک را هم نشان می‌دهد |
| کنسول پلتفرم | هویت/نقش جدا (`platform_admins`، توکن `typ=vidara_platform`)؛ بدون دسترسی به محتوا | حذف کلاس ریسک نشت بین‌مستأجری |
| خطای آپلود | اعتبارسنجی فرمت/حجم در لحظهٔ انتخاب + دلیل خطا زیر هر فایل ناموفق | هیچ شکست آپلودی بی‌صدا نمی‌ماند |
| استقرار | Docker Compose + nginx؛ گواهی دستی یا TLS لبه؛ بیلد آفلاین (wheels + ffmpeg باندل‌شده) | سازگار با سرورهای دارای شبکهٔ فیلترشده |

## File Tree (فعلی)

```
app/frontend/src/
  pages/           # Login, CompleteProfile, Dashboard, Meetings, MeetingDetail,
                   # Settings, Account, PrintMinutes, PlatformAdmin, blog/
  components/      # AppShell, PlatformShell, AssistantPanel, AiUsagePanel, MarkdownText,
                   # HighlightText, JalaliDateTimePicker, MeetingAttachmentsCard,
                   # OrganizationSwitcher, LoadingGif, VidaraBranding, ui/, settings/, blog/
  lib/             # mgmt, appAuth, platform, assistant, aiSettings, notify, session, utils
app/backend/
  main.py
  core/            # config, database, enums, auth
  dependencies/    # app_auth (get_workspace_user), platform_admin
  models/          # meetings, minutes, transcripts, recordings, jobs, participants,
                   # meeting_speakers, platform_admins, ai_user_usage, org_* و …
  routers/         # workspace, meeting_ai, minutes_flow, app_auth, platform, assistant,
                   # archive, meeting_attachments, ai_settings, notify_settings, runtime_config و …
  services/        # ai_providers, ai_usage, assistant, meeting_speakers, minutes_docx,
                   # minutes_settings, meeting_archive, external_storage, notify_channels,
                   # upload_limits, mgmt_core و …
  bundle/          # ffmpeg/ffprobe استاتیک + فونت‌ها
  .wheels/         # wheelهای آفلاین pip
deploy/
  docker-compose.yml, .env.example
  nginx/           # templates + entrypoint + certs/
  scripts/         # init-env, install, init-storage, issue-ssl, backup, restore, update, status, logs
  oss-gateway/     # دروازهٔ MinIO با OSS_API_KEY
docs/              # architecture, deployment, quickstart, mvp_feature_review, test-scenario
.notes/            # ARCHITECTURE, ATOMS, PROGRESS
uploads/           # مستندات مرجع «حرف» و پنل پیامک
```

## Implementation Notes

- **رونویسی:** آداپتر «حرف» توکن را در حافظه کش می‌کند و در ۴۰۱ یک‌بار ورود مجدد می‌زند؛ مصرف از `duration` بازگشتی سرویس ثبت می‌شود؛ واژه‌های نامطمئن (کروشه) در متن حفظ و در پرامپت DeepSeek صریحاً «نامطمئن» اعلام می‌شوند.
- **صورت‌جلسه:** یک فراخوان DeepSeek هم متن و هم مصوبات/اقدامات را تولید می‌کند؛ تنظیمات تولید (استفاده از دستور جلسه/مدعوین، طول، ملاحظات) به‌ازای هر جلسه در `meeting_minutes_settings` است.
- **جست‌وجو:** بک‌اند برای هر جلسه متن‌های عنوان/دستور/صورتجلسه/رونویسی/مصوبات/اقدامات را جمع و با `fa_normalize` تطبیق می‌دهد و تا ۳ بند با برچسب منبع برمی‌گرداند؛ فرانت با `?q=&scope=` به همان بخش صفحهٔ جلسه می‌پرد و واژه را هایلایت می‌کند.
- **پلتفرم:** ساخت مدیر سازمان با `POST /platform/orgs` (رمز رندوم پیامک‌شده + `must_change_password`)؛ پاک‌سازی کامل سازمان داده‌ها و فایل‌های Storage با پیشوند `org-{id}/` را حذف می‌کند.
- **مصرف AI:** `GET /platform/ai-summary` مجموع دقیقهٔ حرف و توکن DeepSeek (کل و ماه جاری)، معادل توکن ویدارا و دلار نرخ روز (ورودی ۰٫۲۲$ / خروجی ۰٫۶۶$ برای هر میلیون توکن — قابل تنظیم با `DEEPSEEK_CURRENT_*`) را برمی‌گرداند؛ «لاگ و آمار» هر سازمان هم همین تفکیک را دارد.

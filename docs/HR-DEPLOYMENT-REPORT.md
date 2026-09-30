# گزارش استقرار نسخهٔ دوم (HR) + گزارش حادثه و بازیابی

> تاریخ: ۱۴۰۵/۰۷/۰۸ (2026-09-30) · سرور: `212.80.18.20` (SSH روی پورت ۲۲۲۴، کاربر `samim`)
> دامنهٔ نسخهٔ جدید: **https://hr.vidara-meeting.ir** · نسخهٔ قبلی: **https://vidara-meeting.ir**
> مخزن: [`ebkh2010/HRmeeting`](https://github.com/ebkh2010/HRmeeting) (خصوصی)

---

## ۱. خلاصه

نسخهٔ دوم **کاملاً مستقل** روی همان سرور راه‌اندازی شد: پروژهٔ compose جدا (`hr-meetings`)، شبکه،
دیتابیس PostgreSQL، MinIO، دروازهٔ ذخیره‌سازی، بک‌اند، فرانت و پروکسی جدا؛ پورت‌های `7081` و `7444`.
داده‌ها هم منتقل نشد و دیتابیس نسخهٔ دوم از صفر ساخته شد.

**در میانهٔ کار یک حادثهٔ تولیدی رخ داد:** کانتینرهای نسخهٔ اول موقتاً با کانفیگ نسخهٔ دوم بازساخته
شدند و `vidara-meeting.ir` حدود **۷ دقیقه** با خطای ۵۰۲ از دسترس خارج شد. علت، یک باگ واقعی در
`deploy/docker-compose.yml` بود (نام پروژه ثابت ⇒ دو استک با یک نام پروژه). علت رفع، نسخهٔ اول
**کامل بازیابی شد** (هیچ داده‌ای از دست نرفت) و سپس استقرار با ایزولاسیون درست ادامه یافت.
شرح کامل در بخش ۵.

---

## ۲. وضعیت نهایی (تأییدشده)

| مورد | نسخهٔ اول (جلسات) | نسخهٔ دوم (HR) |
|---|---|---|
| دامنه | `https://vidara-meeting.ir` | `https://hr.vidara-meeting.ir` |
| مسیر استقرار | `/home/samim/vidara-meetings` | `/home/samim/hr-meetings/app` |
| نام پروژهٔ compose | `vidara-meetings` | `hr-meetings` |
| پورت‌های میزبان | `7080` / `7443` | `7081` / `7444` |
| دیتابیس | `vidara-meetings_db_data` | `hr-meetings_db_data` (از صفر) |
| MinIO | `vidara-meetings_minio_data` | `hr-meetings_minio_data` |
| نشست/JWT | کلید مستقل | **کلید مستقل تازه** |
| کلیدهای AI | DeepSeek + حرف | **همان کلیدها** (طبق درخواست؛ در `.env` مستقل ثبت شده) |
| گواهی TLS | لبه (wildcard `*.vidara-meeting.ir`) | همان گواهی، در لبه |
| وضعیت `/health` | `200` ✅ | `200` ✅ |
| `sitemap.xml` / `robots.txt` | `https://vidara-meeting.ir` ✅ | `https://hr.vidara-meeting.ir` ✅ (پس از بیلد مجدد فرانت) |

**جداسازی تأییدشده:** ایمیج‌های نسخهٔ دوم حالا `hr-meetings-backend/frontend/oss-gateway`
هستند (قبلاً به‌اشتباه `vidara-meetings-*` ساخته می‌شدند)؛ شبکهٔ `hr-meetings_internal` و
ولوم‌های `hr-meetings_*` مستقل‌اند؛ هیچ کانتینر یا پورتی مشترک نیست.

---

## ۳. آنچه انجام شد (خلاصهٔ مراحل)

1. **انتقال کد:** سرور به `github.com` دسترسی ندارد (بررسی‌شده: `github.com:443`, `codeload`, `api`, `raw` همه BLOCKED).
   بنابراین مخزن با `git bundle` از این ماشین منتقل و روی سرور بازسازی شد (۱۳۷ مگابایت، ۴۶۱ فایل، کامیت `fac623e`).
2. **ساخت `.env` مستقل** با `deploy/scripts/init-env.sh`: رمز دیتابیس، `JWT_SECRET_KEY`، رمز MinIO و
   `OSS_API_KEY` همه **تصادفی و تازه**؛ فقط `POSTGRES_USER`/`POSTGRES_DB`/`MINIO_ROOT_USER` که در
   `.env.example` مقدار دارند، بدون تغییر ماندند (بدون اثر امنیتی).
3. **انتقال کلیدهای AI** از `.env` نسخهٔ اول: `DEFAULT_DEEPSEEK_API_KEY`، `DEFAULT_HARF_ENABLED`،
   `DEFAULT_HARF_AUTH_USERNAME`، `DEFAULT_HARF_AUTH_PASSWORD` و `TZ`.
4. **تنظیم پورت/دامنه:** `APP_PORT=7081`، `STORAGE_HOST_PORT=7444`، `APP_DOMAIN=STORAGE_DOMAIN=hr.vidara-meeting.ir`،
   `COMPOSE_PROJECT_NAME=hr-meetings`، `VITE_SITE_URL=https://hr.vidara-meeting.ir`، `CORS_ALLOWED_ORIGINS` اختصاصی.
5. **بیلد آفلاین و بالا آوردن استک** (۶ کانتینر؛ بک‌اند healthy).
6. **لبه:** بلوک nginx برای `hr.vidara-meeting.ir` روی ۸۰/۴۴۳ (اپ → `127.0.0.1:7081`) و ۸۴۴۴ (فایل‌ها → `127.0.0.1:7444`)
   با همان گواهی wildcard موجود.
7. **به‌روزرسانی خودکار:** اسکریپت‌های `deploy/ci-poller.sh`، `deploy/ci-deploy.sh` و
   `deploy/systemd/hr-poller.{service,timer}` ساخته و روی سرور نصب شد (هر ۲ دقیقه).

---

## ۴. سازوکار به‌روزرسانی (واقعیت شبکه)

⚠️ **سرور به GitHub دسترسی ندارد**، پس «poller ای که از GitHub بکشد» روی این سرور کار نمی‌کند.
مسیر واقعیِ کارآمد:

```bash
# روی ماشین توسعه (این ماشین):
git bundle create hr.bundle main
scp -P 2224 hr.bundle samim@212.80.18.20:/home/samim/hr-meetings/
# روی سرور:
cd /home/samim/hr-meetings/app && git fetch ../hr.bundle main:refs/heads/main
# poller (systemd timer هر ۲ دقیقه) تغییر را می‌بیند و ci-deploy.sh را اجرا می‌کند.
```

همچنین `gitlab.samimgroup.com` از سرور **قابل دسترسی** است؛ اگر مخزن HRmeeting به GitLab هم
آینه (mirror) شود، می‌توان به‌روزرسانی خودکار واقعی از GitLab داشت — پیشنهاد بعدی.

وضعیت فعلی: `hr-poller.timer` روی سرور **نصب** شده ولی **غیرفعال** است تا پس از تثبیت استقرار و
تعیین مسیر به‌روزرسانی، با یک دستور فعال شود:

```bash
# پس از تعیین مسیر به‌روزرسانی (bundle یا آینهٔ GitLab):
sudo systemctl enable --now hr-poller.timer
# علامت‌گذاری کامیت فعلی به‌عنوان «استقرار‌شده» تا اولین اجرا بی‌دلیل بیلد نکند:
mkdir -p ~/.local/state/hr-meetings && (cd /home/samim/hr-meetings/app && git rev-parse main) > ~/.local/state/hr-meetings/last-deployed-commit
```

⚠️ هشدار: تا وقتی `ci-deploy.sh` را برای به‌روزرسانی **هر نمونه** جداگانه فراخوانی نکنید، poller را
روی نمونهٔ دیگری فعال نکنید؛ درس حادثهٔ بخش ۵ دقیقاً همین بود.

---

## ۵. حادثه: قطعی موقت نسخهٔ اول و بازیابی

### چه اتفاقی افتاد
در بازهٔ ۱۱:۵۷ تا ۱۲:۰۴، کانتینرهای **نسخهٔ اول** با محیط و کانفیگ **نسخهٔ دوم** بازساخته شدند:

- `vidara-meetings-backend-1` با `CORS_ALLOWED_ORIGINS=https://hr.vidara-meeting.ir` و رمز دیتابیس نسخهٔ دوم،
  در حلقهٔ ری‌استارت با `asyncpg.exceptions.InvalidPasswordError` (رمز دیتابیس نسخهٔ اول با رمز نسخهٔ دوم جایگزین شده بود).
- `vidara-meetings-proxy-1` با `APP_DOMAIN=hr.vidara-meeting.ir` و پورت‌های `7081/7444` بازساخته شد؛
  در نتیجه پورت‌های ۷۰۸۰/۷۴۴۳ آزاد شدند و `https://vidara-meeting.ir` پاسخ **۵۰۲** داد.

### علت ریشه‌ای
در `deploy/docker-compose.yml` نام پروژه **ثابت** بود:

```yaml
name: vidara-meetings     # ← باگ: هر نمونه‌ای که این فایل را اجرا کند، همان پروژه می‌شود
```

و `ci-deploy.sh` (که خودم نوشتم و برای آزمایش poller اجرا شد) اسکریپت را از **پوشهٔ نسخهٔ دوم**
با `.env` نسخهٔ دوم اجرا می‌کرد، ولی چون `name` ثابت بود، `docker compose up -d --remove-orphans`
روی پروژهٔ `vidara-meetings` عمل کرد و کانتینرهای نسخهٔ اول را با کانفیگ نسخهٔ دوم جایگزین کرد.

### بازیابی (انجام شد)
1. استک HR موقتاً `stop` شد (بدون حذف داده).
2. در پوشهٔ نسخهٔ اول: `docker compose up -d --force-recreate` با `.env` و فایل compose خودش.
3. تأیید: `/health` داخلی `200`، `https://vidara-meeting.ir/health` و `/` هر دو `200`، همهٔ داده‌ها سالم
   (کانتینر دیتابیس گزارش داد «PostgreSQL Database directory appears to contain a database; Skipping initialization»).
4. آن‌گاه ایزولاسیون اصلاح و استقرار HR ادامه یافت.

**مدت قطعی:** حدود ۷ دقیقه (۱۱:۵۷ تا ۱۲:۰۴). **از دست رفتن داده:** هیچ.

### اصلاحات ساختاری انجام‌شده
| اصلاح | فایل |
|---|---|
| نام پروژه پارامتری شد: `name: ${COMPOSE_PROJECT_NAME:-vidara-meetings}` | `deploy/docker-compose.yml` |
| `ci-deploy.sh` نام پروژه و آدرس سلامت را از `.env` همان نمونه می‌خواند | `deploy/ci-deploy.sh` |
| `COMPOSE_PROJECT_NAME=hr-meetings` در `.env` نسخهٔ دوم | روی سرور |
| ایمیج‌های نسخهٔ دوم با پیشوند `hr-meetings-` ساخته شدند | نتیجهٔ بیلد |

> درس عملی: هر «نام» ثابت در compose (نام پروژه، `container_name`، نام ولوم، نام image) یک
> خطر تداخل بین نمونه‌ها است؛ باید همه پارامتری شوند.

---

## ۶. رفع اشکالات فنی که در مسیر پیدا شد

1. **باگ قالب HTTPS پروکسی داخلی:** `deploy/nginx/templates/https.conf.template` وقتی با
   `https.conf` ساخته می‌شود، nginx با خطای
   `no "ssl_certificate" is defined for the "listen ... ssl" directive in default.conf:24` بالا نمی‌آید
   (خطا به بلوک اول نسبت داده می‌شود و منشأ آن ترکیب `listen 80 ssl` با ترتیب قالب است).
   ⇒ راه‌حل انتخاب‌شده: **همان الگوی اثبات‌شدهٔ نسخهٔ اول** — پوشهٔ `deploy/nginx/certs` خالی می‌ماند،
   پروکسی داخلی فقط HTTP سرو می‌کند و **TLS در لبه** خاتمه می‌یابد. (باگ قالب برای رفع در فرصت بعدی ثبت شد.)
2. **entrypoint پیش‌فرض ایمیج nginx** قالب‌های `/etc/nginx/templates` را با `envsubst` خالی پردازش
   می‌کند و فایل ناقص می‌نویسد؛ با `NGINX_ENVSUBST_TEMPLATE_DIR=""` و `NGINX_ENVSUBST_OUTPUT_DIR=""`
   این مرحله غیرفعال شد (در compose ثبت شده).
3. **دامنهٔ sitemap/robots:** متغیر `VITE_SITE_URL` باید به‌عنوان `build.args` به بیلد فرانت داده شود؛
   اضافه شد (`frontend.build.args.VITE_SITE_URL`). بیلد مجدد فرانت HR در حال انجام است تا
   `hr.vidara-meeting.ir/sitemap.xml` به دامنهٔ خودش اشاره کند (پیش از آن، مقدار پیش‌فرض نسخهٔ جلسات می‌آمد).
4. **تداخل `default_server`:** بلوک لبهٔ دامنهٔ جدید نباید `default_server` باشد (با نسخهٔ اول تضاد می‌کرد)؛
   حذف شد.
5. **مسیر گواهی:** در کپی کانفیگ لبه، مسیر گواهی نباید به نام زیردامنه تغییر کند؛ باید همان
   `/etc/letsencrypt/archive/vidara-meeting.ir/` (گواهی wildcard) بماند.
6. **دسترسی:** کاربر `samim` **sudo با رمز** دارد (نه بدون رمز) و ورود SSH با `root` بسته است؛
   عملیات لبه/گواهی با `echo '<pass>' | sudo -S` انجام شد.

---

## ۷. کارهای باقی‌مانده (پیشنهاد ترتیب)

1. **فعال‌سازی poller** پس از تثبیت: `sudo systemctl enable --now hr-poller.timer` و تعیین مسیر
   به‌روزرسانی (bundle یا آینهٔ GitLab).
2. **افزودن توکن/کلید CI برای به‌روزرسانی**: یا Deploy Key گیت‌هاب (که از سرور قابل استفاده نیست)،
   یا آینهٔ GitLab (قابل دسترس از سرور — پیشنهاد اصلی).
3. **رفع باگ قالب `https.conf.template`** تا پروکسی داخلی هم بتواند TLS را مستقیم خاتمه دهد
   (فعلاً لبه این کار را می‌کند و مشکلی نیست).
4. **بررسی `STORAGE_PUBLIC_URL`**: مقدار فعلی `https://hr.vidara-meeting.ir:7444` است، ولی پورت
   ۷۴۴۴ روی لبه HTTPS سرو نمی‌کند (لبه روی ۸۴۴۴ گوش می‌دهد و ufw فقط IPهای خاص را مجاز می‌کند).
   باید یکی انتخاب شود: (الف) افزودن `listen 7444 ssl` در لبه و باز کردن ufw، یا
   (ب) تغییر `STORAGE_PUBLIC_URL` به `https://hr.vidara-meeting.ir/storage` با مسیر پروکسی‌شده روی ۴۴۳.
5. **بکاپ نسخهٔ دوم**: افزودن مسیر جدید به اسکریپت `backup.sh` یا کرون جداگانه.
6. **گواهی:** گواهی wildcard فعلی تا **۲۴ نوامبر ۲۰۲۶** اعتبار دارد و تمدید آن
   `authenticator = manual` است ⇒ نیاز به اقدام دستی دارد؛ برای پایداری هر دو سامانه،
   تمدید خودکار (DNS-01 با API آروان‌کلاد یا webroot) تنظیم شود.

---

## ۸. دستورهای عملیاتی نسخهٔ دوم

```bash
# وضعیت
cd /home/samim/hr-meetings/app/deploy && docker compose -p hr-meetings ps
curl -s https://hr.vidara-meeting.ir/health

# لاگ‌ها
docker logs --tail 50 hr-meetings-backend-1
tail -20 ~/.local/state/hr-meetings/poller.log

# استقرار دستی
cd /home/samim/hr-meetings/app && bash deploy/ci-deploy.sh main

# به‌روزرسانی از bundle (مسیر کارآمد با شبکهٔ فعلی)
# روی این ماشین:  git bundle create hr.bundle main && scp -P 2224 hr.bundle samim@212.80.18.20:/home/samim/hr-meetings/
# روی سرور:        cd /home/samim/hr-meetings/app && git fetch ../hr.bundle main:refs/heads/main
```

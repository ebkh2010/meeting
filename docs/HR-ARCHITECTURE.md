# سند معماری سامانهٔ «استخدام و مصاحبهٔ HR» (Vidara HR)

> نسخه ۱٫۰ · تاریخ ۱۴۰۵/۰۷/۰۸ · مخزن: [`ebkh2010/HRmeeting`](https://github.com/ebkh2010/HRmeeting)
> دامنهٔ زنده: **https://hr.vidara-meeting.ir**
> **سند حاکم:** [`HR-DECISIONS.md`](HR-DECISIONS.md) — هرجا تناقضی با این سند یا اسناد دیگر بود، آن سند مقدم است.

---

## ۱. سامانه چیست

سامانهٔ HR یک محصول **مستقل** برای مدیریت چرخهٔ استخدام است: از بارگذاری رزومه و رتبه‌بندی
کاندیدها تا زمان‌بندی مصاحبه، رونویسی صوت مصاحبه و ارزیابی مصاحبه با هوش مصنوعی.

**سامانه سه ستون دارد:**

| ستون | کار | خروجی |
|---|---|---|
| **غربال رزومه** | استخراج ساختاریافته از رزومه + امتیازدهی شاخص‌محور + رتبه‌بندی | جدول رتبه با امتیاز و شاهد متنی |
| **مدیریت مصاحبه** | زمان‌بندی مستقل + دعوت مصاحبه‌گران و کاندید + آپلود و رونویسی صوت | تقویم مصاحبه + رونویسی زمان‌دار |
| **ارزیابی مصاحبه** | امتیازدهی هر شاخص از متن مصاحبه + توصیف و توصیه + بازبینی انسانی | کارت امتیاز قابل چاپ |

---

## ۲. مرزهای سامانه (اصل حاکم: دامنه از صفر، زیرساخت بازاستفاده)

### ۲٫۱ آنچه در این سامانه **وجود ندارد** (تصمیم بنیادی کارفرما)

> سامانهٔ HR هیچ ربطی به سامانهٔ جلسات (`vidara-meeting.ir`) ندارد و **مفهوم «جلسه» در آن وجود ندارد.**

| مفهوم ممنوع | جایگزین در HR |
|---|---|
| `Meetings` (جلسه) | `Hr_interviews` (مصاحبه) |
| `Participants` (شرکت‌کنندهٔ جلسه) | `Hr_interview_participants` (مدعو مصاحبه) |
| `Invitations` (دعوت‌نامهٔ جلسه) | دعوت مصاحبه + ICS از کانال اعلان |
| `Agenda_items` (دستور جلسه) | پرسش‌های مصاحبه (`Hr_interview_questions`) |
| `Minutes` / `Decisions` / `Action_items` | `Hr_evaluations` (ارزیابی) |
| صفحه/منوی جلسات، جست‌وجوی جلسات، دستیار جلسه | صفحه/منوی HR، جست‌وجوی کاندید |

**قواعد سخت:**
1. هیچ جدول HR کلید خارجی به جداول جلسه ندارد و هیچ کوئری روی آن‌ها نمی‌زند.
2. هیچ روتر HR به `Meetings`/`Participants`/`Minutes` import نمی‌کند.
3. هیچ صفحهٔ HR داده‌ای از API جلسات نمی‌خواند.
4. تغییر در سامانهٔ HR **نباید** هیچ اثری روی `vidara-meeting.ir` بگذارد (پروژهٔ compose، پورت، دیتابیس،
   MinIO، شبکه و ولوم جدا — بخش ۷).

### ۲٫۲ آنچه بازاستفاده می‌شود (موتور، نه دامنه)

| موتور | محل در مخزن | کاربرد در HR |
|---|---|---|
| احراز هویت سازمانی + چندمستاجری + مرز مستأجر | `routers/app_auth.py`, `services/mgmt_core.py` | پایهٔ امنیتی و عایق‌بندی دادهٔ کاندید |
| نقش‌ها و ماتریس دسترسی | `mgmt_core.require_role`, `ROLE_*` | دو نقش جدید HR (بخش ۴) |
| رمزنگاری اسرار و کلیدهای AI هر سازمان | `services/app_auth.py`, `services/ai_providers.py` | اتصال به مدل زبانی و رونویسی |
| زنجیرهٔ LLM با اولویت/fallback | `ai_providers.run_chat` + `parse_json_object` | موتور امتیازدهی و ارزیابی |
| رونویسی گفتار به نوشتار (+ تفکیک گوینده) | `ai_providers.run_transcription` | رونویسی صوت مصاحبه |
| صف کار پایدار | جدول `jobs` + اجرای in-process | کارهای `hr_*` |
| استوریج شیئی + نشانی امضاشده | `services/storage.py` + `deploy/oss-gateway` | رزومه و مدیای مصاحبه |
| مصرف‌سنجی «توکن ویدارا» + بودجه | `services/ai_usage.py` | کنترل هزینهٔ AI |
| کانال اعلان (ایمیل/پیامک) + سازندهٔ ICS | `services/notify_channels.py` | دعوت مصاحبه |
| تولید سند Word راست‌به‌چپ | `services/minutes_docx.py` | کارت امتیاز و گزارش |
| ffmpeg/ffprobe باندل‌شده | `app/backend/bundle/bin/` | استخراج صدا، مدت، برش |

> قاعدهٔ عملی: کدی که نامش «جلسه/صورت‌جلسه/مصوبه/دستور» دارد **کپی نمی‌شود**، ولی کدی که موتور است
> **دوباره‌نویسی نمی‌شود**.

---

## ۳. پشتهٔ فنی

| لایه | فناوری | نکته |
|---|---|---|
| بک‌اند | FastAPI (async) + SQLAlchemy 2 + PostgreSQL 16 | جداول با `create_all` + مهاجرت دستی idempotent |
| کارهای پس‌زمینه | جدول `jobs` + `asyncio.create_task` | بدون Celery/Redis؛ قابل ادامه نیست ⇒ «تلاش دوباره» |
| هوش مصنوعی | زنجیرهٔ LLM سازمان (پیش‌فرض DeepSeek) + سرویس رونویسی («حرف»/پلتفرم) | کلیدها رمزنگاری‌شده در `org_ai_providers` |
| ذخیره‌سازی | MinIO خصوصی از طریق `oss-gateway` با نشانی امضاشده | باکت‌های `hr-resumes` و `hr-interview-media` |
| فرانت | React 18 + TypeScript + Vite 5 + shadcn/ui + Tailwind (RTL فارسی) | تقویم شمسی دست‌ساز `lib/jalali.ts` |
| استقرار | Docker Compose، پروژهٔ `hr-meetings`، پورت‌های `7081`/`7445` | TLS در لبه (nginx میزبان) با گواهی wildcard |
| به‌روزرسانی | `hr-bundle-import.path` (bundle از ماشین توسعه) + `hr-poller.timer` (پشتیبان) | سرور به GitHub/GitLab دسترسی ندارد |

---

## ۴. نقش‌ها و دسترسی

### ۴٫۱ نقش‌های سازمانی

| نقش | کلید | دسترسی |
|---|---|---|
| مدیر سازمان | `org_admin` | همه‌چیز + تنظیمات HR + دیدن همهٔ کاندیدها |
| **مدیر استخدام** | `hr_manager` 🆕 | دسترسی کامل به ماژول HR: موقعیت‌ها، شاخص‌ها، همهٔ کاندیدها، همهٔ مصاحبه‌ها، تأیید و قفل ارزیابی |
| **مصاحبه‌گر** | `interviewer` 🆕 | فقط مصاحبه‌هایی که مدعو آن‌هاست: دیدن رزومهٔ همان کاندید + ثبت/ویرایش امتیاز خودش؛ بدون دیدن سایر کاندیدها و بدون تغییر شاخص‌ها |
| دبیر جلسه | `secretary` | در سامانهٔ HR دسترسی ندارد (نقش متعلق به دامنهٔ جلسه است) |
| عضو | `member` | در سامانهٔ HR دسترسی ندارد |

### ۴٫۲ قواعد اجرایی

1. هر مسیر HR با `require_role(ctx, ROLE_ADMIN, ROLE_HR_MANAGER, ROLE_INTERVIEWER)` محافظت می‌شود؛
   سپس **فیلتر دامنه‌ای**: مصاحبه‌گر فقط رکوردهایی را می‌بیند که در `Hr_interview_participants`
   با `user_id` او ثبت شده‌اند (`hr_visible_candidate_ids(ctx)`).
2. `get_owned`/`list_owned` روی همهٔ جدول‌های `Hr_*` اجباری است (مرز مستأجر).
3. سوییچ ماژول: `Hr_settings.hr_enabled`؛ اگر خاموش باشد همهٔ مسیرها `404` و منو پنهان می‌شود.
   وضعیت در `bootstrap` به فرانت داده می‌شود: `hr: {enabled, role, can_manage, can_evaluate}`.
4. هر عمل مهم (تغییر مرحله، آپلود، امتیاز، تأیید، حذف) در `audit_logs` و `Hr_candidate_events` ثبت می‌شود.

---

## ۵. مدل داده (۱۲ جدول، همه با پیشوند `Hr_`)

قواعد مدل‌سازی این پروژه: `Base` + `__table_args__ = {"extend_existing": True}` · کلید `Integer`
autoincrement · `organization_id` ایندکس‌دار روی همه · **بدون ForeignKey سخت** · بدون soft-delete ·
`created_at/updated_at` با `default=datetime.now` · زمان‌هایی که باید JSON شوند به‌صورت `String` ISO.

| جدول | ستون‌های کلیدی | توضیح |
|---|---|---|
| `Hr_settings` | `organization_id`, `hr_enabled`, `retention_days_resume` (۱۸۰), `retention_days_media` (۹۰), `blind_review`, `monthly_ai_budget_cents`, `max_concurrent_hr_jobs`, `threshold_ok` (۷۰), `threshold_maybe` (۵۰), `notify_on_ready`, `brand_name` | یک ردیف به‌ازای هر سازمان |
| `Hr_positions` | `title`, `department`, `description`, `headcount`, `status`, `criteria_json`, `opened_at`, `closed_at`, `owner_membership_id` | موقعیت شغلی + اسنپ‌شات شاخص‌ها |
| `Hr_criteria` | `scope` (resume\|interview), `round_no`, `title`, `description`, `weight`, `scale_min`, `scale_max`, `levels_json`, `is_required`, `knockout_below`, `position_id`, `sort_order`, `is_active` | شاخص‌های وزنی؛ `round_no` برای چند دور مصاحبه |
| `Hr_candidates` | `position_id`, `full_name`, `email`, `mobile`, `city`, `language` (fa\|en), `source`, `stage` (۹ مرحله), `stage_note`, `resume_object_key`, `resume_file_name`, `resume_content_type`, `resume_text`, `resume_text_hash`, `parsed_json`, `resume_score`, `match_label`, `interview_score`, `final_score`, `rank`, `consent_ack`, `purge_after`, `created_by_name` | کاندید؛ امتیازها denormalized برای مرتب‌سازی سریع |
| `Hr_candidate_events` | `candidate_id`, `kind`, `actor_name`, `detail`, `meta_json` | تایم‌لاین و Audit دامنه‌ای |
| `Hr_interviews` | `candidate_id`, `position_id`, `round_no`, `title`, `format` (onsite\|phone\|video), `status`, `scheduled_at`, `duration_minutes`, `location`, `online_url`, `interviewer_membership_ids_json`, `scorecard_json` | **مصاحبهٔ مستقل** — زمان/مکان/لینک خودش (بدون هیچ ارجاع به جلسه) |
| `Hr_interview_participants` | `interview_id`, `membership_id`, `user_id`, `full_name`, `role` (interviewer\|candidate\|observer), `rsvp_status`, `attended`, `note` | 🆕 جانشین `Participants` جلسه |
| `Hr_interview_media` | `interview_id`, `position`, `media_kind` (audio\|video), `bucket_name`, `object_key`, `video_object_key`, `file_name`, `mime_type`, `size_bytes`, `duration_seconds`, `upload_status`, `purge_after` | صوت/ویدیوی مصاحبه |
| `Hr_interview_transcripts` | `interview_id`, `media_id`, `provider`, `model`, `full_text`, `segments_json`, `speakers_json`, `duration_seconds`, `known_word_ratio` | رونویسی زمان‌دار + گوینده‌ها |
| `Hr_evaluations` | `candidate_id`, `kind` (resume\|interview), `interview_id`, `round_no`, `provider`, `model`, `scores_json`, `summary`, `strengths_json`, `risks_json`, `recommendation`, `total_score`, `tokens_in`, `tokens_out`, `cost_cents`, `status`, `reviewed_by_name`, `reviewed_at`, `is_locked` | خروجی AI + بازبینی انسانی (قابل قفل) |
| `Hr_interview_questions` | `criteria_id`, `round_no`, `competency`, `question`, `good_answer_hint`, `follow_ups_json`, `is_active` | بانک پرسش (جانشین «دستور جلسه») |
| `Hr_notes` | `candidate_id`, `author_membership_id`, `body`, `mentions_json` | کامنت تیمی |

### ۵٫۱ شکل دادهٔ امتیاز (قرارداد ثابت)

```json
{
  "criterion_id": 12,
  "criterion_title": "تجربهٔ مرتبط",
  "score": 8,
  "evidence": "۵ سال کار با FastAPI در شرکت الف (صفحهٔ ۲)",
  "evidence_location": {"kind": "resume", "page": 2},
  "comment": "شاهد کافی و مرتبط"
}
```
برای مصاحبه، `evidence_location` شکل `{"kind": "transcript", "start_ms": 754000, "end_ms": 771000, "speaker": "candidate"}` می‌گیرد تا پخش‌کنندهٔ همگام به لحظهٔ نقل‌قول بپرد.

### ۵٫۲ گردش مرحلهٔ کاندید (۹ مرحله)

```
new → screening → shortlisted → interview_scheduled → interviewed
    → evaluated → offer → hired
                      └→ rejected  (از هر مرحله‌ای)
```

---

## ۶. پایپ‌لاین‌های هوش مصنوعی

### ۶٫۱ غربال رزومه

```
آپلود (.docx/.txt/PDF متنی) → استخراج متن (python-docx / PyMuPDF)
   → تشخیص زبان (fa|en) → نرمال‌سازی فارسی
   → [کار hr_resume_extract] فراخوان ۱: استخراج JSON ساختاریافته
   → [کار hr_resume_score]  فراخوان ۲: امتیاز هر شاخص + شاهد + برچسب
   → جمع وزن‌دار در Python → رتبه → رویداد + اعلان
```

**قواعد پرامپت (الزامی):**
1. خروجی فقط یک شیء JSON معتبر، بدون بلوک کد؛ پارس با `ai_providers.parse_json_object`.
2. **ممنوعیت ساخت اطلاعات:** هر داده‌ای که در رزومه نیست ⇒ `null` یا رشتهٔ خالی. «حدس نزن».
3. **شاهد اجباری:** هر امتیاز باید `evidence` داشته باشد؛ امتیاز بدون شاهد در UI با نشان هشدار نمایش داده می‌شود.
4. تعریف سطح‌ها (`levels_json`) به مدل داده می‌شود تا امتیاز بین کاندیدها قابل مقایسه بماند.
5. زبان متن ⇒ زبان پرامپت و زبان خروجی (فارسی/انگلیسی).
6. سقف متن ~۱۴٬۰۰۰ کاراکتر؛ رزومهٔ بلندتر به دو قطعه تقسیم و ادغام می‌شود.

### ۶٫۲ ارزیابی مصاحبه (فقط صوت)

```
آپلود صوت/ویدیو (چند فایل، ترتیب دلخواه) → [ffmpeg] استخراج صدا از ویدیو
   → [کار transcribe] رونویسی + تفکیک گوینده
   → تصحیح دستی نقش گوینده‌ها («کاندید» / «مصاحبه‌گر»)
   → [کار hr_interview_eval] امتیاز شاخص‌محور هر دور + شاهد زمان‌دار + توصیهٔ نهایی
   → تأیید/اصلاح انسانی → قفل → کارت امتیاز
```

**نکات حیاتی:**
- **رندر زمان‌دار باید ساخته شود:** مسیر موجود فقط `full_text` را به مدل می‌دهد؛ برای ارجاع به لحظهٔ
  نقل‌قول باید هر قطعه به شکل `[mm:ss] گوینده: متن` رندر شود.
- **نقش گوینده تعیین‌کننده است:** اگر تأمین‌کنندهٔ رونویسی تفکیک گوینده نداشت، انتخاب دستی نقش گوینده اجباری است.
- **مصاحبهٔ بلند:** صدای استخراج‌شده مونو/۱۶kHz حدود ۲۸MB در ساعت است؛ برای Whisper (سقف ۲۵MB)
  برش با `ffmpeg -f segment` و چسباندن متن با آفست زمانی لازم است.
- **بدون تحلیل تصویر:** هیچ ارزیابی لحن/چهره‌ای انجام نمی‌شود (تصمیم #۴). ویدیو فقط نگهداری می‌شود.

### ۶٫۳ امتیازدهی قطعی (بیرون از LLM)

```python
# services/hr_scoring.py
def weighted_total(scores: list[dict], criteria: list[dict]) -> float:
    """جمع وزن‌دار؛ وزن‌ها به ۱۰۰ نرمال و مقیاس هر شاخص به ۰..۱۰ نگاشت می‌شود."""

def match_label(total: float, threshold_ok: float, threshold_maybe: float) -> str:
    """واجد شرایط | مرزی | رد — آستانه‌ها از Hr_settings (پیش‌فرض ۷۰ و ۵۰)."""
```
⇒ تغییر وزن‌ها یا آستانه‌ها **بدون فراخوان دوبارهٔ LLM** رتبه را بازمحاسبه می‌کند.

---

## ۷. استقرار، عایق‌بندی و عملیات

| موضوع | نسخهٔ جلسات | **نسخهٔ HR** |
|---|---|---|
| مسیر کد | `/home/samim/vidara-meetings` | `/home/samim/hr-meetings/app` |
| پروژهٔ compose | `vidara-meetings` | `hr-meetings` |
| پورت اپ / فایل | `7080` / `7443` | **`7081`** / **`7445`** (لبه روی `7444` TLS) |
| دیتابیس / MinIO / شبکه / ولوم | `vidara-meetings_*` | **`hr-meetings_*`** (کاملاً جدا) |
| ایمیج‌ها | `vidara-meetings-*` | **`hr-meetings-*`** |
| دامنه | `vidara-meeting.ir` | **`hr.vidara-meeting.ir`** |
| گواهی | wildcard `*.vidara-meeting.ir` (لبه) | همان گواهی، لبه |
| به‌روزرسانی | دستی | **خودکار:** `hr-bundle-import.path` + `hr-poller.timer` |
| پایش | — | `cert-monitor.timer` (روزانه ۹:۰۰) |

**قواعد عایق‌بندی (پس از حادثهٔ ۱۴۰۵/۰۷/۰۸):**
1. نام پروژه در `deploy/docker-compose.yml` **پارامتری** است: `${COMPOSE_PROJECT_NAME}`.
2. هیچ `container_name`، نام ولوم یا نام image ثابت در compose نیست.
3. `ci-deploy.sh` نام پروژه و آدرس سلامت را از `.env` همان نمونه می‌خواند.
4. هیچ اسکریپت استقراری نباید روی نمونهٔ دیگر اجرا شود؛ هر نمونه فایل deploy خودش را دارد.

---

## ۸. معماری فرانت

### ۸٫۱ مسیرها و ناوبری

```
/hr                        داشبورد استخدام (قیف، شاخص‌ها، هزینهٔ AI)
/hr/positions              موقعیت‌های شغلی
/hr/positions/:id          جزئیات موقعیت + رتبه‌بندی کاندیدها
/hr/candidates             فهرست و رتبه‌بندی کاندیدها (فیلتر، جست‌وجو، مرتب‌سازی)
/hr/candidates/:id         پروفایل کاندید (تب‌محور)
/hr/candidates/:id/compare مقایسهٔ کناربه‌کنار (۲ تا ۴ کاندید)
/hr/interviews             تقویم و فهرست مصاحبه‌ها
/hr/interviews/:id         جزئیات مصاحبه: مدعوین، مدیا، رونویسی، ارزیابی هر دور
/hr/criteria               شاخص‌ها و قالب‌های ارزیابی
/hr/questions              بانک پرسش مصاحبه
/hr/settings               تنظیمات ماژول (سوییچ، نگهداری، آستانه‌ها، ظرفیت، بودجه)
/print/scorecard/:id       کارت امتیاز قابل چاپ (بدون پوسته)
```

منو: **داشبورد · کاندیدها · مصاحبه‌ها · موقعیت‌ها · شاخص‌ها · تنظیمات HR** — و هیچ آیتم جلسه‌ای وجود ندارد.

### ۸٫۲ الگوهای الزامی فرانت

| موضوع | قاعده |
|---|---|
| پوستهٔ صفحه | `export default function Page(){ return <AppShell>{(bootstrap) => <Body bootstrap={bootstrap}/>}</AppShell> }` |
| مسیرها | فقط در `src/App.tsx` بین نشانه‌های `MODULE_ROUTES_START/END` |
| آیتم منو | آرایهٔ `BASE_NAV` در `components/AppShell.tsx` + شرط `bootstrap.hr?.enabled` و نقش |
| واکشی داده | `useState` + `useCallback` + `useEffect`؛ **بدون react-query و بدون react-hook-form** |
| حالت فهرست | `null` ⇒ `Skeleton`×۳ · `[]` ⇒ کارت خالی · خطا ⇒ کارت «تلاش دوباره» |
| جدول | `components/ui/table.tsx`؛ مرتب‌سازی/صفحه‌بندی دستی (کتابخانهٔ جدول نصب نیست) |
| تقویم شمسی | فقط `components/JalaliDateTimePicker.tsx` (مقدار ISO) — `ui/calendar.tsx` میلادی است و استفاده نمی‌شود |
| آپلود | `FilePicker` + `putWithProgress` (باید `export` شود) + صف `MeetingAttachmentsCard` الگو |
| پولینگ کار AI | کپی الگوی `MeetingDetail.tsx:186` (هر ۶ ثانیه، فقط وقتی کاری queued/running است) |
| نمایش متن AI | `<MarkdownText text={…} query={…} />` |
| برجسته‌سازی شاهد | `HighlightText` + `faNormalizeText` |
| اعلان | `toast` از `sonner`؛ پیام خطا با `errorMessage(err, 'پیام فارسی')` |
| برچسب‌ها | نقشهٔ برچسب صادرشده در `lib/hr.ts` (بدون i18n) |
| RTL و ریسپانسیو | `dir="rtl"`، اعداد `toPersianDigits`، بدون سرریز افقی از ۳۲۰px |
| بیلد | `pnpm run build` شامل `tsc --noEmit`؛ افزودن وابستگی npm ممنوع (بیلد آفلاین) |

---

## ۹. جریان‌های اصلی (سناریوهای سرتاسری)

1. **رزومه → رتبه:** آپلود ۱۰ رزومهٔ Word در یک موقعیت ⇒ تحلیل خودکار ⇒ جدول رتبه با امتیاز هر شاخص، شاهد و برچسب.
2. **تغییر شاخص‌ها:** وزن یک شاخص عوض شود ⇒ رتبه بازمحاسبه می‌شود و **هیچ فراخوان LLM جدیدی ثبت نمی‌شود**.
3. **زمان‌بندی مصاحبه:** انتخاب کاندید ⇒ تعیین دور، زمان (شمسی)، مدت، مکان/لینک و مصاحبه‌گران ⇒ دعوت‌نامه + ICS + اعلان (بدون هیچ ارجاع به جلسه).
4. **مصاحبهٔ ویدیویی:** آپلود ویدیوی ۶۰ دقیقه‌ای ⇒ استخراج صدا ⇒ رونویسی زمان‌دار ⇒ تصحیح نقش گوینده ⇒ ارزیابی.
5. **ارزیابی چند دور:** دور اول فنی و دور دوم HR با شاخص‌های جدا ⇒ دو کارت امتیاز مستقل + امتیاز نهایی ترکیبی.
6. **بازبینی انسانی:** مصاحبه‌گر امتیازی را اصلاح می‌کند ⇒ امتیاز نهایی و رتبه به‌روز، تغییر در Audit، ارزیابی قفل می‌شود.
7. **مرز مستأجر:** کاربر سازمان B با شناسهٔ کاندید سازمان A ⇒ `404`.
8. **دسترسی مصاحبه‌گر:** مصاحبه‌گر فقط کاندیدهای مصاحبهٔ خودش را در فهرست می‌بیند.
9. **نگهداری:** پس از ۱۸۰ روز فایل رزومه و پس از ۹۰ روز مدیای مصاحبه پاک می‌شود، ولی رکورد و امتیاز و Audit می‌ماند.

---

## ۱۰. الزامات فنی و تله‌های شناخته‌شده

### ۱۰٫۱ بک‌اند (الزامی)

| # | قاعده |
|---|---|
| ۱ | `ai_providers.run_chat` **استثنا پرتاب نمی‌کند**؛ متن خالی را باید خودتان به `AIGatewayError` تبدیل کنید |
| ۲ | پیش از هر `run_chat` تابع `ai_providers.ensure_defaults(db, org_id)` را صدا بزنید |
| ۳ | امکان تعیین مدل برای یک فراخوان وجود ندارد؛ مدل از `org_ai_providers.model` می‌آید |
| ۴ | پارس JSON فقط با `ai_providers.parse_json_object` |
| ۵ | بودجه: `ensure_user_budget` با تخمین، و `record_user_usage` با مصرف واقعی |
| ۶ | شمارندهٔ ظرفیت **مستقل** برای کارهای `hr_*` با سقف `Hr_settings.max_concurrent_hr_jobs` |
| ۷ | همهٔ جدول‌های `Hr_*` به `ORG_DELETION_TABLES` اضافه شوند (حذف کامل سازمان) |
| ۸ | کارها قابل ادامه نیستند؛ ری‌استارت سرور آن‌ها را `failed` می‌کند ⇒ «تلاش دوباره» + بررسی وجود نتیجه پیش از فراخوان |
| ۹ | برش صوت با `ffmpeg -f segment` برای فایل‌های بلند (سقف Whisper) |
| ۱۰ | مدل‌ها را مثل `models/jobs.py` بنویسید (`Base` مستقیم؛ `BaseModel` کد مرده است) + ستون جدید روی جدول موجود ⇒ `ensure_platform_columns()` |

### ۱۰٫۲ حریم خصوصی و انطباق

- رضایت کاندید (`consent_ack`) اجباری پیش از آپلود رزومه/مدیا.
- نگهداری محدود: رزومه ۱۸۰ روز، مدیا ۹۰ روز (قابل تغییر در تنظیمات سازمان).
- ویژگی‌های حساس (سن، جنسیت، قومیت، وضعیت تأهل) در پرامپت ارسال نمی‌شوند.
- حالت «بررسی کور» (blind review) اختیاری: پنهان‌کردن نام و مشخصات هویتی از ارزیاب و از پرامپت.
- خروجی AI همیشه «کمک‌کننده» است؛ تصمیم نهایی انسانی است و این در UI و سند چاپی صریح نوشته می‌شود.

---

## ۱۱. نقشهٔ فایل‌ها (پیاده‌سازی)

```
app/backend/
  models/hr_settings.py, hr_positions.py, hr_criteria.py, hr_candidates.py,
  models/hr_candidate_events.py, hr_interviews.py, hr_interview_participants.py,
  models/hr_interview_media.py, hr_interview_transcripts.py, hr_evaluations.py,
  models/hr_interview_questions.py, hr_notes.py                        ← ۱۲ جدول (جدید)
  routers/hr.py                                                        ← روتر واحد /api/v1/hr
  services/hr_resume.py        ← استخراج متن رزومه (docx/متن/PDF متنی) + تشخیص زبان + هش
  services/hr_extract.py       ← پایپ‌لاین ۱: رزومه → JSON ساختاریافته
  services/hr_scoring.py       ← امتیاز وزن‌دار قطعی + برچسب + رتبه
  services/hr_interview_eval.py← پایپ‌لاین ۲: رونویسی → امتیاز شاخص‌محور + شاهد زمان‌دار
  services/hr_questions.py     ← بانک پرسش و تولید پرسش اختصاصی
  services/hr_scheduling.py    ← زمان‌بندی مستقل مصاحبه + ICS + اعلان
  services/mgmt_core.py        ← افزودن ROLE_HR_MANAGER و ROLE_INTERVIEWER + برچسب‌ها
  services/ai_usage.py         ← انواع مصرف جدید: hr_resume_screen, hr_interview_eval
  services/database.py         ← در صورت نیاز: ستون جدید در ensure_platform_columns()
  routers/app_auth.py          ← افزودن جدول‌های Hr_* به ORG_DELETION_TABLES

app/frontend/src/
  pages/hr/Dashboard.tsx, Positions.tsx, PositionDetail.tsx, Candidates.tsx,
  pages/hr/CandidateProfile.tsx, Compare.tsx, Interviews.tsx, InterviewDetail.tsx,
  pages/hr/Criteria.tsx, Questions.tsx, HrSettings.tsx, PrintScorecard.tsx   ← ۱۲ صفحه (جدید)
  lib/hr.ts                    ← کلاینت API + برچسب‌ها + اعتبارسنجی فایل
  components/AppShell.tsx      ← آیتم‌های منوی HR + شرط سوییچ و نقش
  App.tsx                      ← مسیرها بین MODULE_ROUTES_START/END

deploy/
  (بدون تغییر ساختاری؛ فقط .env نمونهٔ HR)
docs/
  HR-DECISIONS.md (حاکم) · HR-ARCHITECTURE.md (این سند) · HR-FEATURES.md · HR-DEPLOYMENT-REPORT.md
```

---

## ۱۲. مسیر تحویل

| مرحله | محتوا | معیار پذیرش |
|---|---|---|
| **M1 (MVP)** | WP1 پایهٔ داده و نقش‌ها · WP2 کاندید و رزومه · WP3 غربال و امتیاز · زمان‌بندی مصاحبه | بارگذاری رزومهٔ Word، رتبه‌بندی با شاهد، زمان‌بندی مصاحبه با دعوت‌نامه |
| **M2** | مدیا و رونویسی مصاحبه · ارزیابی مصاحبه (چند دور) · بازبینی و قفل | رونویسی زمان‌دار + کارت امتیاز هر دور + تأیید انسانی |
| **M3** | داشبورد و گزارش‌ها · نگهداری خودکار · بانک پرسش · مقایسه | خروجی Word/Excel + پاک‌سازی ۱۸۰/۹۰ روزه |
| **M4** | سخت‌سازی، تست مرز مستأجر و ریسپانسیو، مستندات، آموزش | تست‌های سبز + مستند عملیاتی |

**تخمین کل:** MVP ۴–۵ هفته · M2 +۳ هفته · M3 +۲ هفته · M4 +۱٫۵ هفته (جمع ۱۰–۱۲ هفته).

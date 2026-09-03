"""دستیار هوشمند سازمان: بازیابی محتوای واقعی جلسات و دانش\u200cپایهٔ راهنمای سامانه.

این ماژول «مغز بازیابی» دستیار است و هیچ فراخوان شبکه\u200cای انجام نمی\u200cدهد؛ فقط
قطعه\u200cهای مرتبط (context) را می\u200cسازد تا روتر آن\u200cها را به زنجیرهٔ مدل زبانی سازمان
بدهد. دو حالت پشتیبانی می\u200cشود:

* ``MODE_MEETINGS`` — جست\u200cوجوی هوشمند در محتوای واقعی جلسات: عنوان و توضیح جلسه،
  بندهای دستور جلسه، قطعه\u200cهای زمان\u200cدار رونویسی، متن صورتجلسه، مصوبات و اقدامات.
  هر قطعه لینک برگشت به همان جلسه (``/meetings/<id>``) و برچسب زمان دارد.
* ``MODE_GUIDE`` — راهنمای استفاده از سامانه بر پایهٔ قابلیت\u200cهای واقعی پیاده\u200cشده
  (ورود چندسازمانی، جلسات و پیوست، رونویسی، صورتجلسه، مصوبات، تنظیمات و سهمیه).

قواعد کلیدی:

* **مرز مستأجر**: همهٔ کوئری\u200cها با ``organization_id`` زمینهٔ جاری محدود می\u200cشوند.
* **جست\u200cوجوی فارسی**: نرمال\u200cسازی ی/ک/نیم\u200cفاصله با ``fa_normalize`` تا «صورتجلسه»
  و «صورت جلسه» یکسان دیده شوند.
* **بدون توهم**: اگر هیچ قطعهٔ مرتبطی پیدا نشود، بازیابی خالی برمی\u200cگردد و روتر
  پیام راهنما می\u200cدهد، نه پاسخ ساختگی.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from models.action_items import Action_items
from models.agenda_items import Agenda_items
from models.decisions import Decisions
from models.meetings import Meetings
from models.minutes import Minutes
from models.participants import Participants
from models.transcripts import Transcripts
from services.mgmt_core import TenantContext, fa_normalize

MODE_MEETINGS = "meetings"
MODE_GUIDE = "guide"
ALL_MODES = (MODE_MEETINGS, MODE_GUIDE)

MODE_LABELS = {
    MODE_MEETINGS: "جست\u200cوجو در محتوای جلسات",
    MODE_GUIDE: "راهنمای استفاده از سامانه",
}

# سقف\u200cهای محافظه\u200cکارانه تا هزینهٔ حافظه/توکن کنترل\u200cشده بماند.
MAX_MEETINGS_SCANNED = 150
MAX_CHUNK_CHARS = 900
MAX_CONTEXT_CHUNKS = 8
MAX_CONTEXT_CHARS = 9000

# آستانهٔ مطلق و نسبی امتیاز: جلوی ورود قطعه\u200cهای بی\u200cربط به context را می\u200cگیرد تا
# پرسش نامرتبط با «منبع ساختگی» پاسخ نگیرد.
MIN_ABSOLUTE_SCORE = 1.5
MIN_RELATIVE_SCORE = 0.45

# واژه\u200cهای پرتکرار فارسی که ارزش تفکیکی ندارند و از امتیازدهی حذف می\u200cشوند.
_STOPWORDS = {
    "از",
    "به",
    "با",
    "در",
    "که",
    "را",
    "این",
    "آن",
    "برای",
    "های",
    "هاي",
    "یک",
    "است",
    "بود",
    "شد",
    "شده",
    "می",
    "چه",
    "چی",
    "کی",
    "کجا",
    "چرا",
    "چگونه",
    "چطور",
    "و",
    "یا",
    "هم",
    "تا",
    "بر",
    "کن",
    "کنم",
    "کنید",
    "بگو",
    "لطفا",
    "لطفاً",
    "درباره",
    "مورد",
    "روی",
    "من",
    "ما",
    "شما",
    "آیا",
    "کجاست",
    "چیست",
    "هست",
    "کدام",
    "ساخت",
    "دارد",
    "دارم",
    "باشد",
}


@dataclass
class Chunk:
    """یک قطعهٔ قابل استناد برای دستیار."""

    kind: str
    kind_label: str
    title: str
    text: str
    link: str
    meeting_id: Optional[int] = None
    meeting_title: str = ""
    time_label: str = ""
    score: float = 0.0

    def payload(self) -> Dict[str, Any]:
        return {
            "kind": self.kind,
            "kind_label": self.kind_label,
            "title": self.title,
            "snippet": self.text[:400],
            "link": self.link,
            "meeting_id": self.meeting_id,
            "meeting_title": self.meeting_title,
            "time_label": self.time_label,
            "score": round(self.score, 3),
        }


# ---------------------------------------------------------------------------
# دانش\u200cپایهٔ راهنمای سامانه (برگرفته از قابلیت\u200cهای واقعی پیاده\u200cشده)
# ---------------------------------------------------------------------------

GUIDE_SECTIONS: List[Dict[str, str]] = [
    {
        "title": "ورود، انتخاب سازمان و تغییر سازمان",
        "link": "/account",
        "body": (
            "نام کاربری پیش\u200cفرض هر کاربر، شمارهٔ موبایل و رمز اولیه، کد ملی اوست. "
            "اگر یک شخص در چند سازمان حساب فعال داشته باشد، پس از زدن «ورود» فهرست سازمان\u200cها "
            "با نقش هر سازمان نمایش داده می\u200cشود و باید سازمان فعال نشست انتخاب شود. "
            "رمز عبور هر سازمان مستقل است؛ برای ورود به هر سازمان باید رمز همان سازمان وارد شود. "
            "برای جابه\u200cجایی بین سازمان\u200cها بدون خروج کامل، از کلید تغییر سازمان در نوار بالای صفحه "
            "استفاده کنید؛ پس از تغییر، نقش و منوها فوراً از سازمان جدید خوانده می\u200cشوند. "
            "تغییر رمز عبور از بخش «حساب من» انجام می\u200cشود."
        ),
    },
    {
        "title": "نقش\u200cها و سطح دسترسی",
        "link": "/settings?tab=users",
        "body": (
            "سه نقش وجود دارد: «مدیر سازمان» (org_admin) به همهٔ بخش\u200cها از جمله تنظیمات سازمان، "
            "مدیریت کاربران، تنظیمات ایمیل/پیامک و تنظیمات هوش مصنوعی دسترسی دارد؛ «دبیر جلسه» "
            "(secretary) جلسه\u200cهای خود را مدیریت می\u200cکند، صوت بارگذاری و رونویسی می\u200cکند و پیش\u200cنویس "
            "صورتجلسه را تهیه و برای تأیید ارسال می\u200cکند؛ «عضو» (member) جلسات و صورتجلسه\u200cهای مربوط "
            "به خود را می\u200cبیند، حضور خود را اعلام می\u200cکند و اقدامات خود را پیگیری می\u200cکند. "
            "دستیار هوشمند فقط برای مدیر سازمان و دبیر جلسه فعال است و برای نقش عضو نمایش داده نمی\u200cشود."
        ),
    },
    {
        "title": "تعریف جلسه جدید، دستور جلسه و پیوست\u200cها",
        "link": "/meetings",
        "body": (
            "از صفحهٔ «جلسات» و دکمهٔ تعریف جلسه جدید، عنوان، نوع جلسه (هیئت\u200cمدیره، عملیاتی، "
            "پروژه\u200cای، کمیته)، زمان شروع، مدت، محل یا نشانی جلسهٔ آنلاین و دبیر جلسه را ثبت کنید. "
            "در همان فرم می\u200cتوانید بندهای دستور جلسه را با عنوان، زمان پیش\u200cبینی\u200cشده، مسئول و توضیح "
            "اضافه یا حذف کنید و چند فایل پیوست بارگذاری نمایید. پیوست\u200cها در فضای ذخیره\u200cسازی خصوصی "
            "نگه\u200cداری می\u200cشوند و فقط با نشانی امضاشده و موقت قابل دانلود هستند. ویرایش بندها و "
            "پیوست\u200cها برای مدیر سازمان و دبیر همان جلسه مجاز است."
        ),
    },
    {
        "title": "ارسال دعوت\u200cنامه، ایمیل و پیامک",
        "link": "/settings?tab=email",
        "body": (
            "پس از ثبت جلسه، دعوت\u200cنامه برای شرکت\u200cکنندگان ارسال می\u200cشود؛ متن دعوت شامل تاریخ شمسی، "
            "بندهای دستور جلسه و فایل\u200cهای پیوست است و فایل تقویم (ICS) هم ضمیمه می\u200cشود. اگر لازم شد، "
            "با دکمهٔ «ارسال دوبارهٔ دستور جلسه و پیوست\u200cها» می\u200cتوان دعوت را دوباره فرستاد؛ این کار در "
            "لاگ رویدادها ثبت می\u200cشود. تنظیمات SMTP ایمیل و پنل پیامک و همچنین گزارش وضعیت ارسال\u200cها "
            "در بخش تنظیمات سازمان، زبانهٔ ایمیل و پیامک، در دسترس مدیر است."
        ),
    },
    {
        "title": "بارگذاری صوت و رونویسی جلسه",
        "link": "/meetings",
        "body": (
            "در صفحهٔ جزئیات هر جلسه، فایل صوتی جلسه را با تأیید رضایت ضبط بارگذاری کنید. فرمت\u200cهای "
            "مجاز mp3، wav، m4a، ogg، webm، aac و flac است و حجم و مدت فایل به سقف تعیین\u200cشدهٔ سازمان "
            "محدود می\u200cشود. رونویسی به\u200cصورت غیرهمزمان اجرا می\u200cشود؛ پیشرفت کار نمایش داده می\u200cشود و در "
            "صورت خطا با «تلاش دوباره» ادامه می\u200cیابد بدون اینکه هزینهٔ رونویسی دوباره پرداخت شود. "
            "خروجی رونویسی قطعه\u200cبندی زمان\u200cدار دارد و متن آن قابل جست\u200cوجو است."
        ),
    },
    {
        "title": "صورتجلسه: پیش\u200cنویس هوشمند، تأیید و قفل",
        "link": "/meetings",
        "body": (
            "پس از آماده شدن رونویسی، دبیر می\u200cتواند پیش\u200cنویس هوشمند صورتجلسه را تولید کند؛ خروجی شامل "
            "جمع\u200cبندی، متن مذاکرات بر پایهٔ دستور جلسه، مصوبات و اقدامات پیشنهادی است. گردش کار "
            "صورتجلسه چهار وضعیت دارد: پیش\u200cنویس، در انتظار تأیید، تأییدشده و قفل\u200cشده. متن پیش از تأیید "
            "قابل ویرایش است و هر تغییر نسخهٔ جدید می\u200cسازد؛ پس از قفل شدن، صورتجلسه تغییرناپذیر است. "
            "خروجی چاپ و PDF فارسی از نمای چاپ صورتجلسه گرفته می\u200cشود."
        ),
    },
    {
        "title": "مصوبات و اقدامات",
        "link": "/meetings",
        "body": (
            "مصوبات هر جلسه در زبانهٔ «مصوبات و اقدامات» همان جلسه نگه\u200cداری می\u200cشود و برای هر مصوبه "
            "می\u200cتوان اقدام با مسئول، مهلت و وضعیت ثبت کرد. وضعیت\u200cهای اقدام: باز، در حال انجام، "
            "انجام\u200cشده و تأخیر. اقدام باز با مهلت گذشته به\u200cصورت خودکار به وضعیت تأخیر منتقل می\u200cشود و "
            "برای مسئول اعلان ساخته می\u200cشود. صفحهٔ مستقل «اقدامات» حذف شده و پیگیری در دل هر جلسه انجام می\u200cشود."
        ),
    },
    {
        "title": "تنظیمات هوش مصنوعی سازمان، اولویت و جانشینی",
        "link": "/settings?tab=ai",
        "body": (
            "مدیر سازمان در بخش تنظیمات، زبانهٔ هوش مصنوعی، سرویس\u200cهای رونویسی گفتار و مدل زبانی را "
            "پیکربندی می\u200cکند: نشانی سرویس، نام مدل، کلید دسترسی یا نام کاربری و رمز، تفکیک گوینده، "
            "فعال/غیرفعال بودن و ترتیب اولویت. کلیدها رمزنگاری\u200cشده ذخیره می\u200cشوند و فقط به\u200cصورت "
            "ماسک\u200cشده نمایش داده می\u200cشوند. با «تست اتصال» صحت کلید به\u200cصورت واقعی بررسی می\u200cشود. "
            "هنگام اجرا، سرویس\u200cها به ترتیب اولویت امتحان می\u200cشوند و با خطا سرویس بعدی جایگزین می\u200cشود. "
            "اگر هیچ مدل زبانی فعالی با کلید معتبر ثبت نشده باشد، قابلیت\u200cهای متنی هوشمند از جمله "
            "دستیار هوشمند کار نمی\u200cکنند و باید ابتدا یک مدل زبانی فعال شود."
        ),
    },
    {
        "title": "سهمیهٔ مصرف، اعلان\u200cها و لاگ رویدادها",
        "link": "/settings",
        "body": (
            "سهمیهٔ ماهانهٔ دقیقهٔ رونویسی هر سازمان در نوار بالای صفحه نمایش داده می\u200cشود و پیش از شروع "
            "هر کار هوش مصنوعی بررسی می\u200cگردد؛ در صورت کافی نبودن سهمیه، کار شروع نمی\u200cشود و پیام روشن "
            "نمایش داده می\u200cشود. اعلان\u200cهای درون\u200cبرنامه\u200cای (درخواست تأیید صورتجلسه، مهلت نزدیک، دعوت به "
            "جلسه) از آیکون زنگ در دسترس است. همهٔ رویدادهای حساس مثل تغییر تنظیمات، تست اتصال، ارسال "
            "دوبارهٔ دعوت و تأیید یا قفل صورتجلسه در لاگ رویدادها ثبت می\u200cشود."
        ),
    },
    {
        "title": "مدیریت کاربران سازمان",
        "link": "/settings?tab=users",
        "body": (
            "مدیر سازمان از تنظیمات، زبانهٔ کاربران و نقش\u200cها، کاربر جدید می\u200cسازد (نام، نام خانوادگی، "
            "موبایل، کد ملی، جنسیت، ایمیل و نقش). پس از ساخت کاربر، نام کاربری و رمز اولیه به مدیر "
            "نمایش داده می\u200cشود تا به کاربر تحویل دهد. نقش هر کاربر بعداً قابل تغییر است و غیرفعال کردن "
            "حساب بلافاصله دسترسی او را قطع می\u200cکند."
        ),
    },
]


# ---------------------------------------------------------------------------
# امتیازدهی و برش متن
# ---------------------------------------------------------------------------


def query_tokens(question: str) -> List[str]:
    """واژه\u200cهای کلیدی پرسش پس از نرمال\u200cسازی فارسی و حذف واژه\u200cهای پرتکرار."""
    normalized = fa_normalize(question)
    raw = re.split(r"[^\w\u0600-\u06FF]+", normalized)
    tokens: List[str] = []
    for word in raw:
        cleaned = word.strip()
        if len(cleaned) < 2 or cleaned in _STOPWORDS:
            continue
        if cleaned not in tokens:
            tokens.append(cleaned)
    return tokens[:12]


def score_text(text: str, tokens: List[str]) -> float:
    """امتیاز سادهٔ تکرار واژه\u200cهای کلیدی؛ تطبیق کامل واژه وزن بیشتری می\u200cگیرد."""
    if not tokens:
        return 0.0
    normalized = fa_normalize(text)
    if not normalized:
        return 0.0
    words = set(re.split(r"[^\w\u0600-\u06FF]+", normalized))
    score = 0.0
    for token in tokens:
        occurrences = normalized.count(token)
        if occurrences:
            score += 1.0 + min(occurrences - 1, 3) * 0.25
        if token in words:
            score += 0.5
    return score


def trim_around_match(text: str, tokens: List[str], limit: int = MAX_CHUNK_CHARS) -> str:
    """برش متن حول نخستین تطبیق تا context کوتاه و مرتبط بماند."""
    body = re.sub(r"[ \t]+", " ", (text or "").strip())
    if len(body) <= limit:
        return body
    normalized = fa_normalize(body)
    position = -1
    for token in tokens:
        found = normalized.find(token)
        if found >= 0 and (position < 0 or found < position):
            position = found
    if position < 0:
        return body[:limit].rstrip() + " …"
    start = max(position - limit // 3, 0)
    snippet = body[start : start + limit].strip()
    prefix = "… " if start > 0 else ""
    suffix = " …" if start + limit < len(body) else ""
    return f"{prefix}{snippet}{suffix}"


def ms_label(start_ms: Any) -> str:
    """برچسب زمان قطعهٔ رونویسی به قالب دقیقه:ثانیه."""
    try:
        total = max(int(start_ms or 0), 0) // 1000
    except (TypeError, ValueError):
        return ""
    return f"{total // 60:02d}:{total % 60:02d}"


def _split_paragraphs(text: str, size: int = 700) -> List[str]:
    """تقسیم متن بلند به پاراگراف\u200cهای قابل استناد."""
    body = (text or "").strip()
    if not body:
        return []
    parts = [part.strip() for part in re.split(r"\n{2,}", body) if part.strip()]
    if not parts:
        parts = [body]
    chunks: List[str] = []
    for part in parts:
        if len(part) <= size:
            chunks.append(part)
            continue
        for index in range(0, len(part), size):
            piece = part[index : index + size].strip()
            if piece:
                chunks.append(piece)
    return chunks


# ---------------------------------------------------------------------------
# ساخت قطعه\u200cهای محتوای جلسات
# ---------------------------------------------------------------------------


async def collect_meeting_chunks(db: AsyncSession, ctx: TenantContext) -> List[Chunk]:
    """جمع\u200cآوری قطعه\u200cهای قابل استناد از محتوای واقعی جلسات همین سازمان."""
    org_id = ctx.organization_id

    meetings_result = await db.execute(
        select(Meetings)
        .where(Meetings.organization_id == org_id)
        .order_by(Meetings.starts_at.desc())
        .limit(MAX_MEETINGS_SCANNED)
    )
    meetings = list(meetings_result.scalars().all())
    if not meetings:
        return []

    titles = {int(meeting.id): (meeting.title or "جلسهٔ بدون عنوان") for meeting in meetings}
    allowed = set(titles.keys())
    chunks: List[Chunk] = []

    def link_of(meeting_id: int) -> str:
        return f"/meetings/{meeting_id}"

    for meeting in meetings:
        meeting_id = int(meeting.id)
        header = " — ".join(
            part
            for part in [
                meeting.title or "",
                meeting.meeting_type or "",
                meeting.location or meeting.online_url or "",
                f"دبیر: {meeting.secretary_name}" if meeting.secretary_name else "",
                (meeting.description or ""),
            ]
            if part
        )
        chunks.append(
            Chunk(
                kind="meeting",
                kind_label="اطلاعات جلسه",
                title=titles[meeting_id],
                text=header,
                link=link_of(meeting_id),
                meeting_id=meeting_id,
                meeting_title=titles[meeting_id],
            )
        )

    agenda_result = await db.execute(
        select(Agenda_items).where(Agenda_items.organization_id == org_id)
    )
    for item in agenda_result.scalars().all():
        meeting_id = int(item.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        text = " — ".join(
            part
            for part in [item.title or "", item.notes or "", f"مسئول: {item.owner_name}" if item.owner_name else ""]
            if part
        )
        if not text.strip():
            continue
        chunks.append(
            Chunk(
                kind="agenda",
                kind_label="بند دستور جلسه",
                title=item.title or "بند دستور جلسه",
                text=text,
                link=link_of(meeting_id),
                meeting_id=meeting_id,
                meeting_title=titles[meeting_id],
            )
        )

    transcripts_result = await db.execute(
        select(Transcripts).where(Transcripts.organization_id == org_id)
    )
    for transcript in transcripts_result.scalars().all():
        meeting_id = int(transcript.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        try:
            segments = json.loads(transcript.segments_json or "[]")
        except (TypeError, ValueError):
            segments = []
        if isinstance(segments, list) and segments:
            buffer: List[str] = []
            start_ms: Any = None
            speakers: List[str] = []
            for segment in segments:
                if not isinstance(segment, dict):
                    continue
                text = str(segment.get("text") or "").strip()
                if not text:
                    continue
                if start_ms is None:
                    start_ms = segment.get("start_ms")
                speaker = str(segment.get("speaker") or "").strip()
                if speaker and speaker not in speakers:
                    speakers.append(speaker)
                buffer.append(text)
                if sum(len(part) for part in buffer) >= 600:
                    chunks.append(
                        _transcript_chunk(buffer, speakers, start_ms, meeting_id, titles[meeting_id])
                    )
                    buffer, speakers, start_ms = [], [], None
            if buffer:
                chunks.append(
                    _transcript_chunk(buffer, speakers, start_ms, meeting_id, titles[meeting_id])
                )
        else:
            for piece in _split_paragraphs(transcript.full_text or ""):
                chunks.append(
                    Chunk(
                        kind="transcript",
                        kind_label="متن رونویسی",
                        title=f"رونویسی «{titles[meeting_id]}»",
                        text=piece,
                        link=link_of(meeting_id),
                        meeting_id=meeting_id,
                        meeting_title=titles[meeting_id],
                    )
                )

    minutes_result = await db.execute(select(Minutes).where(Minutes.organization_id == org_id))
    for minutes in minutes_result.scalars().all():
        meeting_id = int(minutes.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        if (minutes.summary or "").strip():
            chunks.append(
                Chunk(
                    kind="minutes",
                    kind_label="جمع\u200cبندی صورتجلسه",
                    title=f"جمع\u200cبندی «{titles[meeting_id]}»",
                    text=minutes.summary or "",
                    link=link_of(meeting_id),
                    meeting_id=meeting_id,
                    meeting_title=titles[meeting_id],
                )
            )
        for piece in _split_paragraphs(minutes.body_markdown or ""):
            chunks.append(
                Chunk(
                    kind="minutes",
                    kind_label="متن صورتجلسه",
                    title=f"صورتجلسهٔ «{titles[meeting_id]}»",
                    text=piece,
                    link=link_of(meeting_id),
                    meeting_id=meeting_id,
                    meeting_title=titles[meeting_id],
                )
            )

    decisions_result = await db.execute(select(Decisions).where(Decisions.organization_id == org_id))
    for decision in decisions_result.scalars().all():
        meeting_id = int(decision.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        chunks.append(
            Chunk(
                kind="decision",
                kind_label="مصوبه",
                title=decision.title or "مصوبه",
                text=" — ".join(part for part in [decision.title or "", decision.description or ""] if part),
                link=link_of(meeting_id),
                meeting_id=meeting_id,
                meeting_title=titles[meeting_id],
            )
        )

    actions_result = await db.execute(
        select(Action_items).where(Action_items.organization_id == org_id)
    )
    for action in actions_result.scalars().all():
        meeting_id = int(action.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        text = " — ".join(
            part
            for part in [
                action.title or "",
                action.description or "",
                f"مسئول: {action.owner_name}" if action.owner_name else "",
                f"مهلت: {action.due_date}" if action.due_date else "",
                f"وضعیت: {action.status}" if action.status else "",
                action.progress_note or "",
            ]
            if part
        )
        chunks.append(
            Chunk(
                kind="action",
                kind_label="اقدام",
                title=action.title or "اقدام",
                text=text,
                link=link_of(meeting_id),
                meeting_id=meeting_id,
                meeting_title=titles[meeting_id],
            )
        )

    # حاضران و مدعوین هر جلسه (برای پرسش‌هایی مثل «چه کسانی حاضر بودند؟»)
    participants_result = await db.execute(
        select(Participants).where(Participants.organization_id == org_id)
    )
    participants_by_meeting: Dict[int, List[str]] = {}
    for participant in participants_result.scalars().all():
        meeting_id = int(participant.meeting_id or 0)
        if meeting_id not in allowed:
            continue
        name = (participant.full_name or "").strip()
        if not name:
            continue
        entry = name + (" (حاضر)" if participant.attended else " (غایب)")
        participants_by_meeting.setdefault(meeting_id, []).append(entry)
    for meeting_id, names in participants_by_meeting.items():
        chunks.append(
            Chunk(
                kind="participants",
                kind_label="حاضران جلسه",
                title=f"حاضران «{titles[meeting_id]}»",
                text="حاضران/مدعوین: " + "، ".join(names),
                link=link_of(meeting_id),
                meeting_id=meeting_id,
                meeting_title=titles[meeting_id],
            )
        )

    return chunks


def _transcript_chunk(
    buffer: List[str],
    speakers: List[str],
    start_ms: Any,
    meeting_id: int,
    meeting_title: str,
) -> Chunk:
    label = ms_label(start_ms)
    speaker_note = f"گویندگان: {'، '.join(speakers)}. " if speakers else ""
    return Chunk(
        kind="transcript",
        kind_label="قطعهٔ رونویسی",
        title=f"رونویسی «{meeting_title}»" + (f" — دقیقهٔ {label}" if label else ""),
        text=f"{speaker_note}{' '.join(buffer)}",
        link=f"/meetings/{meeting_id}",
        meeting_id=meeting_id,
        meeting_title=meeting_title,
        time_label=label,
    )


# ---------------------------------------------------------------------------
# جست\u200cوجو
# ---------------------------------------------------------------------------


def rank_chunks(chunks: List[Chunk], tokens: List[str], top_k: int = MAX_CONTEXT_CHUNKS) -> List[Chunk]:
    """رتبه\u200cبندی قطعه\u200cها و برش متن هر قطعه حول تطبیق."""
    scored: List[Chunk] = []
    for chunk in chunks:
        score = score_text(f"{chunk.title} {chunk.text}", tokens)
        if score <= 0:
            continue
        chunk.score = score
        chunk.text = trim_around_match(chunk.text, tokens)
        scored.append(chunk)
    if not scored:
        return []
    scored.sort(key=lambda item: item.score, reverse=True)
    best = scored[0].score
    threshold = max(MIN_ABSOLUTE_SCORE, best * MIN_RELATIVE_SCORE)
    return [chunk for chunk in scored if chunk.score >= threshold][:top_k]


async def search_meetings(
    db: AsyncSession, ctx: TenantContext, question: str, top_k: int = MAX_CONTEXT_CHUNKS
) -> List[Chunk]:
    tokens = query_tokens(question)
    if not tokens:
        return []
    chunks = await collect_meeting_chunks(db, ctx)
    return rank_chunks(chunks, tokens, top_k)


def search_guide(question: str, top_k: int = 5) -> List[Chunk]:
    tokens = query_tokens(question)
    chunks = [
        Chunk(
            kind="guide",
            kind_label="راهنمای سامانه",
            title=section["title"],
            text=section["body"],
            link=section["link"],
        )
        for section in GUIDE_SECTIONS
    ]
    if not tokens:
        return chunks[:top_k]
    ranked = rank_chunks([chunk for chunk in chunks], tokens, top_k)
    if ranked:
        return ranked
    # پرسش عمومی: بخش\u200cهای پایه به\u200cعنوان زمینهٔ پیش\u200cفرض برگردانده می\u200cشود.
    return chunks[:3]


# ---------------------------------------------------------------------------
# ساخت prompt
# ---------------------------------------------------------------------------

MEETINGS_SYSTEM_PROMPT = (
    "تو دستیار هوشمند «سامانهٔ مدیریت جلسات» هستی و فقط بر پایهٔ قطعه\u200cهای زمینهٔ داده\u200cشده "
    "پاسخ می\u200cدهی. اگر پاسخ در زمینه نبود، صریح بگو که در محتوای جلسات ثبت\u200cشده چیزی پیدا نشد و "
    "پیشنهاد بده پرسش دقیق\u200cتر شود. هرگز اطلاعات از خودت نساز و به جلسه\u200cای که در زمینه نیست ارجاع نده. "
    "پاسخ فارسی، کوتاه و ساختاریافته باشد و در متن، عنوان جلسهٔ منبع را داخل گیومه ذکر کن. "
    "اگر قطعه زمان دارد، زمان را هم بنویس."
)

GUIDE_SYSTEM_PROMPT = (
    "تو راهنمای کاربری «سامانهٔ مدیریت جلسات» هستی و فقط بر پایهٔ بخش\u200cهای راهنمای داده\u200cشده پاسخ می\u200cدهی. "
    "قابلیتی که در راهنما نیست را ابداع نکن؛ اگر قابلیت وجود ندارد، صریح بگو در این نسخه پشتیبانی نمی\u200cشود. "
    "پاسخ فارسی، گام\u200cبه\u200cگام و عملی باشد و مسیر رسیدن به هر بخش را بنویسی."
)


def build_context_text(chunks: List[Chunk]) -> str:
    """متن زمینه با شمارهٔ منبع تا مدل بتواند به آن ارجاع دهد."""
    parts: List[str] = []
    total = 0
    for index, chunk in enumerate(chunks, start=1):
        head = f"[منبع {index}] نوع: {chunk.kind_label}"
        if chunk.meeting_title:
            head += f" | جلسه: «{chunk.meeting_title}»"
        if chunk.time_label:
            head += f" | زمان: {chunk.time_label}"
        block = f"{head}\n{chunk.text}"
        if total + len(block) > MAX_CONTEXT_CHARS:
            break
        parts.append(block)
        total += len(block)
    return "\n\n".join(parts)


def build_prompt(mode: str, question: str, chunks: List[Chunk], ctx: TenantContext) -> Dict[str, str]:
    context_text = build_context_text(chunks)
    if mode == MODE_GUIDE:
        user_prompt = (
            f"نقش کاربر پرسش\u200cکننده: {ctx.role}\n"
            f"پرسش کاربر: {question.strip()}\n\n"
            f"بخش\u200cهای راهنمای سامانه:\n{context_text}\n\n"
            "بر پایهٔ راهنمای بالا پاسخ بده و در پایان مسیر یا صفحهٔ مربوط را اشاره کن."
        )
        return {"system": GUIDE_SYSTEM_PROMPT, "user": user_prompt}

    user_prompt = (
        f"سازمان: {ctx.organization.name}\n"
        f"پرسش کاربر: {question.strip()}\n\n"
        f"قطعه\u200cهای محتوای جلسات:\n{context_text}\n\n"
        "با استناد به همین قطعه\u200cها پاسخ بده. اگر چند جلسه مرتبط است، هر مورد را جدا و با عنوان جلسه بنویس."
    )
    return {"system": MEETINGS_SYSTEM_PROMPT, "user": user_prompt}


def fallback_answer(mode: str, chunks: List[Chunk]) -> str:
    """پاسخ بدون مدل زبانی: خلاصهٔ قطعه\u200cهای یافته\u200cشده تا قابلیت بی\u200cفایده نشود."""
    if not chunks:
        return (
            "در محتوای ثبت\u200cشدهٔ سازمان موردی مرتبط با این پرسش پیدا نشد."
            if mode == MODE_MEETINGS
            else "برای این پرسش بخش مرتبطی در راهنما پیدا نشد؛ پرسش را کمی دقیق\u200cتر بنویسید."
        )
    lines = [
        "مدل زبانی فعالی برای تولید پاسخ در دسترس نیست، اما این بخش\u200cهای مرتبط پیدا شد:",
    ]
    for index, chunk in enumerate(chunks[:5], start=1):
        head = chunk.title
        if chunk.time_label:
            head += f" (دقیقهٔ {chunk.time_label})"
        lines.append(f"{index}. {head} — {chunk.text[:220]}")
    return "\n".join(lines)
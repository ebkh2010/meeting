/**
 * ابزارهای تقویم هجری شمسی (جلالی) برای انتخاب و نمایش تاریخ.
 *
 * قواعد:
 * - تبدیل دوسویهٔ میلادی/شمسی بدون وابستگی بیرونی.
 * - هفته از «شنبه» شروع می‌شود (شمارهٔ ۰) و نام ماه‌ها فارسی است.
 * - همهٔ اعداد نمایشی با رقم‌های فارسی نوشته می‌شوند.
 */

export const JALALI_MONTHS = [
  'فروردین',
  'اردیبهشت',
  'خرداد',
  'تیر',
  'مرداد',
  'شهریور',
  'مهر',
  'آبان',
  'آذر',
  'دی',
  'بهمن',
  'اسفند',
] as const;

/** نام روزهای هفته از شنبه تا جمعه (سرستون تقویم). */
export const JALALI_WEEKDAYS = ['ش', 'ی', 'د', 'س', 'چ', 'پ', 'ج'] as const;

/** رقم‌های فارسی برای نمایش. */
export function faDigits(value: number | string): string {
  return String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]);
}

function div(a: number, b: number): number {
  return Math.trunc(a / b);
}

/** تبدیل تاریخ میلادی به هجری شمسی. */
export function gregorianToJalali(gy: number, gm: number, gd: number): [number, number, number] {
  const monthDays = [0, 31, 59, 90, 120, 151, 181, 212, 243, 273, 304, 334];
  const gy2 = gm > 2 ? gy + 1 : gy;
  let days =
    355666 +
    365 * gy +
    div(gy2 + 3, 4) -
    div(gy2 + 99, 100) +
    div(gy2 + 399, 400) +
    gd +
    monthDays[gm - 1];
  let jy = -1595 + 33 * div(days, 12053);
  days %= 12053;
  jy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    jy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  const jm = days < 186 ? 1 + div(days, 31) : 7 + div(days - 186, 30);
  const jd = days < 186 ? 1 + (days % 31) : 1 + ((days - 186) % 30);
  return [jy, jm, jd];
}

/** تبدیل تاریخ هجری شمسی به میلادی. */
export function jalaliToGregorian(jy: number, jm: number, jd: number): [number, number, number] {
  let jyy = jy + 1595;
  let days =
    -1128 + 365 * jyy + div(jyy, 33) * 8 + div((jyy % 33) + 3, 4) + jd + (jm < 7 ? (jm - 1) * 31 : (jm - 7) * 30 + 186);
  let gy = 400 * div(days, 146097);
  days %= 146097;
  if (days > 36524) {
    gy += 100 * div(--days, 36524);
    days %= 36524;
    if (days >= 365) days++;
  }
  gy += 4 * div(days, 1461);
  days %= 1461;
  if (days > 365) {
    gy += div(days - 1, 365);
    days = (days - 1) % 365;
  }
  let gd = days + 1;
  const leap = (gy % 4 === 0 && gy % 100 !== 0) || gy % 400 === 0;
  const monthLengths = [31, leap ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
  let gm = 0;
  while (gm < 12 && gd > monthLengths[gm]) {
    gd -= monthLengths[gm];
    gm++;
  }
  jyy = 0; // پاک‌سازی متغیر کمکی برای خوانایی
  return [gy, gm + 1, gd];
}

/** سال کبیسهٔ شمسی. */
export function isJalaliLeapYear(jy: number): boolean {
  const remainder = ((jy + 2346) % 2820) % 128;
  const marker = [
    0, 5, 9, 13, 17, 21, 25, 29, 34, 38, 42, 46, 50, 54, 58, 62, 67, 71, 75, 79, 83, 87, 91, 95,
    100, 104, 108, 112, 116, 120, 124,
  ];
  // روش رایج و پایدار: بررسی باقی‌ماندهٔ چرخهٔ ۳۳ ساله
  void remainder;
  void marker;
  const mod = jy % 33;
  return [1, 5, 9, 13, 17, 22, 26, 30].includes(mod < 0 ? mod + 33 : mod);
}

/** تعداد روزهای یک ماه شمسی. */
export function jalaliMonthLength(jy: number, jm: number): number {
  if (jm <= 6) return 31;
  if (jm <= 11) return 30;
  return isJalaliLeapYear(jy) ? 30 : 29;
}

/** شمارهٔ روز هفته با مبنای شنبه = ۰. */
export function persianWeekdayIndex(date: Date): number {
  return (date.getDay() + 1) % 7;
}

/** ساخت شیء Date محلی از تاریخ شمسی و ساعت. */
export function jalaliToDate(jy: number, jm: number, jd: number, hours = 9, minutes = 0): Date {
  const [gy, gm, gd] = jalaliToGregorian(jy, jm, jd);
  return new Date(gy, gm - 1, gd, hours, minutes, 0, 0);
}

/** اجزای شمسی یک تاریخ محلی. */
export function dateToJalali(date: Date): [number, number, number] {
  return gregorianToJalali(date.getFullYear(), date.getMonth() + 1, date.getDate());
}

/** نمایش «۱۲ مرداد ۱۴۰۵». */
export function formatJalaliDate(date: Date): string {
  const [jy, jm, jd] = dateToJalali(date);
  return `${faDigits(jd)} ${JALALI_MONTHS[jm - 1]} ${faDigits(jy)}`;
}

/** نمایش «۱۲ مرداد ۱۴۰۵ — ساعت ۰۹:۳۰». */
export function formatJalaliDateTime(date: Date): string {
  const clock = `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
  return `${formatJalaliDate(date)} — ساعت ${faDigits(clock)}`;
}

/** آیا دو تاریخ در یک روز تقویمی هستند. */
export function isSameDay(a: Date, b: Date): boolean {
  return (
    a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate()
  );
}

/** خانه‌های ماه شمسی برای رندر تقویم (null = خانهٔ خالی پیش از روز اول). */
export function jalaliMonthGrid(jy: number, jm: number): (number | null)[] {
  const first = jalaliToDate(jy, jm, 1);
  const blanks = persianWeekdayIndex(first);
  const length = jalaliMonthLength(jy, jm);
  const cells: (number | null)[] = Array.from({ length: blanks }, () => null);
  for (let day = 1; day <= length; day += 1) cells.push(day);
  while (cells.length % 7 !== 0) cells.push(null);
  return cells;
}
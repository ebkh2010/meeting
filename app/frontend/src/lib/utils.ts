import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/* ------------------------------------------------------------------ */
/* نرمال‌سازی فارسی (هم‌ارز fa_normalize سمت سرور) برای جست‌وجو و برجسته‌سازی */
/* ------------------------------------------------------------------ */

const FA_TRANSLATION: Record<string, string> = {
  ي: 'ی',
  ك: 'ک',
  آ: 'ا',
  إ: 'ا',
  أ: 'ا',
  ؤ: 'و',
  ة: 'ه',
  ۀ: 'ه',
  ى: 'ی',
  '\u200c': ' ', // نیم‌فاصله
};

const FA_DIACRITICS = /[\u064B-\u0652\u0640]/;

/** یکسان‌سازی ی/ک/نیم‌فاصله و اعراب برای مقایسهٔ متن فارسی. */
export function faNormalizeText(text: string): string {
  let out = '';
  for (const ch of text) {
    const mapped = FA_TRANSLATION[ch] ?? ch;
    if (FA_DIACRITICS.test(mapped)) continue;
    if (/\s/.test(mapped)) {
      if (out.endsWith(' ')) continue;
      out += ' ';
    } else {
      out += mapped.toLowerCase();
    }
  }
  return out.trim();
}

export interface TextRange {
  /** شاخص آغاز در متن اصلی (شامل). */
  start: number;
  /** شاخص پایان در متن اصلی (نامشمول). */
  end: number;
}

/**
 * بازه‌های وقوع عبارت جست‌وجو در متن، با نگاشت شاخص‌ها از متن نرمال‌شده به متن
 * اصلی تا برجسته‌سازی دقیق حتی با نیم‌فاصله/اعراب کار کند.
 */
export function findQueryRanges(text: string, query: string): TextRange[] {
  const q = faNormalizeText(query);
  if (!q || !text) return [];
  const norm: string[] = [];
  const orig: number[] = [];
  for (let i = 0; i < text.length; i++) {
    const ch = text[i];
    let mapped = FA_TRANSLATION[ch] ?? ch;
    if (FA_DIACRITICS.test(mapped)) continue;
    if (/\s/.test(mapped)) {
      if (norm.length > 0 && norm[norm.length - 1] === ' ') continue;
      mapped = ' ';
    }
    norm.push(mapped.toLowerCase());
    orig.push(i);
  }
  let startIdx = 0;
  let endIdx = norm.length;
  while (startIdx < endIdx && norm[startIdx] === ' ') startIdx += 1;
  while (endIdx > startIdx && norm[endIdx - 1] === ' ') endIdx -= 1;
  const normalized = norm.slice(startIdx, endIdx).join('');
  const index = orig.slice(startIdx, endIdx);
  const ranges: TextRange[] = [];
  if (q.length === 0 || q.length > normalized.length) return ranges;
  let from = 0;
  while (from + q.length <= normalized.length) {
    const pos = normalized.indexOf(q, from);
    if (pos < 0) break;
    ranges.push({ start: index[pos], end: index[pos + q.length - 1] + 1 });
    from = pos + q.length;
  }
  return ranges;
}

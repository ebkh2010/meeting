/**
 * برجسته‌سازی عبارت جست‌وجو در یک متن ساده با <mark>.
 * مقایسه بر پایهٔ نرمال‌سازی فارسی انجام می‌شود تا ی/ک عربی و نیم‌فاصله هم پیدا شوند.
 */
import { useMemo } from 'react';
import { findQueryRanges } from '@/lib/utils';

export default function HighlightText({
  text,
  query,
  className,
}: {
  text: string;
  query?: string;
  className?: string;
}) {
  const parts = useMemo(() => {
    const ranges = query ? findQueryRanges(text, query) : [];
    if (ranges.length === 0) return null;
    const out: Array<{ t: string; mark?: boolean }> = [];
    let last = 0;
    for (const range of ranges) {
      if (range.start > last) out.push({ t: text.slice(last, range.start) });
      out.push({ t: text.slice(range.start, range.end), mark: true });
      last = range.end;
    }
    if (last < text.length) out.push({ t: text.slice(last) });
    return out;
  }, [text, query]);

  if (!parts) return <>{text}</>;
  return (
    <span className={className}>
      {parts.map((part, index) =>
        part.mark ? (
          <mark key={index} className="rounded bg-primary/25 px-0.5 text-inherit">
            {part.t}
          </mark>
        ) : (
          part.t
        ),
      )}
    </span>
  );
}

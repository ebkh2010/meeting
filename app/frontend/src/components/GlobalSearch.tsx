/**
 * جست‌وجوی سراسری در هدر فضای کاری — در همهٔ صفحه‌های داخل `AppShell` در دسترس است.
 *
 * رفتار:
 *  • از سه نویسه به بعد و با تأخیر کوتاه، نتیجه‌ها زنده زیر کادر می‌آیند.
 *  • هر بندِ یافت‌شده پیوندی به همان جلسه با `scope` و `q` است؛ صفحهٔ مقصد همان
 *    برگه را باز می‌کند و واژه را برجسته می‌کند (همان مکانیزم نتایج جست‌وجوی
 *    صفحهٔ جلسات، بدون کد تکراری).
 *  • Enter کاربر را به فهرست کامل نتایج در صفحهٔ جلسات می‌برد.
 */
import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Loader2, Search, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import HighlightText from '@/components/HighlightText';
import { api, errorMessage, formatDateTime, Meeting, toPersianDigits } from '@/lib/mgmt';
import { cn } from '@/lib/utils';

/** کمینهٔ نویسه برای شروع جست‌وجو (هم‌راستا با اعتبارسنجی بک‌اند). */
const MIN_CHARS = 3;
/** تأخیر تایپ تا هر کلید یک درخواست نسازد. */
const DEBOUNCE_MS = 350;
/** سقف نتیجه‌های نمایش‌داده‌شده در کادر هدر. */
const MAX_RESULTS = 6;

export default function GlobalSearch({ className }: { className?: string }) {
  const navigate = useNavigate();
  const [value, setValue] = useState('');
  const [items, setItems] = useState<Meeting[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [open, setOpen] = useState(false);
  const boxRef = useRef<HTMLDivElement>(null);

  const query = value.trim();

  // بستن کادر با کلیک بیرون از آن
  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent) => {
      if (boxRef.current && !boxRef.current.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onPointerDown);
    return () => document.removeEventListener('mousedown', onPointerDown);
  }, [open]);

  // جست‌وجوی زنده با تأخیر؛ درخواست‌های قدیمی با پرچم `alive` بی‌اثر می‌شوند.
  useEffect(() => {
    if (query.length < MIN_CHARS) {
      setItems([]);
      setError('');
      setLoading(false);
      return;
    }
    let alive = true;
    setLoading(true);
    const timer = window.setTimeout(() => {
      void (async () => {
        try {
          const data = await api.listMeetings('all', query, 'all');
          if (!alive) return;
          setItems(data.items.slice(0, MAX_RESULTS));
          setError('');
          setOpen(true);
        } catch (err) {
          if (!alive) return;
          setItems([]);
          setError(errorMessage(err, 'جست‌وجو ناموفق بود.'));
          setOpen(true);
        } finally {
          if (alive) setLoading(false);
        }
      })();
    }, DEBOUNCE_MS);
    return () => {
      alive = false;
      window.clearTimeout(timer);
    };
  }, [query]);

  const detailHref = (meeting: Meeting, scopeOverride?: string) => {
    const params = new URLSearchParams();
    const scope = scopeOverride ?? meeting.matches?.[0]?.scope;
    if (query) params.set('q', query);
    if (scope) params.set('scope', scope);
    const suffix = params.toString();
    return `/meetings/${meeting.id}${suffix ? `?${suffix}` : ''}`;
  };

  const goToMeeting = (meeting: Meeting, scopeOverride?: string) => {
    setOpen(false);
    navigate(detailHref(meeting, scopeOverride));
  };

  const submit = () => {
    setOpen(false);
    navigate(query ? `/meetings?q=${encodeURIComponent(query)}` : '/meetings');
  };

  const clear = () => {
    setValue('');
    setItems([]);
    setError('');
    setOpen(false);
  };

  return (
    <div ref={boxRef} className={cn('relative', className)}>
      <form
        onSubmit={(event) => {
          event.preventDefault();
          submit();
        }}
      >
        <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          value={value}
          onChange={(event) => setValue(event.target.value)}
          onFocus={() => {
            if (query.length >= MIN_CHARS && (items.length > 0 || error)) setOpen(true);
          }}
          onKeyDown={(event) => {
            if (event.key === 'Escape') setOpen(false);
          }}
          placeholder="جست‌وجو در جلسات…"
          className="h-9 px-9"
          aria-label="جست‌وجوی سراسری در جلسات"
        />
        {value ? (
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="absolute left-1 top-1/2 h-7 w-7 -translate-y-1/2"
            onClick={clear}
            aria-label="پاک کردن جست‌وجو"
          >
            <X className="h-4 w-4" />
          </Button>
        ) : null}
      </form>

      {open && query.length >= MIN_CHARS && (
        <div className="absolute inset-x-0 top-full z-50 mt-1 max-h-[70vh] overflow-y-auto rounded-md border border-border bg-popover p-2 shadow-lg">
          {loading && items.length === 0 && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />
              در حال جست‌وجو…
            </div>
          )}

          {error && <p className="px-2 py-3 text-xs text-destructive">{error}</p>}

          {!loading && !error && items.length === 0 && (
            <p className="px-2 py-3 text-xs text-muted-foreground">
              نتیجه‌ای برای «{query}» پیدا نشد.
            </p>
          )}

          {items.map((meeting) => (
            <div key={meeting.id} className="rounded-md p-1">
              <button
                type="button"
                onClick={() => goToMeeting(meeting)}
                className="flex w-full flex-col gap-0.5 rounded-md px-2 py-1.5 text-start transition-colors hover:bg-accent"
              >
                <span className="truncate text-sm font-medium">
                  <HighlightText text={meeting.title} query={query} />
                </span>
                <span className="text-[11px] text-muted-foreground">
                  {formatDateTime(meeting.starts_at)}
                  {meeting.matches?.length
                    ? ` · ${toPersianDigits(meeting.matches.length)} بند یافت‌شده`
                    : ''}
                </span>
              </button>

              {(meeting.matches ?? []).slice(0, 2).map((match, index) => (
                <button
                  key={`${match.scope}-${index}`}
                  type="button"
                  onClick={() => goToMeeting(meeting, match.scope)}
                  className="flex w-full flex-col gap-0.5 rounded-md px-2 py-1 text-start transition-colors hover:bg-accent"
                >
                  <span className="text-[10px] text-muted-foreground">{match.label}</span>
                  <span className="line-clamp-2 text-[11px] leading-5">
                    <HighlightText text={match.snippet} query={query} />
                  </span>
                </button>
              ))}
            </div>
          ))}

          {items.length > 0 && (
            <button
              type="button"
              onClick={submit}
              className="mt-1 w-full rounded-md px-2 py-2 text-center text-xs font-medium text-primary transition-colors hover:bg-accent"
            >
              دیدن همهٔ نتایج در صفحهٔ جلسات
            </button>
          )}
        </div>
      )}
    </div>
  );
}

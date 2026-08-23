/**
 * پنل شناور «دستیار هوشمند» — در همهٔ صفحه‌های فضای کاری و فقط برای مدیر سازمان و دبیر جلسه.
 *
 * دو حالت دارد:
 *  ۱) جست‌وجوی هوشمند در محتوای واقعی جلسات (رونویسی، صورتجلسه، مصوبات، اقدامات)
 *     با نمایش منابع و لینک برگشت به همان جلسه.
 *  ۲) راهنمای استفاده از سامانه بر پایهٔ دانش‌پایهٔ قابلیت‌های واقعی.
 *
 * دکمهٔ شناور برای نقش «عضو» رندر نمی‌شود و بک‌اند نیز همان مسیر را با ۴۰۳ رد می‌کند.
 * اگر هیچ مدل زبانی فعالی در سازمان نباشد، پیام راهنما نمایش داده می‌شود و نتایج
 * جست‌وجو (بدون تولید متن) همچنان در دسترس است.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { Bot, Loader2, SendHorizonal, Sparkles, X } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Textarea } from '@/components/ui/textarea';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AssistantAnswer,
  AssistantMode,
  assistantApi,
  AssistantStatus,
} from '@/lib/assistant';
import { errorMessage } from '@/lib/mgmt';

/** نمونه‌پرسش‌های هر حالت تا کاربر نقطهٔ شروع داشته باشد. */
const SAMPLES: Record<AssistantMode, string[]> = {
  meetings: [
    'دربارهٔ بودجه چه مصوبه‌ای داشتیم؟',
    'در جلسات اخیر چه اقداماتی معوق مانده است؟',
    'خلاصهٔ جلسهٔ هیئت‌مدیره چه بود؟',
  ],
  guide: [
    'چطور جلسهٔ جدید با دستور جلسه و پیوست ثبت کنم؟',
    'چگونه صورتجلسه را تأیید و قفل کنم؟',
    'تنظیم مدل زبانی سازمان از کجاست؟',
  ],
};

interface AssistantPanelProps {
  /** نقش کاربر جاری؛ پنل فقط برای مدیر سازمان و دبیر جلسه فعال است. */
  allowed: boolean;
}

export default function AssistantPanel({ allowed }: AssistantPanelProps) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState<AssistantMode>('meetings');
  const [question, setQuestion] = useState('');
  const [status, setStatus] = useState<AssistantStatus | null>(null);
  const [answer, setAnswer] = useState<AssistantAnswer | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const statusLoaded = useRef(false);

  const loadStatus = useCallback(async () => {
    if (statusLoaded.current) return;
    try {
      const data = await assistantApi.status();
      setStatus(data);
      statusLoaded.current = true;
    } catch (loadError) {
      setError(errorMessage(loadError, 'دریافت وضعیت دستیار هوشمند ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    if (open) void loadStatus();
  }, [open, loadStatus]);

  const handleAsk = async (text?: string) => {
    const value = (text ?? question).trim();
    if (value.length < 3) {
      setError('پرسش خود را کمی کامل‌تر بنویسید.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const result = await assistantApi.ask(mode, value);
      setAnswer(result);
      setQuestion(value);
    } catch (askError) {
      setAnswer(null);
      setError(errorMessage(askError, 'پاسخ‌گویی دستیار ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  };

  if (!allowed) return null;

  return (
    <>
      {!open && (
        <Button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 left-4 z-40 h-12 w-12 gap-2 rounded-full p-0 shadow-lg sm:bottom-6 sm:left-6 sm:h-14 sm:w-auto sm:px-5"
          aria-label="دستیار هوشمند"
          title="دستیار هوشمند"
        >
          <Bot className="h-5 w-5" />
          {/* در موبایل فقط آیکون نمایش داده می‌شود تا دکمه روی محتوا نیفتد. */}
          <span className="hidden sm:inline">دستیار هوشمند</span>
        </Button>
      )}

      {open && (
        <aside
          dir="rtl"
          role="dialog"
          aria-label="دستیار هوشمند"
          className="fixed inset-0 z-50 flex flex-col bg-card shadow-2xl sm:inset-y-0 sm:left-0 sm:right-auto sm:w-full sm:max-w-md sm:border-e sm:border-border"
        >
          <header className="flex items-center justify-between gap-2 border-b border-border px-4 py-3">
            <div className="flex items-center gap-2">
              <Sparkles className="h-5 w-5 text-primary" />
              <span className="text-sm font-bold">دستیار هوشمند</span>
            </div>
            <Button size="icon" variant="ghost" onClick={() => setOpen(false)} aria-label="بستن دستیار">
              <X className="h-4 w-4" />
            </Button>
          </header>

          <div className="border-b border-border px-3 py-3 sm:px-4">
            <Tabs value={mode} onValueChange={(value) => setMode(value as AssistantMode)}>
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="meetings">محتوای جلسات</TabsTrigger>
                <TabsTrigger value="guide">راهنمای سامانه</TabsTrigger>
              </TabsList>
            </Tabs>
            {status && !status.available && (
              <p className="mt-3 rounded-md bg-muted p-2 text-xs leading-6 text-muted-foreground">
                {status.hint}
              </p>
            )}
          </div>

          <ScrollArea className="flex-1">
            <div className="space-y-4 p-4">
              <div className="flex flex-wrap gap-2">
                {SAMPLES[mode].map((sample) => (
                  <Button
                    key={sample}
                    size="sm"
                    variant="outline"
                    className="h-auto whitespace-normal py-1 text-start text-xs"
                    onClick={() => void handleAsk(sample)}
                    disabled={loading}
                  >
                    {sample}
                  </Button>
                ))}
              </div>

              {error && <p className="text-sm text-destructive">{error}</p>}

              {loading && (
                <div className="flex items-center gap-2 text-sm text-muted-foreground">
                  <Loader2 className="h-4 w-4 animate-spin" />
                  در حال بررسی محتوا و آماده‌سازی پاسخ…
                </div>
              )}

              {answer && !loading && (
                <div className="space-y-3">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="secondary">{answer.mode_label}</Badge>
                    {answer.provider ? (
                      <Badge variant="outline">مدل: {answer.provider}</Badge>
                    ) : (
                      <Badge variant="outline">بدون مدل زبانی فعال</Badge>
                    )}
                  </div>

                  <div className="rounded-lg border border-border bg-background p-3">
                    <p className="whitespace-pre-wrap text-sm leading-7">{answer.answer}</p>
                  </div>

                  {answer.sources.length > 0 && (
                    <div className="space-y-2">
                      <Separator />
                      <p className="text-xs font-semibold text-muted-foreground">منابع پاسخ</p>
                      {answer.sources.map((source, index) => (
                        <div
                          key={`${source.kind}-${source.meeting_id ?? 'guide'}-${index}`}
                          className="space-y-1 rounded-md border border-border/70 p-2"
                        >
                          <div className="flex flex-wrap items-center gap-2">
                            <Badge variant="outline" className="text-[10px]">
                              {source.kind_label}
                            </Badge>
                            {source.time_label && (
                              <span className="text-[11px] text-muted-foreground">
                                دقیقهٔ {source.time_label}
                              </span>
                            )}
                          </div>
                          <p className="text-xs font-medium">{source.title}</p>
                          <p className="text-[11px] leading-5 text-muted-foreground">
                            {source.snippet}
                          </p>
                          {source.link && (
                            <Button
                              asChild
                              size="sm"
                              variant="ghost"
                              className="h-7 px-2 text-[11px]"
                              onClick={() => setOpen(false)}
                            >
                              <Link to={source.link}>
                                {source.meeting_id ? 'رفتن به جلسه' : 'رفتن به این بخش'}
                              </Link>
                            </Button>
                          )}
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </ScrollArea>

          <div className="border-t border-border p-3">
            <Textarea
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder={
                mode === 'meetings'
                  ? 'مثلاً: مصوبات مربوط به بودجه در جلسات اخیر چه بود؟'
                  : 'مثلاً: چطور برای جلسه پیوست اضافه کنم؟'
              }
              rows={3}
              className="text-sm"
              onKeyDown={(event) => {
                if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
                  event.preventDefault();
                  void handleAsk();
                }
              }}
            />
            <div className="mt-2 flex items-center justify-between gap-2">
              <span className="hidden text-[11px] text-muted-foreground sm:inline">
                کلید Ctrl + Enter برای ارسال سریع
              </span>
              <Button
                size="sm"
                className="min-h-11 shrink-0"
                onClick={() => void handleAsk()}
                disabled={loading}
              >
                <SendHorizonal className="me-1 h-4 w-4" />
                پرسش
              </Button>
            </div>
          </div>
        </aside>
      )}
    </>
  );
}
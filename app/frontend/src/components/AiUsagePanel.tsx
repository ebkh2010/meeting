/**
 * پنل «سهمیهٔ هوش مصنوعی» کاربر جاری.
 *
 * نمایش سقف و مصرف دورهٔ جاری برای هر دو نوع مصرف (دلار مدل زبانی DeepSeek و
 * دقیقهٔ رونویسی «حرف») به‌همراه آخرین رویدادهای مصرف هر کار؛ وقتی سهمیه‌ای
 * تمام شود، شروع کارهای جدید با پیام روشن رد می‌شود.
 */
import { useCallback, useEffect, useState } from 'react';
import { BrainCircuit, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { authApi, AiUsagePayload } from '@/lib/appAuth';
import { errorMessage, formatDateTime, toPersianDigits } from '@/lib/mgmt';

/** عدد با دو رقم اعشار دلار (برای نمایش فارسی‌شده). */
function faDollars(cents: number): string {
  return toPersianDigits((cents / 100).toFixed(2));
}

/** نمایش دقیقه به‌صورت «X ساعت و Y دقیقه». */
function faDuration(minutes: number): string {
  const total = Math.max(minutes, 0);
  const hours = Math.floor(total / 60);
  const mins = total % 60;
  if (hours === 0) return `${toPersianDigits(mins)} دقیقه`;
  return `${toPersianDigits(hours)} ساعت${mins ? ` و ${toPersianDigits(mins)} دقیقه` : ''}`;
}

export default function AiUsagePanel() {
  const [data, setData] = useState<AiUsagePayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await authApi.aiUsage());
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت سهمیهٔ هوش مصنوعی ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const llm = data?.quota.llm;
  const stt = data?.quota.stt;
  const llmPercent = llm ? Math.min((llm.used_cents / Math.max(llm.limit_cents, 1)) * 100, 100) : 0;
  const sttPercent = stt
    ? Math.min((stt.used_minutes / Math.max(stt.limit_minutes, 1)) * 100, 100)
    : 0;

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <BrainCircuit className="h-5 w-5 text-brand" />
            سهمیهٔ هوش مصنوعی شما
          </CardTitle>
          <CardDescription>
            مصرف دورهٔ {data ? toPersianDigits(data.quota.period) : '…'}؛ سقف هر کاربر جداگانه
            شمارش می‌شود.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" className="!bg-transparent" onClick={load} disabled={loading}>
          <RefreshCw className={`me-1 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          بازخوانی
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="grid gap-4 md:grid-cols-2">
          {/* سهمیهٔ مدل زبانی (دلار) */}
          <div className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">مدل زبانی (DeepSeek)</p>
              <p className="text-xs text-muted-foreground">
                {data ? `باقی‌مانده: ${faDollars(llm!.remaining_cents)} دلار` : '…'}
              </p>
            </div>
            <Progress value={llmPercent} className="mt-2 h-2" />
            <p className="mt-2 text-xs text-muted-foreground">
              {data
                ? `${faDollars(llm!.used_cents)} از ${faDollars(llm!.limit_cents)} دلار مصرف شده`
                : 'در حال دریافت…'}
            </p>
          </div>

          {/* سهمیهٔ رونویسی (ساعت) */}
          <div className="rounded-lg border border-border p-3">
            <div className="flex items-center justify-between gap-2">
              <p className="text-sm font-semibold">رونویسی فایل صوتی (حرف)</p>
              <p className="text-xs text-muted-foreground">
                {data ? `باقی‌مانده: ${faDuration(stt!.remaining_minutes)}` : '…'}
              </p>
            </div>
            <Progress value={sttPercent} className="mt-2 h-2" />
            <p className="mt-2 text-xs text-muted-foreground">
              {data
                ? `${faDuration(stt!.used_minutes)} از ${faDuration(stt!.limit_minutes)} مصرف شده`
                : 'در حال دریافت…'}
            </p>
          </div>
        </div>

        {/* رویدادهای مصرف هر کار */}
        <div>
          <p className="mb-2 text-sm font-semibold">مصرف هر کار</p>
          {!data || data.events.length === 0 ? (
            <p className="rounded-lg border border-dashed border-border px-3 py-5 text-center text-xs text-muted-foreground">
              هنوز مصرف هوش مصنوعی برای شما ثبت نشده است.
            </p>
          ) : (
            <div className="space-y-2">
              {data.events.map((event) => (
                <div
                  key={event.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2 text-xs"
                >
                  <div className="min-w-0">
                    <p className="truncate font-medium">{event.kind_label}</p>
                    <p className="truncate text-muted-foreground">
                      {event.provider || '—'}
                      {event.model ? ` · ${event.model}` : ''} · {formatDateTime(event.created_at)}
                    </p>
                  </div>
                  <p className="shrink-0 font-medium text-primary">
                    {event.minutes_charged > 0
                      ? `${faDuration(event.minutes_charged)} رونویسی`
                      : event.tokens_in + event.tokens_out > 0
                        ? `${toPersianDigits(event.tokens_in + event.tokens_out)} توکن ≈ ${faDollars(event.cost_cents)} دلار`
                        : '—'}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

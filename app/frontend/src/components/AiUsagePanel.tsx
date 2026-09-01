/**
 * پنل «سهمیهٔ توکن ویدارا» کاربر جاری.
 *
 * همهٔ مصرف‌های هوش مصنوعی (رونویسی و مدل زبانی) با یک واحد یکپارچه نمایش داده
 * می‌شوند: هر دقیقهٔ رونویسی = ۱ توکن و هر سنت هزینهٔ مدل زبانی = ۱ توکن.
 * در نمای کاربر هیچ واحد سنت/دلار/دقیقه وجود ندارد.
 */
import { useCallback, useEffect, useState } from 'react';
import { Coins, RefreshCw } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Progress } from '@/components/ui/progress';
import { toast } from 'sonner';
import { authApi, AiUsagePayload } from '@/lib/appAuth';
import { errorMessage, formatDateTime, toPersianDigits } from '@/lib/mgmt';

export default function AiUsagePanel() {
  const [data, setData] = useState<AiUsagePayload | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setData(await authApi.aiUsage());
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت سهمیهٔ توکن ویدارا ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const tokens = data?.quota.tokens;
  const percent = tokens
    ? Math.min((tokens.used / Math.max(tokens.limit, 1)) * 100, 100)
    : 0;

  return (
    <Card className="lg:col-span-2">
      <CardHeader className="flex flex-row items-start justify-between gap-3">
        <div>
          <CardTitle className="flex items-center gap-2">
            <Coins className="h-5 w-5 text-brand" />
            سهمیهٔ توکن ویدارا
          </CardTitle>
          <CardDescription>
            مصرف دورهٔ {data ? toPersianDigits(data.quota.period) : '…'}؛ هر دقیقهٔ رونویسی =
            ۱ توکن و هر سنت هزینهٔ مدل زبانی = ۱ توکن.
          </CardDescription>
        </div>
        <Button size="sm" variant="outline" className="!bg-transparent" onClick={load} disabled={loading}>
          <RefreshCw className={`me-1 h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
          بازخوانی
        </Button>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="rounded-lg border border-border p-4">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-sm font-semibold">موجودی توکن ویدارا</p>
            <p className="text-lg font-bold text-primary">
              {data ? `${toPersianDigits(tokens!.remaining)} توکن` : '…'}
            </p>
          </div>
          <Progress value={percent} className="mt-3 h-2" />
          <p className="mt-2 text-xs text-muted-foreground">
            {data
              ? `${toPersianDigits(tokens!.used)} از ${toPersianDigits(tokens!.limit)} توکن مصرف شده`
              : 'در حال دریافت…'}
          </p>
          {data && (
            <p className="mt-1 text-xs text-muted-foreground">
              رونویسی: {toPersianDigits(tokens!.stt_tokens)} توکن · مدل زبانی:{' '}
              {toPersianDigits(tokens!.llm_tokens)} توکن
            </p>
          )}
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
                    {event.tokens_charged > 0
                      ? `${toPersianDigits(event.tokens_charged)} توکن ویدارا`
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

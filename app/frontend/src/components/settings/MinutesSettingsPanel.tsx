/**
 * پنل «تنظیمات تولید صورتجلسه» در تنظیمات سازمان (فقط مدیر).
 *
 * چهار تنظیم محتوایی که در پرامپت تولید پیش‌نویس صورتجلسه و پیشنهاد مصوبات/
 * اقدامات اعمال می‌شوند: لحاظ دستور جلسه، لحاظ مدعوین، طول هدف (کلمه در ساعت)
 * و ملاحظات دلخواه کاربر.
 */
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Textarea } from '@/components/ui/textarea';
import { Skeleton } from '@/components/ui/skeleton';
import { api, errorMessage, type MinutesSettings } from '@/lib/mgmt';

export default function MinutesSettingsPanel() {
  const [settings, setSettings] = useState<MinutesSettings | null>(null);
  const [draft, setDraft] = useState({
    use_agenda: true,
    use_attendees: false,
    words_per_hour: '1000',
    considerations: '',
  });
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.minutesSettings();
      setSettings(data);
      setDraft({
        use_agenda: data.use_agenda,
        use_attendees: data.use_attendees,
        words_per_hour: String(data.words_per_hour),
        considerations: data.considerations,
      });
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن تنظیمات تولید صورتجلسه ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const save = async () => {
    setBusy(true);
    try {
      const data = await api.updateMinutesSettings({
        use_agenda: draft.use_agenda,
        use_attendees: draft.use_attendees,
        words_per_hour: Number(draft.words_per_hour),
        considerations: draft.considerations,
      });
      setSettings(data);
      setDraft({
        use_agenda: data.use_agenda,
        use_attendees: data.use_attendees,
        words_per_hour: String(data.words_per_hour),
        considerations: data.considerations,
      });
      toast.success('تنظیمات تولید صورتجلسه ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تنظیمات ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  if (!settings) {
    return <Skeleton className="h-48 w-full" />;
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">تنظیمات تولید صورتجلسه</CardTitle>
        <CardDescription>
          این تنظیمات هنگام تولید پیش‌نویس صورتجلسه و پیشنهاد مصوبات/اقدامات از روی رونویسی اعمال
          می‌شوند و هر زمان می‌توانید دوباره تولید کنید.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">لحاظ دستور جلسه</p>
            <p className="text-xs text-muted-foreground">
              دستور جلسه در پرامپت تولید صورتجلسه در نظر گرفته شود (پیش‌فرض: بله).
            </p>
          </div>
          <Switch
            checked={draft.use_agenda}
            onCheckedChange={(value) => setDraft({ ...draft, use_agenda: value })}
          />
        </div>

        <div className="flex items-center justify-between rounded-md border p-3">
          <div>
            <p className="text-sm font-medium">لحاظ مدعوین</p>
            <p className="text-xs text-muted-foreground">
              فهرست مدعوین/حاضران در پرامپت تولید در نظر گرفته شود (پیش‌فرض: خیر).
            </p>
          </div>
          <Switch
            checked={draft.use_attendees}
            onCheckedChange={(value) => setDraft({ ...draft, use_attendees: value })}
          />
        </div>

        <div className="space-y-1">
          <Label htmlFor="words-per-hour">طول هدف صورتجلسه (کلمه به ازای هر ساعت صوت)</Label>
          <Input
            id="words-per-hour"
            type="number"
            dir="ltr"
            className="max-w-40 text-left"
            min={settings.bounds.min_words_per_hour}
            max={settings.bounds.max_words_per_hour}
            value={draft.words_per_hour}
            onChange={(e) => setDraft({ ...draft, words_per_hour: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            بازهٔ مجاز: {settings.bounds.min_words_per_hour} تا {settings.bounds.max_words_per_hour} کلمه؛
            پیش‌فرض ۱۰۰۰. طول نهایی = این عدد × ساعت‌های صوت (گردشده به بالا).
          </p>
        </div>

        <div className="space-y-1">
          <Label htmlFor="considerations">ملاحظات شما برای تهیهٔ صورتجلسه</Label>
          <Textarea
            id="considerations"
            rows={4}
            placeholder="مثلاً: مذاکرات را بدون ذکر نام اشخاص بنویس؛ موارد مالی با دقت عددی ثبت شود؛ لحن رسمی و بی‌طرف باشد…"
            value={draft.considerations}
            onChange={(e) => setDraft({ ...draft, considerations: e.target.value })}
          />
          <p className="text-xs text-muted-foreground">
            این ملاحظات عیناً به پرامپت تولید اضافه می‌شوند و مدل زبانی موظف به رعایت آن‌هاست.
          </p>
        </div>

        <div className="flex justify-end">
          <Button disabled={busy} onClick={() => void save()}>
            {busy ? 'در حال ذخیره…' : 'ذخیرهٔ تنظیمات'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * پنل «سقف‌های بارگذاری» در تنظیمات سازمان.
 *
 * چرا این پنل لازم است: سقف مدت/حجم فایل صوتی و سقف حجم هر پیوست پیش‌تر در کد
 * ثابت بود و مدیر سازمان راهی برای تغییر آن نداشت. بک‌اند اکنون این سقف‌ها را در
 * سطح هر سازمان نگه می‌دارد (`GET/PATCH /workspace/upload-limits`) و این فرم
 * تنها راه رسمی تغییر آن‌ها است.
 *
 * نکتهٔ مهم: پس از ذخیره، مقادیر تازه با `applyUploadLimits` در لایهٔ داده ثبت
 * می‌شود تا اعتبارسنجی پیش از آپلود در فرم‌ها (ایجاد جلسه، پیوست‌ها، صوت) دقیقاً
 * همان چیزی را بگوید که سرور می‌پذیرد.
 */
import { useCallback, useEffect, useState } from 'react';
import { HardDriveUpload, RotateCcw, Save } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import {
  api,
  applyUploadLimits,
  errorMessage,
  toPersianDigits,
  UploadLimits,
} from '@/lib/mgmt';

/** فیلدهای قابل تنظیم به همراه متن راهنما؛ ترتیب همان ترتیب نمایش است. */
const FIELDS = [
  {
    key: 'max_audio_minutes' as const,
    label: 'سقف مدت فایل صوتی (دقیقه)',
    help: 'فایل صوتی طولانی‌تر از این مقدار پذیرفته نمی‌شود و هزینهٔ رونویسی نیز محدود می‌ماند.',
  },
  {
    key: 'max_audio_mb' as const,
    label: 'سقف حجم فایل صوتی (مگابایت)',
    help: 'حجم هر فایل صوتی جلسه؛ برای جلسات طولانی مقدار بیشتری لازم است.',
  },
  {
    key: 'max_attachment_mb' as const,
    label: 'سقف حجم هر پیوست (مگابایت)',
    help: 'روی پیوست دستور جلسه و پیوست‌های صفحهٔ جلسه اعمال می‌شود.',
  },
];

type FormState = Record<(typeof FIELDS)[number]['key'], string>;

/** تبدیل پاسخ سرور به مقدارهای متنی فرم. */
function toForm(limits: UploadLimits): FormState {
  return {
    max_audio_minutes: String(limits.max_audio_minutes),
    max_audio_mb: String(limits.max_audio_mb),
    max_attachment_mb: String(limits.max_attachment_mb),
  };
}

export default function UploadLimitsPanel() {
  const [limits, setLimits] = useState<UploadLimits | null>(null);
  const [form, setForm] = useState<FormState | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.uploadLimits();
      setLimits(data);
      setForm(toForm(data));
      applyUploadLimits(data);
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن سقف‌های بارگذاری ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  /** بازگشت مقادیر فرم به پیش‌فرض‌های سیستم (فقط در فرم؛ ذخیره جداگانه است). */
  const resetToDefaults = () => {
    if (!limits) return;
    setForm({
      max_audio_minutes: String(limits.defaults.max_audio_minutes),
      max_audio_mb: String(limits.defaults.max_audio_mb),
      max_attachment_mb: String(limits.defaults.max_attachment_mb),
    });
  };

  const submit = async () => {
    if (!form || !limits) return;
    // اعتبارسنجی در همان بازه‌ای که بک‌اند اعلام کرده تا پیام خطا با سرور یکی باشد.
    for (const field of FIELDS) {
      const bound = limits.bounds[field.key];
      const value = Number(form[field.key]);
      if (!Number.isFinite(value) || !Number.isInteger(value)) {
        toast.error(`${field.label} باید یک عدد صحیح باشد.`);
        return;
      }
      if (bound && (value < bound.min || value > bound.max)) {
        toast.error(
          `${field.label} باید بین ${toPersianDigits(bound.min)} و ${toPersianDigits(bound.max)} باشد.`,
        );
        return;
      }
    }

    setSaving(true);
    try {
      const data = await api.updateUploadLimits({
        max_audio_minutes: Number(form.max_audio_minutes),
        max_audio_mb: Number(form.max_audio_mb),
        max_attachment_mb: Number(form.max_attachment_mb),
      });
      setLimits(data);
      setForm(toForm(data));
      applyUploadLimits(data);
      toast.success('سقف‌های بارگذاری ذخیره شد و بی‌درنگ اعمال می‌شود.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ سقف‌های بارگذاری ناموفق بود.'));
    } finally {
      setSaving(false);
    }
  };

  if (loading || !form || !limits) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>سقف‌های بارگذاری فایل</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-brand-soft">
          <HardDriveUpload className="h-5 w-5 text-brand" />
        </div>
        <CardTitle>سقف‌های بارگذاری فایل</CardTitle>
        <CardDescription>
          این مقادیر هم در اعتبارسنجی سرور و هم در پیام‌های راهنمای فرم‌های بارگذاری استفاده
          می‌شود.{' '}
          {limits.is_custom
            ? `آخرین تغییر توسط ${limits.updated_by_name || 'مدیر سازمان'}.`
            : 'در حال حاضر مقادیر پیش‌فرض سیستم اعمال است.'}
        </CardDescription>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-3">
        {FIELDS.map((field) => {
          const bound = limits.bounds[field.key];
          return (
            <div key={field.key} className="space-y-2">
              <Label htmlFor={`limit-${field.key}`}>{field.label}</Label>
              <Input
                id={`limit-${field.key}`}
                type="number"
                inputMode="numeric"
                min={bound?.min}
                max={bound?.max}
                value={form[field.key]}
                onChange={(event) =>
                  setForm((prev) => (prev ? { ...prev, [field.key]: event.target.value } : prev))
                }
              />
              <p className="text-xs text-muted-foreground">{field.help}</p>
              {bound && (
                <p className="text-xs text-muted-foreground">
                  بازهٔ مجاز: {toPersianDigits(bound.min)} تا {toPersianDigits(bound.max)} — پیش‌فرض:{' '}
                  {toPersianDigits(limits.defaults[field.key])}
                </p>
              )}
            </div>
          );
        })}
      </CardContent>
      <CardFooter className="flex flex-wrap gap-2">
        <Button onClick={submit} disabled={saving}>
          <Save className="me-2 h-4 w-4" />
          {saving ? 'در حال ذخیره…' : 'ذخیرهٔ سقف‌ها'}
        </Button>
        <Button variant="outline" onClick={resetToDefaults} disabled={saving}>
          <RotateCcw className="me-2 h-4 w-4" />
          بازگردانی به پیش‌فرض
        </Button>
      </CardFooter>
    </Card>
  );
}
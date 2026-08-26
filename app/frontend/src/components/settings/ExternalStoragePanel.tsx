/**
 * پنل «استوریج خارجی و آرشیو جلسات» — فقط در تنظیمات مدیر سازمان.
 *
 * چرا این پنل لازم است: فایل‌های جانبی جلسات (صوت و پیوست‌ها) با گذر زمان فضای
 * سرور اصلی را پر می‌کنند. این پنل تنها راه رسمی برای:
 *   ۱) تعریف مقصد خارجی سازمان (S3 سازگار یا WebDAV) و تست واقعی اتصال،
 *   ۲) انتقال فایل‌های یک جلسه به مقصد خارجی (آرشیو) با چکسام و حذف امن،
 *   ۳) بازگرداندن فایل‌ها از آرشیو برای بازهٔ مشخص (بازیابی).
 *
 * نکات پیاده‌سازی:
 *  - همهٔ عملیات سنگین در بک‌اند صف می‌شود؛ این پنل فقط وضعیت و درصد پیشرفت کار
 *    را با polling می‌خواند و هیچ منطق انتقالی در مرورگر ندارد.
 *  - اعتبارنامه‌ها هرگز خوانده نمی‌شوند؛ فیلد خالی یعنی «بدون تغییر» و مقدار
 *    ماسک‌شده تنها برای اطلاع مدیر نمایش داده می‌شود.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  CloudUpload,
  Database,
  HardDrive,
  Loader2,
  PlugZap,
  RefreshCw,
  RotateCcw,
  Save,
  Server,
} from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
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
import { Progress } from '@/components/ui/progress';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Skeleton } from '@/components/ui/skeleton';
import { Switch } from '@/components/ui/switch';
import {
  api,
  ArchiveJob,
  ArchiveMeetingSummary,
  errorMessage,
  MeetingArchiveState,
  StorageProviderInfo,
  StorageTarget,
  toPersianDigits,
} from '@/lib/mgmt';

/** حالت فرم مقصد؛ همهٔ مقادیر متنی هستند تا کنترل ورودی ساده بماند. */
interface TargetForm {
  provider: string;
  display_name: string;
  enabled: boolean;
  endpoint: string;
  bucket: string;
  region: string;
  path_prefix: string;
  access_key: string;
  secret_key: string;
  force_path_style: boolean;
  webdav_base_url: string;
  webdav_username: string;
  webdav_password: string;
  restore_retention_days: string;
}

function toForm(target: StorageTarget): TargetForm {
  return {
    provider: target.provider || 's3',
    display_name: target.display_name || '',
    enabled: target.enabled,
    endpoint: target.endpoint || '',
    bucket: target.bucket || '',
    region: target.region || 'us-east-1',
    path_prefix: target.path_prefix || 'vidara',
    access_key: target.access_key || '',
    secret_key: '',
    force_path_style: target.force_path_style,
    webdav_base_url: target.webdav_base_url || '',
    webdav_username: target.webdav_username || '',
    webdav_password: '',
    restore_retention_days: String(target.restore_retention_days || 14),
  };
}

/** نمایش خوانا از حجم بایت به فارسی. */
function formatBytes(bytes: number): string {
  if (!bytes) return '۰';
  const units = ['بایت', 'کیلوبایت', 'مگابایت', 'گیگابایت'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? String(Math.round(value)) : value.toFixed(1);
  return `${toPersianDigits(rounded)} ${units[unit]}`;
}

/** رنگ نشان وضعیت هر فایل بر پایهٔ وضعیت واقعی بک‌اند. */
function statusTone(status: string): string {
  if (status === 'archived') return 'bg-brand-surface text-brand border-brand-soft';
  if (status === 'restored') return 'bg-emerald-50 text-emerald-700 border-emerald-200';
  if (status === 'error') return 'bg-error-soft text-error border-error-border';
  if (status === 'archiving' || status === 'restoring')
    return 'bg-amber-50 text-amber-700 border-amber-200';
  return 'bg-muted text-muted-foreground border-border';
}

export default function ExternalStoragePanel() {
  const [target, setTarget] = useState<StorageTarget | null>(null);
  const [catalog, setCatalog] = useState<StorageProviderInfo[]>([]);
  const [form, setForm] = useState<TargetForm | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const [meetings, setMeetings] = useState<ArchiveMeetingSummary[]>([]);
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [state, setState] = useState<MeetingArchiveState | null>(null);
  const [stateLoading, setStateLoading] = useState(false);
  const [job, setJob] = useState<ArchiveJob | null>(null);
  const [queueing, setQueueing] = useState(false);
  const pollRef = useRef<number | null>(null);

  const isWebdav = (form?.provider || '') === 'webdav';

  const loadTarget = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.archiveTarget();
      setTarget(data.target);
      setCatalog(data.catalog || []);
      setForm(toForm(data.target));
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن تنظیمات مقصد ذخیره‌سازی خارجی ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  const loadMeetings = useCallback(async () => {
    try {
      const data = await api.archiveMeetings();
      setMeetings(data.items || []);
      setSelectedId((prev) => prev ?? (data.items?.[0]?.meeting_id ?? null));
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن فهرست جلسات برای آرشیو ناموفق بود.'));
    }
  }, []);

  const loadState = useCallback(async (meetingId: number) => {
    setStateLoading(true);
    try {
      const data = await api.archiveMeetingState(meetingId);
      setState(data);
      setJob(data.active_job ?? null);
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن وضعیت آرشیو جلسه ناموفق بود.'));
    } finally {
      setStateLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTarget();
    void loadMeetings();
  }, [loadTarget, loadMeetings]);

  useEffect(() => {
    if (selectedId !== null) void loadState(selectedId);
  }, [selectedId, loadState]);

  /** پیگیری وضعیت کار در جریان؛ با پایان کار، وضعیت فایل‌ها تازه می‌شود. */
  useEffect(() => {
    if (!job || (job.status !== 'queued' && job.status !== 'running')) {
      if (pollRef.current) {
        window.clearTimeout(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    pollRef.current = window.setTimeout(async () => {
      try {
        const fresh = await api.archiveJob(job.id);
        setJob(fresh);
        if (fresh.status === 'succeeded' || fresh.status === 'failed') {
          if (selectedId !== null) await loadState(selectedId);
          await loadMeetings();
          if (fresh.status === 'succeeded') {
            toast.success(
              fresh.job_type === 'meeting_archive'
                ? 'آرشیو فایل‌های جلسه با موفقیت پایان یافت.'
                : 'بازیابی فایل‌های جلسه با موفقیت پایان یافت.',
            );
          } else {
            toast.error(fresh.error_message || 'عملیات آرشیو/بازیابی ناموفق بود.');
          }
        }
      } catch {
        /* خطای گذرای شبکه: تلاش بعدی ادامه می‌یابد. */
      }
    }, 3000);
    return () => {
      if (pollRef.current) window.clearTimeout(pollRef.current);
    };
  }, [job, selectedId, loadState, loadMeetings]);

  const activeFields = useMemo(() => {
    const entry = catalog.find((item) => item.provider === (form?.provider || ''));
    return entry?.fields || [];
  }, [catalog, form?.provider]);

  const update = <K extends keyof TargetForm>(key: K, value: TargetForm[K]) =>
    setForm((prev) => (prev ? { ...prev, [key]: value } : prev));

  const handleSave = async () => {
    if (!form) return;
    setSaving(true);
    try {
      const payload: Record<string, unknown> = {
        provider: form.provider,
        display_name: form.display_name.trim(),
        enabled: form.enabled,
        path_prefix: form.path_prefix.trim(),
        restore_retention_days: Number(form.restore_retention_days) || 14,
      };
      if (isWebdav) {
        payload.webdav_base_url = form.webdav_base_url.trim();
        payload.webdav_username = form.webdav_username.trim();
        if (form.webdav_password) payload.webdav_password = form.webdav_password;
      } else {
        payload.endpoint = form.endpoint.trim();
        payload.bucket = form.bucket.trim();
        payload.region = form.region.trim();
        payload.access_key = form.access_key.trim();
        payload.force_path_style = form.force_path_style;
        if (form.secret_key) payload.secret_key = form.secret_key;
      }
      const data = await api.saveArchiveTarget(payload);
      setTarget(data.target);
      setForm(toForm(data.target));
      toast.success('تنظیمات مقصد ذخیره‌سازی خارجی ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تنظیمات مقصد ناموفق بود.'));
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    try {
      const data = await api.testArchiveTarget();
      setTarget(data.target);
      if (data.ok) toast.success(data.message || 'اتصال به مقصد خارجی برقرار است.');
      else toast.error(data.message || 'تست اتصال ناموفق بود.');
    } catch (err) {
      toast.error(errorMessage(err, 'تست اتصال به مقصد خارجی ناموفق بود.'));
    } finally {
      setTesting(false);
    }
  };

  const runQueue = async (kind: 'archive' | 'restore') => {
    if (selectedId === null) return;
    setQueueing(true);
    try {
      const created =
        kind === 'archive'
          ? await api.startMeetingArchive(selectedId)
          : await api.startMeetingRestore(selectedId);
      setJob(created);
      toast.success(
        kind === 'archive'
          ? 'عملیات آرشیو در صف قرار گرفت؛ پیشرفت آن همین‌جا نمایش داده می‌شود.'
          : 'عملیات بازیابی در صف قرار گرفت؛ پیشرفت آن همین‌جا نمایش داده می‌شود.',
      );
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت عملیات در صف ناموفق بود.'));
    } finally {
      setQueueing(false);
    }
  };

  const handleRetry = async () => {
    if (!job) return;
    try {
      const fresh = await api.retryArchiveJob(job.id);
      setJob(fresh);
      toast.success('کار برای تلاش دوباره در صف قرار گرفت.');
    } catch (err) {
      toast.error(errorMessage(err, 'تلاش دوبارهٔ کار ناموفق بود.'));
    }
  };

  if (loading || !form) {
    return (
      <Card>
        <CardHeader>
          <Skeleton className="h-5 w-56" />
          <Skeleton className="h-4 w-80" />
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-full" />
          <Skeleton className="h-10 w-2/3" />
        </CardContent>
      </Card>
    );
  }

  const jobRunning = !!job && (job.status === 'queued' || job.status === 'running');

  return (
    <div className="space-y-6">
      {/* ---------------- مقصد ذخیره‌سازی خارجی ---------------- */}
      <Card>
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="space-y-1">
              <CardTitle className="flex items-center gap-2">
                <Server className="h-4 w-4 text-brand" />
                مقصد ذخیره‌سازی خارجی سازمان
              </CardTitle>
              <CardDescription>
                فایل‌های صوتی و پیوست جلسات پس از آرشیو در این مقصد نگه‌داری می‌شوند. انتقال به‌صورت
                جریانی انجام می‌شود، چکسام SHA-256 بررسی می‌گردد و تنها پس از تأیید سلامت، نسخهٔ
                سرور اصلی حذف می‌شود.
              </CardDescription>
            </div>
            {target?.is_active ? (
              <Badge className="border-emerald-200 bg-emerald-50 text-emerald-700">
                <CheckCircle2 className="me-1 h-3.5 w-3.5" /> فعال و آزمون‌شده
              </Badge>
            ) : (
              <Badge variant="outline" className="text-muted-foreground">
                <AlertTriangle className="me-1 h-3.5 w-3.5" /> غیرفعال
              </Badge>
            )}
          </div>
        </CardHeader>

        <CardContent className="space-y-5">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>نوع سرویس</Label>
              <Select value={form.provider} onValueChange={(value) => update('provider', value)}>
                <SelectTrigger>
                  <SelectValue placeholder="انتخاب کنید" />
                </SelectTrigger>
                <SelectContent>
                  {catalog.map((item) => (
                    <SelectItem key={item.provider} value={item.provider}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                {catalog.find((item) => item.provider === form.provider)?.note || ''}
              </p>
            </div>

            <div className="space-y-1.5">
              <Label>نام نمایشی مقصد</Label>
              <Input
                value={form.display_name}
                onChange={(event) => update('display_name', event.target.value)}
                placeholder="مثلاً آرشیو ابری سازمان"
              />
            </div>
          </div>

          {isWebdav ? (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5 md:col-span-2">
                <Label>نشانی WebDAV</Label>
                <Input
                  dir="rtl"
                  value={form.webdav_base_url}
                  onChange={(event) => update('webdav_base_url', event.target.value)}
                  placeholder="https://cloud.example.com/remote.php/dav/files/username"
                />
              </div>
              <div className="space-y-1.5">
                <Label>نام کاربری</Label>
                <Input
                  dir="rtl"
                  value={form.webdav_username}
                  onChange={(event) => update('webdav_username', event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>گذرواژه یا App Password</Label>
                <Input
                  dir="rtl"
                  type="password"
                  value={form.webdav_password}
                  onChange={(event) => update('webdav_password', event.target.value)}
                  placeholder={
                    target?.has_webdav_password
                      ? `ذخیره‌شده: ${target.webdav_password_masked} — خالی بگذارید تا تغییر نکند`
                      : 'گذرواژهٔ دسترسی WebDAV'
                  }
                />
              </div>
            </div>
          ) : (
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-1.5 md:col-span-2">
                <Label>نشانی سرویس (Endpoint)</Label>
                <Input
                  dir="rtl"
                  value={form.endpoint}
                  onChange={(event) => update('endpoint', event.target.value)}
                  placeholder="https://s3.example.com"
                />
              </div>
              <div className="space-y-1.5">
                <Label>نام باکت</Label>
                <Input
                  dir="rtl"
                  value={form.bucket}
                  onChange={(event) => update('bucket', event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>منطقه (Region)</Label>
                <Input
                  dir="rtl"
                  value={form.region}
                  onChange={(event) => update('region', event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>کلید دسترسی (Access Key)</Label>
                <Input
                  dir="rtl"
                  value={form.access_key}
                  onChange={(event) => update('access_key', event.target.value)}
                />
              </div>
              <div className="space-y-1.5">
                <Label>کلید محرمانه (Secret Key)</Label>
                <Input
                  dir="rtl"
                  type="password"
                  value={form.secret_key}
                  onChange={(event) => update('secret_key', event.target.value)}
                  placeholder={
                    target?.has_secret_key
                      ? `ذخیره‌شده: ${target.secret_key_masked} — خالی بگذارید تا تغییر نکند`
                      : 'کلید محرمانهٔ سرویس'
                  }
                />
              </div>
              <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2 md:col-span-2">
                <div>
                  <p className="text-sm font-medium">آدرس‌دهی به سبک مسیر (Path Style)</p>
                  <p className="text-xs text-muted-foreground">
                    برای MinIO و بیشتر سرویس‌های داخلی روشن بماند؛ برای AWS S3 معمولاً خاموش است.
                  </p>
                </div>
                <Switch
                  checked={form.force_path_style}
                  onCheckedChange={(value) => update('force_path_style', value)}
                />
              </div>
            </div>
          )}

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-1.5">
              <Label>پیشوند مسیر در مقصد</Label>
              <Input
                dir="rtl"
                value={form.path_prefix}
                onChange={(event) => update('path_prefix', event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                مسیر نهایی هر سازمان جدا نگه داشته می‌شود:{' '}
                <span dir="rtl">{target?.tenant_prefix || `${form.path_prefix}/org-<id>`}</span>
              </p>
            </div>
            <div className="space-y-1.5">
              <Label>مدت اعتبار نسخهٔ بازیابی‌شده (روز)</Label>
              <Input
                dir="rtl"
                inputMode="numeric"
                value={form.restore_retention_days}
                onChange={(event) => update('restore_retention_days', event.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                پس از این مدت، نسخهٔ محلی فایل بازیابی‌شده پاک می‌شود و نسخهٔ آرشیو دست‌نخورده
                می‌ماند.
              </p>
            </div>
          </div>

          <div className="flex items-center justify-between rounded-lg border border-border bg-muted/40 px-3 py-2">
            <div>
              <p className="text-sm font-medium">فعال‌بودن آرشیو خارجی</p>
              <p className="text-xs text-muted-foreground">
                تا زمانی که تست اتصال با موفقیت انجام نشود، عملیات آرشیو اجرا نمی‌شود.
              </p>
            </div>
            <Switch
              checked={form.enabled}
              onCheckedChange={(value) => update('enabled', value)}
            />
          </div>

          {target?.last_test_at ? (
            <div
              className={`rounded-lg border px-3 py-2 text-xs ${
                target.last_test_ok
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-700'
                  : 'border-error-border bg-error-soft text-error'
              }`}
            >
              آخرین تست اتصال: {target.last_test_ok ? 'موفق' : 'ناموفق'} —{' '}
              {target.last_test_message}
            </div>
          ) : null}

          {activeFields.length > 0 ? (
            <p className="text-xs text-muted-foreground">
              فیلدهای لازم برای این سرویس: <span dir="rtl">{activeFields.join(' · ')}</span>
            </p>
          ) : null}
        </CardContent>

        <CardFooter className="flex flex-wrap gap-2">
          <Button onClick={handleSave} disabled={saving}>
            {saving ? <Loader2 className="me-1 h-4 w-4 animate-spin" /> : <Save className="me-1 h-4 w-4" />}
            ذخیرهٔ تنظیمات
          </Button>
          <Button variant="outline" onClick={handleTest} disabled={testing || !target?.configured}>
            {testing ? (
              <Loader2 className="me-1 h-4 w-4 animate-spin" />
            ) : (
              <PlugZap className="me-1 h-4 w-4" />
            )}
            تست واقعی اتصال
          </Button>
          <Button variant="ghost" onClick={() => setForm(toForm(target as StorageTarget))}>
            <RotateCcw className="me-1 h-4 w-4" />
            بازگردانی فرم
          </Button>
        </CardFooter>
      </Card>

      {/* ---------------- آرشیو و بازیابی جلسه ---------------- */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Database className="h-4 w-4 text-brand" />
            آرشیو و بازیابی فایل‌های جانبی جلسات
          </CardTitle>
          <CardDescription>
            جلسه را انتخاب کنید تا وضعیت هر فایل (روی سرور، در حال انتقال، آرشیوشده، بازیابی‌شده یا
            خطا) را ببینید و عملیات را در صف قرار دهید.
          </CardDescription>
        </CardHeader>

        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_auto] md:items-end">
            <div className="space-y-1.5">
              <Label>جلسه</Label>
              <Select
                value={selectedId !== null ? String(selectedId) : ''}
                onValueChange={(value) => setSelectedId(Number(value))}
              >
                <SelectTrigger>
                  <SelectValue placeholder="یک جلسه را انتخاب کنید" />
                </SelectTrigger>
                <SelectContent>
                  {meetings.map((item) => (
                    <SelectItem key={item.meeting_id} value={String(item.meeting_id)}>
                      {item.title || `جلسهٔ ${toPersianDigits(item.meeting_id)}`}
                      {item.tracked_count
                        ? ` — ${toPersianDigits(item.archived_count)}/${toPersianDigits(item.tracked_count)} آرشیو`
                        : ''}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <Button
              variant="outline"
              onClick={() => {
                void loadMeetings();
                if (selectedId !== null) void loadState(selectedId);
              }}
            >
              <RefreshCw className="me-1 h-4 w-4" />
              به‌روزرسانی وضعیت
            </Button>
          </div>

          {!state?.target_ready ? (
            <div className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
              مقصد ذخیره‌سازی خارجی فعال و آزمون‌شده نیست؛ ابتدا تنظیمات بالا را ذخیره کنید، تست
              اتصال را با موفقیت بگذرانید و کلید «فعال‌بودن آرشیو خارجی» را روشن کنید.
            </div>
          ) : null}

          {jobRunning ? (
            <div className="space-y-2 rounded-lg border border-brand-soft bg-brand-surface px-3 py-3">
              <div className="flex items-center justify-between text-xs text-brand">
                <span className="flex items-center gap-1.5">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {job?.job_type === 'meeting_archive'
                    ? 'انتقال فایل‌ها به مقصد خارجی در جریان است…'
                    : 'بازیابی فایل‌ها از آرشیو در جریان است…'}
                </span>
                <span>{toPersianDigits(job?.progress || 0)}٪</span>
              </div>
              <Progress value={job?.progress || 0} className="h-2" />
            </div>
          ) : null}

          {job && job.status === 'failed' ? (
            <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-error-border bg-error-soft px-3 py-2 text-xs text-error">
              <span>{job.error_message || 'آخرین عملیات ناموفق بود.'}</span>
              <Button size="sm" variant="outline" onClick={handleRetry}>
                <RefreshCw className="me-1 h-3.5 w-3.5" />
                تلاش دوباره
              </Button>
            </div>
          ) : null}

          {stateLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : state && state.files.length > 0 ? (
            <div className="space-y-2">
              {state.files.map((file) => (
                <div
                  key={file.id}
                  className="flex flex-wrap items-center justify-between gap-2 rounded-lg border border-border px-3 py-2"
                >
                  <div className="min-w-0 space-y-0.5">
                    <p className="truncate text-sm font-medium">{file.file_name}</p>
                    <p className="text-xs text-muted-foreground">
                      {file.kind_label} · {formatBytes(file.size_bytes)}
                      {file.remote_path ? (
                        <>
                          {' · '}
                          <span dir="rtl">{file.remote_path}</span>
                        </>
                      ) : null}
                    </p>
                    {file.error_message ? (
                      <p className="text-xs text-error">{file.error_message}</p>
                    ) : null}
                    {file.status === 'restored' && file.restore_expires_at ? (
                      <p className="text-xs text-emerald-700">
                        نسخهٔ محلی تا <span dir="rtl">{file.restore_expires_at}</span> در دسترس است.
                      </p>
                    ) : null}
                  </div>
                  <Badge variant="outline" className={statusTone(file.status)}>
                    {file.is_archived ? (
                      <CloudUpload className="me-1 h-3.5 w-3.5" />
                    ) : (
                      <HardDrive className="me-1 h-3.5 w-3.5" />
                    )}
                    {file.status_label}
                  </Badge>
                </div>
              ))}
              <p className="text-xs text-muted-foreground">
                وضعیت کلی: {state.state_label} — {toPersianDigits(state.archived_count)} از{' '}
                {toPersianDigits(state.total_count)} فایل آرشیو شده (
                {formatBytes(state.archived_bytes)} آزادشده از سرور اصلی).
              </p>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed border-border px-3 py-6 text-center text-sm text-muted-foreground">
              برای این جلسه فایل جانبی (صوت یا پیوست) ثبت نشده است.
            </p>
          )}
        </CardContent>

        <CardFooter className="flex flex-wrap gap-2">
          <Button
            onClick={() => void runQueue('archive')}
            disabled={queueing || jobRunning || selectedId === null || !state?.target_ready}
          >
            <CloudUpload className="me-1 h-4 w-4" />
            آرشیو فایل‌های این جلسه
          </Button>
          <Button
            variant="outline"
            onClick={() => void runQueue('restore')}
            disabled={
              queueing ||
              jobRunning ||
              selectedId === null ||
              !state?.files.some((file) => file.is_archived)
            }
          >
            <HardDrive className="me-1 h-4 w-4" />
            بازیابی از آرشیو
          </Button>
        </CardFooter>
      </Card>
    </div>
  );
}
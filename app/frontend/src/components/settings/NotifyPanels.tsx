/**
 * پنل‌های اعلان در بخش تنظیمات: ایمیل (SMTP)، پیامک (قاصدک) و گزارش ارسال.
 * رمزها و کلیدها هرگز از سرور بازخوانی نمی‌شوند؛ فقط وضعیت «ذخیره‌شده» نمایش داده می‌شود.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Badge } from '@/components/ui/badge';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';
import { errorMessage, formatDateTime } from '@/lib/mgmt';
import {
  CHANNEL_LABELS,
  DELIVERY_STATUS_LABELS,
  DeliveryItem,
  NotifySettings as Settings,
  notifyApi,
} from '@/lib/notify';

/** مدیریت مشترک وضعیت تنظیمات اعلان برای پنل‌های ایمیل و پیامک. */
function useNotifySettings() {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await notifyApi.readSettings();
      setSettings(data);
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت تنظیمات اعلان ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const patch = useCallback(
    async (payload: Record<string, unknown>) => {
      setBusy(true);
      try {
        const data = await notifyApi.updateSettings(payload);
        setSettings(data);
        toast.success('تنظیمات ذخیره شد.');
        return true;
      } catch (error) {
        toast.error(errorMessage(error, 'ذخیرهٔ تنظیمات ناموفق بود.'));
        await load();
        return false;
      } finally {
        setBusy(false);
      }
    },
    [load],
  );

  return { settings, setSettings, busy, setBusy, patch, load };
}

export function EmailSettingsPanel() {
  const { settings, setSettings, busy, setBusy, patch } = useNotifySettings();
  const [smtpPassword, setSmtpPassword] = useState('');
  const [testEmail, setTestEmail] = useState('');

  if (!settings) {
    return <p className="text-sm text-muted-foreground">در حال دریافت تنظیمات…</p>;
  }

  const saveSmtp = async () => {
    const ok = await patch({
      smtp_host: settings.smtp_host,
      smtp_port: settings.smtp_port,
      smtp_username: settings.smtp_username,
      smtp_use_tls: settings.smtp_use_tls,
      smtp_use_ssl: settings.smtp_use_ssl,
      smtp_from_email: settings.smtp_from_email,
      smtp_from_name: settings.smtp_from_name,
      ...(smtpPassword ? { smtp_password: smtpPassword } : {}),
    });
    if (ok) setSmtpPassword('');
  };

  const handleTestEmail = async () => {
    setBusy(true);
    try {
      const result = await notifyApi.testEmail(testEmail.trim());
      toast.success(result.detail || 'ایمیل آزمایشی ارسال شد.');
    } catch (error) {
      toast.error(errorMessage(error, 'ارسال ایمیل آزمایشی ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>ارسال ایمیل (SMTP)</CardTitle>
          <CardDescription>
            دعوت‌نامهٔ جلسه با فایل تقویم به ایمیل اعضا فرستاده می‌شود.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">فعال</span>
          <Switch
            checked={settings.smtp_enabled}
            onCheckedChange={(checked) => patch({ smtp_enabled: checked })}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-3">
          <div className="space-y-2">
            <Label htmlFor="smtp-host">میزبان SMTP</Label>
            <Input
              id="smtp-host"
              dir="rtl"
              value={settings.smtp_host}
              onChange={(event) => setSettings({ ...settings, smtp_host: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="smtp-port">پورت</Label>
            <Input
              id="smtp-port"
              dir="rtl"
              inputMode="numeric"
              value={settings.smtp_port}
              onChange={(event) =>
                setSettings({ ...settings, smtp_port: Number(event.target.value) || 0 })
              }
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="smtp-user">نام کاربری</Label>
            <Input
              id="smtp-user"
              dir="rtl"
              value={settings.smtp_username}
              onChange={(event) => setSettings({ ...settings, smtp_username: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="smtp-pass">
              رمز عبور {settings.smtp_password_set && '(ذخیره‌شده — برای تغییر وارد کنید)'}
            </Label>
            <Input
              id="smtp-pass"
              dir="rtl"
              type="password"
              value={smtpPassword}
              onChange={(event) => setSmtpPassword(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="smtp-from">ایمیل فرستنده</Label>
            <Input
              id="smtp-from"
              dir="rtl"
              type="email"
              value={settings.smtp_from_email}
              onChange={(event) => setSettings({ ...settings, smtp_from_email: event.target.value })}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="smtp-fromname">نام فرستنده</Label>
            <Input
              id="smtp-fromname"
              value={settings.smtp_from_name}
              onChange={(event) => setSettings({ ...settings, smtp_from_name: event.target.value })}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-6">
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={settings.smtp_use_tls}
              onCheckedChange={(checked) => setSettings({ ...settings, smtp_use_tls: checked })}
            />
            STARTTLS
          </label>
          <label className="flex items-center gap-2 text-sm">
            <Switch
              checked={settings.smtp_use_ssl}
              onCheckedChange={(checked) => setSettings({ ...settings, smtp_use_ssl: checked })}
            />
            SSL
          </label>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <Button disabled={busy} onClick={saveSmtp}>
            ذخیرهٔ تنظیمات ایمیل
          </Button>
          <div className="space-y-2">
            <Label htmlFor="test-email">ایمیل مقصد آزمایش</Label>
            <Input
              id="test-email"
              dir="rtl"
              type="email"
              className="w-64"
              value={testEmail}
              onChange={(event) => setTestEmail(event.target.value)}
            />
          </div>
          <Button
            variant="outline"
            className="!bg-transparent hover:!bg-transparent"
            disabled={busy}
            onClick={handleTestEmail}
          >
            ارسال ایمیل آزمایشی
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function SmsSettingsPanel() {
  const { settings, setSettings, busy, setBusy, patch } = useNotifySettings();
  const [smsApiKey, setSmsApiKey] = useState('');
  const [testMobile, setTestMobile] = useState('');

  if (!settings) {
    return <p className="text-sm text-muted-foreground">در حال دریافت تنظیمات…</p>;
  }

  const saveSms = async () => {
    const ok = await patch({
      sms_line_number: settings.sms_line_number,
      ...(smsApiKey ? { sms_api_key: smsApiKey } : {}),
    });
    if (ok) setSmsApiKey('');
  };

  const handleTestSms = async () => {
    setBusy(true);
    try {
      const result = await notifyApi.testSms(testMobile.trim());
      toast.success(result.detail || 'پیامک آزمایشی ارسال شد.');
    } catch (error) {
      toast.error(errorMessage(error, 'ارسال پیامک آزمایشی ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="flex flex-row items-start justify-between gap-4">
        <div>
          <CardTitle>ارسال پیامک (قاصدک)</CardTitle>
          <CardDescription>
            دعوت جلسه با پیامک و خطاب مناسب (جناب آقای / سرکار خانم) ارسال می‌شود.
          </CardDescription>
        </div>
        <div className="flex items-center gap-2">
          <span className="text-sm text-muted-foreground">فعال</span>
          <Switch
            checked={settings.sms_enabled}
            onCheckedChange={(checked) => patch({ sms_enabled: checked })}
          />
        </div>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 md:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="sms-key">
              کلید API قاصدک {settings.sms_api_key_set && '(ذخیره‌شده — برای تغییر وارد کنید)'}
            </Label>
            <Input
              id="sms-key"
              dir="rtl"
              type="password"
              value={smsApiKey}
              onChange={(event) => setSmsApiKey(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="sms-line">شمارهٔ خط ارسال</Label>
            <Input
              id="sms-line"
              dir="rtl"
              value={settings.sms_line_number}
              onChange={(event) => setSettings({ ...settings, sms_line_number: event.target.value })}
            />
          </div>
        </div>

        <div className="flex flex-wrap items-end gap-3">
          <Button disabled={busy} onClick={saveSms}>
            ذخیرهٔ تنظیمات پیامک
          </Button>
          <div className="space-y-2">
            <Label htmlFor="test-sms">موبایل مقصد آزمایش</Label>
            <Input
              id="test-sms"
              dir="rtl"
              className="w-64"
              value={testMobile}
              onChange={(event) => setTestMobile(event.target.value)}
            />
          </div>
          <Button
            variant="outline"
            className="!bg-transparent hover:!bg-transparent"
            disabled={busy}
            onClick={handleTestSms}
          >
            ارسال پیامک آزمایشی
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export function DeliveriesPanel() {
  const [deliveries, setDeliveries] = useState<DeliveryItem[]>([]);
  const [loading, setLoading] = useState(true);

  const loadDeliveries = useCallback(async () => {
    setLoading(true);
    try {
      const data = await notifyApi.deliveries(undefined, 40);
      setDeliveries(data.items || []);
    } catch {
      setDeliveries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadDeliveries();
  }, [loadDeliveries]);

  return (
    <Card>
      <CardHeader className="flex flex-col items-start justify-between gap-3 sm:flex-row">
        <div className="min-w-0">
          <CardTitle>گزارش ارسال اعلان‌ها</CardTitle>
          <CardDescription>آخرین وضعیت ارسال دعوت‌نامه‌ها و پیام‌های آزمایشی.</CardDescription>
        </div>
        <Button
          size="sm"
          variant="outline"
          className="min-h-11 w-full !bg-transparent hover:!bg-transparent sm:w-auto"
          disabled={loading}
          onClick={loadDeliveries}
        >
          به‌روزرسانی
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        {/* در موبایل هر ارسال یک کارت است تا جدول پنج‌ستونی اسکرول افقی نسازد. */}
        <div className="space-y-3 md:hidden">
          {deliveries.length === 0 ? (
            <p className="py-4 text-center text-sm text-muted-foreground">
              {loading ? 'در حال دریافت…' : 'هنوز اعلانی ارسال نشده است.'}
            </p>
          ) : (
            deliveries.map((item) => (
              <div key={`m-${item.id}`} className="space-y-2 rounded-lg border border-border p-3">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-medium">{item.recipient_name || '—'}</p>
                    <p dir="rtl" className="truncate text-xs text-muted-foreground">
                      {item.recipient}
                    </p>
                  </div>
                  <Badge
                    variant={item.status === 'sent' ? 'secondary' : 'outline'}
                    className="shrink-0"
                  >
                    {DELIVERY_STATUS_LABELS[item.status] || item.status}
                  </Badge>
                </div>
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                  <span>{formatDateTime(item.created_at)}</span>
                  <span>کانال: {CHANNEL_LABELS[item.channel] || item.channel}</span>
                </div>
                <p className="break-words text-xs text-muted-foreground">
                  {item.error_message || item.body_preview || '—'}
                </p>
              </div>
            ))
          )}
        </div>

        <div className="hidden overflow-x-auto md:block">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="text-right">زمان</TableHead>
              <TableHead className="text-right">کانال</TableHead>
              <TableHead className="text-right">گیرنده</TableHead>
              <TableHead className="text-right">وضعیت</TableHead>
              <TableHead className="text-right">توضیح</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {deliveries.length === 0 ? (
              <TableRow>
                <TableCell colSpan={5} className="text-center text-muted-foreground">
                  {loading ? 'در حال دریافت…' : 'هنوز اعلانی ارسال نشده است.'}
                </TableCell>
              </TableRow>
            ) : (
              deliveries.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>{formatDateTime(item.created_at)}</TableCell>
                  <TableCell>{CHANNEL_LABELS[item.channel] || item.channel}</TableCell>
                  <TableCell>
                    <div className="flex flex-col">
                      <span>{item.recipient_name || '—'}</span>
                      <span dir="rtl" className="text-xs text-muted-foreground">
                        {item.recipient}
                      </span>
                    </div>
                  </TableCell>
                  <TableCell>
                    <Badge variant={item.status === 'sent' ? 'secondary' : 'outline'}>
                      {DELIVERY_STATUS_LABELS[item.status] || item.status}
                    </Badge>
                  </TableCell>
                  <TableCell className="max-w-72 text-xs text-muted-foreground">
                    {item.error_message || item.body_preview || '—'}
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
        </div>
      </CardContent>
    </Card>
  );
}
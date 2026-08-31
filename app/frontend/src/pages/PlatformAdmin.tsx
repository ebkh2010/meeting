/**
 * صفحهٔ مدیریت پلتفرم: فهرست سازمان‌ها و مدیران، ساخت مدیر سازمان،
 * تنظیمات هر سازمان (ایمیل/پیامک/AI/استوریج)، سقف‌های مصرف AI،
 * و سطل آشغال (بازیابی / پاک‌سازی کامل).
 */
import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import LoadingGif from '@/components/LoadingGif';
import { Building2, RefreshCcw, Settings2, Trash2, UserPlus } from 'lucide-react';
import {
  errorMessage,
  platformApi,
  type CreateOrgResult,
  type PlatformAiProvider,
  type PlatformNotify,
  type PlatformOrg,
  type PlatformOrgQuota,
  type PlatformOverview,
  type PlatformStorage,
} from '@/lib/platform';

const AI_PROVIDER_LABELS: Record<string, string> = {
  harf: 'حرف (رونویسی فارسی)',
  elevenlabs: 'ElevenLabs',
  whisper: 'Whisper OpenAI',
  deepseek: 'DeepSeek',
  avalai: 'AvalAI',
  chatgpt: 'ChatGPT',
  kimi: 'Kimi',
};

export default function PlatformAdmin() {
  const [tab, setTab] = useState<'orgs' | 'trash'>('orgs');

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">مدیریت پلتفرم</h1>
        <Tabs value={tab} onValueChange={(value) => setTab(value as 'orgs' | 'trash')}>
          <TabsList>
            <TabsTrigger value="orgs">سازمان‌ها</TabsTrigger>
            <TabsTrigger value="trash">سطل آشغال</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      {tab === 'orgs' ? <OrgsView /> : <TrashView onChanged={() => setTab('orgs')} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* فهرست سازمان‌ها                                                     */
/* ------------------------------------------------------------------ */

function OrgsView() {
  const [items, setItems] = useState<PlatformOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [createOpen, setCreateOpen] = useState(false);
  const [settingsOrg, setSettingsOrg] = useState<PlatformOrg | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await platformApi.listOrgs();
      setItems(data.items);
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن فهرست سازمان‌ها ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleTrash = async (org: PlatformOrg) => {
    try {
      await platformApi.trashOrg(org.id);
      toast.success(`سازمان «${org.name}» به سطل آشغال منتقل شد.`);
      await load();
    } catch (err) {
      toast.error(errorMessage(err, 'انتقال به سطل آشغال ناموفق بود.'));
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="text-sm text-muted-foreground">
          تعریف مدیر سازمان، تغییر تنظیمات و سقف‌های مصرف هر سازمان
        </p>
        <Button onClick={() => setCreateOpen(true)}>
          <UserPlus className="ml-1 h-4 w-4" />
          تعریف مدیر سازمان
        </Button>
      </div>

      {loading ? (
        <LoadingGif label="در حال دریافت فهرست سازمان‌ها…" />
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">
            هنوز سازمانی ساخته نشده است.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y p-0">
            {items.map((org) => (
              <div key={org.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div className="flex items-start gap-3">
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-md bg-brand/10 text-brand-foreground">
                    <Building2 className="h-5 w-5" />
                  </div>
                  <div>
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-medium">{org.name}</span>
                      {org.status === 'trashed' ? (
                        <Badge variant="destructive">در سطل آشغال</Badge>
                      ) : (
                        <Badge variant="secondary">فعال</Badge>
                      )}
                    </div>
                    <p className="text-xs text-muted-foreground">
                      مدیر: {org.admin ? `${org.admin.full_name} (${org.admin.mobile})` : '—'}
                      {org.admin?.must_change_password ? ' · در انتظار تکمیل مشخصات' : ''}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      سهمیهٔ رونویسی سازمان: {org.quota.org_stt_limit_minutes ?? '—'} دقیقه · مصرف:{' '}
                      {org.quota.org_ai_minutes_used} · سقف دلاری مدل زبانی:{' '}
                      {org.quota.org_llm_limit_cents != null
                        ? `${(org.quota.org_llm_limit_cents / 100).toFixed(2)}$`
                        : 'بدون سقف'}
                    </p>
                  </div>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button variant="outline" size="sm" onClick={() => setSettingsOrg(org)}>
                    <Settings2 className="ml-1 h-4 w-4" />
                    تنظیمات
                  </Button>
                  <Button
                    variant="destructive"
                    size="sm"
                    disabled={org.status === 'trashed'}
                    onClick={() => void handleTrash(org)}
                  >
                    <Trash2 className="ml-1 h-4 w-4" />
                    سطل آشغال
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}

      {createOpen && <CreateOrgDialog open onClose={() => setCreateOpen(false)} onCreated={() => void load()} />}
      {settingsOrg && (
        <SettingsDialog org={settingsOrg} onClose={() => setSettingsOrg(null)} onChanged={() => void load()} />
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* دیالوگ ساخت سازمان + مدیر                                           */
/* ------------------------------------------------------------------ */

function CreateOrgDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}) {
  const [form, setForm] = useState({ organization_name: '', first_name: '', last_name: '', mobile: '' });
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<CreateOrgResult | null>(null);

  const handleSubmit = async () => {
    setBusy(true);
    try {
      const data = await platformApi.createOrg(form);
      setResult(data);
      toast.success(`مدیر سازمان «${data.organization.name}» ساخته شد.`);
      onCreated();
    } catch (err) {
      toast.error(errorMessage(err, 'ساخت مدیر سازمان ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>تعریف مدیر سازمان</DialogTitle>
          <DialogDescription>
            نام کاربری مدیر، شمارهٔ موبایل او خواهد بود و رمز عبور رندوم با پیامک ارسال می‌شود؛
            مدیر در نخستین ورود باید کد ملی و ایمیل خود را وارد و رمز را تغییر دهد.
          </DialogDescription>
        </DialogHeader>
        {result ? (
          <div className="space-y-3 rounded-md border p-3 text-sm">
            <p>
              مدیر <b>{result.admin.full_name}</b> برای سازمان <b>{result.organization.name}</b> ساخته شد.
            </p>
            <div className="space-y-1 rounded-md bg-muted p-3 font-mono text-sm" dir="ltr">
              <p>username: {result.default_credentials.username}</p>
              <p>password: {result.default_credentials.password}</p>
            </div>
            <p className="text-xs text-muted-foreground">
              {result.sms.ok
                ? 'رمز عبور با پیامک برای مدیر ارسال شد.'
                : `پیامک ارسال نشد (${result.sms.error || 'خطای نامشخص'}) — رمز را خودتان اعلام کنید.`}
            </p>
            <div className="flex justify-end gap-2">
              <Button
                variant="outline"
                onClick={() => {
                  setResult(null);
                  setForm({ organization_name: '', first_name: '', last_name: '', mobile: '' });
                }}
              >
                مدیر دیگر
              </Button>
              <Button onClick={onClose}>بستن</Button>
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="space-y-1">
              <Label>نام سازمان</Label>
              <Input
                value={form.organization_name}
                onChange={(e) => setForm({ ...form, organization_name: e.target.value })}
                placeholder="مثال: شرکت نمونه"
              />
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1">
                <Label>نام</Label>
                <Input
                  value={form.first_name}
                  onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                  placeholder="مثال: علی"
                />
              </div>
              <div className="space-y-1">
                <Label>نام خانوادگی</Label>
                <Input
                  value={form.last_name}
                  onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                  placeholder="مثال: رضایی"
                />
              </div>
            </div>
            <div className="space-y-1">
              <Label>شمارهٔ تماس (موبایل)</Label>
              <Input
                value={form.mobile}
                onChange={(e) => setForm({ ...form, mobile: e.target.value })}
                placeholder="۰۹۱۲…"
                dir="ltr"
                className="text-right"
              />
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={onClose}>
                انصراف
              </Button>
              <Button
                disabled={
                  busy ||
                  !form.organization_name.trim() ||
                  !form.first_name.trim() ||
                  !form.last_name.trim() ||
                  !form.mobile.trim()
                }
                onClick={() => void handleSubmit()}
              >
                {busy ? 'در حال ساخت…' : 'ساخت سازمان و مدیر'}
              </Button>
            </div>
          </div>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* دیالوگ تنظیمات سازمان                                               */
/* ------------------------------------------------------------------ */

function SettingsDialog({
  org,
  onClose,
  onChanged,
}: {
  org: PlatformOrg;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      setOverview(await platformApi.overview(org.id));
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن تنظیمات سازمان ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, [org.id]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <Dialog open onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-3xl overflow-y-auto">
        <DialogHeader>
          <DialogTitle>تنظیمات «{org.name}»</DialogTitle>
          <DialogDescription>
            تغییرات اینجا برای کل سازمان اعمال می‌شود و در گزارش رویدادهای پلتفرم ثبت می‌گردد.
          </DialogDescription>
        </DialogHeader>
        {loading || !overview ? (
          <LoadingGif label="در حال دریافت تنظیمات…" />
        ) : (
          <Tabs defaultValue="notify" dir="rtl">
            <TabsList className="w-full justify-start overflow-x-auto">
              <TabsTrigger value="notify">ایمیل و پیامک</TabsTrigger>
              <TabsTrigger value="ai">هوش مصنوعی</TabsTrigger>
              <TabsTrigger value="storage">استوریج خارجی</TabsTrigger>
              <TabsTrigger value="quotas">سقف‌های مصرف AI</TabsTrigger>
            </TabsList>
            <TabsContent value="notify" className="pt-3">
              <NotifyForm orgId={org.id} initial={overview.notify} />
            </TabsContent>
            <TabsContent value="ai" className="pt-3">
              <AiProvidersForm orgId={org.id} providers={overview.ai_providers} onReload={() => void load()} />
            </TabsContent>
            <TabsContent value="storage" className="pt-3">
              <StorageForm orgId={org.id} initial={overview.storage} />
            </TabsContent>
            <TabsContent value="quotas" className="pt-3">
              <QuotasForm
                orgId={org.id}
                quota={overview.organization.quota}
                onSaved={() => {
                  void load();
                  onChanged();
                }}
              />
            </TabsContent>
          </Tabs>
        )}
      </DialogContent>
    </Dialog>
  );
}

/* ------------------------------------------------------------------ */
/* فرم اعلان‌ها                                                        */
/* ------------------------------------------------------------------ */

function NotifyForm({ orgId, initial }: { orgId: number; initial: PlatformNotify }) {
  const [form, setForm] = useState<Record<string, string | boolean>>({});
  const [busy, setBusy] = useState(false);

  const value = (key: string): string => String(form[key] ?? initial[key] ?? '');
  const boolValue = (key: string): boolean => Boolean(form[key] ?? initial[key] ?? false);
  const setField = (key: string, val: string | boolean) => setForm((prev) => ({ ...prev, [key]: val }));

  const save = async () => {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        smtp_host: value('smtp_host') || null,
        smtp_port: value('smtp_port') ? Number(value('smtp_port')) : null,
        smtp_username: value('smtp_username') || null,
        smtp_from_email: value('smtp_from_email') || null,
        smtp_from_name: value('smtp_from_name') || null,
        smtp_use_tls: boolValue('smtp_use_tls'),
        smtp_use_ssl: boolValue('smtp_use_ssl'),
        smtp_enabled: boolValue('smtp_enabled'),
        sms_line_number: value('sms_line_number') || null,
        sms_enabled: boolValue('sms_enabled'),
      };
      if (form.smtp_password) payload.smtp_password = String(form.smtp_password);
      if (form.sms_api_key) payload.sms_api_key = String(form.sms_api_key);
      await platformApi.updateNotify(orgId, payload);
      setForm({ smtp_password: '', sms_api_key: '' });
      toast.success('تنظیمات ایمیل و پیامک ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تنظیمات اعلان ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="rounded-md border p-3">
        <div className="mb-2 flex items-center gap-2">
          <Switch checked={boolValue('smtp_enabled')} onCheckedChange={(v) => setField('smtp_enabled', v)} />
          <Label>ایمیل (SMTP) فعال</Label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field label="میزبان SMTP" value={value('smtp_host')} onChange={(v) => setField('smtp_host', v)} />
          <Field
            label="پورت"
            value={value('smtp_port')}
            onChange={(v) => setField('smtp_port', v)}
            dir="ltr"
          />
          <Field label="نام کاربری" value={value('smtp_username')} onChange={(v) => setField('smtp_username', v)} dir="ltr" />
          <Field
            label="رمز عبور (خالی = بدون تغییر)"
            type="password"
            value={value('smtp_password')}
            onChange={(v) => setField('smtp_password', v)}
            dir="ltr"
          />
          <Field label="ایمیل فرستنده" value={value('smtp_from_email')} onChange={(v) => setField('smtp_from_email', v)} dir="ltr" />
          <Field label="نام فرستنده" value={value('smtp_from_name')} onChange={(v) => setField('smtp_from_name', v)} />
        </div>
        <div className="mt-2 flex gap-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={boolValue('smtp_use_ssl')}
              onChange={(e) => setField('smtp_use_ssl', e.target.checked)}
            />
            SSL
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={boolValue('smtp_use_tls')}
              onChange={(e) => setField('smtp_use_tls', e.target.checked)}
            />
            TLS
          </label>
        </div>
      </div>

      <div className="rounded-md border p-3">
        <div className="mb-2 flex items-center gap-2">
          <Switch checked={boolValue('sms_enabled')} onCheckedChange={(v) => setField('sms_enabled', v)} />
          <Label>پیامک فعال</Label>
        </div>
        <div className="grid grid-cols-2 gap-3">
          <Field
            label="کلید API پیامک (خالی = بدون تغییر)"
            type="password"
            value={value('sms_api_key')}
            onChange={(v) => setField('sms_api_key', v)}
            dir="ltr"
          />
          <Field label="شمارهٔ خط فرستنده" value={value('sms_line_number')} onChange={(v) => setField('sms_line_number', v)} dir="ltr" />
        </div>
      </div>

      <div className="flex justify-end">
        <Button disabled={busy} onClick={() => void save()}>
          {busy ? 'در حال ذخیره…' : 'ذخیرهٔ تنظیمات اعلان'}
        </Button>
      </div>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  dir,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  dir?: string;
}) {
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Input
        type={type}
        value={value}
        dir={dir}
        onChange={(e) => onChange(e.target.value)}
        className={dir === 'ltr' ? 'text-left' : ''}
      />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* فرم تأمین‌کننده‌های AI                                              */
/* ------------------------------------------------------------------ */

function AiProvidersForm({
  orgId,
  providers,
  onReload,
}: {
  orgId: number;
  providers: PlatformAiProvider[];
  onReload: () => void;
}) {
  const [drafts, setDrafts] = useState<Record<number, Record<string, string | boolean>>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);

  const draft = (provider: PlatformAiProvider, key: string): string =>
    String(drafts[provider.id]?.[key] ?? (provider as unknown as Record<string, unknown>)[key] ?? '');

  const setDraft = (id: number, key: string, value: string | boolean) =>
    setDrafts((prev) => ({ ...prev, [id]: { ...prev[id], [key]: value } }));

  const save = async (provider: PlatformAiProvider) => {
    setBusyId(provider.id);
    try {
      const d = drafts[provider.id] || {};
      const payload: Record<string, unknown> = {
        enabled: Boolean(d.enabled ?? provider.enabled),
        priority: Number(d.priority ?? provider.priority),
        model: String(d.model ?? provider.model),
        base_url: String(d.base_url ?? provider.base_url),
        diarization: Boolean(d.diarization ?? provider.diarization),
        auth_username: String(d.auth_username ?? provider.auth_username),
      };
      if (d.api_key) payload.api_key = String(d.api_key);
      if (d.password) payload.password = String(d.password);
      await platformApi.updateAiProvider(orgId, provider.id, payload);
      setDrafts((prev) => ({ ...prev, [provider.id]: {} }));
      toast.success(`تنظیمات ${provider.display_name} ذخیره شد.`);
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تأمین‌کننده ناموفق بود.'));
    } finally {
      setBusyId(null);
    }
  };

  const test = async (provider: PlatformAiProvider) => {
    setTestingId(provider.id);
    try {
      const result = await platformApi.testAiProvider(orgId, provider.id);
      if (result.ok) toast.success(`${provider.display_name}: ${result.message}`);
      else toast.error(`${provider.display_name}: ${result.message}`);
      onReload();
    } catch (err) {
      toast.error(errorMessage(err, 'تست اتصال ناموفق بود.'));
    } finally {
      setTestingId(null);
    }
  };

  return (
    <div className="space-y-3">
      {providers.map((provider) => (
        <Card key={provider.id}>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-1">
            <CardTitle className="text-sm">
              {provider.display_name}
              <span className="mr-2 text-xs font-normal text-muted-foreground">
                {provider.kind === 'stt' ? 'رونویسی' : 'مدل زبانی'}
              </span>
            </CardTitle>
            <Switch
              checked={Boolean(drafts[provider.id]?.enabled ?? provider.enabled)}
              onCheckedChange={(v) => setDraft(provider.id, 'enabled', v)}
            />
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-3">
            <Field
              label="نشانی سرویس"
              value={draft(provider, 'base_url')}
              onChange={(v) => setDraft(provider.id, 'base_url', v)}
              dir="ltr"
            />
            <Field label="نام مدل" value={draft(provider, 'model')} onChange={(v) => setDraft(provider.id, 'model', v)} dir="ltr" />
            <Field label="اولویت" value={draft(provider, 'priority')} onChange={(v) => setDraft(provider.id, 'priority', v)} dir="ltr" />
            <Field
              label="نام کاربری (حرف)"
              value={draft(provider, 'auth_username')}
              onChange={(v) => setDraft(provider.id, 'auth_username', v)}
              dir="ltr"
            />
            <Field
              label="کلید API (خالی = بدون تغییر)"
              type="password"
              value={draft(provider, 'api_key')}
              onChange={(v) => setDraft(provider.id, 'api_key', v)}
              dir="ltr"
            />
            <Field
              label="رمز عبور (خالی = بدون تغییر)"
              type="password"
              value={draft(provider, 'password')}
              onChange={(v) => setDraft(provider.id, 'password', v)}
              dir="ltr"
            />
            {provider.supports_diarization && (
              <label className="col-span-2 flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={Boolean(drafts[provider.id]?.diarization ?? provider.diarization)}
                  onChange={(e) => setDraft(provider.id, 'diarization', e.target.checked)}
                />
                تفکیک گوینده (diarization)
              </label>
            )}
            <div className="col-span-2 flex items-center justify-end gap-2">
              {provider.last_test_message ? (
                <span className="ml-auto text-xs text-muted-foreground">{provider.last_test_message}</span>
              ) : null}
              <Button variant="outline" size="sm" disabled={testingId === provider.id} onClick={() => void test(provider)}>
                {testingId === provider.id ? 'در حال تست…' : 'تست اتصال'}
              </Button>
              <Button size="sm" disabled={busyId === provider.id} onClick={() => void save(provider)}>
                {busyId === provider.id ? 'در حال ذخیره…' : 'ذخیره'}
              </Button>
            </div>
          </CardContent>
        </Card>
      ))}
      <p className="text-xs text-muted-foreground">
        {providers.length} تأمین‌کننده · برچسب: {providers.map((p) => AI_PROVIDER_LABELS[p.provider_key] ?? p.provider_key).join('، ')}
      </p>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* فرم استوریج خارجی                                                   */
/* ------------------------------------------------------------------ */

function StorageForm({ orgId, initial }: { orgId: number; initial: PlatformStorage }) {
  const [form, setForm] = useState<Record<string, string | boolean>>({});
  const [busy, setBusy] = useState(false);

  const value = (key: string): string => String(form[key] ?? initial[key] ?? '');
  const boolValue = (key: string): boolean => Boolean(form[key] ?? initial[key] ?? false);
  const setField = (key: string, val: string | boolean) => setForm((prev) => ({ ...prev, [key]: val }));

  const provider = value('provider') || 's3';

  const save = async () => {
    setBusy(true);
    try {
      const payload: Record<string, unknown> = {
        provider,
        display_name: value('display_name'),
        enabled: boolValue('enabled'),
        path_prefix: value('path_prefix'),
      };
      if (provider === 's3') {
        payload.endpoint = value('endpoint');
        payload.bucket = value('bucket');
        payload.region = value('region');
        payload.access_key = value('access_key');
        payload.force_path_style = true;
        if (form.secret_key) payload.secret_key = String(form.secret_key);
      } else {
        payload.webdav_base_url = value('webdav_base_url');
        payload.webdav_username = value('webdav_username');
        if (form.webdav_password) payload.webdav_password = String(form.webdav_password);
      }
      await platformApi.updateStorage(orgId, payload);
      setForm({ secret_key: '', webdav_password: '' });
      toast.success('مقصد استوریج خارجی ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ استوریج خارجی ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        <div className="space-y-1">
          <Label className="text-xs">نوع مقصد</Label>
          <Select value={provider} onValueChange={(v) => setField('provider', v)}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="s3">سرویس سازگار با S3</SelectItem>
              <SelectItem value="webdav">WebDAV</SelectItem>
            </SelectContent>
          </Select>
        </div>
        <Field label="نام نمایشی" value={value('display_name')} onChange={(v) => setField('display_name', v)} />
      </div>
      {provider === 's3' ? (
        <>
          <Field label="نشانی سرویس (endpoint)" value={value('endpoint')} onChange={(v) => setField('endpoint', v)} dir="ltr" />
          <div className="grid grid-cols-2 gap-3">
            <Field label="نام باکت" value={value('bucket')} onChange={(v) => setField('bucket', v)} dir="ltr" />
            <Field label="منطقه" value={value('region')} onChange={(v) => setField('region', v)} dir="ltr" />
            <Field label="کلید دسترسی" value={value('access_key')} onChange={(v) => setField('access_key', v)} dir="ltr" />
            <Field
              label="کلید محرمانه (خالی = بدون تغییر)"
              type="password"
              value={value('secret_key')}
              onChange={(v) => setField('secret_key', v)}
              dir="ltr"
            />
          </div>
        </>
      ) : (
        <>
          <Field label="نشانی WebDAV" value={value('webdav_base_url')} onChange={(v) => setField('webdav_base_url', v)} dir="ltr" />
          <div className="grid grid-cols-2 gap-3">
            <Field label="نام کاربری" value={value('webdav_username')} onChange={(v) => setField('webdav_username', v)} dir="ltr" />
            <Field
              label="رمز عبور (خالی = بدون تغییر)"
              type="password"
              value={value('webdav_password')}
              onChange={(v) => setField('webdav_password', v)}
              dir="ltr"
            />
          </div>
        </>
      )}
      <Field label="پیشوند مسیر" value={value('path_prefix')} onChange={(v) => setField('path_prefix', v)} dir="ltr" />
      <div className="flex items-center gap-2">
        <Switch checked={boolValue('enabled')} onCheckedChange={(v) => setField('enabled', v)} />
        <Label>مقصد فعال</Label>
      </div>
      <div className="flex justify-end">
        <Button disabled={busy} onClick={() => void save()}>
          {busy ? 'در حال ذخیره…' : 'ذخیرهٔ استوریج خارجی'}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* فرم سقف‌های مصرف AI                                                 */
/* ------------------------------------------------------------------ */

function QuotasForm({
  orgId,
  quota,
  onSaved,
}: {
  orgId: number;
  quota: PlatformOrgQuota;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    org_stt: quota.org_stt_limit_minutes != null ? String(quota.org_stt_limit_minutes) : '',
    org_llm: quota.org_llm_limit_cents != null ? String(quota.org_llm_limit_cents) : '',
    admin_stt:
      quota.admin_user.stt_limit_minutes != null
        ? String(quota.admin_user.stt_limit_minutes)
        : String(quota.admin_user.defaults.stt_limit_minutes),
    admin_llm:
      quota.admin_user.llm_limit_cents != null
        ? String(quota.admin_user.llm_limit_cents)
        : String(quota.admin_user.defaults.llm_limit_cents),
  });
  const [busy, setBusy] = useState(false);

  const save = async () => {
    setBusy(true);
    try {
      await platformApi.updateQuotas(orgId, {
        org_stt_limit_minutes: form.org_stt ? Number(form.org_stt) : null,
        org_llm_limit_cents: form.org_llm ? Number(form.org_llm) : null,
        admin_stt_limit_minutes: form.admin_stt ? Number(form.admin_stt) : null,
        admin_llm_limit_cents: form.admin_llm ? Number(form.admin_llm) : null,
      });
      toast.success('سقف‌های مصرف هوش مصنوعی ذخیره شد.');
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ سقف‌ها ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">
        مصرف فعلی سازمان: {quota.org_ai_minutes_used} دقیقه رونویسی در دورهٔ {quota.quota_period || '—'}
      </p>
      <div className="grid grid-cols-2 gap-3">
        <Field
          label="سقف دقیقهٔ رونویسی سازمان (ماهانه)"
          value={form.org_stt}
          onChange={(v) => setForm({ ...form, org_stt: v })}
          dir="ltr"
        />
        <Field
          label="سقف دلاری مدل زبانی سازمان (سنت؛ خالی = بدون سقف)"
          value={form.org_llm}
          onChange={(v) => setForm({ ...form, org_llm: v })}
          dir="ltr"
        />
        <Field
          label="سقف دقیقهٔ رونویسی مدیر سازمان"
          value={form.admin_stt}
          onChange={(v) => setForm({ ...form, admin_stt: v })}
          dir="ltr"
        />
        <Field
          label="سقف دلاری مدیر سازمان (سنت)"
          value={form.admin_llm}
          onChange={(v) => setForm({ ...form, admin_llm: v })}
          dir="ltr"
        />
      </div>
      <p className="text-xs text-muted-foreground">
        مقادیر خالی = بازگشت به پیش‌فرض سامانه ({quota.admin_user.defaults.llm_limit_cents} سنت مدل زبانی و{' '}
        {quota.admin_user.defaults.stt_limit_minutes} دقیقه رونویسی برای هر کاربر).
      </p>
      <div className="flex justify-end">
        <Button disabled={busy} onClick={() => void save()}>
          {busy ? 'در حال ذخیره…' : 'ذخیرهٔ سقف‌ها'}
        </Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* سطل آشغال                                                           */
/* ------------------------------------------------------------------ */

function TrashView({ onChanged }: { onChanged: () => void }) {
  const [items, setItems] = useState<PlatformOrg[]>([]);
  const [loading, setLoading] = useState(true);
  const [purgeOrg, setPurgeOrg] = useState<PlatformOrg | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await platformApi.listTrash();
      setItems(data.items);
    } catch (err) {
      toast.error(errorMessage(err, 'خواندن سطل آشغال ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const handleRestore = async (org: PlatformOrg) => {
    try {
      await platformApi.restoreOrg(org.id);
      toast.success(`سازمان «${org.name}» بازیابی شد.`);
      await load();
      onChanged();
    } catch (err) {
      toast.error(errorMessage(err, 'بازیابی سازمان ناموفق بود.'));
    }
  };

  return (
    <div className="space-y-3">
      {loading ? (
        <LoadingGif label="در حال دریافت سطل آشغال…" />
      ) : items.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-muted-foreground">سطل آشغال خالی است.</CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="divide-y p-0">
            {items.map((org) => (
              <div key={org.id} className="flex flex-col gap-3 p-4 sm:flex-row sm:items-center sm:justify-between">
                <div>
                  <div className="font-medium">{org.name}</div>
                  <p className="text-xs text-muted-foreground">
                    مدیر: {org.admin ? `${org.admin.full_name} (${org.admin.mobile})` : '—'}
                  </p>
                </div>
                <div className="flex shrink-0 gap-2">
                  <Button variant="outline" size="sm" onClick={() => void handleRestore(org)}>
                    <RefreshCcw className="ml-1 h-4 w-4" />
                    بازیابی
                  </Button>
                  <Button variant="destructive" size="sm" onClick={() => setPurgeOrg(org)}>
                    <Trash2 className="ml-1 h-4 w-4" />
                    حذف کامل
                  </Button>
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      )}
      {purgeOrg && <PurgeDialog org={purgeOrg} onClose={() => setPurgeOrg(null)} onDone={() => void load()} />}
    </div>
  );
}

function PurgeDialog({
  org,
  onClose,
  onDone,
}: {
  org: PlatformOrg;
  onClose: () => void;
  onDone: () => void;
}) {
  const [confirm, setConfirm] = useState('');
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);

  const handlePurge = async () => {
    setBusy(true);
    try {
      const result = await platformApi.purgeOrg(org.id, confirm.trim(), name.trim());
      toast.success(
        `سازمان «${org.name}» برای همیشه پاک شد (${result.total_rows} رکورد، ${result.storage_objects_removed} فایل).`,
      );
      onDone();
      onClose();
    } catch (err) {
      toast.error(errorMessage(err, 'پاک‌سازی کامل ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle className="text-destructive">پاک‌سازی کامل «{org.name}»</DialogTitle>
          <DialogDescription>
            این عملیات بازگشت‌ناپذیر است: همهٔ کاربران، جلسات، صورتجلسه‌ها، فایل‌های صوتی و پیوست‌های این
            سازمان برای همیشه حذف می‌شوند.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1">
            <Label>نام دقیق سازمان</Label>
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={org.name} />
          </div>
          <div className="space-y-1">
            <Label>عبارت تأیید: «حذف کامل»</Label>
            <Input value={confirm} onChange={(e) => setConfirm(e.target.value)} placeholder="حذف کامل" />
          </div>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              انصراف
            </Button>
            <Button
              variant="destructive"
              disabled={busy || confirm.trim() !== 'حذف کامل' || name.trim() !== org.name}
              onClick={() => void handlePurge()}
            >
              {busy ? 'در حال پاک‌سازی…' : 'پاک‌سازی نهایی'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

/**
 * پنل «هوش مصنوعی» در تنظیمات سازمان — فقط برای مدیر سازمان.
 *
 * دو زبانهٔ فرعی دارد:
 *  - «تبدیل گفتار به نوشتار» و «مدل زبانی»: فعال/غیرفعال‌سازی، اولویت، نشانی
 *    سرویس، نام مدل، اعتبارنامه (کلید API یا نام کاربری/رمز)، تفکیک گوینده و
 *    تست اتصال واقعی.
 *  - «زنجیرهٔ اولویت و جانشینی»: ترتیب واقعی اجرای سرویس‌ها که بک‌اند به کار
 *    می‌برد، شامل جانشین نهایی پلتفرم.
 */
import { useCallback, useEffect, useState } from 'react';
import { ArrowDown, ArrowUp, CheckCircle2, PlugZap, RefreshCw, Settings2, XCircle } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import AiCredentialFields from '@/components/settings/AiCredentialFields';
import ModelField from '@/components/settings/ModelField';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  AI_KIND_LABELS,
  aiSettingsApi,
  type AiChainResponse,
  type AiKind,
  type AiProvider,
  type AiProvidersResponse,
} from '@/lib/aiSettings';
import { errorMessage, toPersianDigits } from '@/lib/mgmt';

export default function AiProvidersPanel() {
  const [data, setData] = useState<AiProvidersResponse | null>(null);
  const [chain, setChain] = useState<AiChainResponse | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const [providers, chainData] = await Promise.all([
        aiSettingsApi.listProviders(),
        aiSettingsApi.readChain(),
      ]);
      setData(providers);
      setChain(chainData);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت تنظیمات هوش مصنوعی ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <Card>
        <CardContent className="space-y-3 py-6">
          <p className="text-sm text-destructive">{error}</p>
          <Button onClick={load}>تلاش دوباره</Button>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="space-y-3">
        {[0, 1, 2].map((key) => (
          <Skeleton key={key} className="h-32 w-full" />
        ))}
      </div>
    );
  }

  return (
    <Tabs defaultValue="stt" className="space-y-5">
      <TabsList className="flex h-auto w-full flex-nowrap justify-start gap-1 overflow-x-auto md:flex-wrap">
        <TabsTrigger value="stt">رونویسی گفتار</TabsTrigger>
        <TabsTrigger value="llm">مدل زبانی</TabsTrigger>
        <TabsTrigger value="chain">زنجیرهٔ اولویت و جانشینی</TabsTrigger>
      </TabsList>

      <TabsContent value="stt" className="space-y-4">
        <KindSection kind="stt" providers={data.stt} onSaved={load} />
      </TabsContent>
      <TabsContent value="llm" className="space-y-4">
        <KindSection kind="llm" providers={data.llm} onSaved={load} />
      </TabsContent>
      <TabsContent value="chain" className="space-y-4">
        <ChainSection chain={chain} onRefresh={load} />
      </TabsContent>
    </Tabs>
  );
}

function KindSection({
  kind,
  providers,
  onSaved,
}: {
  kind: AiKind;
  providers: AiProvider[];
  onSaved: () => void;
}) {
  const enabledCount = providers.filter((item) => item.enabled).length;

  /** جابه‌جایی اولویت با تعویض مقدار priority دو ردیف مجاور. */
  const move = async (index: number, direction: -1 | 1) => {
    const target = providers[index + direction];
    const current = providers[index];
    if (!target || !current) return;
    try {
      await aiSettingsApi.updateProvider(current.id, { priority: target.priority });
      await aiSettingsApi.updateProvider(target.id, { priority: current.priority });
      toast.success('ترتیب اولویت به‌روزرسانی شد.');
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'تغییر ترتیب اولویت ناموفق بود.'));
    }
  };

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base">{AI_KIND_LABELS[kind]}</CardTitle>
          <CardDescription>
            سرویس‌ها به ترتیب اولویت اجرا می‌شوند؛ اگر سرویس اول پاسخ ندهد، سرویس بعدی به‌صورت
            خودکار جانشین می‌شود. در حال حاضر {toPersianDigits(enabledCount)} سرویس فعال است.
          </CardDescription>
        </CardHeader>
      </Card>

      {providers.map((provider, index) => (
        <ProviderCard
          key={provider.id}
          provider={provider}
          index={index}
          total={providers.length}
          onMove={move}
          onSaved={onSaved}
        />
      ))}
    </div>
  );
}

function ProviderCard({
  provider,
  index,
  total,
  onMove,
  onSaved,
}: {
  provider: AiProvider;
  index: number;
  total: number;
  onMove: (index: number, direction: -1 | 1) => void;
  onSaved: () => void;
}) {
  const [baseUrl, setBaseUrl] = useState(provider.base_url);
  const [model, setModel] = useState(provider.model);
  const [username, setUsername] = useState(provider.auth_username);
  const [apiKey, setApiKey] = useState('');
  const [password, setPassword] = useState('');
  const [enabled, setEnabled] = useState(provider.enabled);
  const [diarization, setDiarization] = useState(provider.diarization);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    setBaseUrl(provider.base_url);
    setModel(provider.model);
    setUsername(provider.auth_username);
    setEnabled(provider.enabled);
    setDiarization(provider.diarization);
    setApiKey('');
    setPassword('');
  }, [provider]);

  const usesLogin = provider.auth_mode === 'username_password';

  /** اگر کاربر کلید/رمز تازه وارد کند و فعال‌سازی را دست نزده باشد، خودکار فعال می‌شود. */
  const typedCredential = usesLogin
    ? Boolean(password.trim() && username.trim())
    : Boolean(apiKey.trim());
  const effectiveEnabled = typedCredential && !enabled ? true : enabled;

  const save = async () => {
    setSaving(true);
    try {
      await aiSettingsApi.updateProvider(provider.id, {
        enabled: effectiveEnabled,
        base_url: baseUrl.trim(),
        model: model.trim(),
        diarization,
        auth_username: username.trim(),
        // سرویس‌های با ورود کاربری/رمز (حرف) توکن نمی‌گیرند؛ هر توکن قدیمی هم پاک می‌شود
        ...(usesLogin
          ? { clear_api_key: true }
          : apiKey.trim()
            ? { api_key: apiKey.trim() }
            : {}),
        ...(password.trim() ? { password: password.trim() } : {}),
      });
      toast.success(`تنظیمات «${provider.display_name}» ذخیره شد.`);
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تنظیمات ناموفق بود.'));
    } finally {
      setSaving(false);
    }
  };

  const test = async () => {
    setTesting(true);
    try {
      const result = await aiSettingsApi.testProvider(provider.id);
      if (result.ok) toast.success(result.message || 'اتصال برقرار شد.');
      else toast.error(result.message || 'اتصال برقرار نشد.');
      onSaved();
    } catch (err) {
      toast.error(errorMessage(err, 'تست اتصال ناموفق بود.'));
    } finally {
      setTesting(false);
    }
  };

  return (
    <Card className={enabled ? 'border-primary/50' : undefined}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="space-y-1">
            <CardTitle className="flex items-center gap-2 text-base">
              {provider.display_name}
              <Badge variant="outline">اولویت {toPersianDigits(provider.priority)}</Badge>
              {provider.enabled ? (
                <Badge>فعال</Badge>
              ) : (
                <Badge variant="secondary">غیرفعال</Badge>
              )}
            </CardTitle>
            <CardDescription>{provider.note}</CardDescription>
          </div>
          <div className="flex items-center gap-1">
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={index === 0}
              onClick={() => onMove(index, -1)}
              title="انتقال به اولویت بالاتر"
            >
              <ArrowUp className="h-4 w-4" />
            </Button>
            <Button
              type="button"
              variant="outline"
              size="icon"
              disabled={index === total - 1}
              onClick={() => onMove(index, 1)}
              title="انتقال به اولویت پایین‌تر"
            >
              <ArrowDown className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="space-y-4">
        {/* فقط توکن (یا نام کاربری/رمز) و مدل در دید است؛ نشانی و اولویت و
            تفکیک گوینده در «تنظیمات پیشرفته» قرار دارند. */}
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="rounded-md border border-border p-3">
            <AiCredentialFields
              authMode={provider.auth_mode}
              apiKey={apiKey}
              password={password}
              authUsername={username}
              apiKeyMasked={provider.api_key_masked}
              passwordMasked={provider.password_masked}
              hasApiKey={Boolean(provider.has_api_key)}
              hasPassword={Boolean(provider.has_password)}
              clearApiKey={false}
              clearPassword={false}
              onChange={(patch) => {
                if (patch.apiKey !== undefined) setApiKey(patch.apiKey);
                if (patch.password !== undefined) setPassword(patch.password);
                if (patch.authUsername !== undefined) setUsername(patch.authUsername);
              }}
            />
          </div>
          <ModelField
            value={model}
            options={provider.model_options || []}
            onChange={setModel}
          />
        </div>

        {typedCredential && !enabled && (
          <p className="text-xs text-emerald-600">با ذخیره، این سرویس فعال می‌شود.</p>
        )}

        <Button
          type="button"
          variant="ghost"
          size="sm"
          className="h-7 gap-1 px-0 text-xs text-muted-foreground"
          onClick={() => setAdvanced((current) => !current)}
        >
          <Settings2 className="h-3.5 w-3.5" />
          {advanced ? 'بستن تنظیمات پیشرفته' : 'تنظیمات پیشرفته (نشانی سرویس، تفکیک گوینده)'}
        </Button>
        {advanced && (
          <div className="grid gap-4 rounded-md border border-dashed border-border p-3 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor={`base-${provider.id}`}>نشانی سرویس</Label>
              <Input
                id={`base-${provider.id}`}
                dir="ltr"
                className="text-left"
                value={baseUrl}
                onChange={(event) => setBaseUrl(event.target.value)}
              />
            </div>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-5">
          <label className="flex items-center gap-2 text-sm">
            <Checkbox
              checked={enabled}
              onCheckedChange={(value) => setEnabled(value === true)}
            />
            <span>استفاده از این سرویس فعال باشد</span>
          </label>
          {provider.supports_diarization && (
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={diarization}
                onCheckedChange={(value) => setDiarization(value === true)}
              />
              <span>تفکیک گوینده (diarization)</span>
            </label>
          )}
        </div>

        <div className="flex flex-wrap items-center gap-3">
          <Button onClick={save} disabled={saving}>
            {saving ? 'در حال ذخیره…' : 'ذخیرهٔ تنظیمات'}
          </Button>
          <Button variant="outline" onClick={test} disabled={testing} className="gap-2">
            <PlugZap className="h-4 w-4" />
            {testing ? 'در حال تست…' : 'تست اتصال'}
          </Button>
          {provider.last_test_at && (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {provider.last_test_ok ? (
                <CheckCircle2 className="h-4 w-4 text-primary" />
              ) : (
                <XCircle className="h-4 w-4 text-destructive" />
              )}
              {provider.last_test_message || (provider.last_test_ok ? 'موفق' : 'ناموفق')}
            </span>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

function ChainSection({
  chain,
  onRefresh,
}: {
  chain: AiChainResponse | null;
  onRefresh: () => void;
}) {
  if (!chain) return <Skeleton className="h-40 w-full" />;

  const sections: { kind: AiKind; items: typeof chain.stt }[] = [
    { kind: 'stt', items: chain.stt },
    { kind: 'llm', items: chain.llm },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-muted-foreground">
          این ترتیب همان زنجیره‌ای است که بک‌اند هنگام رونویسی و تولید صورتجلسه اجرا می‌کند؛ در صورت
          خطای یک سرویس، سرویس بعدی جانشین می‌شود.
        </p>
        <Button variant="outline" size="sm" onClick={onRefresh} className="gap-2">
          <RefreshCw className="h-4 w-4" />
          بازخوانی
        </Button>
      </div>

      {sections.map((section) => (
        <Card key={section.kind}>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">{AI_KIND_LABELS[section.kind]}</CardTitle>
            <CardDescription>
              {section.items.length === 0
                ? 'هیچ سرویسی فعال و دارای اعتبارنامه نیست؛ فقط جانشین پیش‌فرض پلتفرم به کار می‌رود.'
                : `${toPersianDigits(section.items.length)} سرویس در زنجیره قرار دارد.`}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {section.items.map((item, index) => (
              <div
                key={`${section.kind}-${item.provider_key}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3 text-sm"
              >
                <span className="flex items-center gap-2">
                  <Badge variant="outline">{toPersianDigits(index + 1)}</Badge>
                  {item.display_name}
                  {item.diarization && <Badge variant="secondary">تفکیک گوینده</Badge>}
                </span>
                <span dir="rtl" className="text-xs text-muted-foreground">
                  {item.model}
                </span>
              </div>
            ))}
            <div className="flex items-center justify-between gap-2 rounded-md border border-dashed border-border p-3 text-sm">
              <span className="flex items-center gap-2">
                <Badge variant="outline">آخرین</Badge>
                جانشین پیش‌فرض پلتفرم
              </span>
              <span dir="rtl" className="text-xs text-muted-foreground">
                {chain.platform_fallback}
              </span>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
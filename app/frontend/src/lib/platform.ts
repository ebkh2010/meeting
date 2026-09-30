/**
 * لایهٔ دسترسی مدیریت پلتفرم — قرارداد دقیقاً با روتر `/api/v1/platform` یکسان است.
 * توکن نشست (X-App-Token) همان توکن ورود پلتفرم است.
 */
import axios from 'axios';
import { client } from '@/lib/mgmt';
import { authHeaders, clearToken, isUnauthorized } from '@/lib/session';

const BASE = '/api/v1/platform';

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

function bustCache(url: string, method: HttpMethod): string {
  if (method !== 'GET') return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}_ts=${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

/** استخراج پیام خطای فارسی؛ خطاهای اعتبارسنجی FastAPI (آرایهٔ detail) رشته می‌شوند
 *  تا هرگز شیء/آرایه به toast نرسد و رندر React نشکند. */
export function errorMessage(error: unknown, fallback = 'انجام درخواست ناموفق بود.'): string {
  const candidate = error as {
    data?: { detail?: unknown };
    response?: { data?: { detail?: unknown } };
    message?: unknown;
  };
  const detail = candidate?.data?.detail ?? candidate?.response?.data?.detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) =>
        typeof item === 'object' && item !== null
          ? String((item as { msg?: unknown }).msg ?? JSON.stringify(item))
          : String(item),
      )
      .filter(Boolean);
    if (parts.length) return parts.join('؛ ');
  }
  if (typeof detail === 'string' && detail) return detail;
  if (typeof candidate?.message === 'string' && candidate.message) return candidate.message;
  return fallback;
}

async function call<T>(
  url: string,
  method: HttpMethod = 'GET',
  data: Record<string, unknown> = {},
): Promise<T> {
  try {
    const response = await client.apiCall.invoke({
      url: bustCache(url, method),
      method,
      data,
      options: { headers: authHeaders() },
    });
    return response.data as T;
  } catch (error) {
    if (isUnauthorized(error)) clearToken();
    throw error;
  }
}

/* ------------------------------------------------------------------ */
/* انواع داده                                                          */
/* ------------------------------------------------------------------ */

export interface PlatformMe {
  id: number;
  username: string;
  display_name: string;
  role: string;
  role_label: string;
  /** «مدیر اصلی»: تنها حسابی که می‌تواند مدیر پلتفرم دیگر تعریف/حذف کند. */
  is_owner: boolean;
  status: string;
  is_platform_admin: boolean;
}

/** یک حساب مدیر پلتفرم در فهرست مدیریت مدیران. */
export interface PlatformAdminAccount {
  id: number;
  username: string;
  display_name: string;
  role: string;
  role_label: string;
  is_owner: boolean;
  status: string;
  is_platform_admin: boolean;
  created_at: string;
}

export interface PlatformAdminList {
  admins: PlatformAdminAccount[];
  /** شناسهٔ حساب خودِ کاربر جاری — برای غیرفعال‌کردن عملیات روی خودش. */
  me_id: number;
}

export interface PlatformOrgAdmin {
  id: number;
  username: string;
  full_name: string;
  mobile: string;
  email: string;
  must_change_password: boolean;
  status: string;
  last_login_at: string;
  /** ثبت‌نام شده ولی هنوز فعال نشده: تکمیل مشخصات یا نخستین ورود انجام نشده است. */
  pending_activation: boolean;
}

export interface PlatformOrgQuota {
  org_stt_limit_minutes: number | null;
  org_ai_minutes_used: number;
  quota_period: string;
  org_llm_limit_cents: number | null;
  /** مصرف دلاری کل سازمان در دورهٔ جاری (سنت). */
  org_llm_used_cents: number;
  admin_user: {
    user_id: string | null;
    llm_limit_cents: number | null;
    stt_limit_minutes: number | null;
    used_llm_cents: number | null;
    used_stt_minutes: number | null;
    defaults: { llm_limit_cents: number; stt_limit_minutes: number };
  };
}

export interface PlatformOrg {
  id: number;
  name: string;
  slug: string;
  status: string;
  created_at: string;
  admin: PlatformOrgAdmin | null;
  quota: PlatformOrgQuota;
}

export interface PlatformNotify {
  smtp_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_masked: string;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
  smtp_from_name: string;
  sms_enabled: boolean;
  sms_api_key_masked: string;
  sms_line_number: string;
  [key: string]: unknown;
}

export interface PlatformAiProvider {
  id: number;
  kind: string;
  provider_key: string;
  display_name: string;
  enabled: boolean;
  priority: number;
  base_url: string;
  model: string;
  /** مدل‌های پیشنهادی این تأمین‌کننده برای انتخاب از فهرست. */
  model_options?: string[];
  api_key_masked: string;
  has_api_key?: boolean;
  auth_mode?: string;
  auth_username: string;
  has_password?: boolean;
  password_masked: string;
  diarization: boolean;
  supports_diarization: boolean;
  last_test_ok: boolean;
  last_test_message: string;
  [key: string]: unknown;
}

/** پیش‌فرض سراسری یک تأمین‌کنندهٔ هوش مصنوعی برای همهٔ سازمان‌ها. */
export interface PlatformAiDefault {
  provider_key: string;
  kind: string;
  display_name: string;
  auth_mode: string;
  supports_diarization: boolean;
  note: string;
  model_options: string[];
  default_base_url: string;
  default_model: string;
  /** آیا مقداری از همین پنل ثبت شده است؟ */
  configured: boolean;
  enabled: boolean;
  model: string;
  base_url: string;
  priority: number | null;
  diarization: boolean;
  auth_username: string;
  api_key_masked: string;
  has_api_key: boolean;
  password_masked: string;
  has_password: boolean;
  updated_at: string;
  /** panel = ثبت‌شده در پنل، code = پیش‌فرض کد/متغیر محیطی، none = تعریف‌نشده */
  source: string;
}

export interface PlatformAiDefaults {
  defaults: { stt: PlatformAiDefault[]; llm: PlatformAiDefault[] };
  catalog: Record<
    string,
    {
      provider_key: string;
      display_name: string;
      auth_mode: string;
      supports_diarization: boolean;
      default_base_url: string;
      default_model: string;
      model_options: string[];
      note: string;
    }[]
  >;
}

export interface PlatformAiDefaultApplyResult {
  organizations: number;
  updated_organizations: number;
  updated_providers: number;
  providers: Record<string, number>;
}

export interface PlatformStorage {
  configured: boolean;
  provider: string;
  display_name: string;
  enabled: boolean;
  endpoint: string;
  bucket: string;
  region: string;
  path_prefix: string;
  access_key: string;
  secret_key_masked: string;
  has_secret_key: boolean;
  force_path_style: boolean;
  webdav_base_url: string;
  webdav_username: string;
  webdav_password_masked: string;
  has_webdav_password: boolean;
  restore_retention_days: number;
  tenant_prefix: string;
  last_test_ok: boolean;
  last_test_message: string;
  [key: string]: unknown;
}

export interface PlatformOverview {
  organization: PlatformOrg;
  notify: PlatformNotify;
  ai_providers: PlatformAiProvider[];
  ai_chain: { stt: { provider_key: string; display_name: string }[]; llm: { provider_key: string; display_name: string }[] };
  storage: PlatformStorage;
}

export interface CreateOrgResult {
  organization: { id: number; name: string; slug: string; status: string };
  admin: { username: string; full_name: string; mobile: string };
  default_credentials: { username: string; password: string; is_default_password: boolean };
  sms: { ok: boolean; error: string };
}

/** مصرف کل پلتفرم برای دو هوش پیش‌فرض (حرف/روشن و DeepSeek). */
export interface PlatformAiSummary {
  period: string;
  stt: {
    provider_key: string;
    provider_label: string;
    minutes_total: number;
    minutes_period: number;
    vidara_tokens_total: number;
    vidara_tokens_period: number;
  };
  llm: {
    provider_key: string;
    provider_label: string;
    tokens_in_total: number;
    tokens_out_total: number;
    tokens_total: number;
    tokens_in_period: number;
    tokens_out_period: number;
    tokens_period: number;
    cost_cents_total: number;
    usd_total: number;
    usd_period: number;
    vidara_tokens_total: number;
    vidara_tokens_period: number;
  };
  vidara_tokens_total: number;
  vidara_tokens_period: number;
  deepseek_rates: {
    input_usd_per_m: number;
    output_usd_per_m: number;
    as_of: string;
    source: string;
  };
}

/* ------------------------------------------------------------------ */
/* API                                                                 */
/* ------------------------------------------------------------------ */

export interface PlatformOrgActivity {
  organization: { id: number; name: string };
  admin: {
    username: string;
    full_name: string;
    mobile: string;
    email: string;
    created_at: string;
    last_login_at: string;
  };
  /** مصرف توکن ویدارا و تفکیک دیپ‌سیک / حرف (روشن) همین سازمان. */
  ai_usage: PlatformAiSummary;
  logins: {
    id: number;
    actor_name: string;
    created_at: string;
    detail: string;
  }[];
  activities: {
    id: number;
    actor_name: string;
    actor_role: string;
    action: string;
    entity_type: string;
    detail: string;
    created_at: string;
  }[];
}

/** یک جای‌نگهدار قابل درج در قالب پیامک یادآوری فعال‌سازی. */
export interface PlatformMessagePlaceholder {
  token: string;
  label: string;
  description: string;
  sample: string;
}

/** قالب سراسری پیامک یادآوری فعال‌سازی به‌همراه پیش‌نمایش رندرشده. */
export interface PlatformActivationTemplate {
  template: string;
  default_template: string;
  is_custom: boolean;
  max_length: number;
  optout_line: string;
  placeholders: PlatformMessagePlaceholder[];
  preview: string;
}

/** تنظیم سراسری مدت نگهداری فایل‌های مدیا. */
export interface PlatformMediaRetentionSettings {
  days: number;
  default_days: number;
  is_custom: boolean;
  /** اجرای خودکار (انتقال/حذف پس از انقضا) — پیش‌فرض خاموش. */
  auto: boolean;
  /** اگر روشن باشد، مقدار ثبت‌شده توسط مدیر سازمان مقدم است. */
  allow_org_override: boolean;
  bounds: { min: number; max: number };
}

export interface PlatformMediaRetentionItem {
  organization_id: number;
  organization_name: string;
  organization_days: number;
  meeting_id: number;
  meeting_title: string;
  source_kind: string;
  kind_label: string;
  source_id: number;
  file_name: string;
  size_bytes: number;
  age_days: number;
  created_at: string;
  /** archive = انتقال به استوریج خارجی، delete = حذف از سرور. */
  action: string;
  action_label: string;
}

export interface PlatformMediaRetention {
  settings: PlatformMediaRetentionSettings;
  summary: {
    total: number;
    total_bytes: number;
    archive_count: number;
    delete_count: number;
    organizations: number;
    generated_at: string;
  };
}

export interface PlatformMediaRetentionReport {
  days: number;
  auto: boolean;
  allow_org_override: boolean;
  generated_at: string;
  total: number;
  total_bytes: number;
  archive_count: number;
  delete_count: number;
  organizations: number;
  dry_run?: boolean;
  automatic?: boolean;
  archived?: number;
  deleted?: number;
  failed?: number;
  freed_bytes?: number;
  errors?: { file_name: string; organization_name: string; action: string; message: string }[];
  items: PlatformMediaRetentionItem[];
  truncated: boolean;
}

export const platformApi = {
  me: () => call<{ user: PlatformMe }>(`${BASE}/me`),

  /** تغییر نام کاربری / نام نمایشی مدیر پلتفرم. */
  updateMe: (payload: { username?: string; display_name?: string }) =>
    call<{ user: PlatformMe }>(`${BASE}/me`, 'PATCH', payload),

  /** تغییر رمز عبور مدیر پلتفرم. */
  changePassword: (currentPassword: string, newPassword: string) =>
    call<{ ok: boolean; detail: string }>(`${BASE}/change-password`, 'POST', {
      current_password: currentPassword,
      new_password: newPassword,
    }),

  /* --- مدیریت مدیران پلتفرم (فقط «مدیر اصلی») --- */

  /** فهرست مدیران پلتفرم. */
  listAdmins: () => call<PlatformAdminList>(`${BASE}/admins`),

  /** تعریف مدیر پلتفرم جدید. */
  createAdmin: (payload: { username: string; display_name?: string; password: string }) =>
    call<{ success: boolean; admin: PlatformAdminAccount }>(`${BASE}/admins`, 'POST', payload),

  /** ویرایش نام/نام کاربری/رمز/وضعیت یک مدیر پلتفرم. */
  updateAdmin: (
    adminId: number,
    payload: { username?: string; display_name?: string; password?: string; status?: string },
  ) =>
    call<{ success: boolean; admin: PlatformAdminAccount; detail: string }>(
      `${BASE}/admins/${adminId}`,
      'PATCH',
      payload,
    ),

  /** حذف مدیر پلتفرم. */
  deleteAdmin: (adminId: number) =>
    call<{ success: boolean; id: number; username: string }>(`${BASE}/admins/${adminId}`, 'DELETE'),

  listOrgs: () => call<{ items: PlatformOrg[]; total: number }>(`${BASE}/orgs`),
  listTrash: () => call<{ items: PlatformOrg[]; total: number }>(`${BASE}/trash`),
  overview: (orgId: number) => call<PlatformOverview>(`${BASE}/orgs/${orgId}/overview`),

  /** مصرف کل پلتفرم (حرف/روشن و DeepSeek) با معادل توکن ویدارا و دلار نرخ روز. */
  aiSummary: () => call<PlatformAiSummary>(`${BASE}/ai-summary`),

  /** لاگ و آمار حساب: تاریخ‌های ورود و فعالیت‌های ثبت‌شدهٔ سازمان. */
  orgActivity: (orgId: number) => call<PlatformOrgActivity>(`${BASE}/orgs/${orgId}/activity`),

  createOrg: (payload: {
    organization_name: string;
    first_name: string;
    last_name: string;
    mobile: string;
  }) => call<CreateOrgResult>(`${BASE}/orgs`, 'POST', payload),

  /** تولید رمز جدید برای مدیر سازمان و ارسال دوبارهٔ آن با پیامک. */
  resendAdminSms: (orgId: number) =>
    call<{
      success: boolean;
      sms: { ok: boolean; error: string; provider_message_id: string };
      default_credentials: { username: string; password: string };
    }>(`${BASE}/orgs/${orgId}/resend-admin-sms`, 'POST'),

  /** ارسال پیامک یادآوری فعال‌سازی برای سازمان ثبت‌نام‌شدهٔ هنوز فعال‌نشده. */
  sendActivationReminder: (orgId: number) =>
    call<{
      success: boolean;
      sms: { ok: boolean; error: string; provider_message_id: string };
      default_credentials: { username: string; password: string };
      pending_activation: boolean;
    }>(`${BASE}/orgs/${orgId}/activation-reminder`, 'POST'),

  /** خواندن قالب سراسری پیامک یادآوری فعال‌سازی برای ویرایش در پنل. */
  getActivationTemplate: () =>
    call<PlatformActivationTemplate>(`${BASE}/settings/activation-reminder`),

  /** ثبت قالب جدید؛ با `reset: true` متن به پیش‌فرض بازمی‌گردد. */
  updateActivationTemplate: (payload: { template?: string; reset?: boolean }) =>
    call<PlatformActivationTemplate>(`${BASE}/settings/activation-reminder`, 'PUT', payload),

  /** پیش‌نمایش متن با مقادیر نمونه (بدون ذخیره‌سازی). */
  previewActivationTemplate: (template: string) =>
    call<{ preview: string }>(`${BASE}/settings/activation-reminder/preview`, 'POST', {
      template,
    }),

  /** تنظیم سراسری مدت نگهداری فایل‌های مدیا + خلاصهٔ فایل‌های منقضی. */
  getMediaRetention: () => call<PlatformMediaRetention>(`${BASE}/settings/media-retention`),

  /** ثبت مدت نگهداری، کلید اجرای خودکار و اجازهٔ بازنویسی توسط مدیر سازمان. */
  updateMediaRetention: (payload: {
    days?: number;
    auto?: boolean;
    allow_org_override?: boolean;
    reset_days?: boolean;
  }) => call<PlatformMediaRetention>(`${BASE}/settings/media-retention`, 'PUT', payload),

  /** گزارش فایل‌های منقضی و سرنوشت هرکدام (بدون تغییر). */
  mediaRetentionReport: () => call<PlatformMediaRetentionReport>(`${BASE}/media-retention/report`),

  /** اجرای دستی سیاست نگهداری: انتقال به استوریج خارجی یا حذف از سرور. */
  runMediaRetention: () =>
    call<PlatformMediaRetentionReport>(`${BASE}/media-retention/run`, 'POST'),

  updateNotify: (orgId: number, payload: Record<string, unknown>) =>
    call<PlatformNotify>(`${BASE}/orgs/${orgId}/notify`, 'PATCH', payload),

  /** ارسال ایمیل آزمایشی با تنظیمات ذخیره‌شدهٔ سازمان. */
  testNotifyEmail: (orgId: number, toEmail?: string) =>
    call<{ ok: boolean; recipient: string; detail: string }>(
      `${BASE}/orgs/${orgId}/notify/test-email`,
      'POST',
      { to_email: toEmail || '' },
    ),

  /** ارسال پیامک آزمایشی با تنظیمات ذخیره‌شدهٔ سازمان. */
  testNotifySms: (orgId: number, toMobile?: string) =>
    call<{ ok: boolean; recipient: string; provider_message_id: string; detail: string }>(
      `${BASE}/orgs/${orgId}/notify/test-sms`,
      'POST',
      { to_mobile: toMobile || '' },
    ),

  updateAiProvider: (orgId: number, providerId: number, payload: Record<string, unknown>) =>
    call<PlatformAiProvider>(`${BASE}/orgs/${orgId}/ai-providers/${providerId}`, 'PATCH', payload),

  /** پیش‌فرض‌های هوش مصنوعی همهٔ سازمان‌ها (قابل ویرایش از پنل). */
  getAiDefaults: () => call<PlatformAiDefaults>(`${BASE}/settings/ai-defaults`),

  /** ثبت پیش‌فرض یک تأمین‌کننده: مدل، نشانی، توکن و اعتبارنامه. */
  updateAiDefault: (providerKey: string, payload: Record<string, unknown>) =>
    call<{ defaults: PlatformAiDefaults['defaults'] }>(
      `${BASE}/settings/ai-defaults/${providerKey}`,
      'PUT',
      payload,
    ),

  /** تست اتصال پیش‌فرض؛ مقادیر ارسالی (تست پیش از ذخیره) مقدم‌اند. */
  testAiDefault: (providerKey: string, payload: Record<string, unknown>) =>
    call<{ ok: boolean; message: string }>(
      `${BASE}/settings/ai-defaults/${providerKey}/test`,
      'POST',
      payload,
    ),

  /** حذف پیش‌فرض پنل و بازگشت به پیش‌فرض کد/سرور. */
  removeAiDefault: (providerKey: string) =>
    call<{ defaults: PlatformAiDefaults['defaults'] }>(
      `${BASE}/settings/ai-defaults/${providerKey}`,
      'DELETE',
    ),

  /** اعمال فوری پیش‌فرض‌ها روی سازمان‌های تنظیم‌نشده. */
  applyAiDefaults: () =>
    call<PlatformAiDefaultApplyResult>(`${BASE}/settings/ai-defaults-apply`, 'POST'),

  testAiProvider: (orgId: number, providerId: number) =>
    call<{ ok: boolean; message: string }>(
      `${BASE}/orgs/${orgId}/ai-providers/${providerId}/test`,
      'POST',
    ),

  updateStorage: (orgId: number, payload: Record<string, unknown>) =>
    call<PlatformStorage>(`${BASE}/orgs/${orgId}/storage`, 'PUT', payload),

  updateQuotas: (orgId: number, payload: Record<string, unknown>) =>
    call<PlatformOrgQuota>(`${BASE}/orgs/${orgId}/quotas`, 'PATCH', payload),

  trashOrg: (orgId: number) =>
    call<{ success: boolean; status: string; id: number; name: string }>(
      `${BASE}/orgs/${orgId}/trash`,
      'POST',
    ),

  restoreOrg: (orgId: number) =>
    call<{ success: boolean; status: string; id: number; name: string }>(
      `${BASE}/trash/${orgId}/restore`,
      'POST',
    ),

  purgeOrg: async (orgId: number, confirm: string, confirmOrgName: string) => {
    // web-sdk برای متد DELETE بدنه را به پارامتر کوئری تبدیل می‌کند و بک‌اند
    // بدنهٔ JSON می‌خواهد؛ بنابراین این فراخوان مستقیم با axios انجام می‌شود.
    try {
      const response = await axios.request<{
        success: boolean;
        total_rows: number;
        storage_objects_removed: number;
      }>({
        method: 'DELETE',
        url: `${BASE}/trash/${orgId}`,
        data: { confirm, confirm_org_name: confirmOrgName },
        headers: authHeaders(),
      });
      return response.data;
    } catch (error) {
      if (isUnauthorized(error)) clearToken();
      throw error;
    }
  },
};

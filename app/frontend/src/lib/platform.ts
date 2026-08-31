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
  is_platform_admin: boolean;
}

export interface PlatformOrgAdmin {
  id: number;
  username: string;
  full_name: string;
  mobile: string;
  email: string;
  must_change_password: boolean;
  status: string;
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
  api_key_masked: string;
  auth_username: string;
  password_masked: string;
  diarization: boolean;
  supports_diarization: boolean;
  last_test_ok: boolean;
  last_test_message: string;
  [key: string]: unknown;
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

/* ------------------------------------------------------------------ */
/* API                                                                 */
/* ------------------------------------------------------------------ */

export const platformApi = {
  me: () => call<{ user: PlatformMe }>(`${BASE}/me`),

  listOrgs: () => call<{ items: PlatformOrg[]; total: number }>(`${BASE}/orgs`),
  listTrash: () => call<{ items: PlatformOrg[]; total: number }>(`${BASE}/trash`),
  overview: (orgId: number) => call<PlatformOverview>(`${BASE}/orgs/${orgId}/overview`),

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

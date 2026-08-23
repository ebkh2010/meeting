/**
 * لایهٔ دسترسی به تنظیمات هوش مصنوعی سازمان (`/api/v1/ai-settings`).
 *
 * نام فیلدها دقیقاً با قرارداد روتر `routers/ai_settings.py` یکسان است؛ کلیدهای
 * API هرگز به‌صورت خام برنمی‌گردند و فقط نمای ماسک‌شده در دسترس است.
 */
import { client } from '@/lib/mgmt';
import { authHeaders, clearToken, isUnauthorized } from '@/lib/session';

const BASE = '/api/v1/ai-settings';

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

async function invoke<T>(
  url: string,
  method: HttpMethod = 'GET',
  data: Record<string, unknown> = {},
): Promise<T> {
  try {
    const response = await client.apiCall.invoke({
      url,
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

/** نوع سرویس هوش مصنوعی: تبدیل گفتار به نوشتار یا مدل زبانی. */
export type AiKind = 'stt' | 'llm';

export const AI_KIND_LABELS: Record<AiKind, string> = {
  stt: 'تبدیل گفتار به نوشتار (رونویسی)',
  llm: 'مدل زبانی (صورتجلسه و مصوبات)',
};

/** حالت احراز هویت تأمین‌کننده. */
export type AiAuthMode = 'api_key' | 'username_password';

export interface AiProvider {
  id: number;
  kind: AiKind;
  kind_label: string;
  provider_key: string;
  display_name: string;
  enabled: boolean;
  priority: number;
  base_url: string;
  model: string;
  auth_mode: AiAuthMode;
  supports_diarization: boolean;
  diarization: boolean;
  auth_username: string;
  api_key_masked: string;
  has_api_key: boolean;
  password_masked: string;
  has_password: boolean;
  note: string;
  last_test_ok: boolean;
  last_test_at: string;
  last_test_message: string;
}

export interface AiCatalogEntry {
  provider_key: string;
  display_name: string;
  auth_mode: AiAuthMode;
  supports_diarization: boolean;
  default_base_url: string;
  default_model: string;
  note: string;
}

export interface AiProvidersResponse {
  stt: AiProvider[];
  llm: AiProvider[];
  catalog: Record<AiKind, AiCatalogEntry[]>;
}

export interface AiChainItem {
  priority: number;
  provider_key: string;
  display_name: string;
  diarization: boolean;
  model: string;
}

export interface AiChainResponse {
  stt: AiChainItem[];
  llm: AiChainItem[];
  platform_fallback: string;
}

/** بدنهٔ ذخیرهٔ تنظیمات؛ کلید خالی یعنی «کلید فعلی بدون تغییر». */
export interface AiProviderUpdate {
  enabled?: boolean;
  priority?: number;
  base_url?: string;
  model?: string;
  diarization?: boolean;
  auth_username?: string;
  api_key?: string;
  password?: string;
  clear_api_key?: boolean;
  clear_password?: boolean;
}

export const aiSettingsApi = {
  listProviders: () => invoke<AiProvidersResponse>(`${BASE}/providers`),

  updateProvider: (providerId: number, payload: AiProviderUpdate) =>
    invoke<AiProvider>(`${BASE}/providers/${providerId}`, 'PATCH', payload as Record<string, unknown>),

  testProvider: (providerId: number) =>
    invoke<{ ok: boolean; message: string; provider: AiProvider }>(
      `${BASE}/providers/${providerId}/test`,
      'POST',
    ),

  readChain: () => invoke<AiChainResponse>(`${BASE}/chain`),
};
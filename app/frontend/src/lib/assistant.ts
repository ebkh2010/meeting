/**
 * لایهٔ دسترسی به «دستیار هوشمند» سازمان (`/api/v1/assistant`).
 *
 * قرارداد فیلدها دقیقاً با روتر `routers/assistant.py` یکسان است. دسترسی فقط برای
 * نقش «مدیر سازمان» و «دبیر جلسه» است؛ برای نقش «عضو» بک‌اند ۴۰۳ برمی‌گرداند و
 * فرانت هم دکمهٔ دستیار را رندر نمی‌کند.
 */
import { client } from '@/lib/mgmt';
import { authHeaders, clearToken, isUnauthorized } from '@/lib/session';

const BASE = '/api/v1/assistant';

type HttpMethod = 'GET' | 'POST';

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

/** حالت کار دستیار: جست‌وجو در محتوای جلسات یا راهنمای استفاده از سامانه. */
export type AssistantMode = 'meetings' | 'guide';

export const ASSISTANT_MODE_LABELS: Record<AssistantMode, string> = {
  meetings: 'جست‌وجو در محتوای جلسات',
  guide: 'راهنمای استفاده از سامانه',
};

export interface AssistantSource {
  kind: string;
  kind_label: string;
  title: string;
  snippet: string;
  link: string;
  meeting_id: number | null;
  meeting_title: string;
  time_label: string;
  score: number;
}

export interface AssistantStatus {
  available: boolean;
  role: string;
  modes: { value: AssistantMode; label: string }[];
  llm_providers: { provider_key: string; display_name: string; model: string }[];
  hint: string;
}

export interface AssistantAnswer {
  mode: AssistantMode;
  mode_label: string;
  question: string;
  answer: string;
  provider: string;
  model_available: boolean;
  sources: AssistantSource[];
  attempts_note: string;
}

export const assistantApi = {
  status: () => invoke<AssistantStatus>(`${BASE}/status`),

  ask: (mode: AssistantMode, question: string) =>
    invoke<AssistantAnswer>(`${BASE}/ask`, 'POST', { mode, question }),
};
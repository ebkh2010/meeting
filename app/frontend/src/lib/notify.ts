/**
 * لایهٔ فراخوان تنظیمات اعلان سازمان (SMTP و پیامک قاصدک) و گزارش ارسال‌ها.
 * قرارداد فیلدها دقیقاً مطابق روتر `/api/v1/notify` است.
 */
import { client } from '@/lib/mgmt';
import { authHeaders, clearToken, isUnauthorized } from '@/lib/session';

const BASE = '/api/v1/notify';

async function call<T>(
  url: string,
  method: 'GET' | 'POST' | 'PATCH' = 'GET',
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

export interface NotifySettings {
  smtp_enabled: boolean;
  smtp_host: string;
  smtp_port: number;
  smtp_username: string;
  smtp_password_set: boolean;
  smtp_use_tls: boolean;
  smtp_use_ssl: boolean;
  smtp_from_email: string;
  smtp_from_name: string;
  sms_enabled: boolean;
  sms_api_key_set: boolean;
  sms_line_number: string;
}

export interface DeliveryItem {
  id: number;
  meeting_id: number;
  membership_id: number;
  channel: string;
  recipient: string;
  recipient_name: string;
  status: string;
  provider_message_id: string;
  error_message: string;
  body_preview: string;
  created_at: string;
}

export interface InviteSummary {
  sms_sent?: number;
  sms_failed?: number;
  email_sent?: number;
  email_failed?: number;
  skipped?: number;
  detail?: string;
}

export const CHANNEL_LABELS: Record<string, string> = {
  sms: 'پیامک',
  email: 'ایمیل',
};

export const DELIVERY_STATUS_LABELS: Record<string, string> = {
  sent: 'ارسال شد',
  failed: 'ناموفق',
  skipped: 'ارسال نشد',
  pending: 'در انتظار',
};

export const notifyApi = {
  readSettings: () => call<NotifySettings>(`${BASE}/settings`),
  updateSettings: (payload: Record<string, unknown>) =>
    call<NotifySettings>(`${BASE}/settings`, 'PATCH', payload),
  testEmail: (toEmail: string) =>
    call<{ ok: boolean; recipient: string; detail: string }>(`${BASE}/test-email`, 'POST', {
      to_email: toEmail,
    }),
  testSms: (toMobile: string) =>
    call<{ ok: boolean; recipient: string; detail: string }>(`${BASE}/test-sms`, 'POST', {
      to_mobile: toMobile,
    }),
  deliveries: (meetingId?: number, limit = 60) =>
    call<{ items: DeliveryItem[] }>(`${BASE}/deliveries`, 'GET', {
      ...(meetingId ? { meeting_id: meetingId } : {}),
      limit,
    }),
  resend: (meetingId: number) =>
    call<InviteSummary>(`${BASE}/meetings/${meetingId}/resend`, 'POST', {}),
};

/** خلاصهٔ خوانا از نتیجهٔ ارسال اعلان برای نمایش در پیام موفقیت. */
export function summarizeInvite(summary?: InviteSummary | null): string {
  if (!summary) return '';
  if (summary.detail) return summary.detail;
  const parts: string[] = [];
  if (summary.sms_sent) parts.push(`${summary.sms_sent} پیامک`);
  if (summary.email_sent) parts.push(`${summary.email_sent} ایمیل`);
  const failed = (summary.sms_failed || 0) + (summary.email_failed || 0);
  if (parts.length === 0 && failed === 0) {
    return 'اعلانی ارسال نشد؛ کانال‌های ارسال را در تنظیمات اعلان فعال کنید.';
  }
  const sentText = parts.length ? `ارسال شد: ${parts.join(' و ')}` : 'هیچ اعلانی ارسال نشد';
  return failed ? `${sentText} — ${failed} مورد ناموفق` : sentText;
}
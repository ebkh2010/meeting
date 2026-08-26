/**
 * لایهٔ فراخوان احراز هویت مستقل و مدیریت کاربران سازمان.
 *
 * همهٔ فراخوان‌ها از `client.apiCall.invoke` عبور می‌کنند و توکن نشست را با هدر
 * `X-App-Token` می‌فرستند. نام فیلدها دقیقاً با قرارداد روتر `/api/v1/app-auth`
 * یکسان است تا هیچ نگاشت میانی لازم نباشد.
 */
import { client } from '@/lib/mgmt';
import { authHeaders, clearToken, isUnauthorized, setToken } from '@/lib/session';

const BASE = '/api/v1/app-auth';

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'DELETE';

/**
 * شکستن هر کش URL-keyed برای GETهای احرازشده (پاسخ‌ها وابسته به توکن نشست است).
 */
function bustCache(url: string, method: HttpMethod): string {
  if (method !== 'GET') return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}_ts=${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
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

/**
 * کلیدهای فنی نقش — تنها منبع حقیقت مقایسهٔ دسترسی در فرانت‌اند.
 * این مقادیر باید دقیقاً با `services/mgmt_core.py` در بک‌اند یکسان باشند؛
 * برچسب فارسی فقط برای نمایش است و هرگز مبنای مقایسهٔ دسترسی نیست.
 */
export const ROLE_ADMIN = 'org_admin';
export const ROLE_SECRETARY = 'secretary';
export const ROLE_MEMBER = 'member';

/** نگارش‌های قدیمی/معادل نقش مدیر که ممکن است در دادهٔ پیشین مانده باشد. */
const LEGACY_ADMIN_ROLES = ['admin', 'owner', 'org-admin', 'orgadmin'];

export const ROLE_OPTIONS = [
  { value: ROLE_ADMIN, label: 'مدیر سازمان' },
  { value: ROLE_SECRETARY, label: 'دبیر جلسه' },
  { value: ROLE_MEMBER, label: 'عضو' },
];

/** تشخیص نقش مدیر سازمان با کلید فنی (نه برچسب نمایشی). */
export function isAdminRole(role: string | null | undefined): boolean {
  const value = (role || '').trim().toLowerCase();
  return value === ROLE_ADMIN || LEGACY_ADMIN_ROLES.includes(value);
}

export const GENDER_OPTIONS = [
  { value: 'male', label: 'مرد' },
  { value: 'female', label: 'زن' },
];

/** رمز عبور پیش‌فرض کاربرانی که مدیر بدون تعیین رمز می‌سازد (منبع حقیقت: بک‌اند). */
export const DEFAULT_PASSWORD = 'vidara@12345';

export interface AppUser {
  id: number;
  membership_id: number | null;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  mobile: string;
  email: string;
  email_verified?: boolean;
  mobile_verified?: boolean;
  national_id: string;
  gender: string;
  gender_label: string;
  role: string;
  role_label: string;
  status?: string;
  must_change_password?: boolean;
  last_login_at?: string | null;
}

export interface AppOrganization {
  id: number;
  name: string;
  slug: string;
  timezone: string;
}

/** کارت کوتاه سازمان در مرحلهٔ انتخاب سازمان هنگام ورود. */
export interface LoginOrganizationOption {
  organization_id: number;
  name: string;
  slug: string;
  role: string;
  role_label: string;
  /** فقط در فهرست «تغییر سازمان» پر می‌شود و سازمان فعال نشست را نشان می‌دهد. */
  is_current?: boolean;
}

export interface SessionPayload {
  token: string;
  user: AppUser;
  organization: AppOrganization;
}

/** پاسخ ورود همیشه یک نشست کامل است؛ رمز عبور هر فضا، حساب مقصد را مشخص می‌کند. */
export type LoginResult = SessionPayload;

export interface MePayload {
  user: AppUser;
  organization: AppOrganization;
}

export interface RegisterPayload {
  organization_name: string;
  first_name: string;
  last_name: string;
  mobile: string;
  national_id: string;
  gender: string;
  email?: string;
  username?: string;
  password: string;
}

/**
 * ورودی ساخت کاربر توسط مدیر سازمان — فقط نام، نام خانوادگی و موبایل الزامی است؛
 * کد ملی و جنسیت اختیاری‌اند و رمز عبور در نبودِ مقدار، پیش‌فرض سیستم می‌شود.
 */
export interface UserPayload {
  first_name: string;
  last_name: string;
  mobile: string;
  national_id?: string;
  gender?: string;
  email?: string;
  password?: string;
  role: string;
}

/** تکمیل اجباری مشخصات در نخستین ورود: نام کاربری جدید، رمز جدید و کد ملی. */
export interface CompleteProfilePayload {
  username: string;
  new_password: string;
  national_id: string;
  gender?: string;
  email?: string;
}

export interface CompleteProfileResult {
  ok: boolean;
  detail: string;
  user?: AppUser;
}

export interface CreatedUserResult {
  user?: AppUser;
  id?: number;
  username: string;
  full_name?: string;
  role?: string;
  role_label?: string;
  /** اعتبارنامهٔ بازگشتی روتر: نام کاربری = موبایل، رمز = انتخاب مدیر یا پیش‌فرض سیستم. */
  default_credentials?: {
    username: string;
    password?: string;
    is_default_password?: boolean;
    password_hint?: string;
  };
  temporary_password?: string;
  password?: string;
  detail?: string;
}

export interface MemberOption {
  membership_id: number;
  full_name: string;
  role: string;
  role_label: string;
  email?: string;
  mobile?: string;
}

export interface VerifyRequestResult {
  ok: boolean;
  already_verified?: boolean;
  detail?: string;
  expires_in_seconds?: number;
  cooldown_seconds?: number;
}

export interface VerifyConfirmResult {
  ok: boolean;
  detail: string;
}

/** رویداد مصرف هوش مصنوعی یک کار (برای پنل کاربر). */
export interface AiUsageEvent {
  id: number;
  kind: string;
  kind_label: string;
  provider: string;
  model: string;
  minutes_charged: number;
  tokens_in: number;
  tokens_out: number;
  cost_cents: number;
  detail: string;
  job_id: number | null;
  meeting_id: number | null;
  created_at: string;
}

/** نمای سهمیهٔ هوش مصنوعی کاربر جاری. */
export interface AiUsageQuota {
  period: string;
  llm: {
    limit_cents: number;
    used_cents: number;
    remaining_cents: number;
    currency: string;
  };
  stt: {
    limit_minutes: number;
    used_minutes: number;
    remaining_minutes: number;
  };
}

export interface AiUsagePayload {
  quota: AiUsageQuota;
  events: AiUsageEvent[];
}

/* ------------------------------------------------------------------ */
/* توابع API                                                           */
/* ------------------------------------------------------------------ */

export const authApi = {
  /** ثبت‌نام سازمان جدید؛ ثبت‌نام‌کننده مدیر همان سازمان می‌شود. */
  register: async (payload: RegisterPayload): Promise<SessionPayload> => {
    const result = await call<SessionPayload>(`${BASE}/register`, 'POST', {
      ...payload,
      email: payload.email || '',
      username: payload.username || '',
    });
    setToken(result.token);
    return result;
  },

  /**
   * ورود با جفت «نام کاربری + رمز عبور» بدون مرحلهٔ انتخاب سازمان.
   *
   * رمز عبور هر فضای کاری مستقل است؛ همین جفت اعتبارنامه است که تعیین می‌کند
   * کاربر وارد کدام فضا (سازمان/نقش) می‌شود.
   */
  login: async (username: string, password: string): Promise<LoginResult> => {
    const result = await call<LoginResult>(`${BASE}/login`, 'POST', {
      username,
      password,
    });
    setToken(result.token);
    return result;
  },

  me: () => call<MePayload>(`${BASE}/me`),

  /** سهمیه و مصرف هوش مصنوعی خودِ کاربر (دلار مدل زبانی + دقیقهٔ رونویسی). */
  aiUsage: () => call<AiUsagePayload>(`${BASE}/me/ai-usage`),

  /** ویرایش مشخصات خودِ کاربر — برای همهٔ نقش‌ها (مدیر، دبیر، عضو) باز است. */
  updateMe: (payload: Record<string, unknown>) =>
    call<AppUser>(`${BASE}/me`, 'PATCH', payload),

  /** درخواست کد تأیید ایمیل؛ کد به ایمیل ثبت‌شدهٔ کاربر ارسال می‌شود. */
  requestEmailCode: () =>
    call<VerifyRequestResult>(`${BASE}/verify/email/request`, 'POST', {}),

  /** تأیید ایمیل با کد ۶ رقمی ارسال‌شده. */
  confirmEmailCode: (code: string) =>
    call<VerifyConfirmResult>(`${BASE}/verify/email/confirm`, 'POST', { code }),

  /** درخواست کد تأیید موبایل؛ کد با پیامک ارسال می‌شود. */
  requestMobileCode: () =>
    call<VerifyRequestResult>(`${BASE}/verify/mobile/request`, 'POST', {}),

  /** تأیید شمارهٔ موبایل با کد ۶ رقمی ارسال‌شده. */
  confirmMobileCode: (code: string) =>
    call<VerifyConfirmResult>(`${BASE}/verify/mobile/confirm`, 'POST', { code }),

  /** سازمان‌هایی که کاربر جاری در آن‌ها حساب فعال دارد (برای تغییر سازمان). */
  myOrganizations: () =>
    call<{ items: LoginOrganizationOption[]; current_organization_id: number }>(
      `${BASE}/organizations`,
    ),

  /**
   * تغییر فضای کاری فعال نشست بدون خروج کامل؛ برای جلوگیری از ارتقای دسترسی،
   * نام کاربری و رمز عبور همان فضا الزامی است. توکن تازه با نقش فضای مقصد صادر
   * و جایگزین توکن فعلی می‌شود.
   */
  switchOrganization: async (
    organizationId: number,
    username: string,
    password: string,
  ): Promise<SessionPayload> => {
    const result = await call<SessionPayload>(`${BASE}/switch-organization`, 'POST', {
      organization_id: organizationId,
      username,
      password,
    });
    setToken(result.token);
    return result;
  },

  changePassword: (currentPassword: string, newPassword: string) =>
    call<{ ok: boolean; detail: string }>(`${BASE}/change-password`, 'POST', {
      current_password: currentPassword,
      new_password: newPassword,
    }),

  /**
   * تکمیل اجباری مشخصات در نخستین ورود کاربرِ ساخته‌شده توسط مدیر:
   * نام کاربری جدید، رمز عبور جدید و کد ملی (جنسیت/ایمیل اختیاری).
   */
  completeProfile: (payload: CompleteProfilePayload) =>
    call<CompleteProfileResult>(`${BASE}/complete-profile`, 'POST', {
      ...payload,
      gender: payload.gender || '',
      email: payload.email || '',
    }),

  logout: () => clearToken(),

  /**
   * حذف کامل سازمان و همهٔ داده‌های آن — فقط مدیر سازمان، با تأیید عبارتی
   * «حذف کامل» و نام دقیق سازمان. این عملیات بازگشت‌ناپذیر است.
   */
  deleteOrganization: (confirm: string, orgName: string) =>
    call<{
      success: boolean;
      detail: string;
      removed?: Record<string, number>;
      total?: number;
    }>(`${BASE}/delete-organization`, 'POST', {
      confirm,
      confirm_org_name: orgName,
    }),

  listUsers: () => call<{ items: AppUser[]; total?: number }>(`${BASE}/users`),

  createUser: (payload: UserPayload) =>
    call<CreatedUserResult>(`${BASE}/users`, 'POST', { ...payload, email: payload.email || '' }),

  updateUser: (userId: number, payload: Record<string, unknown>) =>
    call<CreatedUserResult>(`${BASE}/users/${userId}`, 'PATCH', payload),

  listMembers: () => call<{ items: MemberOption[] }>(`${BASE}/members`),
};

export function roleLabel(role: string): string {
  return ROLE_OPTIONS.find((item) => item.value === role)?.label || role;
}
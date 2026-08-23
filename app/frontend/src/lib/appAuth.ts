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

async function call<T>(
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

export interface AppUser {
  id: number;
  membership_id: number | null;
  username: string;
  first_name: string;
  last_name: string;
  full_name: string;
  mobile: string;
  email: string;
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
  needs_organization?: boolean;
  organizations?: LoginOrganizationOption[];
}

/**
 * پاسخ مرحلهٔ اول ورود وقتی شخص در چند سازمان حساب فعال دارد؛ توکنی صادر
 * نمی‌شود تا کاربر ابتدا سازمان فعال نشست را انتخاب کند.
 */
export interface LoginChoicePayload {
  needs_organization: true;
  organizations: LoginOrganizationOption[];
  detail: string;
}

export type LoginResult = SessionPayload | LoginChoicePayload;

/** تشخیص اینکه پاسخ ورود نیازمند انتخاب سازمان است یا نشست کامل ساخته شد. */
export function needsOrganizationChoice(result: LoginResult): result is LoginChoicePayload {
  return (result as LoginChoicePayload).needs_organization === true;
}

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

export interface UserPayload {
  first_name: string;
  last_name: string;
  mobile: string;
  national_id: string;
  gender: string;
  email?: string;
  role: string;
}

export interface CreatedUserResult {
  user?: AppUser;
  id?: number;
  username: string;
  full_name?: string;
  role?: string;
  role_label?: string;
  /** اعتبارنامهٔ پیش‌فرض بازگشتی روتر: نام کاربری = موبایل، رمز = کد ملی. */
  default_credentials?: { username: string; password_hint: string };
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
   * ورود با نام کاربری/رمز و انتخاب اختیاری سازمان.
   *
   * اگر شخص در چند سازمان حساب فعال داشته باشد و `organizationId` ارسال نشود،
   * پاسخ بدون توکن و با `needs_organization` برمی‌گردد تا UI فهرست سازمان‌ها
   * را نشان دهد؛ پس از انتخاب، همین تابع با شناسهٔ سازمان دوباره صدا می‌شود.
   */
  login: async (
    username: string,
    password: string,
    organizationId?: number,
  ): Promise<LoginResult> => {
    const result = await call<LoginResult>(`${BASE}/login`, 'POST', {
      username,
      password,
      ...(organizationId ? { organization_id: organizationId } : {}),
    });
    if (!needsOrganizationChoice(result)) setToken(result.token);
    return result;
  },

  me: () => call<MePayload>(`${BASE}/me`),

  /** سازمان‌هایی که کاربر جاری در آن‌ها حساب فعال دارد (برای تغییر سازمان). */
  myOrganizations: () =>
    call<{ items: LoginOrganizationOption[]; current_organization_id: number }>(
      `${BASE}/organizations`,
    ),

  /**
   * تغییر سازمان فعال نشست بدون خروج کامل؛ توکن تازه با نقش سازمان مقصد صادر و
   * جایگزین توکن فعلی می‌شود تا همهٔ گاردهای دسترسی از سازمان جدید بخوانند.
   */
  switchOrganization: async (
    organizationId: number,
    password: string,
  ): Promise<SessionPayload> => {
    const result = await call<SessionPayload>(`${BASE}/switch-organization`, 'POST', {
      organization_id: organizationId,
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

  logout: () => clearToken(),

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
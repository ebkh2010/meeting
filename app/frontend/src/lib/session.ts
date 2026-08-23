/**
 * نگه‌داری نشست احراز هویت مستقل سامانه در مرورگر.
 *
 * توکن با هدر `X-App-Token` به بک‌اند فرستاده می‌شود تا با هدر استاندارد
 * `Authorization` پلتفرم تداخل نداشته باشد. این فایل هیچ وابستگی به لایهٔ API
 * ندارد تا از حلقهٔ import میان `mgmt.ts` و لایهٔ احراز هویت جلوگیری شود.
 */

const TOKEN_KEY = 'vidara.session.token';

let cachedToken: string | null = null;
const listeners = new Set<() => void>();

/** خواندن توکن نشست؛ در نخستین فراخوان از حافظهٔ مرورگر بازیابی می‌شود. */
export function getToken(): string {
  if (cachedToken !== null) return cachedToken;
  try {
    cachedToken = window.localStorage.getItem(TOKEN_KEY) || '';
  } catch {
    cachedToken = '';
  }
  return cachedToken;
}

export function setToken(token: string): void {
  cachedToken = token || '';
  try {
    if (cachedToken) {
      window.localStorage.setItem(TOKEN_KEY, cachedToken);
    } else {
      window.localStorage.removeItem(TOKEN_KEY);
    }
  } catch {
    /* حالت مرور خصوصی: نشست فقط در حافظهٔ برنامه نگه داشته می‌شود. */
  }
  listeners.forEach((listener) => listener());
}

export function clearToken(): void {
  setToken('');
}

export function isSignedIn(): boolean {
  return Boolean(getToken());
}

/** اشتراک در تغییر نشست (ورود یا خروج) برای هم‌گام‌سازی پوستهٔ برنامه. */
export function onSessionChange(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** هدرهای لازم برای هر فراخوان API؛ در حالت مهمان خالی است. */
export function authHeaders(): Record<string, string> {
  const token = getToken();
  return token ? { 'X-App-Token': token } : {};
}

/** تشخیص پاسخ ۴۰۱ برای پاک‌سازی خودکار نشست منقضی. */
export function isUnauthorized(error: unknown): boolean {
  const candidate = error as { status?: number; response?: { status?: number } };
  return candidate?.status === 401 || candidate?.response?.status === 401;
}
/**
 * صفحهٔ ورود سامانه (مسیر «/»).
 *
 * ثبت‌نام سازمان از این صفحه حذف شده است؛ ساخت سازمان و مدیر آن فقط از طریق
 * کنسول مدیریت پلتفرم انجام می‌شود.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { errorMessage } from '@/lib/mgmt';
import { authApi } from '@/lib/appAuth';
import { getSessionUser, isSignedIn } from '@/lib/session';
import VidaraBranding from '@/components/VidaraBranding';

export default function Login() {
  const navigate = useNavigate();
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  useEffect(() => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.documentElement.setAttribute('lang', 'fa');
    if (isSignedIn()) {
      const sessionUser = getSessionUser();
      const target =
        sessionUser && String(sessionUser.role) === 'platform_admin' ? '/platform' : '/dashboard';
      navigate(target, { replace: true });
    }
  }, [navigate]);

  /**
   * ورود با جفت «نام کاربری + رمز عبور»؛ رمز عبور هر فضای کاری مستقل است و
   * کاربر مستقیم وارد همان فضای کاریِ همان اعتبارنامه می‌شود.
   */
  const handleLogin = async () => {
    setBusy(true);
    setError('');
    try {
      const result = await authApi.login(loginForm.username.trim(), loginForm.password);
      // نشست مدیر پلتفرم به کنسول پلتفرم می‌رود؛ بدون دسترسی به فضای کاری.
      if (result.user?.role === 'platform_admin') {
        navigate('/platform', { replace: true });
        return;
      }
      // کاربری که مدیر ساخته است پیش از ورود به فضای کاری باید مشخصاتش را تکمیل کند.
      if (result.user?.must_change_password) {
        navigate('/complete-profile', { replace: true });
        return;
      }
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'ورود ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-background" dir="rtl">
      <main className="flex flex-1 items-center justify-center px-3 py-6 sm:px-4 sm:py-10">
        <Card className="w-full max-w-xl border-border/70 shadow-lg">
          <CardHeader className="space-y-2 text-center">
            <div className="mx-auto flex h-16 w-full max-w-[220px] items-center justify-center">
              <img
                src="/assets/vidara-logo-horizontal.png"
                alt="ویدارا - نسخه جلسات"
                className="h-full w-full object-contain"
              />
            </div>
            <CardTitle className="text-xl">ویدارا - نسخه جلسات</CardTitle>
            <CardDescription>
              برای مدیریت جلسات، صورتجلسه‌ها و اقدامات سازمان خود وارد شوید.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="login-username">نام کاربری یا شماره موبایل</Label>
              <Input
                id="login-username"
                value={loginForm.username}
                autoComplete="username"
                onChange={(event) =>
                  setLoginForm({ ...loginForm, username: event.target.value })
                }
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="login-password">رمز عبور</Label>
              <Input
                id="login-password"
                type="password"
                value={loginForm.password}
                autoComplete="current-password"
                onChange={(event) =>
                  setLoginForm({ ...loginForm, password: event.target.value })
                }
                onKeyDown={(event) => {
                  if (event.key === 'Enter') handleLogin();
                }}
              />
            </div>
            <p className="text-xs text-muted-foreground">
              رمز عبور هر فضای کاری مستقل است؛ با همین نام کاربری و رمز عبور، وارد همان
              سازمان و نقشی می‌شوید که این اعتبارنامه برای آن تعریف شده است.
            </p>

            <Button className="w-full" disabled={busy} onClick={handleLogin}>
              {busy ? 'در حال ورود…' : 'ورود به سامانه'}
            </Button>

            <p className="text-center text-xs text-muted-foreground">
              برای ثبت‌نام با شماره تماس ۰۲۱۴۱۰۲۱۰۰۰ داخلی ۱۱۴ یا ۳۳۷ پشتیبانی ویدارا تماس
              حاصل فرمایید.
            </p>

            {error && (
              <div className="surface-error mt-4 rounded-lg p-3">
                <p className="text-sm text-error">{error}</p>
              </div>
            )}
          </CardContent>
        </Card>
      </main>

      <footer className="border-t border-border bg-sidebar/60 py-4">
        <div className="flex items-center justify-center">
          <VidaraBranding />
        </div>
      </footer>
    </div>
  );
}

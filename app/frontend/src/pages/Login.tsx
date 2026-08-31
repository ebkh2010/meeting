/**
 * صفحهٔ ورود و ثبت‌نام مستقل سامانه (مسیر «/»).
 * هیچ وابستگی به احراز هویت پلتفرم ندارد؛ نشست با توکن مستقل ساخته می‌شود.
 */
import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { errorMessage } from '@/lib/mgmt';
import { authApi, GENDER_OPTIONS } from '@/lib/appAuth';
import { getSessionUser, isSignedIn } from '@/lib/session';
import VidaraBranding from '@/components/VidaraBranding';

const EMPTY_REGISTER = {
  organization_name: '',
  first_name: '',
  last_name: '',
  mobile: '',
  national_id: '',
  gender: '',
  email: '',
  username: '',
  password: '',
};

export default function Login() {
  const navigate = useNavigate();
  const [tab, setTab] = useState('login');
  const [loginForm, setLoginForm] = useState({ username: '', password: '' });
  const [registerForm, setRegisterForm] = useState({ ...EMPTY_REGISTER });
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

  const handleRegister = async () => {
    setBusy(true);
    setError('');
    try {
      await authApi.register(registerForm);
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'ثبت‌نام ناموفق بود.'));
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
              برای مدیریت جلسات، صورتجلسه‌ها و اقدامات سازمان خود وارد شوید یا سازمان جدید بسازید.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <Tabs value={tab} onValueChange={setTab}>
              <TabsList className="grid h-auto w-full grid-cols-2">
                <TabsTrigger value="login" className="min-h-11">
                  ورود
                </TabsTrigger>
                <TabsTrigger value="register" className="min-h-11">
                  ثبت‌نام سازمان
                </TabsTrigger>
              </TabsList>

              <TabsContent value="login" className="mt-5 space-y-4">
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
              </TabsContent>

              <TabsContent value="register" className="mt-5 space-y-4">
                <div className="space-y-2">
                  <Label htmlFor="reg-org">نام سازمان</Label>
                  <Input
                    id="reg-org"
                    value={registerForm.organization_name}
                    onChange={(event) =>
                      setRegisterForm({ ...registerForm, organization_name: event.target.value })
                    }
                  />
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <div className="space-y-2">
                    <Label htmlFor="reg-first">نام</Label>
                    <Input
                      id="reg-first"
                      value={registerForm.first_name}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, first_name: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-last">نام خانوادگی</Label>
                    <Input
                      id="reg-last"
                      value={registerForm.last_name}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, last_name: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-mobile">شماره موبایل</Label>
                    <Input
                      id="reg-mobile"
                      inputMode="tel"
                      placeholder="۰۹۱۲۳۴۵۶۷۸۹"
                      value={registerForm.mobile}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, mobile: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-national">کد ملی</Label>
                    <Input
                      id="reg-national"
                      inputMode="numeric"
                      value={registerForm.national_id}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, national_id: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>جنسیت</Label>
                    <Select
                      value={registerForm.gender}
                      onValueChange={(value) => setRegisterForm({ ...registerForm, gender: value })}
                    >
                      <SelectTrigger>
                        <SelectValue placeholder="انتخاب کنید" />
                      </SelectTrigger>
                      <SelectContent>
                        {GENDER_OPTIONS.map((option) => (
                          <SelectItem key={option.value} value={option.value}>
                            {option.label}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-email">ایمیل (اختیاری)</Label>
                    <Input
                      id="reg-email"
                      type="email"
                      value={registerForm.email}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, email: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-username">نام کاربری (اختیاری)</Label>
                    <Input
                      id="reg-username"
                      value={registerForm.username}
                      placeholder="پیش‌فرض: شماره موبایل"
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, username: event.target.value })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reg-password">رمز عبور</Label>
                    <Input
                      id="reg-password"
                      type="password"
                      autoComplete="new-password"
                      value={registerForm.password}
                      onChange={(event) =>
                        setRegisterForm({ ...registerForm, password: event.target.value })
                      }
                    />
                  </div>
                </div>
                <p className="text-xs text-muted-foreground">
                  ثبت‌نام‌کننده به‌عنوان «مدیر سازمان» ثبت می‌شود و می‌تواند سایر کاربران سازمان را
                  بسازد.
                </p>
                <Button className="w-full" disabled={busy} onClick={handleRegister}>
                  {busy ? 'در حال ثبت‌نام…' : 'ساخت سازمان و ورود'}
                </Button>
              </TabsContent>
            </Tabs>

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
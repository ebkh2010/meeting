/**
 * تکمیل اجباری مشخصات در نخستین ورود کاربرِ ساخته‌شده توسط مدیر سازمان.
 *
 * کاربر با نام کاربری = شمارهٔ موبایل و رمز تعیین‌شده (یا رمز پیش‌فرض سیستم)
 * وارد شده است و پیش از ورود به فضای کاری باید نام کاربری جدید، رمز عبور جدید
 * و کد ملی خود را ثبت کند؛ جنسیت و ایمیل اختیاری‌اند. این صفحه پوستهٔ برنامه را
 * رندر نمی‌کند تا کاربر پیش از تکمیل، به هیچ بخش دیگری دسترسی نداشته باشد.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { LogOut } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import { errorMessage } from '@/lib/mgmt';
import { authApi, GENDER_OPTIONS } from '@/lib/appAuth';
import { isSignedIn } from '@/lib/session';
import LoadingGif from '@/components/LoadingGif';
import VidaraBranding from '@/components/VidaraBranding';

interface CompleteForm {
  username: string;
  password: string;
  repeat: string;
  national_id: string;
  gender: string;
  email: string;
}

const EMPTY_FORM: CompleteForm = {
  username: '',
  password: '',
  repeat: '',
  national_id: '',
  gender: '',
  email: '',
};

export default function CompleteProfile() {
  const navigate = useNavigate();
  const [form, setForm] = useState<CompleteForm>({ ...EMPTY_FORM });
  const [displayName, setDisplayName] = useState('');
  const [mobile, setMobile] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await authApi.me();
      if (!data.user.must_change_password) {
        // مشخصات قبلاً تکمیل شده؛ نیازی به این صفحه نیست.
        navigate('/dashboard', { replace: true });
        return;
      }
      setDisplayName(data.user.full_name || '');
      setMobile(data.user.mobile || '');
      setForm((current) => ({
        ...current,
        email: data.user.email || '',
        gender: data.user.gender || '',
      }));
    } catch (err) {
      setError(errorMessage(err, 'دریافت مشخصات حساب ناموفق بود.'));
    }
  }, [navigate]);

  useEffect(() => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.documentElement.setAttribute('lang', 'fa');
    if (!isSignedIn()) {
      navigate('/', { replace: true });
      return;
    }
    load();
  }, [load, navigate]);

  const handleSubmit = async () => {
    setError('');

    const username = form.username.trim();
    if (username.length < 4) {
      setError('نام کاربری جدید باید حداقل ۴ نویسه باشد.');
      return;
    }
    if (!/^[A-Za-z0-9._@-]+$/.test(username)) {
      setError('نام کاربری فقط می‌تواند شامل حرف لاتین، رقم و نویسه‌های . _ - @ باشد.');
      return;
    }
    if (form.password.length < 6) {
      setError('رمز عبور جدید باید حداقل ۶ نویسه باشد.');
      return;
    }
    if (form.password !== form.repeat) {
      setError('رمز عبور جدید با تکرار آن یکسان نیست.');
      return;
    }
    const toLatinDigits = (value: string) =>
      value
        .replace(/[۰-۹]/g, (digit) => String('۰۱۲۳۴۵۶۷۸۹'.indexOf(digit)))
        .replace(/[٠-٩]/g, (digit) => String('٠١٢٣٤٥٦٧٨٩'.indexOf(digit)));
    const nationalId = toLatinDigits(form.national_id).replace(/\D/g, '');
    if (!/^\d{10}$/.test(nationalId)) {
      setError('کد ملی باید دقیقاً ۱۰ رقم باشد.');
      return;
    }

    setBusy(true);
    try {
      const result = await authApi.completeProfile({
        username,
        new_password: form.password,
        national_id: nationalId,
        gender: form.gender || undefined,
        email: form.email || undefined,
      });
      toast.success(result.detail || 'مشخصات حساب شما با موفقیت تکمیل شد.');
      navigate('/dashboard', { replace: true });
    } catch (err) {
      setError(errorMessage(err, 'تکمیل مشخصات ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  const handleLogout = () => {
    authApi.logout();
    navigate('/', { replace: true });
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
            <CardTitle className="text-xl">تکمیل مشخصات حساب</CardTitle>
            <CardDescription>
              مدیر سازمان حساب شما را ساخته است؛ برای ورود به سامانه ابتدا باید نام کاربری جدید،
              رمز عبور جدید و کد ملی خود را ثبت کنید. نام کاربری و رمز فعلی شما پس از این مرحله
              منقضی می‌شود.
            </CardDescription>
          </CardHeader>

          <CardContent className="space-y-4">
            {displayName || mobile ? (
              <div className="rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
                <span className="text-muted-foreground">حساب ساخته‌شده برای: </span>
                <span className="font-medium">{displayName}</span>
                {mobile && (
                  <span dir="ltr" className="mr-2 font-mono text-xs text-muted-foreground">
                    ({mobile})
                  </span>
                )}
              </div>
            ) : (
              <div className="flex justify-center py-4">
                <LoadingGif size="md" label="در حال دریافت مشخصات حساب…" />
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="cp-username">
                نام کاربری جدید <span className="text-destructive">*</span>
              </Label>
              <Input
                id="cp-username"
                dir="ltr"
                autoComplete="username"
                value={form.username}
                onChange={(event) => setForm({ ...form, username: event.target.value })}
              />
              <p className="text-xs text-muted-foreground">
                حداقل ۴ نویسه؛ فقط حروف لاتین، رقم و نویسه‌های . _ - @
              </p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="cp-password">
                  رمز عبور جدید <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="cp-password"
                  dir="ltr"
                  type="password"
                  autoComplete="new-password"
                  value={form.password}
                  onChange={(event) => setForm({ ...form, password: event.target.value })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="cp-repeat">
                  تکرار رمز عبور جدید <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="cp-repeat"
                  dir="ltr"
                  type="password"
                  autoComplete="new-password"
                  value={form.repeat}
                  onChange={(event) => setForm({ ...form, repeat: event.target.value })}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') handleSubmit();
                  }}
                />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="cp-national">
                کد ملی <span className="text-destructive">*</span>
              </Label>
              <Input
                id="cp-national"
                dir="ltr"
                inputMode="numeric"
                maxLength={10}
                value={form.national_id}
                onChange={(event) =>
                  setForm({ ...form, national_id: event.target.value.replace(/[^\d۰-۹٠-٩]/g, '') })
                }
              />
              <p className="text-xs text-muted-foreground">دقیقاً ۱۰ رقم</p>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label>جنسیت (اختیاری)</Label>
                <Select
                  value={form.gender || 'none'}
                  onValueChange={(value) =>
                    setForm({ ...form, gender: value === 'none' ? '' : value })
                  }
                >
                  <SelectTrigger>
                    <SelectValue placeholder="انتخاب کنید" />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="none">انتخاب کنید</SelectItem>
                    {GENDER_OPTIONS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {option.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="cp-email">ایمیل (اختیاری)</Label>
                <Input
                  id="cp-email"
                  dir="ltr"
                  type="email"
                  value={form.email}
                  onChange={(event) => setForm({ ...form, email: event.target.value })}
                />
              </div>
            </div>

            {error && (
              <div className="surface-error rounded-lg p-3 text-sm text-error">{error}</div>
            )}

            <Button className="w-full" disabled={busy} onClick={handleSubmit}>
              {busy ? 'در حال ذخیره…' : 'تکمیل مشخصات و ورود به سامانه'}
            </Button>

            <Button variant="ghost" className="w-full" onClick={handleLogout} disabled={busy}>
              <LogOut className="me-1 h-4 w-4" />
              خروج از حساب
            </Button>
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

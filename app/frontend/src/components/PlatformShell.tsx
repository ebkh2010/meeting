/**
 * پوستهٔ مدیریت پلتفرم: هدر ساده با منوی حساب کاربری (تغییر یوزرنیم/رمز) و خروج،
 * بدون هیچ منوی فضای کاری.
 *
 * مدیر پلتفرم هیچ دسترسی به جلسات/رونویسی ندارد؛ تنها مسیر این پوسته
 * `/platform` است و هر مسیر دیگر فضای کاری برایش رد می‌شود.
 */
import { useNavigate } from 'react-router-dom';
import { useEffect, useState, type ReactNode } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { LogOut, UserRound } from 'lucide-react';
import { clearToken, getSessionUser, isSignedIn, onSessionChange, setSessionUser } from '@/lib/session';
import { isPlatformAdminRole } from '@/lib/appAuth';
import { errorMessage, platformApi } from '@/lib/platform';

export default function PlatformShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();
  const [accountOpen, setAccountOpen] = useState(false);

  useEffect(() => {
    if (!isSignedIn()) {
      navigate('/', { replace: true });
      return;
    }
    const user = getSessionUser();
    if (user && !isPlatformAdminRole(String(user.role ?? ''))) {
      navigate('/dashboard', { replace: true });
    }
  }, [navigate]);

  // با منقضی/پاک شدن نشست، کاربر به صفحهٔ ورود برمی‌گردد.
  useEffect(() => {
    const unsubscribe = onSessionChange(() => {
      if (!isSignedIn()) navigate('/', { replace: true });
    });
    return unsubscribe;
  }, [navigate]);

  const handleLogout = () => {
    clearToken();
    navigate('/', { replace: true });
  };

  return (
    <div className="flex min-h-screen flex-col bg-background" dir="rtl">
      <header className="sticky top-0 z-40 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between gap-3 px-4">
          <div className="flex items-center gap-3">
            <div className="flex h-8 w-28 items-center justify-center overflow-hidden">
              <img
                src="/assets/vidara-logo-horizontal.png"
                alt="ویدارا"
                className="h-full w-full object-contain"
              />
            </div>
            <span className="rounded-full bg-brand/10 px-3 py-1 text-xs font-medium text-brand-foreground">
              مدیریت پلتفرم
            </span>
          </div>
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setAccountOpen(true)}>
              <UserRound className="ml-1 h-4 w-4" />
              حساب کاربری
            </Button>
            <Button variant="outline" size="sm" onClick={handleLogout}>
              <LogOut className="ml-1 h-4 w-4" />
              خروج
            </Button>
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t py-3 text-center text-xs text-muted-foreground">
        توسعه داده شده توسط تیم ویدارا. نسخه آزمایشی
      </footer>

      {accountOpen && <AccountDialog onClose={() => setAccountOpen(false)} />}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* دیالوگ حساب کاربری مدیر پلتفرم: تغییر یوزرنیم/نام نمایشی و رمز      */
/* ------------------------------------------------------------------ */

function AccountDialog({ onClose }: { onClose: () => void }) {
  const [profile, setProfile] = useState({ username: '', display_name: '' });
  const [loaded, setLoaded] = useState(false);
  const [busy, setBusy] = useState(false);
  const [pw, setPw] = useState({ current: '', next: '', confirm: '' });

  useEffect(() => {
    platformApi
      .me()
      .then((data) => {
        setProfile({ username: data.user.username, display_name: data.user.display_name });
        setLoaded(true);
      })
      .catch(() => {
        setLoaded(true);
      });
  }, []);

  const saveProfile = async () => {
    setBusy(true);
    try {
      const data = await platformApi.updateMe({
        username: profile.username.trim(),
        display_name: profile.display_name.trim(),
      });
      setProfile({ username: data.user.username, display_name: data.user.display_name });
      const sessionUser = getSessionUser();
      setSessionUser({ ...(sessionUser || {}), username: data.user.username });
      toast.success('مشخصات حساب ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ مشخصات ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  const changePassword = async () => {
    if (pw.next !== pw.confirm) {
      toast.error('تکرار رمز عبور جدید یکسان نیست.');
      return;
    }
    setBusy(true);
    try {
      await platformApi.changePassword(pw.current, pw.next);
      setPw({ current: '', next: '', confirm: '' });
      toast.success('رمز عبور با موفقیت تغییر کرد.');
    } catch (err) {
      toast.error(errorMessage(err, 'تغییر رمز عبور ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>حساب کاربری مدیر پلتفرم</DialogTitle>
          <DialogDescription>
            نام کاربری، نام نمایشی و رمز عبور حساب مدیریت پلتفرم را تغییر دهید.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="space-y-3 rounded-md border p-3">
            <p className="text-sm font-medium">مشخصات</p>
            <div className="space-y-1">
              <Label className="text-xs">نام کاربری</Label>
              <Input
                dir="ltr"
                className="text-left"
                disabled={!loaded}
                value={profile.username}
                onChange={(e) => setProfile({ ...profile, username: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">نام نمایشی</Label>
              <Input
                value={profile.display_name}
                onChange={(e) => setProfile({ ...profile, display_name: e.target.value })}
              />
            </div>
            <div className="flex justify-end">
              <Button size="sm" disabled={busy} onClick={() => void saveProfile()}>
                {busy ? 'در حال ذخیره…' : 'ذخیرهٔ مشخصات'}
              </Button>
            </div>
          </div>

          <div className="space-y-3 rounded-md border p-3">
            <p className="text-sm font-medium">تغییر رمز عبور</p>
            <div className="space-y-1">
              <Label className="text-xs">رمز عبور فعلی</Label>
              <Input
                type="password"
                dir="ltr"
                className="text-left"
                value={pw.current}
                onChange={(e) => setPw({ ...pw, current: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">رمز عبور جدید</Label>
              <Input
                type="password"
                dir="ltr"
                className="text-left"
                value={pw.next}
                onChange={(e) => setPw({ ...pw, next: e.target.value })}
              />
            </div>
            <div className="space-y-1">
              <Label className="text-xs">تکرار رمز عبور جدید</Label>
              <Input
                type="password"
                dir="ltr"
                className="text-left"
                value={pw.confirm}
                onChange={(e) => setPw({ ...pw, confirm: e.target.value })}
              />
            </div>
            <div className="flex justify-end">
              <Button
                size="sm"
                disabled={busy || !pw.current || !pw.next || !pw.confirm}
                onClick={() => void changePassword()}
              >
                {busy ? 'در حال تغییر…' : 'تغییر رمز عبور'}
              </Button>
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

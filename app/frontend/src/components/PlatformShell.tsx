/**
 * پوستهٔ مدیریت پلتفرم: هدر ساده با خروج، بدون هیچ منوی فضای کاری.
 *
 * مدیر پلتفرم هیچ دسترسی به جلسات/رونویسی ندارد؛ تنها مسیر این پوسته
 * `/platform` است و هر مسیر دیگر فضای کاری برایش رد می‌شود.
 */
import { useNavigate } from 'react-router-dom';
import { useEffect, type ReactNode } from 'react';
import { Button } from '@/components/ui/button';
import { LogOut } from 'lucide-react';
import { clearToken, getSessionUser, isSignedIn, onSessionChange } from '@/lib/session';
import { isPlatformAdminRole } from '@/lib/appAuth';

export default function PlatformShell({ children }: { children: ReactNode }) {
  const navigate = useNavigate();

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
          <Button variant="outline" size="sm" onClick={handleLogout}>
            <LogOut className="ml-1 h-4 w-4" />
            خروج
          </Button>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6">{children}</main>
      <footer className="border-t py-3 text-center text-xs text-muted-foreground">
        توسعه داده شده توسط تیم ویدارا. نسخه آزمایشی
      </footer>
    </div>
  );
}

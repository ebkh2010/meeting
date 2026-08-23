/**
 * پوستهٔ فضای کاری: راست‌به‌چپ، ناوبری اصلی، وضعیت احراز هویت مستقل، سهمیه و اعلان‌ها.
 *
 * احراز هویت کاملاً مستقل است: نشست از توکن ذخیره‌شده در مرورگر خوانده می‌شود و در
 * نبودِ نشست معتبر، کاربر به صفحهٔ ورود («/») هدایت می‌شود. صفحه‌ها با تابع فرزند
 * به دادهٔ bootstrap دسترسی دارند.
 *
 * آیکون «تنظیمات» در نوار ابزار هدر تنها برای نقش «مدیر سازمان» رندر می‌شود؛
 * برای دبیر و عضو نمایش داده نمی‌شود و صفحهٔ تنظیمات خودش دسترسی را رد می‌کند.
 *
 * چیدمان واکنش‌گرا: در عرض کمتر از `md` هدر تنها لوگو، اعلان‌ها و دکمهٔ همبرگری را
 * نگه می‌دارد و همهٔ ناوبری، تغییر سازمان، میان‌بُرهای حساب، سهمیه و خروج به drawer
 * راست‌به‌چپ منتقل می‌شود. گاردهای نقش داخل منو هم دقیقاً مثل نسخهٔ دسکتاپ اعمال
 * می‌شوند، پس منوی موبایل مسیر اضافه‌ای برای دسترسی غیرمجاز نمی‌سازد.
 */
import { ReactNode, useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  Building2,
  CalendarDays,
  ChevronDown,
  KeyRound,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings2,
  UserCircle,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Sheet, SheetContent, SheetTitle, SheetTrigger } from '@/components/ui/sheet';
import {
  api,
  applyUploadLimits,
  Bootstrap,
  errorMessage,
  formatDateTime,
  NotificationItem,
  toPersianDigits,
} from '@/lib/mgmt';
import LoadingGif from '@/components/LoadingGif';
import { authApi, isAdminRole, ROLE_SECRETARY } from '@/lib/appAuth';
import { isSignedIn } from '@/lib/session';
import VidaraBranding from '@/components/VidaraBranding';
import OrganizationSwitcher from '@/components/OrganizationSwitcher';
import AssistantPanel from '@/components/AssistantPanel';

const BASE_NAV = [
  { to: '/dashboard', label: 'داشبورد', icon: LayoutDashboard },
  { to: '/meetings', label: 'جلسات', icon: CalendarDays },
];

/** میان‌بُرهای منوی کاربر؛ آیتم‌های مدیریتی فقط برای نقش مدیر سازمان. */
const ACCOUNT_MENU = [
  { to: '/account', label: 'حساب من', icon: UserCircle, adminOnly: false },
  { to: '/account', label: 'تغییر رمز عبور', icon: KeyRound, adminOnly: false },
  { to: '/settings?tab=users', label: 'مدیریت کاربران و نقش‌ها', icon: Building2, adminOnly: true },
  { to: '/settings?tab=email', label: 'تنظیمات ارسال ایمیل و پیامک', icon: Settings2, adminOnly: true },
];

type AuthState = 'loading' | 'authenticated' | 'anonymous';

interface NotificationsMenuProps {
  items: NotificationItem[];
  unread: number;
  onMarkRead: () => void;
}

/**
 * منوی اعلان‌ها؛ در موبایل و دسکتاپ از یک کامپوننت استفاده می‌شود.
 *
 * عرض محتوا با `min()` محدود شده تا در عرض ۳۲۰ پیکسل هم از لبهٔ صفحه بیرون نزند و
 * اسکرول افقی نسازد.
 */
function NotificationsMenu({ items, unread, onMarkRead }: NotificationsMenuProps) {
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button size="icon" variant="ghost" className="relative" aria-label="اعلان‌ها">
          <Bell className="h-5 w-5" />
          {unread > 0 && (
            <span className="absolute -top-0.5 -right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-primary px-1 text-[10px] text-primary-foreground">
              {toPersianDigits(unread)}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent
        align="start"
        dir="rtl"
        className="w-[min(20rem,calc(100vw-1.5rem))] max-w-[20rem]"
      >
        <div className="flex items-center justify-between pb-2">
          <span className="text-sm font-semibold">اعلان‌ها</span>
          <Button size="sm" variant="ghost" onClick={onMarkRead}>
            خوانده شد
          </Button>
        </div>
        <Separator />
        <ScrollArea className="h-64">
          <div className="space-y-3 pt-3">
            {items.length === 0 ? (
              <p className="text-sm text-muted-foreground">اعلان تازه‌ای ندارید.</p>
            ) : (
              items.map((item) => (
                <div key={item.id} className="space-y-1 border-b border-border/60 pb-2">
                  <p className="text-sm font-medium break-words">{item.title}</p>
                  <p className="text-xs text-muted-foreground break-words">{item.body}</p>
                  <p className="text-[11px] text-muted-foreground">
                    {formatDateTime(item.created_at)}
                  </p>
                </div>
              ))
            )}
          </div>
        </ScrollArea>
      </PopoverContent>
    </Popover>
  );
}

interface AppShellProps {
  children: (bootstrap: Bootstrap, reload: () => void) => ReactNode;
}

export default function AppShell({ children }: AppShellProps) {
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [loadError, setLoadError] = useState('');
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [orgDialogOpen, setOrgDialogOpen] = useState(false);
  const location = useLocation();
  const navigate = useNavigate();

  useEffect(() => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.documentElement.setAttribute('lang', 'fa');
  }, []);

  // با هر جابه‌جایی مسیر، drawer موبایل بسته می‌شود تا محتوای صفحهٔ جدید دیده شود.
  useEffect(() => {
    setMobileNavOpen(false);
  }, [location.pathname, location.search]);

  const loadWorkspace = useCallback(async () => {
    try {
      const data = await api.bootstrap();
      setBootstrap(data);
      // سقف‌های بارگذاری سازمان در همان لحظه به لایهٔ اعتبارسنجی فرانت تزریق می‌شود
      // تا پیام‌های خطا و راهنمای فرم‌ها با مقادیر تنظیم‌شدهٔ مدیر یکی باشد.
      applyUploadLimits(data.upload_limits);
      setLoadError('');
    } catch (error) {
      setLoadError(errorMessage(error, 'دریافت اطلاعات فضای کاری ناموفق بود.'));
      if (!isSignedIn()) setAuthState('anonymous');
    }
  }, []);

  const loadNotifications = useCallback(async () => {
    try {
      const data = await api.notifications();
      setNotifications(data.items);
    } catch {
      setNotifications([]);
    }
  }, []);

  useEffect(() => {
    let active = true;
    const check = async () => {
      if (!isSignedIn()) {
        if (active) setAuthState('anonymous');
        return;
      }
      try {
        // اعتبار نشست مستقل در سرور بررسی می‌شود؛ توکن منقضی پاک می‌گردد.
        await authApi.me();
        if (!active) return;
        setAuthState('authenticated');
        await loadWorkspace();
        await loadNotifications();
      } catch {
        if (active) setAuthState('anonymous');
      }
    };
    check();
    return () => {
      active = false;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (authState === 'anonymous') navigate('/', { replace: true });
  }, [authState, navigate]);

  const handleMarkRead = async () => {
    try {
      await api.markNotificationsRead();
      await loadNotifications();
      await loadWorkspace();
    } catch (error) {
      setLoadError(errorMessage(error));
    }
  };

  /**
   * پس از تغییر سازمان، دادهٔ فضای کاری و اعلان‌ها بازخوانی می‌شود تا نقش، منوها
   * و سهمیهٔ نمایش‌داده‌شده متعلق به سازمان جدید باشد.
   */
  const handleOrganizationSwitched = async () => {
    setBootstrap(null);
    await loadWorkspace();
    await loadNotifications();
    navigate('/dashboard', { replace: true });
  };

  const handleLogout = () => {
    authApi.logout();
    setBootstrap(null);
    setAuthState('anonymous');
    navigate('/', { replace: true });
  };

  if (authState !== 'authenticated') {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-8"
        dir="rtl"
      >
        <LoadingGif size="lg" label="در حال بررسی نشست شما…" />
      </div>
    );
  }

  if (!bootstrap) {
    // در حالت انتظار (بدون خطا) فقط گیف دیده می‌شود؛ کارت خطا تنها وقتی رندر
    // می‌شود که دریافت دادهٔ فضای کاری واقعاً شکست خورده باشد.
    if (!loadError) {
      return (
        <div
          className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-6"
          dir="rtl"
        >
          <LoadingGif
            size="lg"
            label="آماده‌سازی فضای کاری"
            hint="در حال دریافت اطلاعات سازمان، نقش شما و سهمیهٔ رونویسی…"
          />
        </div>
      );
    }

    return (
      <div className="flex min-h-screen items-center justify-center bg-background p-4 sm:p-6" dir="rtl">
        <Card className="w-full max-w-md">
          <CardHeader>
            <CardTitle>آماده‌سازی فضای کاری</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-destructive">{loadError}</p>
            <Button className="w-full" onClick={loadWorkspace}>
              تلاش دوباره
            </Button>
            <Button variant="ghost" className="w-full" onClick={handleLogout}>
              خروج از حساب
            </Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  // مقایسهٔ دسترسی همیشه با کلید فنی نقش انجام می‌شود، نه برچسب نمایشی.
  const isAdmin = isAdminRole(bootstrap.membership.role);
  // دستیار هوشمند فقط برای مدیر سازمان و دبیر جلسه؛ برای نقش «عضو» رندر نمی‌شود.
  const canUseAssistant =
    isAdmin || (bootstrap.membership.role || '').trim().toLowerCase() === ROLE_SECRETARY;
  const navItems = BASE_NAV;
  const unread = notifications.filter((item) => !item.is_read).length;
  const quota = bootstrap.quota;
  const accountItems = ACCOUNT_MENU.filter((item) => !item.adminOnly || isAdmin);
  const quotaLabel = quota
    ? `سهمیهٔ رونویسی این ماه: ${toPersianDigits(quota.used_minutes)} از ${toPersianDigits(
        quota.limit_minutes,
      )} دقیقه`
    : '';

  return (
    <div className="flex min-h-screen flex-col bg-background" dir="rtl">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        {/* نوار موبایل: لوگو + اعلان + همبرگری؛ بقیهٔ کنترل‌ها داخل drawer است. */}
        <div className="flex items-center gap-1 px-3 py-2 md:hidden">
          <Link to="/dashboard" className="flex min-w-0 flex-1 items-center gap-2">
            <img
              src="/assets/vidara-icon.png"
              alt="ویدارا"
              className="h-7 w-7 shrink-0 object-contain"
            />
            <span className="truncate text-sm font-bold">ویدارا - نسخه جلسات</span>
          </Link>

          <NotificationsMenu items={notifications} unread={unread} onMarkRead={handleMarkRead} />

          <Sheet open={mobileNavOpen} onOpenChange={setMobileNavOpen}>
            <SheetTrigger asChild>
              <Button size="icon" variant="ghost" aria-label="منوی اصلی">
                <Menu className="h-6 w-6" />
              </Button>
            </SheetTrigger>
            <SheetContent
              side="right"
              dir="rtl"
              className="flex w-[86vw] max-w-xs flex-col gap-0 overflow-y-auto p-0"
            >
              <SheetTitle className="sr-only">منوی اصلی سامانه</SheetTitle>

              <div className="border-b border-border p-4 pe-12">
                <div className="flex items-center gap-2">
                  <img
                    src="/assets/vidara-icon.png"
                    alt="ویدارا"
                    className="h-8 w-8 shrink-0 object-contain"
                  />
                  <div className="min-w-0">
                    <p className="truncate text-sm font-bold">ویدارا - نسخه جلسات</p>
                    <p className="truncate text-xs text-muted-foreground">
                      {bootstrap.user.name || 'حساب من'} — {bootstrap.membership.role_label}
                    </p>
                  </div>
                </div>
              </div>

              <nav className="space-y-1 p-3">
                {navItems.map((item) => {
                  const Icon = item.icon;
                  const active = location.pathname === item.to;
                  return (
                    <Button
                      key={item.to}
                      asChild
                      variant={active ? 'secondary' : 'ghost'}
                      className="min-h-11 w-full justify-start"
                    >
                      <Link to={item.to} className="flex items-center gap-2">
                        <Icon className="h-4 w-4 shrink-0" />
                        {item.label}
                      </Link>
                    </Button>
                  );
                })}

                {/* گارد نقش داخل منوی موبایل نیز دقیقاً مثل هدر دسکتاپ اعمال می‌شود. */}
                {isAdmin && (
                  <Button
                    asChild
                    variant={location.pathname === '/settings' ? 'secondary' : 'ghost'}
                    className="min-h-11 w-full justify-start"
                  >
                    <Link to="/settings" className="flex items-center gap-2">
                      <Settings2 className="h-4 w-4 shrink-0" />
                      تنظیمات سازمان
                    </Link>
                  </Button>
                )}
              </nav>

              <div className="space-y-1 border-t border-border p-3">
                <p className="px-2 pb-1 text-xs font-medium text-muted-foreground">حساب کاربری</p>
                {accountItems.map((item) => {
                  const Icon = item.icon;
                  return (
                    <Button
                      key={`${item.to}-${item.label}`}
                      asChild
                      variant="ghost"
                      className="min-h-11 w-full justify-start"
                    >
                      <Link to={item.to} className="flex items-center gap-2 text-right">
                        <Icon className="h-4 w-4 shrink-0" />
                        <span className="truncate">{item.label}</span>
                      </Link>
                    </Button>
                  );
                })}

                {/*
                  برای پرهیز از تودرتویی دیالوگ در drawer، ابتدا منو بسته می‌شود و
                  سپس دیالوگ تغییر سازمان به‌صورت کنترل‌شده باز می‌گردد.
                */}
                <Button
                  variant="ghost"
                  className="min-h-11 w-full justify-start"
                  onClick={() => {
                    setMobileNavOpen(false);
                    setOrgDialogOpen(true);
                  }}
                >
                  <Building2 className="me-2 h-4 w-4 shrink-0" />
                  <span className="truncate">
                    تغییر سازمان ({bootstrap.organization?.name || 'سازمان من'})
                  </span>
                </Button>
              </div>

              {quota && (
                <div className="space-y-2 border-t border-border p-4 text-xs text-muted-foreground">
                  <p>{quotaLabel}</p>
                  <Progress value={quota.usage_percent} className="h-1.5 w-full" />
                </div>
              )}

              <div className="mt-auto border-t border-border p-3">
                <Button
                  variant="outline"
                  className="min-h-11 w-full justify-center"
                  onClick={() => {
                    setMobileNavOpen(false);
                    handleLogout();
                  }}
                >
                  <LogOut className="me-1 h-4 w-4" />
                  خروج از حساب
                </Button>
              </div>
            </SheetContent>
          </Sheet>
        </div>

        {/* نوار دسکتاپ */}
        <div className="mx-auto hidden max-w-7xl flex-wrap items-center gap-3 px-4 py-3 md:flex">
          <Link to="/dashboard" className="flex items-center gap-2">
            <img src="/assets/vidara-icon.png" alt="ویدارا" className="h-8 w-8 object-contain" />
            <span className="text-base font-bold">ویدارا - نسخه جلسات</span>
          </Link>

          <nav className="flex flex-1 flex-wrap items-center gap-1">
            {navItems.map((item) => {
              const Icon = item.icon;
              const active = location.pathname === item.to;
              return (
                <Button key={item.to} asChild size="sm" variant={active ? 'secondary' : 'ghost'}>
                  <Link to={item.to} className="flex items-center gap-1.5">
                    <Icon className="h-4 w-4" />
                    {item.label}
                  </Link>
                </Button>
              );
            })}
          </nav>

          <div className="flex items-center gap-2">
            {/* تغییر سازمان فعال نشست بدون خروج کامل؛ نقش از سازمان جدید خوانده می‌شود. */}
            <OrganizationSwitcher
              currentName={bootstrap.organization?.name || ''}
              onSwitched={handleOrganizationSwitched}
            />

            {/* آیکون تنظیمات فقط برای مدیر سازمان دیده می‌شود. */}
            {isAdmin && (
              <Button
                asChild
                size="icon"
                variant={location.pathname === '/settings' ? 'secondary' : 'ghost'}
                title="تنظیمات سازمان"
              >
                <Link to="/settings" aria-label="تنظیمات سازمان">
                  <Settings2 className="h-5 w-5" />
                </Link>
              </Button>
            )}

            <NotificationsMenu items={notifications} unread={unread} onMarkRead={handleMarkRead} />

            <Popover>
              <PopoverTrigger asChild>
                <Button size="sm" variant="ghost" className="flex items-center gap-1.5">
                  <UserCircle className="h-4 w-4" />
                  {bootstrap.user.name || 'حساب من'}
                  <ChevronDown className="h-3.5 w-3.5 opacity-70" />
                </Button>
              </PopoverTrigger>
              <PopoverContent align="start" dir="rtl" className="w-64 p-2">
                <p className="px-2 pb-2 text-xs text-muted-foreground">
                  {bootstrap.organization?.name || 'سازمان من'} — {bootstrap.membership.role_label}
                </p>
                <Separator />
                <div className="pt-2">
                  {accountItems.map((item) => {
                    const Icon = item.icon;
                    return (
                      <Button
                        key={`${item.to}-${item.label}`}
                        asChild
                        variant="ghost"
                        size="sm"
                        className="w-full justify-start"
                      >
                        <Link to={item.to} className="flex items-center gap-2">
                          <Icon className="h-4 w-4" />
                          {item.label}
                        </Link>
                      </Button>
                    );
                  })}
                </div>
              </PopoverContent>
            </Popover>

            <Badge variant="outline">{bootstrap.membership.role_label}</Badge>

            <Button size="sm" variant="ghost" onClick={handleLogout}>
              <LogOut className="me-1 h-4 w-4" />
              خروج
            </Button>
          </div>
        </div>

        {quota && (
          <div className="mx-auto hidden max-w-7xl items-center gap-3 px-4 pb-3 text-xs text-muted-foreground md:flex">
            <span>{quotaLabel}</span>
            <Progress value={quota.usage_percent} className="h-1.5 w-40" />
          </div>
        )}
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-3 py-4 sm:px-4 sm:py-6">
        {loadError && <p className="mb-4 text-sm text-destructive">{loadError}</p>}
        {children(bootstrap, loadWorkspace)}
      </main>

      <footer className="border-t border-border bg-sidebar/60 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-center px-4">
          <VidaraBranding />
        </div>
      </footer>

      {/*
        نمونهٔ کنترل‌شدهٔ تغییر سازمان برای منوی موبایل؛ دکمهٔ trigger ندارد و فقط با
        انتخاب آیتم منو باز می‌شود.
      */}
      <OrganizationSwitcher
        hideTrigger
        open={orgDialogOpen}
        onOpenChange={setOrgDialogOpen}
        currentName={bootstrap.organization?.name || ''}
        onSwitched={handleOrganizationSwitched}
      />

      {/* پنل شناور دستیار هوشمند در همهٔ صفحه‌های فضای کاری */}
      <AssistantPanel allowed={canUseAssistant} />
    </div>
  );
}
/**
 * پوستهٔ فضای کاری: راست‌به‌چپ، سایدبار راستِ جمع‌شونده (مانند دیپ‌سیک)، وضعیت
 * احراز هویت مستقل، سهمیه و اعلان‌ها.
 *
 * چیدمان دسکتاپ: منوهای اصلی (داشبورد، جلسات، تنظیمات سازمان برای مدیر و
 * «حساب کاربری» — ادغام «حساب من» و «تغییر رمز عبور») و تغییر فضای کاری در
 * سایدبار سمت راست قرار دارند؛ بخش پایینی منو حذف شده و سهمیه و خروج به نوار
 * بالا منتقل شده‌اند. سایدبار با دکمهٔ کنار نوار بالا به حالت آیکونی جمع می‌شود
 * و وضعیت آن در مرورگر نگه داشته می‌شود. در موبایل، همان منوها داخل drawer سمت
 * راست باز می‌شوند (side="right").
 *
 * احراز هویت کاملاً مستقل است: نشست از توکن ذخیره‌شده در مرورگر خوانده می‌شود و
 * در نبودِ نشست معتبر، کاربر به صفحهٔ ورود («/») هدایت می‌شود. صفحه‌ها با تابع
 * فرزند به دادهٔ bootstrap دسترسی دارند.
 */
import { ReactNode, useCallback, useEffect, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import {
  Bell,
  Building2,
  CalendarDays,
  LayoutDashboard,
  LogOut,
  Menu,
  PanelRightClose,
  PanelRightOpen,
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
import { cn } from '@/lib/utils';
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
import { authApi, isAdminRole, isPlatformAdminRole, ROLE_SECRETARY } from '@/lib/appAuth';
import { getSessionUser, isSignedIn } from '@/lib/session';
import VidaraBranding from '@/components/VidaraBranding';
import OrganizationSwitcher from '@/components/OrganizationSwitcher';
import AssistantPanel from '@/components/AssistantPanel';

const BASE_NAV = [
  { to: '/dashboard', label: 'داشبورد', icon: LayoutDashboard },
  { to: '/meetings', label: 'جلسات', icon: CalendarDays },
];

const SIDEBAR_KEY = 'vidara.sidebar.collapsed';

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

/** آیتم ناوبری سایدبار دسکتاپ؛ در حالت جمع‌شده فقط آیکون با tooltip دیده می‌شود. */
function SidebarLink({
  to,
  label,
  icon: Icon,
  collapsed,
  active,
}: {
  to: string;
  label: string;
  icon: typeof LayoutDashboard;
  collapsed: boolean;
  active: boolean;
}) {
  return (
    <Button
      asChild
      variant={active ? 'secondary' : 'ghost'}
      title={collapsed ? label : undefined}
      className={cn('min-h-11 w-full', collapsed ? 'justify-center px-0' : 'justify-start')}
    >
      <Link to={to} className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0" />
        {!collapsed && <span className="truncate">{label}</span>}
      </Link>
    </Button>
  );
}

export default function AppShell({ children }: AppShellProps) {
  const [authState, setAuthState] = useState<AuthState>('loading');
  const [bootstrap, setBootstrap] = useState<Bootstrap | null>(null);
  const [loadError, setLoadError] = useState('');
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [orgDialogOpen, setOrgDialogOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState<boolean>(() => {
    try {
      return window.localStorage.getItem(SIDEBAR_KEY) === '1';
    } catch {
      return false;
    }
  });
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

  const toggleSidebar = useCallback(() => {
    setSidebarCollapsed((value) => {
      const next = !value;
      try {
        window.localStorage.setItem(SIDEBAR_KEY, next ? '1' : '0');
      } catch {
        /* حالت مرور خصوصی: وضعیت فقط در حافظهٔ برنامه می‌ماند. */
      }
      return next;
    });
  }, []);

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
      // نشست مدیر پلتفرم به پوستهٔ فضای کاری تعلق ندارد.
      const sessionUser = getSessionUser();
      if (sessionUser && isPlatformAdminRole(String(sessionUser.role ?? ''))) {
        navigate('/platform', { replace: true });
        return;
      }
      try {
        // اعتبار نشست مستقل در سرور بررسی می‌شود؛ توکن منقضی پاک می‌گردد.
        const meData = await authApi.me();
        if (!active) return;
        // کاربرِ ساخته‌شده توسط مدیر که هنوز مشخصاتش را تکمیل نکرده است، پیش از
        // ورود به فضای کاری باید صفحهٔ «تکمیل مشخصات» را ببیند.
        if (meData.user?.must_change_password) {
          navigate('/complete-profile', { replace: true });
          return;
        }
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
   * پس از تغییر فضای کاری، دادهٔ فضای کاری و اعلان‌ها بازخوانی می‌شود تا نقش،
   * منوها و سهمیهٔ نمایش‌داده‌شده متعلق به فضای جدید باشد.
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
  const unread = notifications.filter((item) => !item.is_read).length;
  const quota = bootstrap.quota;
  const quotaLabel = quota
    ? `سهمیهٔ رونویسی این ماه: ${toPersianDigits(quota.used_minutes)} از ${toPersianDigits(
        quota.limit_minutes,
      )} دقیقه`
    : '';
  const orgName = bootstrap.organization?.name || 'سازمان من';
  const userName = bootstrap.user.name || 'حساب من';

  /* ------------------------- بلوک منوهای مشترک ------------------------- */
  const navBlock = (collapsed: boolean) => (
    <>
      {BASE_NAV.map((item) => {
        const Icon = item.icon;
        return (
          <SidebarLink
            key={item.to}
            to={item.to}
            label={item.label}
            icon={Icon}
            collapsed={collapsed}
            active={location.pathname === item.to}
          />
        );
      })}
      {isAdmin && (
        <SidebarLink
          to="/settings"
          label="تنظیمات سازمان"
          icon={Settings2}
          collapsed={collapsed}
          active={location.pathname === '/settings'}
        />
      )}
      {/*
        «حساب من» و «تغییر رمز عبور» در یک آیتم واحد به نام «حساب کاربری»
        ادغام شده‌اند؛ بخش‌های «مدیریت کاربران» و «تنظیمات ایمیل/پیامک» هم از
        منو حذف شده‌اند چون در زبانه‌های «تنظیمات سازمان» در دسترس‌اند.
      */}
      <SidebarLink
        to="/account"
        label="حساب کاربری"
        icon={UserCircle}
        collapsed={collapsed}
        active={location.pathname === '/account'}
      />
    </>
  );

  return (
    <div className="flex min-h-screen flex-col bg-background" dir="rtl">
      <header className="sticky top-0 z-40 border-b border-border bg-background/95 backdrop-blur">
        {/* نوار موبایل: همبرگری در سمت راست (ابتدای RTL) + لوگو + اعلان؛ منوها در drawer راست. */}
        <div className="flex items-center gap-1 px-3 py-2 md:hidden">
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
                      {userName} — {bootstrap.membership.role_label}
                    </p>
                  </div>
                </div>
              </div>

              <nav className="space-y-1 p-3">
                {navBlock(false)}

                {/* برای پرهیز از تودرتویی دیالوگ در drawer، ابتدا منو بسته می‌شود و
                    سپس دیالوگ تغییر فضای کاری به‌صورت کنترل‌شده باز می‌گردد. */}
                <Button
                  variant="ghost"
                  className="min-h-11 w-full justify-start"
                  onClick={() => {
                    setMobileNavOpen(false);
                    setOrgDialogOpen(true);
                  }}
                >
                  <Building2 className="me-2 h-4 w-4 shrink-0" />
                  <span className="truncate">تغییر فضای کاری ({orgName})</span>
                </Button>
              </nav>

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

          <Link to="/dashboard" className="flex min-w-0 flex-1 items-center gap-2">
            <img
              src="/assets/vidara-icon.png"
              alt="ویدارا"
              className="h-7 w-7 shrink-0 object-contain"
            />
            <span className="truncate text-sm font-bold">ویدارا - نسخه جلسات</span>
          </Link>

          <NotificationsMenu items={notifications} unread={unread} onMarkRead={handleMarkRead} />
        </div>

        {/* نوار دسکتاپ: دکمهٔ جمع‌کردن سایدبار + نام فضا + سهمیه + نقش + اعلان + خروج */}
        <div className="hidden h-14 items-center justify-between gap-3 px-4 md:flex">
          <div className="flex min-w-0 items-center gap-2">
            <Button
              size="icon"
              variant="ghost"
              onClick={toggleSidebar}
              title={sidebarCollapsed ? 'باز کردن منو' : 'جمع کردن منو'}
              aria-label={sidebarCollapsed ? 'باز کردن منو' : 'جمع کردن منو'}
            >
              {sidebarCollapsed ? (
                <PanelRightOpen className="h-5 w-5" />
              ) : (
                <PanelRightClose className="h-5 w-5" />
              )}
            </Button>
            <span className="truncate text-sm font-semibold">{orgName}</span>
            {quota && (
              <span className="hidden items-center gap-2 text-xs text-muted-foreground lg:flex">
                <span className="truncate">{quotaLabel}</span>
                <Progress value={quota.usage_percent} className="h-1.5 w-28" />
              </span>
            )}
          </div>
          <div className="flex shrink-0 items-center gap-2">
            <Badge variant="outline">{bootstrap.membership.role_label}</Badge>
            <NotificationsMenu items={notifications} unread={unread} onMarkRead={handleMarkRead} />
            <Button
              size="icon"
              variant="ghost"
              onClick={handleLogout}
              title="خروج از حساب"
              aria-label="خروج از حساب"
            >
              <LogOut className="h-5 w-5" />
            </Button>
          </div>
        </div>
      </header>

      <div className="flex flex-1">
        {/* سایدبار دسکتاپ — سمت راست (اولین فرزند در RTL)، جمع‌شونده با حفظ وضعیت */}
        <aside
          className={cn(
            'sticky top-14 hidden h-[calc(100vh-3.5rem)] shrink-0 flex-col gap-1 border-l border-border bg-sidebar/50 transition-[width] duration-200 md:flex',
            sidebarCollapsed ? 'w-[76px]' : 'w-64',
          )}
        >
          <div className={cn('flex items-center gap-2 px-3 pt-4 pb-3', sidebarCollapsed && 'justify-center px-0')}>
            <Link
              to="/dashboard"
              title={sidebarCollapsed ? 'ویدارا - نسخه جلسات' : undefined}
              className="flex min-w-0 items-center gap-2"
            >
              <img
                src="/assets/vidara-icon.png"
                alt="ویدارا"
                className="h-8 w-8 shrink-0 object-contain"
              />
              {!sidebarCollapsed && (
                <span className="truncate text-sm font-bold">ویدارا - نسخه جلسات</span>
              )}
            </Link>
          </div>

          <Separator className="mx-3 w-auto" />

          <nav className="space-y-1 px-3">{navBlock(sidebarCollapsed)}</nav>

          {/* تغییر فضای کاری از داخل سایدبار */}
          <div className="px-3">
            <Button
              variant="ghost"
              title={sidebarCollapsed ? `تغییر فضای کاری (${orgName})` : undefined}
              className={cn('min-h-11 w-full', sidebarCollapsed ? 'justify-center px-0' : 'justify-start')}
              onClick={() => setOrgDialogOpen(true)}
            >
              <Building2 className="h-4 w-4 shrink-0" />
              {!sidebarCollapsed && (
                <span className="ms-2 min-w-0 truncate text-right">
                  تغییر فضای کاری
                  <span className="block truncate text-xs text-muted-foreground">{orgName}</span>
                </span>
              )}
            </Button>
          </div>
        </aside>

        <main className="min-w-0 flex-1 px-3 py-4 sm:px-4 sm:py-6">
          {loadError && <p className="mb-4 text-sm text-destructive">{loadError}</p>}
          {children(bootstrap, loadWorkspace)}
        </main>
      </div>

      <footer className="border-t border-border bg-sidebar/60 py-4">
        <div className="mx-auto flex max-w-7xl items-center justify-center px-4">
          <VidaraBranding />
        </div>
      </footer>

      {/*
        نمونهٔ کنترل‌شدهٔ تغییر فضای کاری برای سایدبار دسکتاپ و drawer موبایل؛
        دکمهٔ trigger ندارد و فقط با انتخاب آیتم منو باز می‌شود.
      */}
      <OrganizationSwitcher
        hideTrigger
        open={orgDialogOpen}
        onOpenChange={setOrgDialogOpen}
        currentName={orgName}
        onSwitched={handleOrganizationSwitched}
      />

      {/* پنل شناور دستیار هوشمند در همهٔ صفحه‌های فضای کاری */}
      <AssistantPanel allowed={canUseAssistant} />
    </div>
  );
}

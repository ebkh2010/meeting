import { lazy, Suspense } from 'react';
import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DirectionProvider } from '@radix-ui/react-direction';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import CompleteProfile from './pages/CompleteProfile';
import LoadingGif from './components/LoadingGif';
import PlatformShell from './components/PlatformShell';
import ErrorBoundary from './components/ErrorBoundary';

/*
 * صفحهٔ ورود (و پوستهٔ پلتفرم) در باندل اصلی می‌مانند تا نخستین نمایش خیلی
 * سریع باشد؛ صفحه‌های سنگین فضای کاری (داشبورد، جلسات و …) با بارگذاری تنبل
 * فقط در صورت نیاز دریافت می‌شوند.
 */
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Meetings = lazy(() => import('./pages/Meetings'));
const MeetingDetail = lazy(() => import('./pages/MeetingDetail'));
const Settings = lazy(() => import('./pages/Settings'));
const Account = lazy(() => import('./pages/Account'));
const PrintMinutes = lazy(() => import('./pages/PrintMinutes'));
const PlatformAdmin = lazy(() => import('./pages/PlatformAdmin'));

const queryClient = new QueryClient();

function PageFallback() {
  return (
    <div className="flex min-h-[60vh] items-center justify-center" dir="rtl">
      <LoadingGif label="در حال بارگذاری…" />
    </div>
  );
}

const AppRoutes = () => (
  <Suspense fallback={<PageFallback />}>
    <Routes>
      {/* ریشهٔ سامانه صفحهٔ ورود/ثبت‌نام مستقل است؛ صفحهٔ معرفی حذف شده است. */}
      <Route path="/" element={<Login />} />
      {/* تکمیل اجباری مشخصات کاربران ساخته‌شده توسط مدیر در نخستین ورود */}
      <Route path="/complete-profile" element={<CompleteProfile />} />
      <Route path="/dashboard" element={<Dashboard />} />
      <Route path="/meetings" element={<Meetings />} />
      <Route path="/meetings/:meetingId" element={<MeetingDetail />} />
      {/* صفحهٔ مستقل «اقدامات» حذف شد؛ اقدامات در زبانهٔ «مصوبات و اقدامات» هر جلسه پیگیری می‌شود. */}
      <Route path="/actions" element={<Navigate to="/meetings" replace />} />
      {/* بخش یکپارچهٔ تنظیمات سازمان (فقط مدیر) */}
      <Route path="/settings" element={<Settings />} />
      {/* مسیرهای قدیمی به زبانهٔ متناظر در تنظیمات هدایت می‌شوند. */}
      <Route path="/users" element={<Navigate to="/settings?tab=users" replace />} />
      <Route path="/notify-settings" element={<Navigate to="/settings?tab=deliveries" replace />} />
      <Route path="/account" element={<Account />} />
      {/* کنسول قدیمی مدیریت حذف شد؛ نقطهٔ ورود واحد، بخش تنظیمات است. */}
      <Route path="/admin" element={<Navigate to="/settings?tab=users" replace />} />
      <Route path="/print/:meetingId" element={<PrintMinutes />} />
      {/* کنسول مدیریت پلتفرم — فقط برای نشست مدیر پلتفرم (بدون دسترسی به جلسات) */}
      <Route
        path="/platform"
        element={
          <PlatformShell>
            <PlatformAdmin />
          </PlatformShell>
        }
      />
      {/* MODULE_ROUTES_START */}
      {/* MODULE_ROUTES_END */}
    </Routes>
  </Suspense>
);

const App = () => (
  /*
   * همهٔ اجزای Radix (تب‌ها، منوی انتخابی، دیالوگ، پاپ‌اور، سوییچ و …) بدون
   * DirectionProvider به‌صورت پیش‌فرض با dir="ltr" رندر می‌شوند و صفت dir روی
   * <html> را نادیده می‌گیرند؛ همین موضوع ساختار صفحات را چپ‌به‌راست می‌کرد.
   * این provider جهت راست‌به‌چپ را به کل درخت Radix تزریق می‌کند.
   */
  <DirectionProvider dir="rtl">
    <QueryClientProvider client={queryClient}>
      {/* MODULE_PROVIDERS_START */}
      {/* MODULE_PROVIDERS_END */}
      <TooltipProvider>
        <Toaster />
        <BrowserRouter>
          {/* مرز خطا: به‌جای صفحهٔ سفید، کارت «بارگذاری مجدد» نمایش داده می‌شود. */}
          <ErrorBoundary>
            <AppRoutes />
          </ErrorBoundary>
        </BrowserRouter>
      </TooltipProvider>
      {/* MODULE_PROVIDERS_CLOSE */}
    </QueryClientProvider>
  </DirectionProvider>
);

export default App;
export { AppRoutes };
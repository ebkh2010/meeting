import { Toaster } from '@/components/ui/sonner';
import { TooltipProvider } from '@/components/ui/tooltip';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DirectionProvider } from '@radix-ui/react-direction';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import Login from './pages/Login';
import CompleteProfile from './pages/CompleteProfile';
import Dashboard from './pages/Dashboard';
import Meetings from './pages/Meetings';
import MeetingDetail from './pages/MeetingDetail';
import Settings from './pages/Settings';
import Account from './pages/Account';
import PrintMinutes from './pages/PrintMinutes';
import PlatformAdmin from './pages/PlatformAdmin';
import PlatformShell from './components/PlatformShell';

const queryClient = new QueryClient();

const AppRoutes = () => (
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
    <Route path="/notify-settings" element={<Navigate to="/settings?tab=email" replace />} />
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
          <AppRoutes />
        </BrowserRouter>
      </TooltipProvider>
      {/* MODULE_PROVIDERS_CLOSE */}
    </QueryClientProvider>
  </DirectionProvider>
);

export default App;
export { AppRoutes };
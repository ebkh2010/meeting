/**
 * بخش یکپارچهٔ «تنظیمات» سازمان — فقط برای نقش «مدیر سازمان».
 *
 * زبانه‌ها: کاربران و نقش‌ها، سقف‌های بارگذاری، گزارش ارسال.
 * تنظیمات ایمیل، پیامک، هوش مصنوعی و استوریج خارجی از این بخش حذف شده و
 * فقط توسط مدیریت پلتفرم انجام می‌شود.
 * برای دبیر جلسات و عضو، پیام دسترسی ممنوع (۴۰۳) نمایش داده می‌شود و آیکون تنظیمات
 * در هدر برای آن‌ها دیده نمی‌شود.
 */
import { useSearchParams } from 'react-router-dom';
import { Bell, HardDriveUpload, ShieldAlert, Users2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import AppShell from '@/components/AppShell';
import UsersPanel from '@/components/settings/UsersPanel';
import UploadLimitsPanel from '@/components/settings/UploadLimitsPanel';
import DangerZonePanel from '@/components/settings/DangerZonePanel';
import { DeliveriesPanel } from '@/components/settings/NotifyPanels';
import { isAdminRole } from '@/lib/appAuth';

const TABS = [
  { value: 'users', label: 'کاربران و نقش‌ها', icon: Users2 },
  { value: 'uploads', label: 'سقف‌های بارگذاری', icon: HardDriveUpload },
  { value: 'deliveries', label: 'گزارش ارسال', icon: Bell },
];

export default function SettingsPage() {
  return (
    <AppShell>
      {(bootstrap) => (
        <SettingsView
          isAdmin={isAdminRole(bootstrap.membership.role)}
          roleLabel={bootstrap.membership.role_label}
        />
      )}
    </AppShell>
  );
}

function SettingsView({ isAdmin, roleLabel }: { isAdmin: boolean; roleLabel: string }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const requested = searchParams.get('tab') || '';
  const activeTab = TABS.some((tab) => tab.value === requested) ? requested : 'users';

  if (!isAdmin) {
    return (
      <Card className="mx-auto max-w-xl border-destructive/40">
        <CardHeader className="items-start">
          <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
            <ShieldAlert className="h-5 w-5 text-destructive" />
          </div>
          <CardTitle>خطای ۴۰۳ — دسترسی ممنوع</CardTitle>
          <CardDescription>
            بخش تنظیمات سازمان تنها برای نقش «مدیر سازمان» در دسترس است. نقش فعلی شما «{roleLabel}»
            است و اجازهٔ ورود به این بخش را ندارد.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-muted-foreground">
            اگر به این بخش نیاز دارید، از مدیر سازمان بخواهید نقش شما را تغییر دهد.
          </p>
        </CardContent>
      </Card>
    );
  }

  const handleTabChange = (value: string) => {
    setSearchParams({ tab: value }, { replace: true });
  };

  return (
    <div className="space-y-6">
      <div>
        <h1>تنظیمات سازمان</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          تعریف کاربران و نقش‌ها، سقف‌های بارگذاری و گزارش ارسال‌ها. تنظیمات ایمیل، پیامک،
          هوش مصنوعی و استوریج خارجی توسط مدیریت پلتفرم انجام می‌شود و تنظیمات تولید صورتجلسه
          برای هر جلسه جداگانه در همان جلسه است.
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
        <TabsList className="flex h-auto w-full flex-nowrap justify-start gap-1 overflow-x-auto md:flex-wrap">
          {TABS.map((tab) => {
            const Icon = tab.icon;
            return (
              <TabsTrigger key={tab.value} value={tab.value} className="flex items-center gap-1.5">
                <Icon className="h-4 w-4" />
                {tab.label}
              </TabsTrigger>
            );
          })}
        </TabsList>

        <TabsContent value="users" className="space-y-6">
          <UsersPanel />
        </TabsContent>
        <TabsContent value="uploads" className="space-y-6">
          <UploadLimitsPanel />
        </TabsContent>
        <TabsContent value="deliveries" className="space-y-6">
          <DeliveriesPanel />
        </TabsContent>
      </Tabs>

      {/* حذف کامل سازمان و داده‌ها — فقط مدیر، با تأیید عبارتی و نام دقیق سازمان */}
      <DangerZonePanel />
    </div>
  );
}
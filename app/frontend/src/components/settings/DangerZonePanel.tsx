/**
 * ناحیهٔ خطرناک تنظیمات: حذف کامل سازمان و همهٔ داده‌های آن.
 *
 * فقط مدیر سازمان می‌تواند این عملیات بازگشت‌ناپذیر را اجرا کند؛ برای جلوگیری از
 * حذف اشتباهی، عبارت «حذف کامل» و نام دقیق سازمان باید تایپ شود و پس از موفقیت،
 * نشست پاک و کاربر به صفحهٔ ورود بازگردانده می‌شود.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import { errorMessage } from '@/lib/mgmt';
import { authApi } from '@/lib/appAuth';
import { clearToken } from '@/lib/session';

export default function DangerZonePanel() {
  const navigate = useNavigate();
  const [orgName, setOrgName] = useState('');
  const [confirmPhrase, setConfirmPhrase] = useState('');
  const [confirmOrgName, setConfirmOrgName] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authApi
      .me()
      .then((data) => setOrgName(data.organization?.name || ''))
      .catch(() => {
        /* نام سازمان فقط برای نمایش است */
      });
  }, []);

  const canSubmit =
    confirmPhrase.trim() === 'حذف کامل' && confirmOrgName.trim() === orgName.trim() && orgName;

  const handleDelete = async () => {
    if (!canSubmit) return;
    setBusy(true);
    try {
      const result = await authApi.deleteOrganization(confirmPhrase.trim(), confirmOrgName.trim());
      toast.success(result.detail || 'سازمان حذف شد.');
      clearToken();
      navigate('/', { replace: true });
    } catch (error) {
      toast.error(errorMessage(error, 'حذف سازمان ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card className="border-destructive/40">
      <CardHeader className="items-start">
        <div className="mb-2 flex h-10 w-10 items-center justify-center rounded-full bg-destructive/10">
          <Trash2 className="h-5 w-5 text-destructive" />
        </div>
        <CardTitle>حذف سازمان و همهٔ داده‌ها</CardTitle>
        <CardDescription>
          این عملیات بازگشت‌ناپذیر است: همهٔ کاربران، جلسات، صورتجلسه‌ها، فایل‌های صوتی و
          تنظیمات این سازمان برای همیشه حذف می‌شوند و هیچ راهی برای بازیابی وجود ندارد.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {orgName ? (
          <p className="text-sm text-muted-foreground">
            نام سازمان برای تأیید: <span className="font-medium text-foreground">{orgName}</span>
          </p>
        ) : (
          <p className="text-sm text-muted-foreground">در حال دریافت نام سازمان…</p>
        )}

        <div className="space-y-2">
          <Label htmlFor="danger-confirm">عبارت تأیید</Label>
          <Input
            id="danger-confirm"
            dir="rtl"
            placeholder="حذف کامل"
            value={confirmPhrase}
            onChange={(event) => setConfirmPhrase(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="danger-org-name">نام دقیق سازمان</Label>
          <Input
            id="danger-org-name"
            dir="rtl"
            placeholder="نام سازمان را دقیقاً وارد کنید"
            value={confirmOrgName}
            onChange={(event) => setConfirmOrgName(event.target.value)}
          />
        </div>

        <Button
          variant="destructive"
          className="w-full sm:w-auto"
          disabled={busy || !canSubmit}
          onClick={handleDelete}
        >
          {busy ? 'در حال حذف…' : 'حذف قطعی سازمان و همهٔ داده‌ها'}
        </Button>
        {orgName && !canSubmit && (
          <p className="text-xs text-muted-foreground">
            دکمهٔ حذف فقط وقتی فعال می‌شود که عبارت «حذف کامل» و نام دقیق سازمان تایپ شود.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

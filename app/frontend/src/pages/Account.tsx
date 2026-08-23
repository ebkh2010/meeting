/**
 * صفحهٔ حساب کاربری: نمایش پروفایل و تغییر رمز عبور.
 * برای همهٔ نقش‌ها در دسترس است.
 */
import { useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { toast } from 'sonner';
import AppShell from '@/components/AppShell';
import { errorMessage } from '@/lib/mgmt';
import { authApi, AppUser } from '@/lib/appAuth';

export default function Account() {
  return <AppShell>{() => <AccountView />}</AppShell>;
}

function AccountView() {
  const [profile, setProfile] = useState<AppUser | null>(null);
  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    authApi
      .me()
      .then((data) => setProfile(data.user))
      .catch((error) => toast.error(errorMessage(error)));
  }, []);

  const handleChangePassword = async () => {
    if (newPassword !== repeatPassword) {
      toast.error('رمز عبور جدید با تکرار آن یکسان نیست.');
      return;
    }
    setBusy(true);
    try {
      const result = await authApi.changePassword(currentPassword, newPassword);
      toast.success(result.detail || 'رمز عبور تغییر کرد.');
      setCurrentPassword('');
      setNewPassword('');
      setRepeatPassword('');
      const data = await authApi.me();
      setProfile(data.user);
    } catch (error) {
      toast.error(errorMessage(error, 'تغییر رمز عبور ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>مشخصات حساب</CardTitle>
          <CardDescription>این اطلاعات توسط مدیر سازمان قابل ویرایش است.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3 text-sm">
          {profile ? (
            <>
              <Row label="نام و نام خانوادگی" value={profile.full_name} />
              <Row label="نام کاربری" value={profile.username} />
              <Row label="شماره موبایل" value={profile.mobile || '—'} />
              <Row label="ایمیل" value={profile.email || '—'} />
              <Row label="کد ملی" value={profile.national_id || '—'} />
              <Row label="جنسیت" value={profile.gender_label || '—'} />
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">نقش</span>
                <Badge variant="outline">{profile.role_label}</Badge>
              </div>
            </>
          ) : (
            <p className="text-muted-foreground">در حال دریافت اطلاعات…</p>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>تغییر رمز عبور</CardTitle>
          <CardDescription>رمز عبور باید حداقل ۶ نویسه باشد.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="cur-pass">رمز عبور فعلی</Label>
            <Input
              id="cur-pass"
              type="password"
              value={currentPassword}
              onChange={(event) => setCurrentPassword(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="new-pass">رمز عبور جدید</Label>
            <Input
              id="new-pass"
              type="password"
              value={newPassword}
              onChange={(event) => setNewPassword(event.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="rep-pass">تکرار رمز عبور جدید</Label>
            <Input
              id="rep-pass"
              type="password"
              value={repeatPassword}
              onChange={(event) => setRepeatPassword(event.target.value)}
            />
          </div>
          <Button disabled={busy} onClick={handleChangePassword}>
            {busy ? 'در حال ذخیره…' : 'ذخیره رمز جدید'}
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
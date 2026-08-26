/**
 * صفحهٔ حساب کاربری: ویرایش مشخصات توسط خود کاربر (همهٔ نقش‌ها)،
 * تأیید ایمیل و موبایل با کد یکبارمصرف، و تغییر رمز عبور.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { toast } from 'sonner';
import AppShell from '@/components/AppShell';
import AiUsagePanel from '@/components/AiUsagePanel';
import { errorMessage } from '@/lib/mgmt';
import { authApi, AppUser, GENDER_OPTIONS } from '@/lib/appAuth';

interface ProfileForm {
  first_name: string;
  last_name: string;
  mobile: string;
  email: string;
  national_id: string;
  gender: string;
}

export default function Account() {
  return <AppShell>{() => <AccountView />}</AppShell>;
}

function AccountView() {
  const [profile, setProfile] = useState<AppUser | null>(null);
  const [form, setForm] = useState<ProfileForm>({
    first_name: '',
    last_name: '',
    mobile: '',
    email: '',
    national_id: '',
    gender: '',
  });
  const [busySave, setBusySave] = useState(false);

  const [emailCode, setEmailCode] = useState('');
  const [mobileCode, setMobileCode] = useState('');
  const [busyEmail, setBusyEmail] = useState(false);
  const [busyMobile, setBusyMobile] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [repeatPassword, setRepeatPassword] = useState('');
  const [busyPassword, setBusyPassword] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await authApi.me();
      setProfile(data.user);
      setForm({
        first_name: data.user.first_name || '',
        last_name: data.user.last_name || '',
        mobile: data.user.mobile || '',
        email: data.user.email || '',
        national_id: data.user.national_id || '',
        gender: data.user.gender || '',
      });
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت مشخصات حساب ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSaveProfile = async () => {
    setBusySave(true);
    try {
      await authApi.updateMe({
        first_name: form.first_name,
        last_name: form.last_name,
        mobile: form.mobile,
        email: form.email,
        national_id: form.national_id,
        gender: form.gender,
      });
      toast.success('مشخصات حساب ذخیره شد.');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'ذخیرهٔ مشخصات ناموفق بود.'));
    } finally {
      setBusySave(false);
    }
  };

  const handleSendEmailCode = async () => {
    setBusyEmail(true);
    try {
      const result = await authApi.requestEmailCode();
      toast.success(result.detail || 'کد تأیید به ایمیل شما ارسال شد.');
    } catch (error) {
      toast.error(errorMessage(error, 'ارسال کد تأیید ایمیل ناموفق بود.'));
    } finally {
      setBusyEmail(false);
    }
  };

  const handleConfirmEmailCode = async () => {
    if (!/^\d{6}$/.test(emailCode.trim())) {
      toast.error('کد تأیید باید ۶ رقم باشد.');
      return;
    }
    setBusyEmail(true);
    try {
      const result = await authApi.confirmEmailCode(emailCode.trim());
      toast.success(result.detail || 'ایمیل شما تأیید شد.');
      setEmailCode('');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'تأیید ایمیل ناموفق بود.'));
    } finally {
      setBusyEmail(false);
    }
  };

  const handleSendMobileCode = async () => {
    setBusyMobile(true);
    try {
      const result = await authApi.requestMobileCode();
      toast.success(result.detail || 'کد تأیید به موبایل شما پیامک شد.');
    } catch (error) {
      toast.error(errorMessage(error, 'ارسال کد تأیید موبایل ناموفق بود.'));
    } finally {
      setBusyMobile(false);
    }
  };

  const handleConfirmMobileCode = async () => {
    if (!/^\d{6}$/.test(mobileCode.trim())) {
      toast.error('کد تأیید باید ۶ رقم باشد.');
      return;
    }
    setBusyMobile(true);
    try {
      const result = await authApi.confirmMobileCode(mobileCode.trim());
      toast.success(result.detail || 'شمارهٔ موبایل شما تأیید شد.');
      setMobileCode('');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'تأیید موبایل ناموفق بود.'));
    } finally {
      setBusyMobile(false);
    }
  };

  const handleChangePassword = async () => {
    if (newPassword !== repeatPassword) {
      toast.error('رمز عبور جدید با تکرار آن یکسان نیست.');
      return;
    }
    setBusyPassword(true);
    try {
      const result = await authApi.changePassword(currentPassword, newPassword);
      toast.success(result.detail || 'رمز عبور تغییر کرد.');
      setCurrentPassword('');
      setNewPassword('');
      setRepeatPassword('');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'تغییر رمز عبور ناموفق بود.'));
    } finally {
      setBusyPassword(false);
    }
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>مشخصات حساب</CardTitle>
          <CardDescription>
            شما در هر زمان می‌توانید مشخصات خود را ویرایش کنید. تغییر ایمیل یا موبایل،
            تأیید آن را باطل می‌کند و باید دوباره با کد تأیید شود.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="first-name">نام</Label>
              <Input
                id="first-name"
                value={form.first_name}
                onChange={(event) => setForm({ ...form, first_name: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="last-name">نام خانوادگی</Label>
              <Input
                id="last-name"
                value={form.last_name}
                onChange={(event) => setForm({ ...form, last_name: event.target.value })}
              />
            </div>
          </div>

          <div className="space-y-2">
            <Label htmlFor="mobile">شماره موبایل</Label>
            <Input
              id="mobile"
              dir="ltr"
              inputMode="tel"
              value={form.mobile}
              onChange={(event) => setForm({ ...form, mobile: event.target.value })}
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="email">ایمیل</Label>
            <Input
              id="email"
              dir="ltr"
              type="email"
              value={form.email}
              onChange={(event) => setForm({ ...form, email: event.target.value })}
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="national-id">کد ملی</Label>
              <Input
                id="national-id"
                dir="ltr"
                inputMode="numeric"
                value={form.national_id}
                onChange={(event) => setForm({ ...form, national_id: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>جنسیت</Label>
              <Select
                value={form.gender || 'none'}
                onValueChange={(value) => setForm({ ...form, gender: value === 'none' ? '' : value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="انتخاب کنید" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="none">انتخاب کنید</SelectItem>
                  {GENDER_OPTIONS.map((item) => (
                    <SelectItem key={item.value} value={item.value}>
                      {item.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          {profile && (
            <div className="flex items-center justify-between rounded-lg border border-border bg-muted/30 px-3 py-2 text-sm">
              <span className="text-muted-foreground">
                نام کاربری: <span dir="ltr" className="font-medium text-foreground">{profile.username}</span>
              </span>
              <Badge variant="outline">{profile.role_label}</Badge>
            </div>
          )}

          <Button disabled={busySave} onClick={handleSaveProfile}>
            {busySave ? 'در حال ذخیره…' : 'ذخیرهٔ مشخصات'}
          </Button>
        </CardContent>
      </Card>

      <div className="space-y-6">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              تأیید ایمیل
              {profile?.email_verified ? (
                <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">تأیید شده</Badge>
              ) : (
                <Badge className="bg-amber-50 text-amber-700 border-amber-200">تأیید نشده</Badge>
              )}
            </CardTitle>
            <CardDescription>
              {profile?.email
                ? `کد تأیید به نشانی ${profile.email} ارسال می‌شود.`
                : 'ابتدا ایمیل خود را در مشخصات حساب ذخیره کنید.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {profile?.email_verified ? (
              <p className="text-sm text-muted-foreground">
                ایمیل شما تأیید شده است. اگر ایمیل را تغییر دهید، باید دوباره تأیید شود.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    disabled={busyEmail || !profile?.email}
                    onClick={handleSendEmailCode}
                  >
                    {busyEmail ? 'در حال ارسال…' : 'ارسال کد تأیید'}
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    dir="ltr"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="کد ۶ رقمی"
                    className="max-w-[140px]"
                    value={emailCode}
                    onChange={(event) => setEmailCode(event.target.value.replace(/\D/g, ''))}
                  />
                  <Button
                    variant="secondary"
                    disabled={busyEmail || !profile?.email || emailCode.length !== 6}
                    onClick={handleConfirmEmailCode}
                  >
                    تأیید کد
                  </Button>
                </div>
              </>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              تأیید شمارهٔ موبایل
              {profile?.mobile_verified ? (
                <Badge className="bg-emerald-50 text-emerald-700 border-emerald-200">تأیید شده</Badge>
              ) : (
                <Badge className="bg-amber-50 text-amber-700 border-amber-200">تأیید نشده</Badge>
              )}
            </CardTitle>
            <CardDescription>
              {profile?.mobile
                ? `کد تأیید به شمارهٔ ${profile.mobile} پیامک می‌شود.`
                : 'شمارهٔ موبایل ثبت نشده است.'}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {profile?.mobile_verified ? (
              <p className="text-sm text-muted-foreground">
                شمارهٔ موبایل شما تأیید شده است. اگر شماره را تغییر دهید، باید دوباره تأیید شود.
              </p>
            ) : (
              <>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    disabled={busyMobile || !profile?.mobile}
                    onClick={handleSendMobileCode}
                  >
                    {busyMobile ? 'در حال ارسال…' : 'ارسال کد تأیید'}
                  </Button>
                </div>
                <div className="flex items-center gap-2">
                  <Input
                    dir="ltr"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="کد ۶ رقمی"
                    className="max-w-[140px]"
                    value={mobileCode}
                    onChange={(event) => setMobileCode(event.target.value.replace(/\D/g, ''))}
                  />
                  <Button
                    variant="secondary"
                    disabled={busyMobile || !profile?.mobile || mobileCode.length !== 6}
                    onClick={handleConfirmMobileCode}
                  >
                    تأیید کد
                  </Button>
                </div>
              </>
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
            <Button disabled={busyPassword} onClick={handleChangePassword}>
              {busyPassword ? 'در حال ذخیره…' : 'ذخیره رمز جدید'}
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* سهمیه و مصرف هوش مصنوعی این کاربر */}
      <AiUsagePanel />
    </div>
  );
}

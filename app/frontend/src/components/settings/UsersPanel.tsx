/**
 * پنل «کاربران و نقش‌ها» در بخش تنظیمات (فقط مدیر سازمان).
 * ساخت کاربر، تغییر نقش، فعال/غیرفعال‌سازی و بازنشانی رمز عبور.
 *
 * این پنل خودش گارد دسترسی ندارد؛ کنترل نقش در صفحهٔ تنظیمات انجام می‌شود.
 */
import { useCallback, useEffect, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Separator } from '@/components/ui/separator';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { toast } from 'sonner';
import { errorMessage } from '@/lib/mgmt';
import { AppUser, authApi, GENDER_OPTIONS, ROLE_OPTIONS } from '@/lib/appAuth';

const EMPTY_FORM = {
  first_name: '',
  last_name: '',
  mobile: '',
  national_id: '',
  gender: '',
  email: '',
  role: 'member',
};

export default function UsersPanel() {
  const [items, setItems] = useState<AppUser[]>([]);
  const [form, setForm] = useState({ ...EMPTY_FORM });
  const [busy, setBusy] = useState(false);
  const [createdInfo, setCreatedInfo] = useState('');

  const load = useCallback(async () => {
    try {
      const data = await authApi.listUsers();
      setItems(data.items || []);
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت فهرست کاربران ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleCreate = async () => {
    setBusy(true);
    setCreatedInfo('');
    try {
      const result = await authApi.createUser(form);
      const password = result.temporary_password || result.password || '';
      const loginName = result.default_credentials?.username || result.username || form.mobile;
      const hint = result.default_credentials?.password_hint || '';
      if (password) {
        setCreatedInfo(`کاربر ساخته شد — نام کاربری: ${loginName} | رمز موقت: ${password}`);
      } else {
        setCreatedInfo(
          `کاربر ساخته شد — نام کاربری: ${loginName} | رمز عبور اولیه: ${
            hint || 'کد ملی کاربر'
          }. کاربر در نخستین ورود باید رمز خود را تغییر دهد.`,
        );
      }
      toast.success('کاربر جدید ساخته شد.');
      setForm({ ...EMPTY_FORM });
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'ساخت کاربر ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  const handleUpdate = async (user: AppUser, payload: Record<string, unknown>) => {
    try {
      const result = await authApi.updateUser(user.id, payload);
      const password = result.temporary_password || result.password || '';
      if (password) {
        setCreatedInfo(`رمز موقت جدید برای ${user.full_name}: ${password}`);
      }
      toast.success(result.detail || 'تغییرات ذخیره شد.');
      await load();
    } catch (error) {
      toast.error(errorMessage(error, 'ذخیرهٔ تغییرات ناموفق بود.'));
    }
  };

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle>افزودن کاربر سازمان</CardTitle>
          <CardDescription>
            نام کاربری کاربر جدید، شمارهٔ موبایل او و رمز عبور اولیه، کد ملی او است؛ این اعتبارنامه
            پس از ساخت در همین بخش نمایش داده می‌شود و کاربر در نخستین ورود باید رمز را تغییر دهد.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid gap-4 md:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="u-first">نام</Label>
              <Input
                id="u-first"
                value={form.first_name}
                onChange={(event) => setForm({ ...form, first_name: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="u-last">نام خانوادگی</Label>
              <Input
                id="u-last"
                value={form.last_name}
                onChange={(event) => setForm({ ...form, last_name: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="u-mobile">شماره موبایل</Label>
              <Input
                id="u-mobile"
                inputMode="tel"
                placeholder="۰۹۱۲۳۴۵۶۷۸۹"
                value={form.mobile}
                onChange={(event) => setForm({ ...form, mobile: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="u-national">کد ملی</Label>
              <Input
                id="u-national"
                inputMode="numeric"
                value={form.national_id}
                onChange={(event) => setForm({ ...form, national_id: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="u-email">ایمیل (برای دعوت‌نامهٔ ایمیلی)</Label>
              <Input
                id="u-email"
                type="email"
                value={form.email}
                onChange={(event) => setForm({ ...form, email: event.target.value })}
              />
            </div>
            <div className="space-y-2">
              <Label>جنسیت</Label>
              <Select
                value={form.gender}
                onValueChange={(value) => setForm({ ...form, gender: value })}
              >
                <SelectTrigger>
                  <SelectValue placeholder="انتخاب کنید" />
                </SelectTrigger>
                <SelectContent>
                  {GENDER_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-2">
              <Label>نقش</Label>
              <Select value={form.role} onValueChange={(value) => setForm({ ...form, role: value })}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {ROLE_OPTIONS.map((option) => (
                    <SelectItem key={option.value} value={option.value}>
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <Button disabled={busy} onClick={handleCreate}>
            {busy ? 'در حال ساخت…' : 'ساخت کاربر'}
          </Button>

          {createdInfo && (
            <div className="rounded-md border border-primary/40 bg-primary/5 p-3 text-sm">
              {createdInfo}
            </div>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>کاربران سازمان</CardTitle>
          <CardDescription>تغییر نقش، وضعیت و بازنشانی رمز عبور کاربران.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          {/*
            نمای کارتی موبایل: جدول هفت‌ستونی در عرض ۳۲۰ پیکسل اسکرول افقی می‌سازد،
            پس در موبایل هر کاربر یک کارت مستقل با همان کنترل‌های واقعی است.
          */}
          <div className="space-y-3 md:hidden">
            {items.length === 0 ? (
              <p className="py-4 text-center text-sm text-muted-foreground">
                هنوز کاربری ثبت نشده است.
              </p>
            ) : (
              items.map((user) => (
                <div key={`m-${user.id}`} className="space-y-3 rounded-lg border border-border p-3">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{user.full_name}</p>
                      <p dir="ltr" className="truncate text-xs text-muted-foreground">
                        {user.username}
                      </p>
                    </div>
                    <Badge
                      variant={(user.status || 'active') === 'active' ? 'secondary' : 'outline'}
                      className="shrink-0"
                    >
                      {(user.status || 'active') === 'active' ? 'فعال' : 'غیرفعال'}
                    </Badge>
                  </div>

                  <dl className="space-y-1 text-xs">
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">موبایل</dt>
                      <dd dir="ltr" className="truncate">
                        {user.mobile || '—'}
                      </dd>
                    </div>
                    <div className="flex items-center justify-between gap-2">
                      <dt className="text-muted-foreground">ایمیل</dt>
                      <dd dir="ltr" className="truncate">
                        {user.email || '—'}
                      </dd>
                    </div>
                  </dl>

                  <Select
                    value={user.role}
                    onValueChange={(value) => handleUpdate(user, { role: value })}
                  >
                    <SelectTrigger className="h-11 w-full">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {ROLE_OPTIONS.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {option.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>

                  <div className="grid grid-cols-2 gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      className="min-h-11 !bg-transparent hover:!bg-transparent"
                      onClick={() => handleUpdate(user, { reset_password: true })}
                    >
                      بازنشانی رمز
                    </Button>
                    <Button
                      size="sm"
                      variant="secondary"
                      className="min-h-11"
                      onClick={() =>
                        handleUpdate(user, {
                          status: (user.status || 'active') === 'active' ? 'disabled' : 'active',
                        })
                      }
                    >
                      {(user.status || 'active') === 'active' ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="hidden overflow-x-auto md:block">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="text-right">نام</TableHead>
                <TableHead className="text-right">نام کاربری</TableHead>
                <TableHead className="text-right">موبایل</TableHead>
                <TableHead className="text-right">ایمیل</TableHead>
                <TableHead className="text-right">نقش</TableHead>
                <TableHead className="text-right">وضعیت</TableHead>
                <TableHead className="text-right">عملیات</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={7} className="text-center text-muted-foreground">
                    هنوز کاربری ثبت نشده است.
                  </TableCell>
                </TableRow>
              ) : (
                items.map((user) => (
                  <TableRow key={user.id}>
                    <TableCell className="font-medium">{user.full_name}</TableCell>
                    <TableCell>{user.username}</TableCell>
                    <TableCell>{user.mobile || '—'}</TableCell>
                    <TableCell>{user.email || '—'}</TableCell>
                    <TableCell>
                      <Select
                        value={user.role}
                        onValueChange={(value) => handleUpdate(user, { role: value })}
                      >
                        <SelectTrigger className="h-8 w-36">
                          <SelectValue />
                        </SelectTrigger>
                        <SelectContent>
                          {ROLE_OPTIONS.map((option) => (
                            <SelectItem key={option.value} value={option.value}>
                              {option.label}
                            </SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                    </TableCell>
                    <TableCell>
                      <Badge variant={(user.status || 'active') === 'active' ? 'secondary' : 'outline'}>
                        {(user.status || 'active') === 'active' ? 'فعال' : 'غیرفعال'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <div className="flex flex-wrap items-center gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="!bg-transparent hover:!bg-transparent"
                          onClick={() => handleUpdate(user, { reset_password: true })}
                        >
                          بازنشانی رمز
                        </Button>
                        <Separator orientation="vertical" className="h-5" />
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            handleUpdate(user, {
                              status: (user.status || 'active') === 'active' ? 'disabled' : 'active',
                            })
                          }
                        >
                          {(user.status || 'active') === 'active' ? 'غیرفعال‌سازی' : 'فعال‌سازی'}
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
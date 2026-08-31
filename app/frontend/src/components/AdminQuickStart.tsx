/**
 * بخش «شروع سریع» داشبورد برای نقش مدیر سازمان.
 *
 * فقط گام «افزودن کاربران» را پیگیری می‌کند؛ تنظیمات ایمیل، پیامک، هوش مصنوعی و
 * استوریج خارجی توسط مدیریت پلتفرم انجام می‌شود و کارت پشتیبانی، شمارهٔ تماس را
 * نشان می‌دهد.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, Headphones, Users2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { toPersianDigits } from '@/lib/mgmt';
import { authApi } from '@/lib/appAuth';

const SUPPORT_PHONE = '۰۲۱۴۱۰۲۱۰۰۰';
const SUPPORT_EXTENSIONS = 'داخلی ۱۱۴ یا ۳۳۷';

export default function AdminQuickStart() {
  const [userCount, setUserCount] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const result = await authApi.listUsers().catch(() => null);
    if (result) {
      setUserCount((result.items || []).length);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading) {
    return <Skeleton className="h-40 w-full" />;
  }

  const hasTeam = (userCount ?? 0) > 1;

  return (
    <Card className="border-primary/30">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">شروع سریع مدیر سازمان</CardTitle>
            <CardDescription>
              {hasTeam
                ? 'راه‌اندازی سازمان کامل است؛ می‌توانید جلسه ثبت کنید.'
                : 'برای شروع، اعضا و دبیر جلسات سازمان را اضافه کنید.'}
            </CardDescription>
          </div>
          <Badge variant={hasTeam ? 'secondary' : 'destructive'}>
            {hasTeam ? '۱' : '۰'} از ۱
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-2">
        <div
          className={`flex flex-col gap-2 rounded-lg border p-3 ${
            hasTeam ? 'border-border' : 'border-destructive/40 bg-destructive/5'
          }`}
        >
          <div className="flex items-center gap-2">
            <Users2 className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">افزودن کاربران و تعیین نقش</span>
            {hasTeam ? (
              <CheckCircle2 className="ms-auto h-4 w-4 text-primary" />
            ) : (
              <Circle className="ms-auto h-4 w-4 text-destructive" />
            )}
          </div>
          <p className="text-xs text-muted-foreground">
            {hasTeam
              ? `${toPersianDigits(userCount ?? 0)} کاربر در سازمان ثبت شده است.`
              : 'هنوز کاربر دیگری نساخته‌اید؛ اعضا و دبیر جلسات را اضافه کنید.'}
          </p>
          <Button asChild size="sm" variant={hasTeam ? 'outline' : 'default'} className="mt-auto">
            <Link to="/settings?tab=users" className={hasTeam ? '!bg-transparent' : ''}>
              مدیریت کاربران
            </Link>
          </Button>
        </div>

        <div className="flex flex-col gap-2 rounded-lg border border-border p-3">
          <div className="flex items-center gap-2">
            <Headphones className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium">پشتیبانی پلتفرم</span>
          </div>
          <p className="text-xs text-muted-foreground">
            تنظیمات ایمیل، پیامک، هوش مصنوعی و استوریج خارجی توسط مدیریت پلتفرم انجام می‌شود؛
            برای تغییر یا ثبت‌نام با شمارهٔ {SUPPORT_PHONE} ({SUPPORT_EXTENSIONS}) پشتیبانی
            ویدارا تماس حاصل فرمایید.
          </p>
        </div>
      </CardContent>
    </Card>
  );
}

/**
 * بخش «شروع سریع» داشبورد برای نقش مدیر سازمان.
 *
 * وضعیت واقعی راه‌اندازی را از سرور می‌خواند (تعداد کاربران و تنظیمات ارسال ایمیل/پیامک)
 * و برای هر گام ناقص، کارت اقدام قابل کلیک به صفحهٔ مربوط نشان می‌دهد. هدف این است که
 * مدیر بدون جست‌وجو در منو، مسیر «افزودن کاربران» و «تنظیم SMTP/پیامک» را پیدا کند.
 */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, Mail, MessageSquare, Users2 } from 'lucide-react';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { toPersianDigits } from '@/lib/mgmt';
import { authApi } from '@/lib/appAuth';
import { notifyApi, NotifySettings } from '@/lib/notify';

interface StepState {
  key: string;
  done: boolean;
  title: string;
  description: string;
  to: string;
  cta: string;
  icon: typeof Users2;
}

export default function AdminQuickStart() {
  const [userCount, setUserCount] = useState<number | null>(null);
  const [settings, setSettings] = useState<NotifySettings | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    const [usersResult, settingsResult] = await Promise.allSettled([
      authApi.listUsers(),
      notifyApi.readSettings(),
    ]);
    if (usersResult.status === 'fulfilled') {
      setUserCount((usersResult.value.items || []).length);
    }
    if (settingsResult.status === 'fulfilled') {
      setSettings(settingsResult.value);
    }
    setLoading(false);
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (loading) {
    return <Skeleton className="h-40 w-full" />;
  }

  const smtpReady = Boolean(
    settings?.smtp_enabled && settings?.smtp_host && settings?.smtp_from_email,
  );
  const smsReady = Boolean(settings?.sms_enabled && settings?.sms_api_key_set);
  const hasTeam = (userCount ?? 0) > 1;

  const steps: StepState[] = [
    {
      key: 'users',
      done: hasTeam,
      title: 'افزودن کاربران و تعیین نقش',
      description: hasTeam
        ? `${toPersianDigits(userCount ?? 0)} کاربر در سازمان ثبت شده است.`
        : 'هنوز کاربر دیگری نساخته‌اید؛ اعضا و دبیر جلسات را اضافه کنید.',
      to: '/settings?tab=users',
      cta: 'مدیریت کاربران',
      icon: Users2,
    },
    {
      key: 'smtp',
      done: smtpReady,
      title: 'تنظیم سرور ایمیل (SMTP)',
      description: smtpReady
        ? `ارسال ایمیل فعال است (${settings?.smtp_host}).`
        : 'برای ارسال دعوت‌نامهٔ ایمیلی جلسات، اطلاعات سرور ایمیل را وارد کنید.',
      to: '/settings?tab=email',
      cta: 'تنظیم ایمیل',
      icon: Mail,
    },
    {
      key: 'sms',
      done: smsReady,
      title: 'تنظیم پنل پیامک قاصدک',
      description: smsReady
        ? `ارسال پیامک فعال است (خط ${settings?.sms_line_number || '—'}).`
        : 'برای ارسال پیامک دعوت جلسه، کلید API قاصدک و شمارهٔ خط را وارد کنید.',
      to: '/settings?tab=sms',
      cta: 'تنظیم پیامک',
      icon: MessageSquare,
    },
  ];

  const pending = steps.filter((step) => !step.done);

  return (
    <Card className="border-primary/30">
      <CardHeader>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">شروع سریع مدیر سازمان</CardTitle>
            <CardDescription>
              {pending.length === 0
                ? 'راه‌اندازی سازمان کامل است؛ می‌توانید جلسه ثبت کنید.'
                : `${toPersianDigits(pending.length)} گام برای کامل‌شدن راه‌اندازی باقی مانده است.`}
            </CardDescription>
          </div>
          <Badge variant={pending.length === 0 ? 'secondary' : 'destructive'}>
            {toPersianDigits(steps.length - pending.length)} از {toPersianDigits(steps.length)}
          </Badge>
        </div>
      </CardHeader>
      <CardContent className="grid gap-3 md:grid-cols-3">
        {steps.map((step) => {
          const Icon = step.icon;
          return (
            <div
              key={step.key}
              className={`flex flex-col gap-2 rounded-lg border p-3 ${
                step.done ? 'border-border' : 'border-destructive/40 bg-destructive/5'
              }`}
            >
              <div className="flex items-center gap-2">
                <Icon className="h-4 w-4 text-muted-foreground" />
                <span className="text-sm font-medium">{step.title}</span>
                {step.done ? (
                  <CheckCircle2 className="ms-auto h-4 w-4 text-primary" />
                ) : (
                  <Circle className="ms-auto h-4 w-4 text-destructive" />
                )}
              </div>
              <p className="text-xs text-muted-foreground">{step.description}</p>
              <Button asChild size="sm" variant={step.done ? 'outline' : 'default'} className="mt-auto">
                <Link to={step.to} className={step.done ? '!bg-transparent' : ''}>
                  {step.cta}
                </Link>
              </Button>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
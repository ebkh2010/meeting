/** داشبورد فضای کاری: شمارنده‌ها، نمودارها، جلسات آینده و اقدام‌های من. */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as ChartTooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { AlertTriangle, CalendarDays, ClipboardCheck, FileClock } from 'lucide-react';
import AppShell from '@/components/AppShell';
import AdminQuickStart from '@/components/AdminQuickStart';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ACTION_STATUS_LABELS,
  api,
  DashboardData,
  errorMessage,
  formatDate,
  formatDateTime,
  MINUTES_STATUS_LABELS,
  toPersianDigits,
} from '@/lib/mgmt';
import { isAdminRole } from '@/lib/appAuth';

const CHART_COLORS = [
  'hsl(var(--chart-1))',
  'hsl(var(--chart-2))',
  'hsl(var(--chart-3))',
  'hsl(var(--chart-4))',
  'hsl(var(--chart-5))',
];

function StatCard({
  label,
  value,
  hint,
  icon: Icon,
}: {
  label: string;
  value: string;
  hint: string;
  icon: typeof CalendarDays;
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">{label}</CardTitle>
        <Icon className="h-4 w-4 text-muted-foreground" />
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-bold tabular">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

export default function Dashboard() {
  return (
    <AppShell>
      {(bootstrap) => <DashboardBody isAdmin={isAdminRole(bootstrap.membership.role)} />}
    </AppShell>
  );
}

function DashboardBody({ isAdmin }: { isAdmin: boolean }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api.dashboard());
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت داشبورد ناموفق بود.'));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (error) {
    return (
      <Card>
        <CardContent className="space-y-3 py-6">
          <p className="text-sm text-destructive">{error}</p>
          <Button onClick={load}>تلاش دوباره</Button>
        </CardContent>
      </Card>
    );
  }

  if (!data) {
    return (
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {[0, 1, 2, 3].map((key) => (
            <Skeleton key={key} className="h-28 w-full" />
          ))}
        </div>
        <Skeleton className="h-72 w-full" />
      </div>
    );
  }

  const { totals } = data;
  const typeData = data.meetings_by_type.filter((item) => item.value > 0);

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
        <h1>داشبورد</h1>
        <Link to="/meetings" className="w-full sm:w-auto">
          <Button className="min-h-11 w-full sm:w-auto">مدیریت جلسات</Button>
        </Link>
      </div>

      {isAdmin && <AdminQuickStart />}

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        <StatCard
          label="جلسات آینده"
          value={toPersianDigits(totals.upcoming)}
          hint={`مجموع جلسات: ${toPersianDigits(totals.meetings)}`}
          icon={CalendarDays}
        />
        <StatCard
          label="نرخ حضور"
          value={`${toPersianDigits(totals.attendance_rate)}٪`}
          hint={`جلسات برگزارشده: ${toPersianDigits(totals.past)}`}
          icon={ClipboardCheck}
        />
        <StatCard
          label="پیشرفت اقدامات"
          value={`${toPersianDigits(totals.action_completion_rate)}٪`}
          hint={`مجموع اقدامات: ${toPersianDigits(totals.actions)}`}
          icon={ClipboardCheck}
        />
        <StatCard
          label="نیازمند توجه"
          value={toPersianDigits(totals.overdue_actions + totals.pending_minutes)}
          hint={`اقدام دارای تأخیر: ${toPersianDigits(
            totals.overdue_actions,
          )} • صورتجلسهٔ در انتظار تأیید: ${toPersianDigits(totals.pending_minutes)}`}
          icon={AlertTriangle}
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle className="text-base">روند جلسات در ماه‌های گذشته</CardTitle>
          </CardHeader>
          <CardContent className="h-56 px-2 sm:px-6 md:h-72">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={data.meetings_by_month}>
                <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
                <XAxis dataKey="month" tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                <YAxis allowDecimals={false} tick={{ fontSize: 12 }} stroke="hsl(var(--muted-foreground))" />
                <ChartTooltip
                  contentStyle={{
                    background: 'hsl(var(--popover))',
                    border: '1px solid hsl(var(--border))',
                    borderRadius: 8,
                    direction: 'rtl',
                  }}
                  formatter={(value: number) => [`${toPersianDigits(value)} جلسه`, '']}
                />
                <Bar dataKey="value" fill="hsl(var(--chart-1))" radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-base">ترکیب نوع جلسات</CardTitle>
          </CardHeader>
          <CardContent className="h-56 px-2 sm:px-6 md:h-72">
            {typeData.length === 0 ? (
              <p className="text-sm text-muted-foreground">هنوز جلسه‌ای ثبت نشده است.</p>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie data={typeData} dataKey="value" nameKey="name" innerRadius={50} outerRadius={90}>
                    {typeData.map((entry, index) => (
                      <Cell key={entry.name} fill={CHART_COLORS[index % CHART_COLORS.length]} />
                    ))}
                  </Pie>
                  <ChartTooltip
                    contentStyle={{
                      background: 'hsl(var(--popover))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: 8,
                      direction: 'rtl',
                    }}
                    formatter={(value: number, name: string) => [
                      `${toPersianDigits(value)} جلسه`,
                      name,
                    ]}
                  />
                </PieChart>
              </ResponsiveContainer>
            )}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">جلسات پیش‌رو</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {data.next_meetings.length === 0 ? (
              <p className="text-sm text-muted-foreground">جلسهٔ آینده‌ای ثبت نشده است.</p>
            ) : (
              data.next_meetings.map((meeting) => (
                <Link
                  key={meeting.id}
                  to={`/meetings/${meeting.id}`}
                  className="block rounded-md border border-border p-3 transition-colors hover:bg-accent/40"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{meeting.title}</span>
                    <Badge variant="outline">{meeting.meeting_type}</Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatDateTime(meeting.starts_at)} • دبیر: {meeting.secretary_name || '—'}
                  </p>
                </Link>
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">اقدام‌های باز من</CardTitle>
            <FileClock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent className="space-y-3">
            {data.my_open_actions.length === 0 ? (
              <p className="text-sm text-muted-foreground">اقدام بازی به شما واگذار نشده است.</p>
            ) : (
              data.my_open_actions.map((action) => (
                <Link
                  key={action.id}
                  to={`/meetings/${action.meeting_id}`}
                  className="block rounded-md border border-border p-3 transition-colors hover:bg-accent/40"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <span className="font-medium">{action.title}</span>
                    <Badge variant={action.status === 'overdue' ? 'destructive' : 'secondary'}>
                      {ACTION_STATUS_LABELS[action.status] || action.status}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    مهلت: {formatDate(action.due_date)} • جلسه: {action.meeting_title || '—'}
                  </p>
                </Link>
              ))
            )}
            <div className="pt-1">
              <Link to="/meetings">
                <Button variant="outline" size="sm" className="!bg-transparent">
                  همهٔ جلسات
                </Button>
              </Link>
            </div>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">وضعیت صورتجلسه‌ها</CardTitle>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-3">
          {Object.entries(MINUTES_STATUS_LABELS).map(([key, label]) => (
            <div key={key} className="rounded-md border border-border px-4 py-3">
              <p className="text-xs text-muted-foreground">{label}</p>
              <p className="text-lg font-semibold tabular">
                {toPersianDigits(data.minutes_counts?.[key] ?? 0)}
              </p>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
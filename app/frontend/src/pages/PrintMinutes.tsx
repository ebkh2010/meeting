/** نمای چاپ/PDF صورتجلسهٔ فارسی و راست‌به‌چپ؛ خروجی با گفت‌وگوی چاپ مرورگر گرفته می‌شود. */
import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { Printer } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import {
  ACTION_STATUS_LABELS,
  api,
  errorMessage,
  ExportPackage,
  formatDate,
  formatDateTime,
  MINUTES_STATUS_LABELS,
  RSVP_LABELS,
  toPersianDigits,
} from '@/lib/mgmt';
import VidaraBranding from '@/components/VidaraBranding';
import MarkdownText from '@/components/MarkdownText';

export default function PrintMinutes() {
  const { meetingId } = useParams();
  const id = Number(meetingId);
  const [data, setData] = useState<ExportPackage | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setData(await api.exportPackage(id));
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت بستهٔ خروجی صورتجلسه ناموفق بود.'));
    }
  }, [id]);

  useEffect(() => {
    document.documentElement.setAttribute('dir', 'rtl');
    document.documentElement.setAttribute('lang', 'fa');
    load();
  }, [load]);

  if (error) {
    return (
      <div className="min-h-screen bg-background p-8" dir="rtl">
        <Card className="mx-auto max-w-xl">
          <CardContent className="space-y-3 py-6">
            <p className="text-sm text-destructive">{error}</p>
            <Button onClick={load}>تلاش دوباره</Button>
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="min-h-screen bg-background p-8" dir="rtl">
        <Skeleton className="mx-auto h-96 max-w-3xl" />
      </div>
    );
  }

  const { meeting, minutes } = data;

  return (
    <div className="min-h-screen bg-muted/40 py-8" dir="rtl">
      <div className="no-print mx-auto mb-4 flex max-w-3xl items-center justify-between px-4">
        <p className="text-sm text-muted-foreground">
          برای گرفتن فایل PDF، از گفت‌وگوی چاپ گزینهٔ «ذخیره به‌صورت PDF» را انتخاب کنید.
        </p>
        <Button className="gap-2" onClick={() => window.print()}>
          <Printer className="h-4 w-4" />
          چاپ / ذخیرهٔ PDF
        </Button>
      </div>

      <article className="print-sheet mx-auto max-w-3xl rounded-lg border border-border bg-card p-10 text-[13px] leading-8 text-foreground shadow-sm">
        <header className="border-b border-border pb-4">
          <p className="text-xs text-muted-foreground">{data.organization.name}</p>
          <h1 className="mt-1 text-2xl font-bold">صورتجلسه: {meeting.title}</h1>
          <p className="mt-2 text-xs text-muted-foreground">
            {formatDateTime(meeting.starts_at)} • مدت: {toPersianDigits(meeting.duration_minutes)}{' '}
            دقیقه • نوع: {meeting.meeting_type}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            دبیر جلسه: {meeting.secretary_name || '—'} • محل: {meeting.location || '—'}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            وضعیت صورتجلسه:{' '}
            {minutes ? MINUTES_STATUS_LABELS[minutes.status] || minutes.status : 'ثبت نشده'}
            {minutes ? ` • نسخهٔ ${toPersianDigits(minutes.current_version)}` : ''}
            {minutes?.approved_by_name ? ` • تأییدکننده: ${minutes.approved_by_name}` : ''}
          </p>
        </header>

        {minutes?.summary && (
          <section className="mt-5">
            <h2 className="text-base font-bold">خلاصهٔ جلسه</h2>
            <p className="mt-1 whitespace-pre-wrap">{minutes.summary}</p>
          </section>
        )}

        <section className="mt-5">
          <h2 className="text-base font-bold">دستور جلسه</h2>
          {data.agenda.length === 0 ? (
            <p className="mt-1 text-muted-foreground">بندی ثبت نشده است.</p>
          ) : (
            <ol className="mt-1 space-y-1">
              {data.agenda.map((item) => (
                <li key={item.id}>
                  {toPersianDigits(item.position)}. {item.title} (
                  {toPersianDigits(item.planned_minutes)} دقیقه)
                  {item.owner_name ? ` — ${item.owner_name}` : ''}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="mt-5">
          <h2 className="text-base font-bold">حاضران و دعوت‌شدگان</h2>
          {data.participants.length === 0 ? (
            <p className="mt-1 text-muted-foreground">فهرستی ثبت نشده است.</p>
          ) : (
            <table className="mt-2 w-full border-collapse text-xs">
              <thead>
                <tr className="bg-secondary">
                  <th className="border border-border p-2 text-right">نام</th>
                  <th className="border border-border p-2 text-right">پاسخ دعوت</th>
                  <th className="border border-border p-2 text-right">حضور</th>
                </tr>
              </thead>
              <tbody>
                {data.participants.map((participant) => (
                  <tr key={participant.id}>
                    <td className="border border-border p-2">{participant.full_name}</td>
                    <td className="border border-border p-2">
                      {RSVP_LABELS[participant.rsvp_status] || participant.rsvp_status}
                    </td>
                    <td className="border border-border p-2">
                      {participant.attended ? 'حاضر' : 'غایب'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <section className="mt-5">
          <h2 className="text-base font-bold">متن صورتجلسه</h2>
          <div className="mt-1">
            {minutes?.body_markdown ? (
              <MarkdownText text={minutes.body_markdown} className="text-sm leading-7" />
            ) : (
              'متن صورتجلسه ثبت نشده است.'
            )}
          </div>
        </section>

        <section className="mt-5">
          <h2 className="text-base font-bold">مصوبات</h2>
          {data.decisions.length === 0 ? (
            <p className="mt-1 text-muted-foreground">مصوبه‌ای ثبت نشده است.</p>
          ) : (
            <ol className="mt-1 space-y-1">
              {data.decisions.map((decision) => (
                <li key={decision.id}>
                  {toPersianDigits(decision.position)}. {decision.title}
                  {decision.description ? ` — ${decision.description}` : ''}
                </li>
              ))}
            </ol>
          )}
        </section>

        <section className="mt-5">
          <h2 className="text-base font-bold">اقدامات</h2>
          {data.actions.length === 0 ? (
            <p className="mt-1 text-muted-foreground">اقدامی ثبت نشده است.</p>
          ) : (
            <table className="mt-2 w-full border-collapse text-xs">
              <thead>
                <tr className="bg-secondary">
                  <th className="border border-border p-2 text-right">اقدام</th>
                  <th className="border border-border p-2 text-right">مسئول</th>
                  <th className="border border-border p-2 text-right">مهلت</th>
                  <th className="border border-border p-2 text-right">وضعیت</th>
                </tr>
              </thead>
              <tbody>
                {data.actions.map((action) => (
                  <tr key={action.id}>
                    <td className="border border-border p-2">{action.title}</td>
                    <td className="border border-border p-2">{action.owner_name || '—'}</td>
                    <td className="border border-border p-2">{formatDate(action.due_date)}</td>
                    <td className="border border-border p-2">
                      {ACTION_STATUS_LABELS[action.status] || action.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>

        <footer className="mt-8 border-t border-border pt-4 text-xs text-muted-foreground">
          <div className="flex justify-between">
            <span>امضای دبیر جلسه: ______________</span>
            <span>امضای رئیس جلسه: ______________</span>
          </div>
          {minutes?.locked_at && (
            <p className="mt-3">
              این صورتجلسه در {formatDateTime(minutes.locked_at)} قفل نهایی شده است.
            </p>
          )}
          <VidaraBranding variant="print" className="mt-4" />
        </footer>
      </article>
    </div>
  );
}
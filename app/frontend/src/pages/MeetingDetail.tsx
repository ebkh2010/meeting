/**
 * جزئیات جلسه: دستور جلسه، دعوت‌شدگان و حضور، صوت و رونویسی، صورتجلسه با گردش تأیید،
 * مصوبات و اقدامات. کارهای هوش مصنوعی به‌صورت غیرهمزمان با polling پیگیری می‌شوند.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import {
  CalendarDays,
  Download,
  FileText,
  Loader2,
  Mic,
  Plus,
  Printer,
  RefreshCw,
  Settings2,
  Sparkles,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import AppShell from '@/components/AppShell';
import JalaliDateTimePicker from '@/components/JalaliDateTimePicker';
import MeetingAttachmentsCard from '@/components/MeetingAttachmentsCard';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Progress } from '@/components/ui/progress';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Separator } from '@/components/ui/separator';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  ACTION_STATUS_LABELS,
  api,
  Bootstrap,
  downloadMinutesDocx,
  errorMessage,
  formatDate,
  formatDateTime,
  formatMinutes,
  getUploadLimits,
  Job,
  JOB_STATUS_LABELS,
  JOB_TYPE_LABELS,
  MEETING_STATUS_LABELS,
  MeetingDetail as MeetingDetailData,
  MeetingSpeaker,
  MINUTES_STATUS_LABELS,
  Member,
  MinuteVersion,
  MinutesSettings,
  RSVP_LABELS,
  SuggestedItems,
  toPersianDigits,
  Transcript,
  uploadMeetingAudio,
} from '@/lib/mgmt';

export default function MeetingDetailPage() {
  return <AppShell>{(bootstrap) => <MeetingDetailBody bootstrap={bootstrap} />}</AppShell>;
}

function MeetingDetailBody({ bootstrap }: { bootstrap: Bootstrap }) {
  const { meetingId } = useParams();
  const id = Number(meetingId);
  const navigate = useNavigate();

  const [detail, setDetail] = useState<MeetingDetailData | null>(null);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [transcript, setTranscript] = useState<Transcript | null>(null);
  const [speakers, setSpeakers] = useState<MeetingSpeaker[]>([]);
  const [members, setMembers] = useState<Member[]>([]);
  const [versions, setVersions] = useState<MinuteVersion[]>([]);
  const [error, setError] = useState('');
  const pollRef = useRef<number | null>(null);

  const loadDetail = useCallback(async () => {
    try {
      setDetail(await api.meetingDetail(id));
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت جزئیات جلسه ناموفق بود.'));
    }
  }, [id]);

  const loadJobs = useCallback(async () => {
    try {
      const data = await api.meetingJobs(id);
      setJobs(data.jobs);
      setTranscript(data.transcript);
      return data.jobs;
    } catch {
      return [] as Job[];
    }
  }, [id]);

  const loadSpeakers = useCallback(async () => {
    try {
      const data = await api.meetingSpeakers(id);
      setSpeakers(data.speakers);
    } catch {
      setSpeakers([]);
    }
  }, [id]);

  useEffect(() => {
    if (!Number.isFinite(id)) return;
    loadDetail();
    loadJobs();
    loadSpeakers();
    api
      .members()
      .then((data) => setMembers(data.members))
      .catch(() => setMembers([]));
  }, [id, loadDetail, loadJobs, loadSpeakers]);

  // پیگیری کارهای در جریان: هر ۶ ثانیه وضعیت صف بررسی می‌شود.
  useEffect(() => {
    const hasActive = jobs.some((job) => job.status === 'queued' || job.status === 'running');
    if (!hasActive) {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    if (pollRef.current) return;
    pollRef.current = window.setInterval(async () => {
      const fresh = await loadJobs();
      const stillActive = fresh.some(
        (job) => job.status === 'queued' || job.status === 'running',
      );
      if (!stillActive) {
        await loadDetail();
        await loadSpeakers();
        if (pollRef.current) {
          window.clearInterval(pollRef.current);
          pollRef.current = null;
        }
      }
    }, 6000);
    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [jobs, loadDetail, loadJobs, loadSpeakers]);

  const loadVersions = useCallback(async () => {
    try {
      const data = await api.minutesVersions(id);
      setVersions(data.items);
    } catch {
      setVersions([]);
    }
  }, [id]);

  if (error) {
    return (
      <Card>
        <CardContent className="space-y-3 py-6">
          <p className="text-sm text-destructive">{error}</p>
          <Button onClick={loadDetail}>تلاش دوباره</Button>
        </CardContent>
      </Card>
    );
  }

  if (!detail) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-24 w-full" />
        <Skeleton className="h-80 w-full" />
      </div>
    );
  }

  const { meeting, permissions } = detail;
  const canManage = permissions.can_manage;

  const handleDelete = async () => {
    try {
      await api.deleteMeeting(id);
      toast.success('جلسه حذف شد.');
      navigate('/meetings');
    } catch (err) {
      toast.error(errorMessage(err, 'حذف جلسه ناموفق بود.'));
    }
  };

  const downloadIcs = async () => {
    try {
      const content = await api.meetingIcs(id);
      const blob = new Blob([String(content)], { type: 'text/calendar;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `meeting-${id}.ics`;
      anchor.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت فایل تقویم ناموفق بود.'));
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-stretch justify-between gap-3 lg:flex-row lg:items-start">
        <div className="min-w-0 space-y-2">
          <h1 className="break-words">{meeting.title}</h1>
          <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="outline">{meeting.meeting_type}</Badge>
            <Badge variant={meeting.status === 'cancelled' ? 'destructive' : 'secondary'}>
              {MEETING_STATUS_LABELS[meeting.status] || meeting.status}
            </Badge>
            <span>{formatDateTime(meeting.starts_at)}</span>
            <span>• {toPersianDigits(meeting.duration_minutes)} دقیقه</span>
            <span>• دبیر: {meeting.secretary_name || '—'}</span>
          </div>
          {meeting.description && <p className="max-w-2xl text-sm">{meeting.description}</p>}
          {(meeting.location || meeting.online_url) && (
            <p className="text-sm text-muted-foreground">
              {meeting.location && <span>محل: {meeting.location}</span>}
              {meeting.online_url && (
                <a
                  href={meeting.online_url}
                  target="_blank"
                  rel="noreferrer"
                  className="mr-3 text-primary hover:underline"
                >
                  پیوند جلسهٔ برخط
                </a>
              )}
            </p>
          )}
        </div>
        {/* در موبایل دکمه‌های عملیات تمام‌عرض و لمس‌پذیر می‌شوند. */}
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-3 lg:flex lg:flex-wrap">
          <Button
            variant="outline"
            className="!bg-transparent min-h-11 gap-2"
            onClick={downloadIcs}
          >
            <CalendarDays className="h-4 w-4" />
            افزودن به تقویم
          </Button>
          <Link to={`/print/${id}`} className="w-full lg:w-auto">
            <Button variant="outline" className="!bg-transparent min-h-11 w-full gap-2">
              <Printer className="h-4 w-4" />
              نمای چاپ / PDF
            </Button>
          </Link>
          {canManage && (
            <Button variant="destructive" className="min-h-11 gap-2" onClick={handleDelete}>
              <Trash2 className="h-4 w-4" />
              حذف جلسه
            </Button>
          )}
        </div>
      </div>

      <RsvpBar detail={detail} onDone={loadDetail} />

      <Tabs defaultValue="agenda" dir="rtl">
        <TabsList className="flex w-full flex-nowrap justify-start overflow-x-auto md:flex-wrap">
          <TabsTrigger value="agenda">دستور جلسه و حضور</TabsTrigger>
          <TabsTrigger value="audio">صوت و رونویسی</TabsTrigger>
          <TabsTrigger value="minutes">صورتجلسه</TabsTrigger>
          <TabsTrigger value="decisions">مصوبات و اقدامات</TabsTrigger>
        </TabsList>

        <TabsContent value="agenda" className="mt-4 space-y-4">
          <AgendaAndAttendance
            detail={detail}
            members={members}
            canManage={canManage}
            onDone={loadDetail}
          />
          <MeetingAttachmentsCard meetingId={detail.meeting.id} canManage={canManage} />
        </TabsContent>

        <TabsContent value="audio" className="mt-4">
          <AudioAndTranscript
            detail={detail}
            jobs={jobs}
            transcript={transcript}
            speakers={speakers}
            canManage={canManage}
            quotaRemaining={bootstrap.quota.remaining_minutes}
            onDone={async () => {
              await loadDetail();
              await loadJobs();
              await loadSpeakers();
            }}
            onSpeakersChanged={loadSpeakers}
          />
        </TabsContent>

        <TabsContent value="minutes" className="mt-4">
          <MinutesPanel
            detail={detail}
            jobs={jobs}
            transcript={transcript}
            versions={versions}
            loadVersions={loadVersions}
            onDone={async () => {
              await loadDetail();
              await loadJobs();
            }}
          />
        </TabsContent>

        <TabsContent value="decisions" className="mt-4">
          <DecisionsPanel
            detail={detail}
            members={members}
            canManage={canManage}
            onDone={loadDetail}
          />
        </TabsContent>
      </Tabs>
    </div>
  );
}

/* ---------------------------------------------------------------- */

function RsvpBar({ detail, onDone }: { detail: MeetingDetailData; onDone: () => void }) {
  const [saving, setSaving] = useState(false);
  const current = detail.my_rsvp || 'pending';

  const submit = async (status: string) => {
    setSaving(true);
    try {
      await api.submitRsvp(detail.meeting.id, status);
      toast.success('پاسخ دعوت شما ثبت شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت پاسخ دعوت ناموفق بود.'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card>
      <CardContent className="flex flex-wrap items-center gap-3 py-4">
        <span className="text-sm font-medium">پاسخ شما به دعوت:</span>
        <Badge variant="secondary">{RSVP_LABELS[current] || current}</Badge>
        <div className="flex flex-wrap gap-2">
          {(['accepted', 'tentative', 'declined'] as const).map((status) => (
            <Button
              key={status}
              size="sm"
              variant={current === status ? 'default' : 'outline'}
              className={current === status ? '' : '!bg-transparent'}
              disabled={saving}
              onClick={() => submit(status)}
            >
              {RSVP_LABELS[status]}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function AgendaAndAttendance({
  detail,
  members,
  canManage,
  onDone,
}: {
  detail: MeetingDetailData;
  members: Member[];
  canManage: boolean;
  onDone: () => void;
}) {
  const [title, setTitle] = useState('');
  const [minutes, setMinutes] = useState('15');
  const [owner, setOwner] = useState('');
  const [attendance, setAttendance] = useState<Record<string, boolean>>({});
  const [selected, setSelected] = useState<number[]>(
    detail.participants.map((item) => Number(item.membership_id || 0)).filter(Boolean),
  );

  useEffect(() => {
    const next: Record<string, boolean> = {};
    detail.participants.forEach((item) => {
      next[String(item.id)] = Boolean(item.attended);
    });
    setAttendance(next);
    setSelected(
      detail.participants.map((item) => Number(item.membership_id || 0)).filter(Boolean),
    );
  }, [detail.participants]);

  const addAgenda = async () => {
    if (title.trim().length < 2) {
      toast.error('عنوان بند دستور جلسه را وارد کنید.');
      return;
    }
    try {
      await api.addAgenda(detail.meeting.id, {
        title: title.trim(),
        planned_minutes: Number(minutes) || 15,
        owner_name: owner.trim(),
        notes: '',
      });
      setTitle('');
      setOwner('');
      toast.success('بند دستور جلسه اضافه شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'افزودن بند ناموفق بود.'));
    }
  };

  const removeAgenda = async (itemId: number) => {
    try {
      await api.deleteAgenda(itemId);
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'حذف بند ناموفق بود.'));
    }
  };

  const saveAttendance = async () => {
    try {
      const result = await api.saveAttendance(detail.meeting.id, attendance);
      toast.success(
        `حضور ثبت شد: ${toPersianDigits(result.present)} از ${toPersianDigits(result.total)} نفر`,
      );
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت حضور ناموفق بود.'));
    }
  };

  const saveParticipants = async () => {
    try {
      await api.setParticipants(detail.meeting.id, selected);
      toast.success('فهرست دعوت‌شدگان به‌روزرسانی شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'به‌روزرسانی دعوت‌شدگان ناموفق بود.'));
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">دستور جلسه</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.agenda.length === 0 && (
            <p className="text-sm text-muted-foreground">بندی برای دستور جلسه ثبت نشده است.</p>
          )}
          <ol className="space-y-2">
            {detail.agenda.map((item) => (
              <li
                key={item.id}
                className="flex items-start justify-between gap-3 rounded-md border border-border p-3"
              >
                <div>
                  <p className="text-sm font-medium">
                    {toPersianDigits(item.position)}. {item.title}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {toPersianDigits(item.planned_minutes)} دقیقه
                    {item.owner_name && ` • ارائه‌دهنده: ${item.owner_name}`}
                  </p>
                </div>
                {canManage && (
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="حذف بند"
                    onClick={() => removeAgenda(item.id)}
                  >
                    <Trash2 className="h-4 w-4" />
                  </Button>
                )}
              </li>
            ))}
          </ol>

          {canManage && (
            <>
              <Separator />
              <div className="grid gap-2 sm:grid-cols-[2fr_1fr_1fr_auto]">
                <Input
                  value={title}
                  onChange={(event) => setTitle(event.target.value)}
                  placeholder="عنوان بند"
                />
                <Input
                  type="number"
                  min={5}
                  value={minutes}
                  onChange={(event) => setMinutes(event.target.value)}
                  placeholder="دقیقه"
                />
                <Input
                  value={owner}
                  onChange={(event) => setOwner(event.target.value)}
                  placeholder="ارائه‌دهنده"
                />
                <Button className="gap-2" onClick={addAgenda}>
                  <Plus className="h-4 w-4" />
                  افزودن
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">دعوت‌شدگان و حضور</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.participants.length === 0 && (
            <p className="text-sm text-muted-foreground">کسی به این جلسه دعوت نشده است.</p>
          )}
          <ul className="space-y-2">
            {detail.participants.map((participant) => (
              <li
                key={participant.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
              >
                <div>
                  <p className="text-sm font-medium">{participant.full_name}</p>
                  <p className="text-xs text-muted-foreground">
                    {RSVP_LABELS[participant.rsvp_status] || participant.rsvp_status}
                  </p>
                </div>
                <label className="flex items-center gap-2 text-sm">
                  <Checkbox
                    checked={Boolean(attendance[String(participant.id)])}
                    disabled={!canManage}
                    onCheckedChange={(value) =>
                      setAttendance((prev) => ({
                        ...prev,
                        [String(participant.id)]: Boolean(value),
                      }))
                    }
                  />
                  حاضر بود
                </label>
              </li>
            ))}
          </ul>

          {canManage && (
            <>
              <Button size="sm" onClick={saveAttendance}>
                ثبت حضور
              </Button>
              <Separator />
              <div className="space-y-2">
                <Label>ویرایش فهرست دعوت‌شدگان</Label>
                <div className="grid max-h-40 gap-2 overflow-y-auto rounded-md border border-border p-3 sm:grid-cols-2">
                  {members.map((member) => (
                    <label key={member.id} className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={selected.includes(member.id)}
                        onCheckedChange={() =>
                          setSelected((prev) =>
                            prev.includes(member.id)
                              ? prev.filter((value) => value !== member.id)
                              : [...prev, member.id],
                          )
                        }
                      />
                      {member.full_name}
                    </label>
                  ))}
                </div>
                <Button size="sm" variant="outline" className="!bg-transparent" onClick={saveParticipants}>
                  ذخیرهٔ دعوت‌شدگان
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function JobRow({ job, onRetry }: { job: Job; onRetry: (job: Job) => void }) {
  const isActive = job.status === 'queued' || job.status === 'running';
  // مصرف این کار برای نمایش شفاف به کاربر — واحد یکپارچه: توکن ویدارا
  // (هر دقیقهٔ رونویسی = ۱ توکن، هر سنت مدل زبانی = ۱ توکن)
  const result = (job.result || {}) as Record<string, unknown>;
  const minutesCharged = Number(result.minutes_charged || 0);
  const costCents = Number(result.cost_cents || 0);
  const tokensCharged = minutesCharged + costCents;
  const hasUsage = tokensCharged > 0;
  return (
    <div className="rounded-md border border-border p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-sm font-medium">
          {JOB_TYPE_LABELS[job.job_type] || job.job_type}
        </span>
        <Badge variant={job.status === 'failed' ? 'destructive' : 'secondary'}>
          {JOB_STATUS_LABELS[job.status] || job.status}
        </Badge>
      </div>
      {isActive && <Progress value={job.progress} className="mt-2 h-2" />}
      <p className="mt-2 text-xs text-muted-foreground">
        تلاش {toPersianDigits(job.attempts)} از {toPersianDigits(job.max_attempts)} • ثبت‌کننده:{' '}
        {job.created_by_name || '—'} • {formatDateTime(job.created_at)}
      </p>
      {hasUsage && job.status === 'succeeded' && (
        <p className="mt-1 text-xs font-medium text-primary">
          مصرف این کار: {toPersianDigits(tokensCharged)} توکن ویدارا
        </p>
      )}
      {job.error_message && <p className="mt-1 text-xs text-destructive">{job.error_message}</p>}
      {job.status === 'failed' && (
        <Button size="sm" variant="outline" className="!bg-transparent mt-2 gap-2" onClick={() => onRetry(job)}>
          <RefreshCw className="h-4 w-4" />
          تلاش دوباره
        </Button>
      )}
    </div>
  );
}

function AudioAndTranscript({
  detail,
  jobs,
  transcript,
  speakers,
  canManage,
  quotaRemaining,
  onDone,
  onSpeakersChanged,
}: {
  detail: MeetingDetailData;
  jobs: Job[];
  transcript: Transcript | null;
  speakers: MeetingSpeaker[];
  canManage: boolean;
  quotaRemaining: number;
  onDone: () => Promise<void>;
  onSpeakersChanged: () => Promise<void>;
}) {
  const [file, setFile] = useState<File | null>(null);
  const [consent, setConsent] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [busyId, setBusyId] = useState<number | null>(null);
  /** کلیپ آمادهٔ پخش هر گوینده (شناسهٔ گوینده → نشانی امضاشده). */
  const [clipUrls, setClipUrls] = useState<Record<number, string>>({});
  const [loadingClip, setLoadingClip] = useState<number | null>(null);
  /** نام در حال ویرایش هر گوینده (تا پیش از ذخیره). */
  const [nameDrafts, setNameDrafts] = useState<Record<number, string>>({});
  const [savingName, setSavingName] = useState<number | null>(null);
  /**
   * درصد پیشرفت بارگذاری صوت.
   *
   * `null` یعنی بارگذاری در جریان نیست. فایل صوتی معمولاً چند ده مگابایت است، پس
   * بدون این نوار کاربر هیچ نشانه‌ای از پیشرفت نمی‌بیند و تصور می‌کند برنامه هنگ کرده.
   */
  const [audioPercent, setAudioPercent] = useState<number | null>(null);
  /** کنترل‌گر لغو تا کاربر بتواند بارگذاری طولانی را متوقف کند. */
  const [audioAbort, setAudioAbort] = useState<AbortController | null>(null);
  const limits = getUploadLimits();

  const upload = async () => {
    if (!file) {
      toast.error('یک فایل صوتی انتخاب کنید.');
      return;
    }
    if (!consent) {
      toast.error('برای بارگذاری صوت، تأیید اطلاع‌رسانی به حاضران لازم است.');
      return;
    }
    const controller = new AbortController();
    setAudioAbort(controller);
    setUploading(true);
    // از صفر شروع می‌شود تا نوار بی‌درنگ (پیش از رسیدن اولین رویداد شبکه) دیده شود.
    setAudioPercent(0);
    try {
      await uploadMeetingAudio(detail.meeting.id, file, consent, {
        signal: controller.signal,
        onProgress: (progress) => setAudioPercent(progress.percent),
      });
      toast.success('فایل صوتی ثبت شد. اکنون می‌توانید رونویسی را آغاز کنید.');
      setFile(null);
      setConsent(false);
      setAudioPercent(null);
      await onDone();
    } catch (err) {
      setAudioPercent(null);
      if (controller.signal.aborted) {
        toast.info('بارگذاری فایل صوتی لغو شد.');
      } else {
        toast.error(errorMessage(err, 'بارگذاری فایل صوتی ناموفق بود.'));
      }
    } finally {
      setAudioAbort(null);
      setUploading(false);
    }
  };

  const startTranscribe = async (recordingId: number) => {
    setBusyId(recordingId);
    try {
      await api.startTranscribe(recordingId);
      toast.success('کار رونویسی در صف قرار گرفت. وضعیت آن به‌صورت خودکار به‌روزرسانی می‌شود.');
      await onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'آغاز رونویسی ناموفق بود.'));
    } finally {
      setBusyId(null);
    }
  };

  const play = async (recordingId: number) => {
    try {
      const data = await api.recordingPlayUrl(recordingId);
      window.open(data.download_url, '_blank', 'noreferrer');
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت پیوند پخش ناموفق بود.'));
    }
  };

  const removeRecording = async (recordingId: number) => {
    try {
      await api.deleteRecording(recordingId);
      toast.success('فایل صوتی حذف شد.');
      await onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'حذف فایل صوتی ناموفق بود.'));
    }
  };

  const retry = async (job: Job) => {
    try {
      await api.retryJob(job.id);
      toast.success('کار برای اجرای دوباره ثبت شد.');
      await onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'اجرای دوبارهٔ کار ناموفق بود.'));
    }
  };

  /** نمایش زمان قطعه به شکل دقیقه:ثانیه (فارسی). */
  const formatMs = (ms?: number) => {
    if (ms === undefined || ms === null) return '--:--';
    const total = Math.max(Math.floor(ms / 1000), 0);
    const minutes = Math.floor(total / 60);
    const seconds = total % 60;
    return `${toPersianDigits(String(minutes).padStart(2, '0'))}:${toPersianDigits(
      String(seconds).padStart(2, '0'),
    )}`;
  };

  /** نام قابل نمایش هر گوینده: نام کاربر یا برچسب پیش‌فرض. */
  const speakerNameOf = (key?: string) => {
    if (!key) return '';
    const speaker = speakers.find((item) => item.speaker_key === key);
    return speaker?.display_name || speaker?.default_label || key;
  };

  const segments = transcript?.segments || [];
  const hasSpeakerSegments = segments.some((segment) => Boolean(segment.speaker));

  const playClip = async (speakerId: number) => {
    setLoadingClip(speakerId);
    try {
      const data = await api.speakerClipUrl(speakerId);
      setClipUrls((prev) => ({ ...prev, [speakerId]: data.clip_url }));
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت نمونهٔ صدای گوینده ناموفق بود.'));
    } finally {
      setLoadingClip(null);
    }
  };

  const saveSpeakerName = async (speakerId: number) => {
    const name = (nameDrafts[speakerId] ?? '').trim();
    if (!name) {
      toast.error('نام گوینده را وارد کنید.');
      return;
    }
    setSavingName(speakerId);
    try {
      await api.renameSpeaker(speakerId, name);
      toast.success('نام گوینده ذخیره شد.');
      await onSpeakersChanged();
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ نام گوینده ناموفق بود.'));
    } finally {
      setSavingName(null);
    }
  };

  const transcribeJobs = jobs.filter((job) => job.job_type === 'transcribe');

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">فایل‌های صوتی جلسه</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.recordings.length === 0 && (
            <p className="text-sm text-muted-foreground">
              فایلی بارگذاری نشده است. صوت در فضای خصوصی نگه‌داری می‌شود و پس از پایان مهلت
              نگه‌داری پاک می‌شود.
            </p>
          )}
          {detail.recordings.map((recording) => (
            <div key={recording.id} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-medium">{recording.file_name}</span>
                <Badge variant="outline">{formatMinutes(recording.duration_seconds)}</Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                حجم: {toPersianDigits(Math.round(recording.size_bytes / 1024 / 1024))} مگابایت •
                بارگذاری: {recording.uploaded_by_name || '—'} • مهلت نگه‌داری:{' '}
                {formatDate(recording.purge_after)}
              </p>
              <div className="mt-2 flex flex-wrap gap-2">
                <Button size="sm" variant="outline" className="!bg-transparent gap-2" onClick={() => play(recording.id)}>
                  <Download className="h-4 w-4" />
                  پخش / دریافت
                </Button>
                {canManage && (
                  <>
                    <Button
                      size="sm"
                      className="gap-2"
                      disabled={busyId === recording.id}
                      onClick={() => startTranscribe(recording.id)}
                    >
                      {busyId === recording.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Mic className="h-4 w-4" />
                      )}
                      رونویسی خودکار
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => removeRecording(recording.id)}
                    >
                      حذف
                    </Button>
                  </>
                )}
              </div>
            </div>
          ))}

          {canManage && (
            <>
              <Separator />
              <div className="space-y-3">
                <Label htmlFor="audio-file">بارگذاری فایل صوتی</Label>
                <Input
                  id="audio-file"
                  type="file"
                  accept="audio/*"
                  onChange={(event) => setFile(event.target.files?.[0] ?? null)}
                />
                <label className="flex items-start gap-2 text-xs text-muted-foreground">
                  <Checkbox
                    checked={consent}
                    onCheckedChange={(value) => setConsent(Boolean(value))}
                  />
                  <span>
                    تأیید می‌کنم به حاضران جلسه اطلاع داده شده که صدای جلسه ضبط و برای تهیهٔ
                    صورتجلسه رونویسی می‌شود.
                  </span>
                </label>
                <p className="text-xs text-muted-foreground">
                  توکن ویدارای باقی‌مانده: {toPersianDigits(quotaRemaining)} توکن • سقف مدت صوت:{' '}
                  {toPersianDigits(limits.maxAudioMinutes)} دقیقه • سقف حجم:{' '}
                  {toPersianDigits(limits.maxAudioMb)} مگابایت
                </p>

                {/* نوار پیشرفت واقعی بارگذاری صوت با درصد و دکمهٔ لغو */}
                {audioPercent !== null && (
                  <div className="space-y-1 rounded-md border border-border p-3">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="truncate font-medium">{file?.name || 'فایل صوتی'}</span>
                      <span className="shrink-0 text-muted-foreground">
                        {toPersianDigits(audioPercent)}٪
                      </span>
                    </div>
                    <Progress value={audioPercent} className="h-2 w-full" />
                    <p className="text-[11px] text-muted-foreground">
                      {audioPercent >= 100
                        ? 'بارگذاری کامل شد؛ در حال ثبت اطلاعات فایل…'
                        : 'در حال ارسال فایل صوتی به فضای خصوصی سازمان…'}
                    </p>
                  </div>
                )}

                <div className="flex flex-wrap gap-2">
                  <Button onClick={upload} disabled={uploading}>
                    {uploading ? 'در حال بارگذاری…' : 'بارگذاری صوت'}
                  </Button>
                  {uploading && audioAbort && (
                    <Button
                      variant="outline"
                      className="!bg-transparent"
                      onClick={() => audioAbort.abort()}
                    >
                      لغو بارگذاری
                    </Button>
                  )}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">وضعیت کارهای رونویسی</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {transcribeJobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">کاری ثبت نشده است.</p>
            ) : (
              transcribeJobs.map((job) => <JobRow key={job.id} job={job} onRetry={retry} />)
            )}
          </CardContent>
        </Card>

        {speakers.length > 0 && (
          <Card>
            <CardHeader>
              <CardTitle className="text-base">گوینده‌های جلسه</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <p className="text-xs text-muted-foreground">
                برای تشخیص اینکه هر گوینده کیست، چند ثانیه از صدای او را بشنوید و نامش را وارد
                کنید. نام‌ها در متن رونویسی جایگزین برچسب گوینده می‌شوند.
              </p>
              {speakers.map((speaker) => {
                const draft = nameDrafts[speaker.id] ?? speaker.display_name ?? '';
                const clipUrl = clipUrls[speaker.id];
                return (
                  <div key={speaker.id} className="rounded-md border border-border p-3">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <span className="text-sm font-medium">
                        {speakerNameOf(speaker.speaker_key)}
                      </span>
                      <span className="text-xs text-muted-foreground">
                        {toPersianDigits(speaker.segment_count)} قطعه · {formatMs(speaker.total_ms)}{' '}
                        صحبت
                      </span>
                    </div>
                    {canManage && (
                      <div className="mt-2 flex flex-wrap items-center gap-2">
                        <Input
                          value={draft}
                          placeholder={speaker.default_label}
                          className="h-8 max-w-xs text-sm"
                          onChange={(event) =>
                            setNameDrafts((prev) => ({
                              ...prev,
                              [speaker.id]: event.target.value,
                            }))
                          }
                        />
                        <Button
                          variant="outline"
                          size="sm"
                          disabled={savingName === speaker.id || !draft.trim()}
                          onClick={() => saveSpeakerName(speaker.id)}
                        >
                          {savingName === speaker.id ? 'در حال ذخیره…' : 'ذخیرهٔ نام'}
                        </Button>
                      </div>
                    )}
                    <div className="mt-2 flex flex-wrap items-center gap-2">
                      <Button
                        variant="outline"
                        size="sm"
                        disabled={loadingClip === speaker.id}
                        onClick={() => playClip(speaker.id)}
                      >
                        {loadingClip === speaker.id
                          ? 'در حال ساخت نمونه…'
                          : clipUrl
                            ? 'نمونهٔ صدا'
                            : 'شنیدن نمونهٔ صدا'}
                      </Button>
                      {clipUrl && <audio controls src={clipUrl} className="h-9 min-w-0 flex-1" />}
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        )}

        <Card>
          <CardHeader>
            <CardTitle className="text-base">متن رونویسی</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {!transcript ? (
              <p className="text-sm text-muted-foreground">
                هنوز رونویسی‌ای برای این جلسه ثبت نشده است.
              </p>
            ) : (
              <>
                <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                  <Badge variant="outline">{transcript.provider}</Badge>
                  <span>مدت: {formatMinutes(transcript.duration_seconds)}</span>
                  {transcript.known_word_ratio !== null && (
                    <span>
                      نسبت واژه‌های شناخته‌شده:{' '}
                      {toPersianDigits(Math.round((transcript.known_word_ratio || 0) * 100))}٪
                    </span>
                  )}
                </div>
                {transcript.known_word_ratio !== null && transcript.known_word_ratio < 0.8 && (
                  <p className="rounded-md bg-accent p-2 text-xs text-accent-foreground">
                    کیفیت صوت پایین به نظر می‌رسد؛ پیش از تأیید صورتجلسه، متن را با دقت بازبینی
                    کنید.
                  </p>
                )}
                {hasSpeakerSegments ? (
                  <div className="max-h-96 space-y-2 overflow-y-auto rounded-md border border-border p-3">
                    {segments.map((segment, index) => (
                      <div key={index} className="text-sm leading-7">
                        <span className="me-2 inline-flex items-center gap-1 align-top">
                          <Badge variant="secondary" className="px-1.5 py-0 text-[11px]">
                            {speakerNameOf(segment.speaker) || 'بدون گوینده'}
                          </Badge>
                          <span className="text-xs text-muted-foreground">
                            {formatMs(segment.start_ms)}
                          </span>
                        </span>
                        <span className="whitespace-pre-wrap">{segment.text}</span>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="max-h-72 overflow-y-auto whitespace-pre-wrap rounded-md border border-border p-3 text-sm leading-7">
                    {transcript.full_text || 'متنی ثبت نشده است.'}
                  </div>
                )}
              </>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function MinutesPanel({
  detail,
  jobs,
  transcript,
  versions,
  loadVersions,
  onDone,
}: {
  detail: MeetingDetailData;
  jobs: Job[];
  transcript: Transcript | null;
  versions: MinuteVersion[];
  loadVersions: () => Promise<void>;
  onDone: () => Promise<void>;
}) {
  const minutes = detail.minutes;
  const [body, setBody] = useState(minutes?.body_markdown || '');
  const [summary, setSummary] = useState(minutes?.summary || '');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);

  useEffect(() => {
    setBody(detail.minutes?.body_markdown || '');
    setSummary(detail.minutes?.summary || '');
  }, [detail.minutes]);

  const status = minutes?.status || 'draft';
  const canManage = detail.permissions.can_manage;
  const canApprove = detail.permissions.can_approve;
  const isLocked = status === 'locked';
  const minutesJobs = jobs.filter((job) => job.job_type === 'minutes_draft');

  const runAction = async (fn: () => Promise<unknown>, message: string) => {
    setBusy(true);
    try {
      await fn();
      toast.success(message);
      setNote('');
      await onDone();
    } catch (err) {
      toast.error(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="grid gap-4 lg:grid-cols-3">
      {settingsOpen && (
        <MinutesSettingsDialog
          meetingId={detail.meeting.id}
          onClose={() => setSettingsOpen(false)}
        />
      )}
      <Card className="lg:col-span-2">
        <CardHeader>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <CardTitle className="text-base">متن صورتجلسه</CardTitle>
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={isLocked ? 'default' : 'secondary'}>
                {MINUTES_STATUS_LABELS[status] || status}
              </Badge>
              {minutes && (
                <Badge variant="outline">
                  نسخهٔ {toPersianDigits(minutes.current_version)}
                </Badge>
              )}
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-3">
          {canManage && !isLocked && (
            <div className="space-y-2">
              <Label htmlFor="minutes-summary">خلاصهٔ جلسه</Label>
              <Textarea
                id="minutes-summary"
                value={summary}
                onChange={(event) => setSummary(event.target.value)}
                rows={2}
              />
            </div>
          )}
          <div className="space-y-2">
            <Label htmlFor="minutes-body">متن کامل</Label>
            <Textarea
              id="minutes-body"
              value={body}
              onChange={(event) => setBody(event.target.value)}
              rows={16}
              readOnly={!canManage || isLocked}
              placeholder="متن صورتجلسه را وارد کنید یا از رونویسی، پیش‌نویس هوشمند بسازید."
              className="leading-8"
            />
          </div>

          {canManage && !isLocked && (
            <div className="space-y-2">
              <Label htmlFor="minutes-note">یادداشت تغییر / پیام گردش کار</Label>
              <Input
                id="minutes-note"
                value={note}
                onChange={(event) => setNote(event.target.value)}
                placeholder="مثال: اصلاح بند سه پس از بازبینی"
              />
            </div>
          )}

          <div className="flex flex-wrap gap-2">
            {canManage && !isLocked && (
              <Button
                disabled={busy || body.trim().length < 10}
                onClick={() =>
                  runAction(
                    () =>
                      api.saveMinutes({
                        meeting_id: detail.meeting.id,
                        body_markdown: body,
                        summary,
                        change_note: note,
                      }),
                    'صورتجلسه ذخیره و نسخهٔ تازه ثبت شد.',
                  )
                }
              >
                ذخیره و ثبت نسخه
              </Button>
            )}
            {canManage && !isLocked && (
              <>
                <Button
                  variant="outline"
                  className="!bg-transparent gap-2"
                  disabled={busy || !transcript}
                  onClick={() =>
                    runAction(
                      () => api.startMinutesDraft(detail.meeting.id),
                      'ساخت پیش‌نویس هوشمند در صف قرار گرفت.',
                    )
                  }
                >
                  <Sparkles className="h-4 w-4" />
                  {detail.minutes
                    ? 'تولید مجدد پیش‌نویس و مصوبات/اقدامات'
                    : 'پیش‌نویس هوشمند از رونویسی'}
                </Button>
                <Button
                  variant="outline"
                  className="!bg-transparent gap-2"
                  disabled={busy}
                  onClick={() => setSettingsOpen(true)}
                >
                  <Settings2 className="h-4 w-4" />
                  تنظیمات تولید
                </Button>
              </>
            )}
            {canManage && status === 'draft' && (
              <Button
                variant="secondary"
                disabled={busy}
                onClick={() =>
                  runAction(
                    () => api.submitMinutesForReview(detail.meeting.id, note),
                    'صورتجلسه برای تأیید ارسال شد.',
                  )
                }
              >
                ارسال برای تأیید
              </Button>
            )}
            {canApprove && status === 'in_review' && (
              <>
                <Button
                  disabled={busy}
                  onClick={() =>
                    runAction(
                      () => api.approveMinutes(detail.meeting.id, note),
                      'صورتجلسه تأیید شد.',
                    )
                  }
                >
                  تأیید صورتجلسه
                </Button>
                <Button
                  variant="destructive"
                  disabled={busy}
                  onClick={() =>
                    runAction(
                      () => api.rejectMinutes(detail.meeting.id, note),
                      'صورتجلسه برای اصلاح بازگردانده شد.',
                    )
                  }
                >
                  بازگشت برای اصلاح
                </Button>
              </>
            )}
            {canApprove && status === 'approved' && (
              <Button
                disabled={busy}
                onClick={() =>
                  runAction(
                    () => api.lockMinutes(detail.meeting.id, note),
                    'صورتجلسه قفل نهایی شد.',
                  )
                }
              >
                قفل نهایی
              </Button>
            )}
            <Link to={`/print/${detail.meeting.id}`}>
              <Button variant="outline" className="!bg-transparent gap-2">
                <FileText className="h-4 w-4" />
                نمای چاپ
              </Button>
            </Link>
            <Button
              variant="outline"
              className="!bg-transparent gap-2"
              disabled={busy || !minutes}
              onClick={() =>
                runAction(
                  () => downloadMinutesDocx(detail.meeting.id),
                  'فایل Word صورتجلسه دانلود شد.',
                )
              }
            >
              <Download className="h-4 w-4" />
              دانلود فایل Word
            </Button>
          </div>

          {!transcript && canManage && (
            <p className="text-xs text-muted-foreground">
              برای ساخت پیش‌نویس هوشمند، نخست فایل صوتی را بارگذاری و رونویسی کنید.
            </p>
          )}
          {minutes?.approved_by_name && (
            <p className="text-xs text-muted-foreground">
              تأییدکننده: {minutes.approved_by_name} • {formatDateTime(minutes.approved_at)}
            </p>
          )}
        </CardContent>
      </Card>

      <div className="space-y-4">
        <Card>
          <CardHeader>
            <CardTitle className="text-base">کارهای پیش‌نویس هوشمند</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            {minutesJobs.length === 0 ? (
              <p className="text-sm text-muted-foreground">کاری ثبت نشده است.</p>
            ) : (
              minutesJobs.map((job) => (
                <JobRow
                  key={job.id}
                  job={job}
                  onRetry={async (target) => {
                    await api.retryJob(target.id);
                    await onDone();
                  }}
                />
              ))
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0">
            <CardTitle className="text-base">تاریخچهٔ نسخه‌ها</CardTitle>
            <Button size="sm" variant="ghost" onClick={loadVersions}>
              بارگذاری
            </Button>
          </CardHeader>
          <CardContent className="space-y-2">
            {versions.length === 0 ? (
              <p className="text-sm text-muted-foreground">
                برای دیدن تاریخچه، دکمهٔ بارگذاری را بزنید.
              </p>
            ) : (
              versions.map((version) => (
                <div key={version.id} className="rounded-md border border-border p-3">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium">
                      نسخهٔ {toPersianDigits(version.version)}
                    </span>
                    <Badge variant="outline">
                      {MINUTES_STATUS_LABELS[version.status_at_version] ||
                        version.status_at_version}
                    </Badge>
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {version.changed_by_name || '—'} • {formatDateTime(version.created_at)}
                  </p>
                  {version.change_note && (
                    <p className="mt-1 text-xs">{version.change_note}</p>
                  )}
                </div>
              ))
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

function DecisionsPanel({
  detail,
  members,
  canManage,
  onDone,
}: {
  detail: MeetingDetailData;
  members: Member[];
  canManage: boolean;
  onDone: () => void;
}) {
  const [decisionTitle, setDecisionTitle] = useState('');
  const [decisionDesc, setDecisionDesc] = useState('');
  const [actionTitle, setActionTitle] = useState('');
  const [actionOwner, setActionOwner] = useState('none');
  const [actionDue, setActionDue] = useState('');
  const [actionDecision, setActionDecision] = useState('none');

  // پیشنهادهای هوش مصنوعی؛ تا زمانی که کاربر «افزودن» را نزند هیچ‌چیز ذخیره نمی‌شود.
  const [suggesting, setSuggesting] = useState(false);
  const [suggested, setSuggested] = useState<SuggestedItems | null>(null);
  const [acceptingKey, setAcceptingKey] = useState('');

  const fetchSuggestions = async () => {
    setSuggesting(true);
    try {
      const data = await api.suggestMeetingItems(detail.meeting.id);
      setSuggested(data);
      if (data.decisions.length === 0 && data.actions.length === 0) {
        toast.info('برای این جلسه پیشنهادی استخراج نشد؛ متن صورتجلسه یا رونویسی را کامل‌تر کنید.');
      } else {
        toast.success(
          `${toPersianDigits(data.decisions.length)} مصوبه و ${toPersianDigits(
            data.actions.length,
          )} اقدام پیشنهاد شد. پیش از ثبت، آن‌ها را بازبینی کنید.`,
        );
      }
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت پیشنهاد هوش مصنوعی ناموفق بود.'));
    } finally {
      setSuggesting(false);
    }
  };

  /** ویرایش درجای یک پیشنهاد مصوبه پیش از ثبت. */
  const editSuggestedDecision = (index: number, patch: { title?: string; description?: string }) => {
    setSuggested((current) => {
      if (!current) return current;
      const decisions = current.decisions.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      );
      return { ...current, decisions };
    });
  };

  /** ویرایش درجای یک پیشنهاد اقدام پیش از ثبت. */
  const editSuggestedAction = (
    index: number,
    patch: { title?: string; owner_membership_id?: number | null; due_date?: string },
  ) => {
    setSuggested((current) => {
      if (!current) return current;
      const actions = current.actions.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      );
      return { ...current, actions };
    });
  };

  const acceptSuggestedDecision = async (index: number) => {
    const item = suggested?.decisions[index];
    if (!item) return;
    if (item.title.trim().length < 3) {
      toast.error('عنوان مصوبه باید حداقل سه نویسه باشد.');
      return;
    }
    setAcceptingKey(`decision-${index}`);
    try {
      await api.createDecision({
        meeting_id: detail.meeting.id,
        title: item.title.trim(),
        description: item.description.trim(),
        source: 'ai',
      });
      setSuggested((current) =>
        current
          ? { ...current, decisions: current.decisions.filter((_, pos) => pos !== index) }
          : current,
      );
      toast.success('مصوبهٔ پیشنهادی ثبت شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت مصوبهٔ پیشنهادی ناموفق بود.'));
    } finally {
      setAcceptingKey('');
    }
  };

  const acceptSuggestedAction = async (index: number) => {
    const item = suggested?.actions[index];
    if (!item) return;
    if (item.title.trim().length < 3) {
      toast.error('عنوان اقدام باید حداقل سه نویسه باشد.');
      return;
    }
    setAcceptingKey(`action-${index}`);
    try {
      await api.createAction({
        meeting_id: detail.meeting.id,
        decision_id: null,
        title: item.title.trim(),
        description: item.description.trim(),
        owner_membership_id: item.owner_membership_id,
        due_date: item.due_date || '',
        source: 'ai',
      });
      setSuggested((current) =>
        current
          ? { ...current, actions: current.actions.filter((_, pos) => pos !== index) }
          : current,
      );
      toast.success('اقدام پیشنهادی ثبت و به مسئول آن اطلاع داده شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت اقدام پیشنهادی ناموفق بود.'));
    } finally {
      setAcceptingKey('');
    }
  };

  const addDecision = async () => {
    if (decisionTitle.trim().length < 3) {
      toast.error('عنوان مصوبه را وارد کنید.');
      return;
    }
    try {
      await api.createDecision({
        meeting_id: detail.meeting.id,
        title: decisionTitle.trim(),
        description: decisionDesc.trim(),
      });
      setDecisionTitle('');
      setDecisionDesc('');
      toast.success('مصوبه ثبت شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت مصوبه ناموفق بود.'));
    }
  };

  const addAction = async () => {
    if (actionTitle.trim().length < 3) {
      toast.error('عنوان اقدام را وارد کنید.');
      return;
    }
    try {
      await api.createAction({
        meeting_id: detail.meeting.id,
        decision_id: actionDecision === 'none' ? null : Number(actionDecision),
        title: actionTitle.trim(),
        description: '',
        owner_membership_id: actionOwner === 'none' ? null : Number(actionOwner),
        due_date: actionDue,
      });
      setActionTitle('');
      setActionDue('');
      toast.success('اقدام ثبت و به مسئول آن اطلاع داده شد.');
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت اقدام ناموفق بود.'));
    }
  };

  const hasSuggestions =
    !!suggested && (suggested.decisions.length > 0 || suggested.actions.length > 0);

  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {canManage && (
        <Card className="lg:col-span-2">
          <CardHeader>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <CardTitle className="text-base">پیشنهاد هوشمند مصوبات و اقدامات</CardTitle>
              <Button
                variant="outline"
                className="gap-2"
                disabled={suggesting}
                onClick={fetchSuggestions}
              >
                {suggesting ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Sparkles className="h-4 w-4" />
                )}
                {suggesting ? 'در حال استخراج…' : 'دریافت پیشنهاد'}
              </Button>
            </div>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-xs text-muted-foreground">
              پیشنهادها از متن صورتجلسه و رونویسی استخراج می‌شوند. هیچ موردی تا زمانی که خودتان
              «افزودن» را نزنید ذخیره نمی‌شود؛ پیش از ثبت می‌توانید متن و مسئول و مهلت را اصلاح کنید.
            </p>

            {!hasSuggestions && !suggesting && (
              <p className="text-sm text-muted-foreground">
                {suggested
                  ? 'موردی برای پیشنهاد یافت نشد.'
                  : 'برای دیدن پیشنهادها دکمهٔ بالا را بزنید.'}
              </p>
            )}

            {hasSuggestions && suggested && (
              <div className="grid gap-4 lg:grid-cols-2">
                <div className="space-y-3">
                  <p className="text-sm font-medium">
                    مصوبات پیشنهادی ({toPersianDigits(suggested.decisions.length)})
                  </p>
                  {suggested.decisions.length === 0 && (
                    <p className="text-xs text-muted-foreground">مصوبهٔ پیشنهادی باقی نمانده است.</p>
                  )}
                  {suggested.decisions.map((item, index) => (
                    <div
                      key={`suggested-decision-${index}`}
                      className="space-y-2 rounded-md border border-dashed border-border p-3"
                    >
                      <Input
                        value={item.title}
                        onChange={(event) =>
                          editSuggestedDecision(index, { title: event.target.value })
                        }
                        placeholder="عنوان مصوبهٔ پیشنهادی"
                      />
                      <Textarea
                        value={item.description}
                        onChange={(event) =>
                          editSuggestedDecision(index, { description: event.target.value })
                        }
                        rows={2}
                        placeholder="شرح مصوبه"
                      />
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          className="gap-2"
                          disabled={acceptingKey === `decision-${index}`}
                          onClick={() => acceptSuggestedDecision(index)}
                        >
                          {acceptingKey === `decision-${index}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Plus className="h-4 w-4" />
                          )}
                          افزودن به مصوبات
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setSuggested((current) =>
                              current
                                ? {
                                    ...current,
                                    decisions: current.decisions.filter((_, pos) => pos !== index),
                                  }
                                : current,
                            )
                          }
                        >
                          رد پیشنهاد
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>

                <div className="space-y-3">
                  <p className="text-sm font-medium">
                    اقدامات پیشنهادی ({toPersianDigits(suggested.actions.length)})
                  </p>
                  {suggested.actions.length === 0 && (
                    <p className="text-xs text-muted-foreground">اقدام پیشنهادی باقی نمانده است.</p>
                  )}
                  {suggested.actions.map((item, index) => (
                    <div
                      key={`suggested-action-${index}`}
                      className="space-y-2 rounded-md border border-dashed border-border p-3"
                    >
                      <Input
                        value={item.title}
                        onChange={(event) =>
                          editSuggestedAction(index, { title: event.target.value })
                        }
                        placeholder="عنوان اقدام پیشنهادی"
                      />
                      <div className="grid gap-2 sm:grid-cols-2">
                        <Select
                          value={
                            item.owner_membership_id ? String(item.owner_membership_id) : 'none'
                          }
                          onValueChange={(value) =>
                            editSuggestedAction(index, {
                              owner_membership_id: value === 'none' ? null : Number(value),
                            })
                          }
                        >
                          <SelectTrigger>
                            <SelectValue placeholder="مسئول" />
                          </SelectTrigger>
                          <SelectContent>
                            <SelectItem value="none">بدون مسئول</SelectItem>
                            {members.map((member) => (
                              <SelectItem key={member.id} value={String(member.id)}>
                                {member.full_name}
                              </SelectItem>
                            ))}
                          </SelectContent>
                        </Select>
                        <JalaliDateTimePicker
                          value={item.due_date}
                          onChange={(iso) => editSuggestedAction(index, { due_date: iso })}
                          withTime={false}
                        />
                      </div>
                      {item.owner_name && !item.owner_membership_id && (
                        <p className="text-xs text-muted-foreground">
                          نام پیشنهادی مسئول: {item.owner_name} (در فهرست اعضا یافت نشد)
                        </p>
                      )}
                      <div className="flex flex-wrap gap-2">
                        <Button
                          size="sm"
                          className="gap-2"
                          disabled={acceptingKey === `action-${index}`}
                          onClick={() => acceptSuggestedAction(index)}
                        >
                          {acceptingKey === `action-${index}` ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Plus className="h-4 w-4" />
                          )}
                          افزودن به اقدامات
                        </Button>
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() =>
                            setSuggested((current) =>
                              current
                                ? {
                                    ...current,
                                    actions: current.actions.filter((_, pos) => pos !== index),
                                  }
                                : current,
                            )
                          }
                        >
                          رد پیشنهاد
                        </Button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      <Card>
        <CardHeader>
          <CardTitle className="text-base">مصوبات</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.decisions.length === 0 && (
            <p className="text-sm text-muted-foreground">مصوبه‌ای ثبت نشده است.</p>
          )}
          {detail.decisions.map((decision) => (
            <div key={decision.id} className="rounded-md border border-border p-3">
              <div className="flex items-start justify-between gap-2">
                <div>
                  <p className="text-sm font-medium">
                    {toPersianDigits(decision.position)}. {decision.title}
                  </p>
                  {decision.description && (
                    <p className="mt-1 text-xs text-muted-foreground">{decision.description}</p>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <Badge variant="outline">
                    {decision.source === 'ai' ? 'پیشنهاد هوش مصنوعی' : 'ثبت دستی'}
                  </Badge>
                  {canManage && (
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="حذف مصوبه"
                      onClick={async () => {
                        try {
                          await api.deleteDecision(decision.id);
                          onDone();
                        } catch (err) {
                          toast.error(errorMessage(err, 'حذف مصوبه ناموفق بود.'));
                        }
                      }}
                    >
                      <Trash2 className="h-4 w-4" />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))}

          {canManage && (
            <>
              <Separator />
              <div className="space-y-2">
                <Input
                  value={decisionTitle}
                  onChange={(event) => setDecisionTitle(event.target.value)}
                  placeholder="عنوان مصوبه"
                />
                <Textarea
                  value={decisionDesc}
                  onChange={(event) => setDecisionDesc(event.target.value)}
                  rows={2}
                  placeholder="شرح مصوبه"
                />
                <Button className="gap-2" onClick={addDecision}>
                  <Plus className="h-4 w-4" />
                  افزودن مصوبه
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">اقدامات این جلسه</CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          {detail.actions.length === 0 && (
            <p className="text-sm text-muted-foreground">اقدامی ثبت نشده است.</p>
          )}
          {detail.actions.map((action) => (
            <div key={action.id} className="rounded-md border border-border p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <p className="text-sm font-medium">{action.title}</p>
                <Badge variant={action.status === 'overdue' ? 'destructive' : 'secondary'}>
                  {ACTION_STATUS_LABELS[action.status] || action.status}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
                مسئول: {action.owner_name || '—'} • مهلت: {formatDate(action.due_date)}
              </p>
              {action.progress_note && (
                <p className="mt-1 text-xs">یادداشت: {action.progress_note}</p>
              )}
            </div>
          ))}

          {canManage && (
            <>
              <Separator />
              <div className="space-y-2">
                <Input
                  value={actionTitle}
                  onChange={(event) => setActionTitle(event.target.value)}
                  placeholder="عنوان اقدام"
                />
                <div className="grid gap-2 sm:grid-cols-3">
                  <Select value={actionOwner} onValueChange={setActionOwner}>
                    <SelectTrigger>
                      <SelectValue placeholder="مسئول" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">بدون مسئول</SelectItem>
                      {members.map((member) => (
                        <SelectItem key={member.id} value={String(member.id)}>
                          {member.full_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select value={actionDecision} onValueChange={setActionDecision}>
                    <SelectTrigger>
                      <SelectValue placeholder="مصوبهٔ مرتبط" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="none">بدون مصوبه</SelectItem>
                      {detail.decisions.map((decision) => (
                        <SelectItem key={decision.id} value={String(decision.id)}>
                          {decision.title}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <JalaliDateTimePicker
                    value={actionDue}
                    onChange={setActionDue}
                    withTime={false}
                  />
                </div>
                <Button className="gap-2" onClick={addAction}>
                  <Plus className="h-4 w-4" />
                  افزودن اقدام
                </Button>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
/* ------------------------------------------------------------------ */
/* دیالوگ تنظیمات تولید صورتجلسهٔ همین جلسه                             */
/* ------------------------------------------------------------------ */

function MinutesSettingsDialog({
  meetingId,
  onClose,
}: {
  meetingId: number;
  onClose: () => void;
}) {
  const [settings, setSettings] = useState<MinutesSettings | null>(null);
  const [draft, setDraft] = useState({
    use_agenda: true,
    use_attendees: false,
    words_per_hour: '1000',
    generate_items: true,
    considerations: '',
  });
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api
      .meetingMinutesSettings(meetingId)
      .then((data) => {
        setSettings(data);
        setDraft({
          use_agenda: data.use_agenda,
          use_attendees: data.use_attendees,
          words_per_hour: String(data.words_per_hour),
          generate_items: data.generate_items,
          considerations: data.considerations,
        });
      })
      .catch((err) => toast.error(errorMessage(err, 'خواندن تنظیمات تولید ناموفق بود.')));
  }, [meetingId]);

  const save = async () => {
    setBusy(true);
    try {
      const data = await api.updateMeetingMinutesSettings(meetingId, {
        use_agenda: draft.use_agenda,
        use_attendees: draft.use_attendees,
        words_per_hour: Number(draft.words_per_hour),
        generate_items: draft.generate_items,
        considerations: draft.considerations,
      });
      setSettings(data);
      setDraft({
        use_agenda: data.use_agenda,
        use_attendees: data.use_attendees,
        words_per_hour: String(data.words_per_hour),
        generate_items: data.generate_items,
        considerations: data.considerations,
      });
      toast.success('تنظیمات تولید این جلسه ذخیره شد.');
    } catch (err) {
      toast.error(errorMessage(err, 'ذخیرهٔ تنظیمات ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open onOpenChange={(value) => !value && onClose()}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto">
        <DialogHeader>
          <DialogTitle>تنظیمات تولید صورتجلسهٔ این جلسه</DialogTitle>
          <DialogDescription>
            این تنظیمات فقط برای همین جلسه اعمال می‌شوند و هنگام تولید پیش‌نویس و پیشنهاد
            مصوبات/اقدامات در پرامپت لحاظ می‌گردند.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <p className="text-sm font-medium">لحاظ دستور جلسه</p>
              <p className="text-xs text-muted-foreground">پیش‌فرض: بله</p>
            </div>
            <Switch
              checked={draft.use_agenda}
              onCheckedChange={(value) => setDraft({ ...draft, use_agenda: value })}
            />
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <p className="text-sm font-medium">لحاظ مدعوین</p>
              <p className="text-xs text-muted-foreground">پیش‌فرض: خیر</p>
            </div>
            <Switch
              checked={draft.use_attendees}
              onCheckedChange={(value) => setDraft({ ...draft, use_attendees: value })}
            />
          </div>

          <div className="flex items-center justify-between rounded-md border p-3">
            <div>
              <p className="text-sm font-medium">تولید مصوبات و اقدامات</p>
              <p className="text-xs text-muted-foreground">پیش‌فرض: بله</p>
            </div>
            <Switch
              checked={draft.generate_items}
              onCheckedChange={(value) => setDraft({ ...draft, generate_items: value })}
            />
          </div>

          <div className="space-y-1">
            <Label htmlFor="mds-words">طول هدف صورتجلسه (کلمه به ازای هر ساعت صوت)</Label>
            <Input
              id="mds-words"
              type="number"
              dir="ltr"
              className="max-w-40 text-left"
              min={settings?.bounds.min_words_per_hour ?? 100}
              max={settings?.bounds.max_words_per_hour ?? 5000}
              value={draft.words_per_hour}
              onChange={(e) => setDraft({ ...draft, words_per_hour: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">پیش‌فرض: ۱۰۰۰ کلمه در ساعت</p>
          </div>

          <div className="space-y-1">
            <Label htmlFor="mds-considerations">ملاحظات شما برای تهیهٔ صورتجلسه</Label>
            <Textarea
              id="mds-considerations"
              rows={4}
              placeholder="مثلاً: مذاکرات را بدون ذکر نام اشخاص بنویس؛ موارد مالی با دقت عددی ثبت شود…"
              value={draft.considerations}
              onChange={(e) => setDraft({ ...draft, considerations: e.target.value })}
            />
            <p className="text-xs text-muted-foreground">
              این ملاحظات عیناً به پرامپت تولید اضافه می‌شوند و مدل زبانی موظف به رعایت آن‌هاست.
            </p>
          </div>

          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={onClose}>
              بستن
            </Button>
            <Button disabled={busy} onClick={() => void save()}>
              {busy ? 'در حال ذخیره…' : 'ذخیرهٔ تنظیمات'}
            </Button>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}

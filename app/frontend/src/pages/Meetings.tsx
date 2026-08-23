/** فهرست جلسات با جست‌وجو، فیلتر و ساخت جلسهٔ تازه همراه با دستور جلسه و اعضا. */
import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CalendarPlus, Paperclip, Plus, Search, Trash2 } from 'lucide-react';
import { toast } from 'sonner';
import AppShell from '@/components/AppShell';
import JalaliDateTimePicker from '@/components/JalaliDateTimePicker';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import LoadingGif from '@/components/LoadingGif';
import { Skeleton } from '@/components/ui/skeleton';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Textarea } from '@/components/ui/textarea';
import {
  api,
  Bootstrap,
  errorMessage,
  formatDateTime,
  formatFileSize,
  MEETING_STATUS_LABELS,
  getUploadLimits,
  Meeting,
  Member,
  MINUTES_STATUS_LABELS,
  toPersianDigits,
  uploadMeetingAttachment,
  validateAttachmentFile,
} from '@/lib/mgmt';

/** یک بند دستور جلسه در فرم ایجاد جلسه (پیش از ذخیرهٔ جلسه). */
interface AgendaDraft {
  title: string;
  planned_minutes: string;
  owner_name: string;
  notes: string;
}

const EMPTY_AGENDA_ITEM: AgendaDraft = {
  title: '',
  planned_minutes: '15',
  owner_name: '',
  notes: '',
};

export default function MeetingsPage() {
  return <AppShell>{(bootstrap) => <MeetingsBody bootstrap={bootstrap} />}</AppShell>;
}

function MeetingsBody({ bootstrap }: { bootstrap: Bootstrap }) {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [scope, setScope] = useState('all');
  const [search, setSearch] = useState('');
  const [error, setError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await api.listMeetings(scope, search);
      setMeetings(data.items);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت فهرست جلسات ناموفق بود.'));
    }
  }, [scope, search]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    api
      .members()
      .then((data) => {
        setMembers(data.members);
        setCanManage(data.can_manage);
      })
      .catch(() => setMembers([]));
  }, []);

  const role = bootstrap.membership.role;
  const allowCreate = canManage || role === 'org_admin' || role === 'secretary';

  return (
    <div className="space-y-6">
      <div className="flex flex-col items-stretch justify-between gap-3 sm:flex-row sm:items-center">
        <h1>جلسات</h1>
        {allowCreate && (
          <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
            <DialogTrigger asChild>
              <Button className="min-h-11 w-full gap-2 sm:w-auto">
                <CalendarPlus className="h-4 w-4" />
                جلسهٔ جدید
              </Button>
            </DialogTrigger>
            <CreateMeetingDialog
              bootstrap={bootstrap}
              members={members}
              onDone={() => {
                setDialogOpen(false);
                load();
              }}
            />
          </Dialog>
        )}
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 py-4 md:flex-row md:items-center">
          {/* در موبایل فیلترها یک ردیف اسکرول‌پذیر می‌شوند تا از عرض صفحه بیرون نزنند. */}
          <Tabs value={scope} onValueChange={setScope} className="min-w-0 max-w-full">
            <TabsList className="flex w-full flex-nowrap justify-start overflow-x-auto">
              <TabsTrigger value="all">همه</TabsTrigger>
              <TabsTrigger value="upcoming">آینده</TabsTrigger>
              <TabsTrigger value="past">گذشته</TabsTrigger>
              <TabsTrigger value="mine">جلسات من</TabsTrigger>
            </TabsList>
          </Tabs>
          <div className="relative w-full min-w-0 md:flex-1">
            <Search className="absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="جست‌وجوی عنوان یا شرح جلسه"
              className="pr-9"
            />
          </div>
        </CardContent>
      </Card>

      {error && (
        <Card>
          <CardContent className="space-y-3 py-6">
            <p className="text-sm text-destructive">{error}</p>
            <Button onClick={load}>تلاش دوباره</Button>
          </CardContent>
        </Card>
      )}

      {!meetings && !error && (
        <div className="space-y-3">
          {[0, 1, 2].map((key) => (
            <Skeleton key={key} className="h-24 w-full" />
          ))}
        </div>
      )}

      {meetings && meetings.length === 0 && (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-sm text-muted-foreground">
              جلسه‌ای با این فیلتر یافت نشد. با دکمهٔ «جلسهٔ جدید» نخستین جلسه را ثبت کنید.
            </p>
          </CardContent>
        </Card>
      )}

      <div className="grid gap-3">
        {meetings?.map((meeting) => (
          <Link key={meeting.id} to={`/meetings/${meeting.id}`}>
            <Card className="transition-colors hover:border-primary/60">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">{meeting.title}</CardTitle>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant="outline">{meeting.meeting_type}</Badge>
                    <Badge variant={meeting.status === 'cancelled' ? 'destructive' : 'secondary'}>
                      {MEETING_STATUS_LABELS[meeting.status] || meeting.status}
                    </Badge>
                    {meeting.minutes_status && (
                      <Badge>{MINUTES_STATUS_LABELS[meeting.minutes_status]}</Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-1 text-xs text-muted-foreground">
                <p>
                  {formatDateTime(meeting.starts_at)} • {toPersianDigits(meeting.duration_minutes)}{' '}
                  دقیقه • دبیر: {meeting.secretary_name || '—'}
                </p>
                <p>
                  دعوت‌شده: {toPersianDigits(meeting.counts?.total ?? 0)} • تأیید حضور:{' '}
                  {toPersianDigits(meeting.counts?.accepted ?? 0)} • حاضر:{' '}
                  {toPersianDigits(meeting.counts?.attended ?? 0)}
                </p>
              </CardContent>
            </Card>
          </Link>
        ))}
      </div>
    </div>
  );
}

function CreateMeetingDialog({
  bootstrap,
  members,
  onDone,
}: {
  bootstrap: Bootstrap;
  members: Member[];
  onDone: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [meetingType, setMeetingType] = useState(bootstrap.meeting_types[0] || 'عملیاتی');
  const [startsAt, setStartsAt] = useState(() => new Date().toISOString());
  const [duration, setDuration] = useState('60');
  const [location, setLocation] = useState('');
  const [onlineUrl, setOnlineUrl] = useState('');
  const [secretaryId, setSecretaryId] = useState('none');
  const [selected, setSelected] = useState<number[]>([]);
  const [agendaItems, setAgendaItems] = useState<AgendaDraft[]>([{ ...EMPTY_AGENDA_ITEM }]);
  const [files, setFiles] = useState<File[]>([]);
  const [saving, setSaving] = useState(false);
  /** درصد پیشرفت واقعی بارگذاری هر پیوست، بر پایهٔ نام فایل. */
  const [uploadProgress, setUploadProgress] = useState<Record<string, number>>({});
  /**
   * مرحلهٔ جاری ثبت.
   *
   * چرا لازم است: پیش‌تر تنها یک پرچم `saving` وجود داشت، پس در فاصلهٔ «ساخت جلسه و
   * ارسال دعوت‌نامه» تا «شروع بارگذاری فایل‌ها» هیچ نشانه‌ای دیده نمی‌شد و کاربر
   * تصور می‌کرد نوار پیشرفت کار نمی‌کند. با تفکیک مرحله، وضعیت هر لحظه شفاف است.
   */
  const [stage, setStage] = useState<'idle' | 'creating' | 'uploading'>('idle');
  const limits = getUploadLimits();

  const toggle = (id: number) => {
    setSelected((prev) => (prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]));
  };

  const updateAgenda = (index: number, patch: Partial<AgendaDraft>) => {
    setAgendaItems((prev) =>
      prev.map((item, position) => (position === index ? { ...item, ...patch } : item)),
    );
  };

  const addAgendaRow = () => setAgendaItems((prev) => [...prev, { ...EMPTY_AGENDA_ITEM }]);

  const removeAgendaRow = (index: number) =>
    setAgendaItems((prev) =>
      prev.length === 1 ? [{ ...EMPTY_AGENDA_ITEM }] : prev.filter((_, key) => key !== index),
    );

  /** فایل‌های نامعتبر پیش از ارسال رد می‌شوند تا آپلود بی‌صدا شکست نخورد. */
  const pickFiles = (selection: FileList | null) => {
    if (!selection || selection.length === 0) return;
    const accepted: File[] = [];
    Array.from(selection).forEach((file) => {
      const problem = validateAttachmentFile(file);
      if (problem) {
        toast.error(problem);
        return;
      }
      accepted.push(file);
    });
    if (accepted.length > 0) setFiles((prev) => [...prev, ...accepted]);
  };

  const removeFile = (index: number) =>
    setFiles((prev) => prev.filter((_, key) => key !== index));

  const submit = async () => {
    if (title.trim().length < 2) {
      toast.error('عنوان جلسه را وارد کنید.');
      return;
    }
    const startDate = startsAt ? new Date(startsAt) : null;
    if (!startDate || Number.isNaN(startDate.getTime())) {
      toast.error('زمان شروع جلسه معتبر نیست. تاریخ شمسی و ساعت را انتخاب کنید.');
      return;
    }
    const iso = startDate.toISOString();
    // بندهای خالی نادیده گرفته می‌شوند؛ فقط بندهای دارای عنوان معتبر ارسال می‌شوند.
    const agendaPayload = agendaItems
      .filter((item) => item.title.trim().length >= 2)
      .map((item) => ({
        title: item.title.trim(),
        notes: item.notes.trim(),
        planned_minutes: Number(item.planned_minutes) || 15,
        owner_name: item.owner_name.trim(),
      }));

    setSaving(true);
    setStage('creating');
    // همهٔ پیوست‌ها از ابتدا در حالت «در نوبت» (صفر درصد) قرار می‌گیرند تا نوار
    // پیشرفت بی‌درنگ رندر شود، نه فقط پس از رسیدن اولین رویداد شبکه.
    if (files.length > 0) {
      setUploadProgress(Object.fromEntries(files.map((file) => [file.name, 0])));
    }
    try {
      const meeting = await api.createMeeting({
        title: title.trim(),
        description: description.trim(),
        meeting_type: meetingType,
        starts_at: iso,
        duration_minutes: Number(duration) || 60,
        location: location.trim(),
        online_url: onlineUrl.trim(),
        secretary_membership_id: secretaryId === 'none' ? null : Number(secretaryId),
        participant_membership_ids: selected,
        agenda_items: agendaPayload,
      });

      // پیوست‌ها پس از ساخت جلسه بارگذاری می‌شوند؛ شکست یک فایل، ثبت جلسه را باطل نمی‌کند.
      if (files.length > 0) setStage('uploading');
      let uploaded = 0;
      let failedUploads = 0;
      for (const file of files) {
        try {
          await uploadMeetingAttachment(meeting.id, file, {
            onProgress: (progress) =>
              setUploadProgress((prev) => ({ ...prev, [file.name]: progress.percent })),
          });
          uploaded += 1;
          setUploadProgress((prev) => ({ ...prev, [file.name]: 100 }));
        } catch (uploadError) {
          failedUploads += 1;
          setUploadProgress((prev) => ({ ...prev, [file.name]: -1 }));
          toast.error(errorMessage(uploadError, `بارگذاری فایل «${file.name}» ناموفق بود.`));
        }
      }

      const parts = ['جلسه ثبت شد و دعوت‌نامه ارسال شد.'];
      if (agendaPayload.length > 0) {
        parts.push(`${toPersianDigits(agendaPayload.length)} بند دستور جلسه ثبت شد.`);
      }
      if (uploaded > 0) {
        parts.push(`${toPersianDigits(uploaded)} فایل پیوست بارگذاری شد.`);
      }
      if (failedUploads > 0) {
        parts.push(
          `${toPersianDigits(failedUploads)} فایل بارگذاری نشد؛ از صفحهٔ جلسه دوباره تلاش کنید.`,
        );
      }
      toast.success(parts.join(' '));
      onDone();
    } catch (err) {
      toast.error(errorMessage(err, 'ثبت جلسه ناموفق بود.'));
    } finally {
      setStage('idle');
      setSaving(false);
    }
  };

  return (
    <DialogContent className="max-h-[90vh] max-w-2xl overflow-y-auto" dir="rtl">
      <DialogHeader>
        <DialogTitle>ثبت جلسهٔ جدید</DialogTitle>
      </DialogHeader>
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="meeting-title">عنوان جلسه</Label>
          <Input
            id="meeting-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="مثال: جلسهٔ هفتگی عملیات"
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="meeting-desc">شرح</Label>
          <Textarea
            id="meeting-desc"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
          />
        </div>
        <div className="space-y-2">
          <Label>نوع جلسه</Label>
          <Select value={meetingType} onValueChange={setMeetingType}>
            <SelectTrigger>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {bootstrap.meeting_types.map((type) => (
                <SelectItem key={type} value={type}>
                  {type}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="meeting-start">زمان شروع (تاریخ شمسی)</Label>
          <JalaliDateTimePicker
            id="meeting-start"
            value={startsAt}
            onChange={setStartsAt}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="meeting-duration">مدت (دقیقه)</Label>
          <Input
            id="meeting-duration"
            type="number"
            min={5}
            max={600}
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
          />
        </div>
        <div className="space-y-2">
          <Label>دبیر جلسه</Label>
          <Select value={secretaryId} onValueChange={setSecretaryId}>
            <SelectTrigger>
              <SelectValue placeholder="انتخاب دبیر" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="none">تعیین نشده</SelectItem>
              {members.map((member) => (
                <SelectItem key={member.id} value={String(member.id)}>
                  {member.full_name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="meeting-location">محل برگزاری</Label>
          <Input
            id="meeting-location"
            value={location}
            onChange={(event) => setLocation(event.target.value)}
            placeholder="اتاق جلسات طبقهٔ سوم"
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="meeting-url">نشانی جلسهٔ برخط</Label>
          <Input
            id="meeting-url"
            value={onlineUrl}
            onChange={(event) => setOnlineUrl(event.target.value)}
            placeholder="https://"
          />
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label>دعوت‌شدگان</Label>
          <div className="grid max-h-44 gap-2 overflow-y-auto rounded-md border border-border p-3 sm:grid-cols-2">
            {members.length === 0 && (
              <p className="text-xs text-muted-foreground">عضوی برای دعوت ثبت نشده است.</p>
            )}
            {members.map((member) => (
              <label key={member.id} className="flex items-center gap-2 text-sm">
                <Checkbox
                  checked={selected.includes(member.id)}
                  onCheckedChange={() => toggle(member.id)}
                />
                <span>{member.full_name}</span>
              </label>
            ))}
          </div>
        </div>

        <div className="space-y-3 sm:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <Label>دستور جلسه</Label>
            <Button type="button" variant="outline" size="sm" onClick={addAgendaRow} className="gap-1.5">
              <Plus className="h-4 w-4" />
              افزودن بند
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            بندهای دستور جلسه همراه دعوت‌نامه برای شرکت‌کنندگان ارسال می‌شود. بندهای بدون عنوان
            نادیده گرفته می‌شوند.
          </p>
          <div className="space-y-3">
            {agendaItems.map((item, index) => (
              <div
                key={`agenda-${index}`}
                className="space-y-3 rounded-md border border-border p-3"
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-medium text-muted-foreground">
                    بند {toPersianDigits(index + 1)}
                  </span>
                  <Button
                    type="button"
                    variant="ghost"
                    size="icon"
                    onClick={() => removeAgendaRow(index)}
                    title="حذف این بند"
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
                <Input
                  value={item.title}
                  placeholder="عنوان بند، مثال: بررسی گزارش فروش"
                  onChange={(event) => updateAgenda(index, { title: event.target.value })}
                />
                <div className="grid gap-3 sm:grid-cols-2">
                  <Input
                    type="number"
                    min={1}
                    max={480}
                    value={item.planned_minutes}
                    placeholder="زمان پیش‌بینی‌شده (دقیقه)"
                    onChange={(event) =>
                      updateAgenda(index, { planned_minutes: event.target.value })
                    }
                  />
                  <Input
                    value={item.owner_name}
                    placeholder="مسئول ارائهٔ بند"
                    onChange={(event) => updateAgenda(index, { owner_name: event.target.value })}
                  />
                </div>
                <Textarea
                  rows={2}
                  value={item.notes}
                  placeholder="توضیح کوتاه (اختیاری)"
                  onChange={(event) => updateAgenda(index, { notes: event.target.value })}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="space-y-3 sm:col-span-2">
          <Label htmlFor="meeting-files">پیوست دستور جلسه</Label>
          <p className="text-xs text-muted-foreground">
            فایل‌های انتخاب‌شده پس از ثبت جلسه بارگذاری و همراه ایمیل دعوت برای شرکت‌کنندگان ارسال
            می‌شود. سقف حجم هر پیوست: {toPersianDigits(limits.maxAttachmentMb)} مگابایت.
          </p>
          <Input
            id="meeting-files"
            type="file"
            multiple
            onChange={(event) => {
              pickFiles(event.target.files);
              event.target.value = '';
            }}
          />
          {files.length > 0 && (
            <div className="space-y-2">
              {files.map((file, index) => {
                const percent = uploadProgress[file.name];
                const isFailed = percent === -1;
                // در مرحلهٔ «ساخت جلسه» درصد صفر است؛ آن را «در نوبت» نشان می‌دهیم تا
                // نوار پیشرفت از همان ابتدا دیده شود و کاربر بی‌خبر نماند.
                const isUploading = typeof percent === 'number' && percent >= 0 && percent < 100;
                const isDone = percent === 100;
                const isQueued = stage === 'creating' && percent === 0;
                return (
                  <div
                    key={`${file.name}-${index}`}
                    className="space-y-2 rounded-md border border-border px-3 py-2 text-sm"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="flex min-w-0 items-center gap-2">
                        <Paperclip className="h-4 w-4 shrink-0 text-muted-foreground" />
                        <span className="truncate" dir="auto">
                          {file.name}
                        </span>
                      </span>
                      <span className="flex shrink-0 items-center gap-2">
                        <span className="text-xs text-muted-foreground">
                          {isDone
                            ? 'بارگذاری شد'
                            : isFailed
                              ? 'ناموفق'
                              : isQueued
                                ? 'در نوبت بارگذاری'
                                : isUploading
                                  ? `${toPersianDigits(percent)}٪`
                                  : formatFileSize(file.size)}
                        </span>
                        {!saving && (
                          <Button
                            type="button"
                            variant="ghost"
                            size="icon"
                            onClick={() => removeFile(index)}
                            title="حذف فایل از فهرست"
                          >
                            <Trash2 className="h-4 w-4 text-destructive" />
                          </Button>
                        )}
                      </span>
                    </div>
                    {(isUploading || isDone) && (
                      <Progress value={isDone ? 100 : percent} className="h-1.5" />
                    )}
                    {isFailed && (
                      <p className="text-xs text-destructive">
                        بارگذاری این فایل انجام نشد؛ از صفحهٔ جلسه دوباره تلاش کنید.
                      </p>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
      {/* نمایشگر انتظار با گیف در مرحلهٔ ثبت جلسه و بارگذاری پیوست‌ها */}
      {stage !== 'idle' && (
        <div className="rounded-md border border-border bg-muted/40 p-4">
          <LoadingGif
            size="sm"
            label={
              stage === 'creating'
                ? 'در حال ثبت جلسه و ارسال دعوت‌نامه…'
                : 'در حال بارگذاری پیوست‌ها…'
            }
            hint={
              files.length > 0
                ? 'پیشرفت هر فایل در فهرست پیوست‌ها نمایش داده می‌شود؛ این پنجره را نبندید.'
                : undefined
            }
          />
        </div>
      )}
      <DialogFooter>
        <Button onClick={submit} disabled={saving}>
          {saving ? 'در حال ثبت…' : 'ثبت جلسه'}
        </Button>
      </DialogFooter>
    </DialogContent>
  );
}
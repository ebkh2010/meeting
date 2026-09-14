/** فهرست جلسات با جست‌وجو، فیلتر و ساخت جلسهٔ تازه همراه با دستور جلسه و اعضا. */
import { useCallback, useEffect, useState } from 'react';
import type { ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import {
  ArrowLeft,
  CalendarPlus,
  Filter,
  ListChecks,
  MapPin,
  Paperclip,
  Pencil,
  Plus,
  Search,
  Trash2,
  UserPlus,
  Users2,
} from 'lucide-react';
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
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuLabel,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Progress } from '@/components/ui/progress';
import LoadingGif from '@/components/LoadingGif';
import FilePicker from '@/components/FilePicker';
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
  notes: string;
}

const EMPTY_AGENDA_ITEM: AgendaDraft = {
  title: '',
  notes: '',
};

/**
 * فردی که در فهرست اعضای سازمان نیست و با نام/نام خانوادگی/موبایل دعوت می‌شود.
 * بک‌اند برای او حساب کاربری می‌سازد، به اعضای سازمان اضافه می‌کند و پیامک
 * دعوت جلسه را برایش می‌فرستد. ایمیل اختیاری است.
 */
interface NewPersonDraft {
  first_name: string;
  last_name: string;
  mobile: string;
  email: string;
}

const EMPTY_NEW_PERSON: NewPersonDraft = {
  first_name: '',
  last_name: '',
  mobile: '',
  email: '',
};

/** ردیف فرد جدید فقط وقتی معتبر است که نام، نام خانوادگی و موبایل داشته باشد. */
function isCompleteNewPerson(person: NewPersonDraft): boolean {
  return (
    person.first_name.trim().length > 0 &&
    person.last_name.trim().length > 0 &&
    person.mobile.trim().length >= 10
  );
}

/** محدوده‌های جست‌وجوی متن جلسات؛ مقدارها با `search_scope` سمت سرور یکسان‌اند. */
const SEARCH_SCOPES = [
  { value: 'all', label: 'همهٔ موارد' },
  { value: 'title', label: 'نام/توضیح جلسه' },
  { value: 'agenda', label: 'دستور جلسه' },
  { value: 'minutes', label: 'صورت‌جلسه' },
  { value: 'transcript', label: 'متن رونویسی' },
  { value: 'decisions', label: 'مصوبات' },
  { value: 'actions', label: 'اقدامات' },
] as const;

type SearchScope = (typeof SEARCH_SCOPES)[number]['value'];

export default function MeetingsPage() {
  return <AppShell>{(bootstrap) => <MeetingsBody bootstrap={bootstrap} />}</AppShell>;
}

function MeetingsBody({ bootstrap }: { bootstrap: Bootstrap }) {
  const [meetings, setMeetings] = useState<Meeting[] | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [canManage, setCanManage] = useState(false);
  const [scope, setScope] = useState('all');
  // عبارت جست‌وجو می‌تواند از کادر جست‌وجوی سراسری هدر بیاید (`/meetings?q=…`).
  const [urlParams] = useSearchParams();
  const [search, setSearch] = useState(() => urlParams.get('q') || '');
  const [searchScope, setSearchScope] = useState<SearchScope>('all');
  const [error, setError] = useState('');
  const [dialogOpen, setDialogOpen] = useState(false);

  // اگر کاربر از کادر جست‌وجوی هدر دوباره به همین صفحه بیاید، عبارت تازه اعمال شود.
  useEffect(() => {
    const fromUrl = urlParams.get('q');
    if (fromUrl !== null) setSearch(fromUrl);
  }, [urlParams]);

  const load = useCallback(async () => {
    try {
      const data = await api.listMeetings(scope, search, searchScope);
      setMeetings(data.items);
      setError('');
    } catch (err) {
      setError(errorMessage(err, 'دریافت فهرست جلسات ناموفق بود.'));
    }
  }, [scope, search, searchScope]);

  /**
   * نشانی صفحهٔ جزئیات جلسه با عبارت جست‌وجو و بخشِ هدف؛ صفحهٔ مقصد همان بخش
   * (صورت‌جلسه، رونویسی، …) را باز می‌کند و واژهٔ جست‌وجو را برجسته می‌کند.
   */
  const detailHref = (meeting: Meeting, scopeOverride?: string) => {
    const q = search.trim();
    const scope = scopeOverride ?? meeting.matches?.[0]?.scope;
    const params = new URLSearchParams();
    if (q) {
      params.set('q', q);
      if (scope) params.set('scope', scope);
    }
    const qs = params.toString();
    return qs ? `/meetings/${meeting.id}?${qs}` : `/meetings/${meeting.id}`;
  };

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
            <Search className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder="جست‌وجو در نام، دستور، صورت‌جلسه، رونویسی، مصوبات و اقدامات"
              className="px-9"
            />
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button
                  type="button"
                  variant={searchScope === 'all' ? 'ghost' : 'secondary'}
                  size="icon"
                  className="absolute left-1.5 top-1/2 h-7 w-7 -translate-y-1/2"
                  title="محدودهٔ جست‌وجو"
                  aria-label="محدودهٔ جست‌وجو"
                >
                  <Filter
                    className={searchScope === 'all' ? 'h-4 w-4' : 'h-4 w-4 text-primary'}
                  />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="w-56">
                <DropdownMenuLabel>محدودهٔ جست‌وجو</DropdownMenuLabel>
                <DropdownMenuSeparator />
                <DropdownMenuRadioGroup
                  value={searchScope}
                  onValueChange={(value) => setSearchScope(value as SearchScope)}
                >
                  {SEARCH_SCOPES.map((option) => (
                    <DropdownMenuRadioItem key={option.value} value={option.value}>
                      {option.label}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
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
          <Card
            key={meeting.id}
            className="transition-colors hover:border-primary/60"
          >
            <Link to={detailHref(meeting)} className="block">
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <CardTitle className="text-base">{meeting.title}</CardTitle>
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge variant={meeting.status === 'cancelled' ? 'destructive' : 'secondary'}>
                      {MEETING_STATUS_LABELS[meeting.status] || meeting.status}
                    </Badge>
                    {meeting.minutes_status && (
                      <Badge>{MINUTES_STATUS_LABELS[meeting.minutes_status]}</Badge>
                    )}
                  </div>
                </div>
              </CardHeader>
              <CardContent className="space-y-1 pb-2 text-xs text-muted-foreground">
                <p>
                  {formatDateTime(meeting.starts_at)} • دبیر: {meeting.secretary_name || '—'}
                </p>
                <p>
                  دعوت‌شده: {toPersianDigits(meeting.counts?.total ?? 0)} • تأیید حضور:{' '}
                  {toPersianDigits(meeting.counts?.accepted ?? 0)} • حاضر:{' '}
                  {toPersianDigits(meeting.counts?.attended ?? 0)}
                </p>
              </CardContent>
            </Link>
            {/* هنگام جست‌وجو، هر بندِ یافت‌شده یک پیوند است که کاربر را مستقیم به همان
                بخش (صورت‌جلسه، رونویسی، …) در صفحهٔ جزئیات جلسه می‌برد. */}
            {meeting.matches && meeting.matches.length > 0 && (
              <div className="space-y-1 px-6 pb-4 pt-1 text-xs text-muted-foreground">
                {meeting.matches.map((match, index) => (
                  <Link
                    key={`${match.scope}-${index}`}
                    to={detailHref(meeting, match.scope)}
                    className="group flex items-start gap-2 rounded-md px-1.5 py-1 transition-colors hover:bg-accent"
                    title={`مشاهدهٔ این بخش در جلسه (${match.label})`}
                  >
                    <Badge
                      variant="outline"
                      className="mt-px shrink-0 px-1.5 py-0 text-[10px]"
                    >
                      {match.label}
                    </Badge>
                    <span className="min-w-0 break-words leading-relaxed">
                      {match.snippet}
                    </span>
                    <ArrowLeft className="mt-0.5 h-3.5 w-3.5 shrink-0 self-start text-primary opacity-60 transition-opacity group-hover:opacity-100" />
                  </Link>
                ))}
              </div>
            )}
          </Card>
        ))}
      </div>
    </div>
  );
}

/**
 * یک بخش فرم ثبت جلسه: کلید بازکنندهٔ پاپ‌آپ + خودِ پاپ‌آپ.
 *
 * چرا پاپ‌آپ: فرم ثبت جلسه باید کوتاه بماند؛ هر بخش در پنجرهٔ جداگانه باز می‌شود و
 * با «ثبت و بازگشت» بسته می‌شود و کاربر به همان فرم برمی‌گردد. مقدارها همان لحظه
 * در وضعیت فرم نوشته می‌شوند (کنترل‌شده)، پس «ثبت» فقط پنجره را می‌بندد.
 */
function FormSection({
  title,
  description,
  icon: Icon,
  summary,
  open,
  onToggle,
  children,
}: {
  title: string;
  description?: string;
  icon: typeof Users2;
  summary?: string;
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <>
      <Button
        type="button"
        variant="outline"
        onClick={onToggle}
        aria-haspopup="dialog"
        className="flex h-auto w-full items-center justify-between gap-2 py-2.5"
      >
        <span className="flex min-w-0 items-center gap-2">
          <Icon className="h-4 w-4 shrink-0 text-muted-foreground" />
          <span className="truncate text-sm font-medium">{title}</span>
        </span>
        <span className="flex shrink-0 items-center gap-2">
          {summary ? <span className="text-xs text-muted-foreground">{summary}</span> : null}
          <Pencil className="h-3.5 w-3.5 text-muted-foreground" />
        </span>
      </Button>

      <Dialog open={open} onOpenChange={(value) => !value && onToggle()}>
        <DialogContent className="max-h-[88vh] max-w-2xl overflow-y-auto" dir="rtl">
          <DialogHeader>
            <DialogTitle>{title}</DialogTitle>
            {description ? <DialogDescription>{description}</DialogDescription> : null}
          </DialogHeader>
          <div className="space-y-3">{children}</div>
          <DialogFooter>
            <Button type="button" onClick={onToggle}>
              ثبت و بازگشت
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

function CreateMeetingDialog({
  members,
  onDone,
}: {
  members: Member[];
  onDone: () => void;
}) {
  const [title, setTitle] = useState('');
  const [description, setDescription] = useState('');
  const [startsAt, setStartsAt] = useState(() => new Date().toISOString());
  const [location, setLocation] = useState('');
  const [onlineUrl, setOnlineUrl] = useState('');
  const [secretaryId, setSecretaryId] = useState('none');
  const [selected, setSelected] = useState<number[]>([]);
  /**
   * افرادی که در فهرست اعضای سازمان نیستند و فقط با نام/نام خانوادگی/موبایل
   * دعوت می‌شوند. بک‌اند برای هرکدام حساب کاربری + عضویت سازمان می‌سازد و
   * پیامک دعوت جلسه برایشان ارسال می‌شود.
   */
  const [newPeople, setNewPeople] = useState<NewPersonDraft[]>([]);
  /**
   * کدام بخش به‌صورت پاپ‌آپ باز است؛ ``null`` یعنی هیچ‌کدام. هر پاپ‌آپ با «ثبت»
   * بسته می‌شود و کاربر به همین فرم ثبت جلسه برمی‌گردد.
   */
  const [section, setSection] = useState<'members' | 'location' | 'agenda' | null>(null);
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

  /** باز/بسته کردن پاپ‌آپ بخش‌ها. */
  const toggleSection = (target: 'members' | 'location' | 'agenda') =>
    setSection((prev) => (prev === target ? null : target));

  const addNewPerson = () => setNewPeople((prev) => [...prev, { ...EMPTY_NEW_PERSON }]);
  const removeNewPerson = (index: number) =>
    setNewPeople((prev) => prev.filter((_, key) => key !== index));
  const updateNewPerson = (index: number, patch: Partial<NewPersonDraft>) =>
    setNewPeople((prev) => prev.map((item, key) => (key === index ? { ...item, ...patch } : item)));

  const completeNewPeople = newPeople.filter(isCompleteNewPerson);
  const membersSummary = `${toPersianDigits(selected.length + completeNewPeople.length)} نفر`;
  const placeSummary = onlineUrl.trim() ? 'برخط' : location.trim() || 'تعیین نشده';
  const agendaSummary = `${toPersianDigits(
    agendaItems.filter((item) => item.title.trim().length >= 2).length,
  )} بند${files.length ? ` · ${toPersianDigits(files.length)} پیوست` : ''}`;

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
    // ردیف نیمه‌پرشدهٔ فرد جدید پیش از ارسال گرفته می‌شود تا حساب ناقص ساخته نشود.
    const incomplete = newPeople.filter(
      (person) =>
        !isCompleteNewPerson(person) &&
        Boolean(person.first_name || person.last_name || person.mobile || person.email),
    );
    if (incomplete.length > 0) {
      setSection('members');
      toast.error('برای هر فرد جدید، نام و نام خانوادگی و شمارهٔ موبایل را کامل کنید.');
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
        starts_at: iso,
        location: location.trim(),
        online_url: onlineUrl.trim(),
        secretary_membership_id: secretaryId === 'none' ? null : Number(secretaryId),
        participant_membership_ids: selected,
        new_participants: completeNewPeople.map((person) => ({
          first_name: person.first_name.trim(),
          last_name: person.last_name.trim(),
          mobile: person.mobile.trim(),
          email: person.email.trim(),
        })),
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
      {/* حداقلِ لازم همیشه دیده می‌شود (عنوان، شرح، تاریخ)؛ بقیهٔ تنظیمات در سه بخش
          بازشو هستند تا فرم هنگام باز شدن کوتاه و قابل اسکن بماند. */}
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="meeting-title">عنوان جلسه</Label>
          <Input
            id="meeting-title"
            value={title}
            onChange={(event) => setTitle(event.target.value)}
            placeholder="مثال: جلسهٔ هفتگی عملیات"
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="meeting-desc">شرح</Label>
          <Textarea
            id="meeting-desc"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={2}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="meeting-start">تاریخ و زمان شروع</Label>
          <JalaliDateTimePicker id="meeting-start" value={startsAt} onChange={setStartsAt} />
        </div>

        <FormSection
          title="اعضای جلسه"
          description="دبیر جلسه و دعوت‌شدگان را مشخص کنید. افراد خارج از فهرست اعضا را هم می‌توانید فقط با نام و شمارهٔ موبایل دعوت کنید."
          icon={Users2}
          summary={membersSummary}
          open={section === 'members'}
          onToggle={() => toggleSection('members')}
        >
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
            <Label>دعوت‌شدگان از اعضای سازمان</Label>
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

          <div className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <Label>دعوت افراد جدید (خارج از فهرست اعضا)</Label>
              <Button
                type="button"
                variant="outline"
                size="sm"
                className="gap-1.5"
                onClick={addNewPerson}
              >
                <UserPlus className="h-4 w-4" />
                افزودن فرد
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              فقط نام، نام خانوادگی و شمارهٔ موبایل لازم است. برای این افراد حساب کاربری ساخته
              می‌شود، به اعضای سازمان اضافه می‌شوند و پیامک دعوت جلسه برایشان ارسال می‌گردد.
              ایمیل اختیاری است.
            </p>
            {newPeople.length === 0 ? (
              <p className="rounded-md border border-dashed border-border px-3 py-2 text-xs text-muted-foreground">
                فرد جدیدی اضافه نشده است.
              </p>
            ) : (
              <div className="space-y-3">
                {newPeople.map((person, index) => (
                  <div
                    key={`new-person-${index}`}
                    className="space-y-2 rounded-md border border-border p-3"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="text-xs font-medium text-muted-foreground">
                        فرد جدید {toPersianDigits(index + 1)}
                      </span>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        onClick={() => removeNewPerson(index)}
                        title="حذف این فرد"
                      >
                        <Trash2 className="h-4 w-4 text-destructive" />
                      </Button>
                    </div>
                    <div className="grid gap-2 sm:grid-cols-2">
                      <Input
                        value={person.first_name}
                        placeholder="نام"
                        onChange={(event) =>
                          updateNewPerson(index, { first_name: event.target.value })
                        }
                      />
                      <Input
                        value={person.last_name}
                        placeholder="نام خانوادگی"
                        onChange={(event) =>
                          updateNewPerson(index, { last_name: event.target.value })
                        }
                      />
                      <Input
                        dir="ltr"
                        inputMode="tel"
                        value={person.mobile}
                        placeholder="09xxxxxxxxx"
                        onChange={(event) => updateNewPerson(index, { mobile: event.target.value })}
                      />
                      <Input
                        dir="ltr"
                        type="email"
                        value={person.email}
                        placeholder="ایمیل (اختیاری)"
                        onChange={(event) => updateNewPerson(index, { email: event.target.value })}
                      />
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </FormSection>

        <FormSection
          title="محل و لینک برگزاری"
          description="محل حضوری و نشانی جلسهٔ برخط را وارد کنید؛ هر کدام لازم باشد."
          icon={MapPin}
          summary={placeSummary}
          open={section === 'location'}
          onToggle={() => toggleSection('location')}
        >
          <div className="grid gap-3">
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
          </div>
        </FormSection>

        <FormSection
          title="دستور جلسه و پیوست"
          description="بندهای دستور جلسه همراه دعوت‌نامه ارسال می‌شود. پیوست‌ها پس از ثبت جلسه بارگذاری می‌شوند."
          icon={ListChecks}
          summary={agendaSummary}
          open={section === 'agenda'}
          onToggle={() => toggleSection('agenda')}
        >
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
                <Textarea
                  rows={2}
                  value={item.notes}
                  placeholder="توضیح کوتاه (اختیاری)"
                  onChange={(event) => updateAgenda(index, { notes: event.target.value })}
                />
              </div>
            ))}
          </div>

          <div className="space-y-3">
            <Label htmlFor="meeting-files">پیوست دستور جلسه</Label>
            <p className="text-xs text-muted-foreground">
              فایل‌های انتخاب‌شده پس از ثبت جلسه بارگذاری و همراه ایمیل دعوت برای شرکت‌کنندگان
              ارسال می‌شود. سقف حجم هر پیوست: {toPersianDigits(limits.maxAttachmentMb)} مگابایت.
            </p>
            <FilePicker
              id="meeting-files"
              multiple
              onSelect={pickFiles}
              label="انتخاب فایل پیوست"
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
        </FormSection>
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
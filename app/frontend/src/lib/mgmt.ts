/**
 * لایهٔ دسترسی به API بک‌اند «سامانهٔ مدیریت جلسات».
 * همهٔ فراخوان‌ها از طریق web-sdk انجام می‌شود؛ نام فیلدها دقیقاً با قرارداد روترها یکسان است.
 */
import { createClient } from '@metagptx/web-sdk';
import { authHeaders, clearToken, isUnauthorized } from '@/lib/session';

export const client = createClient();

type HttpMethod = 'GET' | 'POST' | 'PATCH' | 'PUT' | 'DELETE';

/** استخراج پیام خطای فارسی از پاسخ بک‌اند؛ خطاهای اعتبارسنجی FastAPI (آرایهٔ
 *  detail) به رشته تبدیل می‌شوند تا رندر React با شیء/آرایه نشکند. */
export function errorMessage(error: unknown, fallback = 'انجام درخواست ناموفق بود.'): string {
  const candidate = error as {
    data?: { detail?: unknown };
    response?: { data?: { detail?: unknown } };
    message?: unknown;
  };
  const detail = candidate?.data?.detail ?? candidate?.response?.data?.detail;
  if (Array.isArray(detail)) {
    const parts = detail
      .map((item) =>
        typeof item === 'object' && item !== null
          ? String((item as { msg?: unknown }).msg ?? JSON.stringify(item))
          : String(item),
      )
      .filter(Boolean);
    if (parts.length) return parts.join('؛ ');
  }
  if (typeof detail === 'string' && detail) return detail;
  if (typeof candidate?.message === 'string' && candidate.message) return candidate.message;
  return fallback;
}

/**
 * شکستن هر کش URL-keyed برای GETهای احرازشده.
 *
 * پاسخ‌های API وابسته به توکن نشست است؛ یک پراکسی/کش واسط که کلیدش فقط URL
 * باشد می‌تواند پاسخ کاربر دیگری (مثلاً مدیر) را به این کاربر برگرداند. پارامتر
 * یکتای زمان/تصادف باعث می‌شود هیچ کش واسطی پاسخ را از حافظهٔ خودش نخواند.
 */
function bustCache(url: string, method: HttpMethod): string {
  if (method !== 'GET') return url;
  const separator = url.includes('?') ? '&' : '?';
  return `${url}${separator}_ts=${Date.now()}_${Math.random().toString(36).slice(2, 8)}`;
}

async function invoke<T>(
  url: string,
  method: HttpMethod = 'GET',
  data: Record<string, unknown> = {},
): Promise<T> {
  try {
    const response = await client.apiCall.invoke({
      url: bustCache(url, method),
      method,
      data,
      options: { headers: authHeaders() },
    });
    return response.data as T;
  } catch (error) {
    // نشست منقضی یا نامعتبر: توکن پاک می‌شود تا کاربر به صفحهٔ ورود بازگردد.
    if (isUnauthorized(error)) clearToken();
    throw error;
  }
}

/* ------------------------------------------------------------------ */
/* انواع داده                                                          */
/* ------------------------------------------------------------------ */

export interface QuotaSnapshot {
  period: string;
  limit_minutes: number;
  used_minutes: number;
  remaining_minutes: number;
  usage_percent: number;
}

/** تنظیمات تولید صورتجلسهٔ سازمان (منبع حقیقت: بک‌اند). */
export interface MinutesSettings {
  use_agenda: boolean;
  use_attendees: boolean;
  words_per_hour: number;
  considerations: string;
  updated_by_name: string;
  bounds: { min_words_per_hour: number; max_words_per_hour: number };
}

/** سقف‌های بارگذاری قابل تنظیم در تنظیمات سازمان (منبع حقیقت: بک‌اند). */
export interface UploadLimits {
  max_audio_minutes: number;
  max_audio_mb: number;
  max_attachment_mb: number;
  max_attachment_bytes: number;
  max_audio_bytes: number;
  bounds: Record<string, { min: number; max: number }>;
  defaults: Record<string, number>;
  updated_by_name: string;
  is_custom: boolean;
}

export interface Bootstrap {
  user: { id: string; email: string; name: string };
  organization: {
    id: number;
    name: string;
    slug: string;
    plan_code: string;
    timezone: string;
    is_demo: boolean;
  };
  membership: { id: number; role: string; role_label: string };
  quota: QuotaSnapshot;
  upload_limits?: UploadLimits;
  unread_notifications: number;
  meeting_types: string[];
  roles: { value: string; label: string }[];
}

export interface Meeting {
  id: number;
  title: string;
  description: string;
  meeting_type: string;
  starts_at: string;
  duration_minutes: number;
  location: string;
  online_url: string;
  secretary_membership_id: number | null;
  secretary_name: string;
  status: string;
  created_by_name: string;
  created_at: string;
  minutes_status?: string | null;
  counts?: { total: number; accepted: number; attended: number };
  is_future?: boolean;
}

export interface AgendaItem {
  id: number;
  meeting_id: number;
  position: number;
  title: string;
  notes: string;
  planned_minutes: number;
  owner_name: string;
}

/** فایل پیوست دستور جلسه (فراداده؛ خود فایل در باکت خصوصی است). */
export interface MeetingAttachment {
  id: number;
  meeting_id: number;
  file_name: string;
  content_type: string;
  size_bytes: number;
  uploaded_by_name: string;
  created_at: string;
}

export interface Participant {
  id: number;
  meeting_id: number;
  membership_id: number | null;
  full_name: string;
  rsvp_status: string;
  rsvp_note: string;
  attended: boolean;
}

export interface Recording {
  id: number;
  meeting_id: number;
  bucket_name: string;
  object_key: string;
  file_name: string;
  mime_type: string;
  size_bytes: number;
  duration_seconds: number;
  upload_status: string;
  consent_ack: boolean;
  purge_after: string;
  uploaded_by_name: string;
  created_at: string;
}

export interface TranscriptSegment {
  index?: number;
  text: string;
  start?: number;
  end?: number;
  start_ms?: number;
  end_ms?: number;
  speaker?: string;
}

/** گویندهٔ تفکیک‌شده در رونویسی + نام دلخواه کاربر (در نبودش برچسب پیش‌فرض). */
export interface MeetingSpeaker {
  id: number;
  meeting_id: number;
  transcript_id: number | null;
  speaker_key: string;
  display_name: string | null;
  default_label: string;
  segment_count: number;
  total_ms: number;
  first_start_ms: number;
}

export interface Transcript {
  id: number;
  meeting_id: number;
  recording_id: number | null;
  provider: string;
  model: string;
  full_text: string;
  duration_seconds: number;
  known_word_ratio: number | null;
  stats_words: number | null;
  stats_known_words: number | null;
  job_id: number | null;
  created_at: string;
  segments?: TranscriptSegment[];
}

export interface Minutes {
  id: number;
  meeting_id: number;
  status: string;
  body_markdown: string;
  summary: string;
  current_version: number;
  generated_by: string;
  review_requested_at: string;
  approved_by_name: string;
  approved_at: string;
  locked_at: string;
  updated_at: string;
}

export interface Decision {
  id: number;
  meeting_id: number;
  minutes_id: number | null;
  position: number;
  title: string;
  description: string;
  source: string;
}

export interface ActionItem {
  id: number;
  meeting_id: number;
  decision_id: number | null;
  title: string;
  description: string;
  owner_membership_id: number | null;
  owner_name: string;
  due_date: string;
  status: string;
  progress_note: string;
  source: string;
  meeting_title?: string;
}

export interface Job {
  id: number;
  meeting_id: number | null;
  job_type: string;
  status: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  error_message: string;
  provider: string;
  started_at: string;
  finished_at: string;
  created_by_name: string;
  created_at: string;
  result?: Record<string, unknown>;
}

export interface Member {
  id: number;
  member_user_id: string;
  email: string;
  full_name: string;
  role: string;
  status: string;
  is_virtual: boolean;
}

export interface Invitation {
  id: number;
  email: string;
  role: string;
  token: string;
  status: string;
  expires_at: string;
  invited_by_name: string;
  created_at: string;
}

export interface NotificationItem {
  id: number;
  kind: string;
  title: string;
  body: string;
  link: string;
  is_read: boolean;
  created_at: string;
}

export interface AuditRow {
  id: number;
  actor_name: string;
  actor_role: string;
  action: string;
  entity_type: string;
  entity_id: number | null;
  detail: string;
  created_at: string;
}

export interface MinuteVersion {
  id: number;
  version: number;
  summary: string;
  body_markdown: string;
  status_at_version: string;
  changed_by_name: string;
  change_note: string;
  created_at: string;
}

export interface MeetingDetail {
  meeting: Meeting;
  agenda: AgendaItem[];
  participants: Participant[];
  recordings: Recording[];
  minutes: Minutes | null;
  decisions: Decision[];
  actions: ActionItem[];
  my_rsvp: string | null;
  permissions: { can_manage: boolean; can_approve: boolean; role: string };
}

export interface DashboardData {
  totals: {
    meetings: number;
    upcoming: number;
    past: number;
    attendance_rate: number;
    actions: number;
    action_completion_rate: number;
    overdue_actions: number;
    pending_minutes: number;
  };
  action_counts: Record<string, number>;
  minutes_counts: Record<string, number>;
  meetings_by_type: { name: string; value: number }[];
  meetings_by_month: { month: string; value: number }[];
  next_meetings: Meeting[];
  my_open_actions: ActionItem[];
  quota: QuotaSnapshot;
}

export interface AdminConsole {
  organization: {
    id: number;
    name: string;
    plan_code: string;
    timezone: string;
    audio_retention_days: number;
    is_demo: boolean;
  };
  quota: QuotaSnapshot;
  job_counts: Record<string, number>;
  recent_jobs: Job[];
  usage_events: {
    id: number;
    kind: string;
    provider: string;
    model: string;
    minutes_charged: number;
    detail: string;
    created_at: string;
  }[];
  storage: { files: number; total_mb: number; retention_days: number };
  transcription_providers: {
    name: string;
    available: boolean;
    reason?: string;
    active?: boolean;
  }[];
  low_quality_transcripts: { meeting_id: number; known_word_ratio: number }[];
  role_counts: Record<string, number>;
  recent_audit: AuditRow[];
  concurrency: { org_limit: number; system_limit: number; active: number };
}

export interface ExportPackage {
  organization: { name: string; timezone: string };
  meeting: Meeting;
  minutes: Minutes | null;
  agenda: AgendaItem[];
  participants: Participant[];
  decisions: Decision[];
  actions: ActionItem[];
}

/** پیشنهاد هوشمند مصوبات و اقدامات از متن رونویسی (بدون ذخیره در پایگاه داده). */
export interface SuggestedItems {
  decisions: { title: string; description: string }[];
  actions: {
    title: string;
    description: string;
    owner_membership_id: number | null;
    owner_name: string;
    due_date: string;
  }[];
  model: string;
  attempts: string;
}

/* ------------------------------------------------------------------ */
/* توابع API                                                           */
/* ------------------------------------------------------------------ */

const WS = '/api/v1/workspace';
const AI = '/api/v1/meeting-ai';
const MF = '/api/v1/minutes-flow';
const ARCH = '/api/v1/archive';

/** یک تأمین‌کنندهٔ مقصد خارجی در فهرست راهنما (S3 یا WebDAV). */
export interface StorageProviderInfo {
  provider: string;
  label: string;
  note: string;
  fields: string[];
}

/** تنظیمات مقصد ذخیره‌سازی خارجی سازمان؛ اعتبارنامه‌ها فقط ماسک‌شده می‌آیند. */
export interface StorageTarget {
  configured: boolean;
  provider: string;
  display_name: string;
  enabled: boolean;
  endpoint: string;
  bucket: string;
  region: string;
  path_prefix: string;
  access_key: string;
  secret_key_masked: string;
  has_secret_key: boolean;
  force_path_style: boolean;
  webdav_base_url: string;
  webdav_username: string;
  webdav_password_masked: string;
  has_webdav_password: boolean;
  restore_retention_days: number;
  tenant_prefix: string;
  last_test_ok: boolean;
  last_test_at: string;
  last_test_message: string;
  updated_by_name: string;
  is_active: boolean;
}

/** وضعیت آرشیو یک فایل جانبی جلسه. */
export interface ArchiveFile {
  id: number;
  meeting_id: number;
  source_kind: string;
  source_id: number;
  file_name: string;
  content_type: string;
  remote_path: string;
  size_bytes: number;
  checksum_sha256: string;
  status: string;
  status_label: string;
  kind_label: string;
  error_message: string;
  archived_at: string;
  restored_at: string;
  restore_expires_at: string;
  archived_by_name: string;
  restored_by_name: string;
  is_archived: boolean;
  is_local: boolean;
}

/** کار صف آرشیو/بازیابی با درصد پیشرفت واقعی. */
export interface ArchiveJob {
  id: number;
  meeting_id: number;
  job_type: string;
  status: string;
  progress: number;
  attempts: number;
  max_attempts: number;
  error_message: string;
  result_json: string;
  started_at: string;
  finished_at: string;
  created_by_name: string;
  created_at: string;
}

/** نمای وضعیت آرشیو یک جلسه. */
export interface MeetingArchiveState {
  meeting_id: number;
  meeting_title: string;
  state: string;
  state_label: string;
  files: ArchiveFile[];
  archived_count: number;
  total_count: number;
  archived_bytes: number;
  target_ready: boolean;
  active_job: ArchiveJob | null;
}

/** خلاصهٔ وضعیت آرشیو یک جلسه در فهرست مدیریت. */
export interface ArchiveMeetingSummary {
  meeting_id: number;
  title: string;
  starts_at: string;
  tracked_count: number;
  archived_count: number;
  archived_bytes: number;
  has_error: boolean;
}

export const api = {
  bootstrap: () => invoke<Bootstrap>(`${WS}/bootstrap`),
  dashboard: () => invoke<DashboardData>(`${WS}/dashboard`),

  listMeetings: (scope = 'all', search = '') =>
    invoke<{ items: Meeting[]; total: number }>(`${WS}/meetings`, 'GET', { scope, search }),
  createMeeting: (payload: Record<string, unknown>) =>
    invoke<Meeting>(`${WS}/meetings`, 'POST', payload),
  meetingDetail: (id: number) => invoke<MeetingDetail>(`${WS}/meetings/${id}`),
  updateMeeting: (id: number, payload: Record<string, unknown>) =>
    invoke<Meeting>(`${WS}/meetings/${id}`, 'PATCH', payload),
  deleteMeeting: (id: number) => invoke<{ success: boolean }>(`${WS}/meetings/${id}`, 'DELETE'),

  addAgenda: (meetingId: number, payload: Record<string, unknown>) =>
    invoke<AgendaItem>(`${WS}/meetings/${meetingId}/agenda`, 'POST', payload),
  deleteAgenda: (itemId: number) => invoke<{ success: boolean }>(`${WS}/agenda/${itemId}`, 'DELETE'),

  setParticipants: (meetingId: number, membershipIds: number[]) =>
    invoke<{ success: boolean; total: number }>(`${WS}/meetings/${meetingId}/participants`, 'POST', {
      membership_ids: membershipIds,
    }),
  submitRsvp: (meetingId: number, status: string, note = '') =>
    invoke<Participant>(`${WS}/meetings/${meetingId}/rsvp`, 'POST', {
      rsvp_status: status,
      rsvp_note: note,
    }),
  saveAttendance: (meetingId: number, attendance: Record<string, boolean>) =>
    invoke<{ success: boolean; present: number; total: number }>(
      `${WS}/meetings/${meetingId}/attendance`,
      'POST',
      { attendance },
    ),

  members: () =>
    invoke<{
      members: Member[];
      invitations: Invitation[];
      can_manage: boolean;
      my_membership_id: number;
    }>(`${WS}/members`),
  addMember: (payload: Record<string, unknown>) => invoke<Member>(`${WS}/members`, 'POST', payload),
  updateMember: (id: number, payload: Record<string, unknown>) =>
    invoke<Member>(`${WS}/members/${id}`, 'PATCH', payload),
  createInvitation: (email: string, role: string) =>
    invoke<Invitation>(`${WS}/invitations`, 'POST', { email, role }),
  revokeInvitation: (id: number) =>
    invoke<Invitation>(`${WS}/invitations/${id}/revoke`, 'POST'),
  uploadLimits: () => invoke<UploadLimits>(`${WS}/upload-limits`),
  updateUploadLimits: (payload: {
    max_audio_minutes?: number;
    max_audio_mb?: number;
    max_attachment_mb?: number;
  }) => invoke<UploadLimits>(`${WS}/upload-limits`, 'PATCH', payload),
  /** تنظیمات تولید صورتجلسه: لحاظ دستور جلسه/مدعوین، طول هدف و ملاحظات. */
  minutesSettings: () => invoke<MinutesSettings>(`${WS}/minutes-settings`),
  updateMinutesSettings: (payload: {
    use_agenda?: boolean;
    use_attendees?: boolean;
    words_per_hour?: number;
    considerations?: string;
  }) => invoke<MinutesSettings>(`${WS}/minutes-settings`, 'PATCH', payload),
  updateSettings: (payload: Record<string, unknown>) =>
    invoke<{ organization: Record<string, unknown>; quota: QuotaSnapshot }>(
      `${WS}/settings`,
      'PATCH',
      payload,
    ),

  purgeDemoData: (confirm: string) =>
    invoke<{
      success: boolean;
      removed: Record<string, number>;
      total: number;
      is_demo: boolean;
    }>(`${WS}/demo-data/purge`, 'POST', { confirm }),

  notifications: () =>
    invoke<{ items: NotificationItem[]; unread: number }>(`${WS}/notifications`),
  markNotificationsRead: () => invoke<{ success: boolean }>(`${WS}/notifications/read`, 'POST'),
  auditLog: () => invoke<{ items: AuditRow[] }>(`${WS}/audit`),

  createUploadUrl: (payload: { meeting_id: number; file_name: string; size_bytes: number }) =>
    invoke<{ bucket_name: string; object_key: string; upload_url: string; expires_at: string }>(
      `${AI}/upload-url`,
      'POST',
      payload,
    ),
  registerRecording: (payload: Record<string, unknown>) =>
    invoke<Recording>(`${AI}/recordings`, 'POST', payload),
  recordingPlayUrl: (id: number) =>
    invoke<{ download_url: string; expires_at: string }>(`${AI}/recordings/${id}/play-url`),
  deleteRecording: (id: number) =>
    invoke<{ success: boolean }>(`${AI}/recordings/${id}`, 'DELETE'),

  startTranscribe: (recordingId: number) =>
    invoke<Job>(`${AI}/jobs/transcribe`, 'POST', { recording_id: recordingId }),
  startMinutesDraft: (meetingId: number) =>
    invoke<Job>(`${AI}/jobs/minutes`, 'POST', { meeting_id: meetingId }),
  jobStatus: (jobId: number) => invoke<Job>(`${AI}/jobs/${jobId}`),
  meetingJobs: (meetingId: number) =>
    invoke<{ jobs: Job[]; transcript: Transcript | null }>(`${AI}/meetings/${meetingId}/jobs`),
  retryJob: (jobId: number) => invoke<Job>(`${AI}/jobs/${jobId}/retry`, 'POST'),

  meetingSpeakers: (meetingId: number) =>
    invoke<{
      transcript_id: number | null;
      speakers: MeetingSpeaker[];
      segments: TranscriptSegment[];
    }>(`${AI}/meetings/${meetingId}/speakers`),
  renameSpeaker: (speakerId: number, displayName: string) =>
    invoke<MeetingSpeaker>(`${AI}/speakers/${speakerId}`, 'PATCH', { display_name: displayName }),
  speakerClipUrl: (speakerId: number) =>
    invoke<{
      clip_url: string;
      expires_at: string;
      start_ms: number;
      end_ms: number;
      speaker_key: string;
    }>(`${AI}/speakers/${speakerId}/clip-url`),

  saveMinutes: (payload: {
    meeting_id: number;
    body_markdown: string;
    summary?: string;
    change_note?: string;
  }) => invoke<Minutes>(`${MF}/save`, 'POST', payload),
  submitMinutesForReview: (meetingId: number, note = '') =>
    invoke<Minutes>(`${MF}/submit-review`, 'POST', { meeting_id: meetingId, note }),
  approveMinutes: (meetingId: number, note = '') =>
    invoke<Minutes>(`${MF}/approve`, 'POST', { meeting_id: meetingId, note }),
  rejectMinutes: (meetingId: number, note = '') =>
    invoke<Minutes>(`${MF}/reject`, 'POST', { meeting_id: meetingId, note }),
  lockMinutes: (meetingId: number, note = '') =>
    invoke<Minutes>(`${MF}/lock`, 'POST', { meeting_id: meetingId, note }),
  minutesVersions: (meetingId: number) =>
    invoke<{ items: MinuteVersion[] }>(`${MF}/versions/${meetingId}`),

  createDecision: (payload: {
    meeting_id: number;
    title: string;
    description?: string;
    /** «ai» برای پیشنهاد پذیرفته‌شدهٔ هوش مصنوعی، در غیر این صورت ثبت دستی. */
    source?: 'manual' | 'ai';
  }) => invoke<Decision>(`${MF}/decisions`, 'POST', payload),
  updateDecision: (id: number, payload: Record<string, unknown>) =>
    invoke<Decision>(`${MF}/decisions/${id}`, 'PATCH', payload),
  deleteDecision: (id: number) => invoke<{ success: boolean }>(`${MF}/decisions/${id}`, 'DELETE'),

  listActions: (scope = 'all', statusFilter = 'all') =>
    invoke<{ items: ActionItem[]; counts: Record<string, number>; my_membership_id: number }>(
      `${MF}/actions`,
      'GET',
      { scope, status_filter: statusFilter },
    ),
  createAction: (payload: Record<string, unknown>) =>
    invoke<ActionItem>(`${MF}/actions`, 'POST', payload),
  updateAction: (id: number, payload: Record<string, unknown>) =>
    invoke<ActionItem>(`${MF}/actions/${id}`, 'PATCH', payload),
  deleteAction: (id: number) => invoke<{ success: boolean }>(`${MF}/actions/${id}`, 'DELETE'),

  listAttachments: (meetingId: number) =>
    invoke<{ items: MeetingAttachment[]; total: number; can_manage: boolean }>(
      `${WS}/meetings/${meetingId}/attachments`,
    ),
  attachmentUploadUrl: (
    meetingId: number,
    payload: { file_name: string; size_bytes: number; content_type: string },
  ) =>
    invoke<{ upload_url: string; object_key: string; content_type: string }>(
      `${WS}/meetings/${meetingId}/attachments/upload-url`,
      'POST',
      payload,
    ),
  registerAttachment: (
    meetingId: number,
    payload: {
      object_key: string;
      file_name: string;
      size_bytes: number;
      content_type: string;
    },
  ) => invoke<MeetingAttachment>(`${WS}/meetings/${meetingId}/attachments`, 'POST', payload),
  attachmentDownloadUrl: (attachmentId: number) =>
    invoke<{ download_url: string; file_name: string }>(
      `${WS}/attachments/${attachmentId}/download-url`,
    ),
  deleteAttachment: (attachmentId: number) =>
    invoke<{ success: boolean }>(`${WS}/attachments/${attachmentId}`, 'DELETE'),
  resendAgenda: (meetingId: number) =>
    invoke<{
      sms_sent: number;
      sms_failed: number;
      email_sent: number;
      email_failed: number;
      skipped: number;
      detail?: string;
      agenda_items?: number;
      attachments_sent?: number;
      attachments_skipped?: number;
    }>(`${WS}/meetings/${meetingId}/resend-agenda`, 'POST'),

  suggestMeetingItems: (meetingId: number) =>
    invoke<SuggestedItems>(`${AI}/suggest-items`, 'POST', { meeting_id: meetingId }),

  /* --- استوریج خارجی و آرشیو جلسات (فقط مدیر سازمان) --- */
  archiveTarget: () =>
    invoke<{
      target: StorageTarget;
      catalog: StorageProviderInfo[];
      retention_bounds: { min: number; max: number };
    }>(`${ARCH}/target`),
  saveArchiveTarget: (payload: Record<string, unknown>) =>
    invoke<{ target: StorageTarget; changes: string[] }>(`${ARCH}/target`, 'PUT', payload),
  testArchiveTarget: () =>
    invoke<{ ok: boolean; message: string; target: StorageTarget }>(
      `${ARCH}/target/test`,
      'POST',
    ),
  archiveMeetings: () =>
    invoke<{ items: ArchiveMeetingSummary[]; target_ready: boolean }>(`${ARCH}/meetings`),
  archiveMeetingState: (meetingId: number) =>
    invoke<MeetingArchiveState>(`${ARCH}/meetings/${meetingId}`),
  startMeetingArchive: (meetingId: number, fileIds: number[] = []) =>
    invoke<ArchiveJob>(`${ARCH}/meetings/${meetingId}/archive`, 'POST', { file_ids: fileIds }),
  startMeetingRestore: (meetingId: number, fileIds: number[] = []) =>
    invoke<ArchiveJob>(`${ARCH}/meetings/${meetingId}/restore`, 'POST', { file_ids: fileIds }),
  archiveJob: (jobId: number) => invoke<ArchiveJob>(`${ARCH}/jobs/${jobId}`),
  retryArchiveJob: (jobId: number) => invoke<ArchiveJob>(`${ARCH}/jobs/${jobId}/retry`, 'POST'),

  exportPackage: (meetingId: number) => invoke<ExportPackage>(`${MF}/export/${meetingId}`),
  meetingIcs: (meetingId: number) => invoke<string>(`${MF}/ics/${meetingId}`),
  adminConsole: () => invoke<AdminConsole>(`${MF}/admin/console`),
  purgeExpiredAudio: () =>
    invoke<{ success: boolean; removed: number }>(`${MF}/admin/purge-expired-audio`, 'POST'),
};

/* ------------------------------------------------------------------ */
/* بارگذاری فایل صوتی                                                  */
/* ------------------------------------------------------------------ */

/** خواندن مدت فایل صوتی در مرورگر (برای بررسی سقف مدت و سنجش سهمیه). */
export function readAudioDuration(file: File): Promise<number> {
  return new Promise((resolve) => {
    const url = URL.createObjectURL(file);
    const audio = document.createElement('audio');
    const done = (value: number) => {
      URL.revokeObjectURL(url);
      resolve(value);
    };
    audio.preload = 'metadata';
    audio.onloadedmetadata = () =>
      done(Number.isFinite(audio.duration) ? Math.round(audio.duration) : 0);
    audio.onerror = () => done(0);
    audio.src = url;
  });
}

/* ------------------------------------------------------------------ */
/* دانلود فایل Word صورتجلسه                                           */
/* ------------------------------------------------------------------ */

/** استخراج نام فایل فارسی از هدر Content-Disposition پاسخ. */
function fileNameFromDisposition(header: string, fallback: string): string {
  const utf8 = /filename\*=UTF-8''([^;]+)/i.exec(header || '');
  if (utf8) {
    try {
      return decodeURIComponent(utf8[1].trim());
    } catch {
      /* هدر خراب: به نام پیش‌فرض بازمی‌گردیم. */
    }
  }
  const plain = /filename="?([^";]+)"?/i.exec(header || '');
  return plain ? plain[1].trim() : fallback;
}

/** ذخیرهٔ یک Blob در مرورگر با نام دلخواه (پشتیبانی کامل از نام فارسی). */
function saveBlob(blob: Blob, fileName: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = fileName;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

/**
 * دانلود فایل پیوست با نام فارسی اصلی.
 *
 * کلید شیء در فضای ذخیره‌سازی به‌صورت ASCII امن ساخته می‌شود؛ بنابراین محتوای
 * فایل با پیوند امضاشده خوانده و با نام اصلی ثبت‌شده در پایگاه داده ذخیره
 * می‌گردد تا نام فارسی و پسوند درست به کاربر برسد.
 */
export async function downloadAttachment(
  attachmentId: number,
): Promise<{ file_name: string; fallback_url: string }> {
  const data = await api.attachmentDownloadUrl(attachmentId);
  const fileName = data.file_name || `پیوست-${attachmentId}`;
  try {
    const response = await fetch(data.download_url);
    if (!response.ok) throw new Error(String(response.status));
    saveBlob(await response.blob(), fileName);
    return { file_name: fileName, fallback_url: '' };
  } catch {
    // اگر خواندن مستقیم ممکن نبود (مثلاً محدودیت CORS)، پیوند امضاشده باز می‌شود.
    return { file_name: fileName, fallback_url: data.download_url };
  }
}

/**
 * دریافت فایل Word صورتجلسه و ذخیرهٔ آن در مرورگر.
 *
 * دانلود با `fetch` انجام می‌شود تا هدر نشست (`X-App-Token`) ارسال شود؛
 * سپس فایل به‌صورت Blob با نام فارسی بازگشتی از بک‌اند ذخیره می‌گردد.
 */
export async function downloadMinutesDocx(meetingId: number): Promise<string> {
  const response = await fetch(`${MF}/export/${meetingId}/docx`, {
    method: 'GET',
    headers: authHeaders(),
  });
  if (response.status === 401) {
    clearToken();
    throw new Error('نشست شما منقضی شده است. دوباره وارد شوید.');
  }
  if (!response.ok) {
    let detail = '';
    try {
      const payload = await response.json();
      detail = (payload as { detail?: string })?.detail || '';
    } catch {
      /* پاسخ خطا JSON نبود. */
    }
    throw new Error(detail || 'دریافت فایل Word صورتجلسه ناموفق بود. دوباره تلاش کنید.');
  }

  const blob = await response.blob();
  const fileName = fileNameFromDisposition(
    response.headers.get('Content-Disposition') || '',
    `صورتجلسه-${meetingId}.docx`,
  );
  saveBlob(blob, fileName);
  return fileName;
}

/* ------------------------------------------------------------------ */
/* بارگذاری فایل با پیشرفت واقعی                                       */
/* ------------------------------------------------------------------ */

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
}

export interface UploadOptions {
  onProgress?: (progress: UploadProgress) => void;
  signal?: AbortSignal;
}

/** سقف پیش‌فرض حجم پیوست؛ تا خوانده‌شدن سقف سازمان از سرور به کار می‌رود. */
export const MAX_ATTACHMENT_BYTES = 25 * 1024 * 1024;

/** سقف پیش‌فرض حجم فایل صوتی جلسه. */
export const MAX_AUDIO_BYTES = 300 * 1024 * 1024;

/**
 * سقف‌های مؤثر بارگذاری در حافظهٔ ماژول.
 *
 * چرا در سطح ماژول: توابع اعتبارسنجی (`validateAttachmentFile`) از چند نقطهٔ UI
 * فراخوانی می‌شوند و پاس‌دادن سقف به همهٔ آن‌ها، امضای زیادی را می‌شکست. مقدار
 * پس از هر `bootstrap` یا خواندن تنظیمات به‌روزرسانی می‌شود.
 */
let effectiveLimits = {
  maxAttachmentBytes: MAX_ATTACHMENT_BYTES,
  maxAudioBytes: MAX_AUDIO_BYTES,
  maxAudioMinutes: 90,
  maxAttachmentMb: 25,
  maxAudioMb: 300,
};

/** ثبت سقف‌های سازمان تا اعتبارسنجی فرانت با سرور یکی بماند. */
export function applyUploadLimits(limits?: UploadLimits | null): void {
  if (!limits) return;
  effectiveLimits = {
    maxAttachmentBytes: Number(limits.max_attachment_bytes) || MAX_ATTACHMENT_BYTES,
    maxAudioBytes: Number(limits.max_audio_bytes) || MAX_AUDIO_BYTES,
    maxAudioMinutes: Number(limits.max_audio_minutes) || 90,
    maxAttachmentMb: Number(limits.max_attachment_mb) || 25,
    maxAudioMb: Number(limits.max_audio_mb) || 300,
  };
}

/** سقف‌های مؤثر جاری برای نمایش راهنما در فرم‌ها. */
export function getUploadLimits() {
  return { ...effectiveLimits };
}

const EXTENSION_CONTENT_TYPES: Record<string, string> = {
  pdf: 'application/pdf',
  doc: 'application/msword',
  docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
  xls: 'application/vnd.ms-excel',
  xlsx: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
  ppt: 'application/vnd.ms-powerpoint',
  pptx: 'application/vnd.openxmlformats-officedocument.presentationml.presentation',
  txt: 'text/plain',
  csv: 'text/csv',
  png: 'image/png',
  jpg: 'image/jpeg',
  jpeg: 'image/jpeg',
  webp: 'image/webp',
  zip: 'application/zip',
};

const ALLOWED_ATTACHMENT_TYPES = new Set(Object.values(EXTENSION_CONTENT_TYPES));

const ALLOWED_FORMATS_MESSAGE =
  'فقط فایل‌های PDF، Word، Excel، PowerPoint، تصویر (PNG/JPG/WebP)، متن، CSV و ZIP پذیرفته می‌شوند.';

/** نوع محتوای فایل؛ اگر مرورگر تشخیص نداد (رایج در نام‌های فارسی) از پسوند حدس زده می‌شود. */
export function guessContentType(fileName: string, browserType = ''): string {
  const clean = (browserType || '').split(';')[0].trim().toLowerCase();
  if (clean && ALLOWED_ATTACHMENT_TYPES.has(clean)) return clean;
  const extension = (fileName.split('.').pop() || '').toLowerCase();
  return EXTENSION_CONTENT_TYPES[extension] || clean || 'application/octet-stream';
}

/** اعتبارسنجی سمت کاربر تا هیچ آپلودی بی‌صدا شکست نخورد. */
export function validateAttachmentFile(file: File): string {
  if (!file.size) {
    return `فایل «${file.name}» خالی است و بارگذاری نمی‌شود.`;
  }
  if (file.size > effectiveLimits.maxAttachmentBytes) {
    return `حجم فایل «${file.name}» (${formatFileSize(file.size)}) بیشتر از سقف ${toPersianDigits(
      effectiveLimits.maxAttachmentMb,
    )} مگابایت است.`;
  }
  const contentType = guessContentType(file.name, file.type);
  if (!ALLOWED_ATTACHMENT_TYPES.has(contentType)) {
    return `نوع فایل «${file.name}» پشتیبانی نمی‌شود. ${ALLOWED_FORMATS_MESSAGE}`;
  }
  return '';
}

/** بارگذاری با XHR برای گزارش درصد واقعی پیشرفت و امکان لغو. */
function putWithProgress(
  url: string,
  file: File,
  contentType: string,
  options?: UploadOptions,
): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open('PUT', url, true);
    request.setRequestHeader('Content-Type', contentType);

    request.upload.onprogress = (event) => {
      if (!options?.onProgress) return;
      const total = event.lengthComputable && event.total > 0 ? event.total : file.size;
      const loaded = Math.min(event.loaded, total);
      options.onProgress({
        loaded,
        total,
        percent: total > 0 ? Math.min(99, Math.round((loaded / total) * 100)) : 0,
      });
    };

    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        options?.onProgress?.({ loaded: file.size, total: file.size, percent: 100 });
        resolve();
        return;
      }
      if (request.status === 413) {
        reject(
          new Error(
            `حجم فایل «${file.name}» برای فضای ذخیره‌سازی زیاد است؛ فایل کوچک‌تری بارگذاری کنید.`,
          ),
        );
        return;
      }
      reject(
        new Error(
          `بارگذاری «${file.name}» در فضای ذخیره‌سازی ناموفق بود (کد ${request.status}). دوباره تلاش کنید.`,
        ),
      );
    };

    request.onerror = () =>
      reject(
        new Error(
          `ارتباط با فضای ذخیره‌سازی هنگام بارگذاری «${file.name}» قطع شد. اتصال شبکه را بررسی و دوباره تلاش کنید.`,
        ),
      );
    request.ontimeout = () =>
      reject(new Error(`زمان بارگذاری «${file.name}» به پایان رسید. دوباره تلاش کنید.`));
    request.onabort = () => reject(new Error(`بارگذاری «${file.name}» لغو شد.`));

    if (options?.signal) {
      if (options.signal.aborted) {
        reject(new Error(`بارگذاری «${file.name}» لغو شد.`));
        return;
      }
      options.signal.addEventListener('abort', () => request.abort(), { once: true });
    }

    request.send(file);
  });
}

export async function uploadMeetingAttachment(
  meetingId: number,
  file: File,
  options?: UploadOptions,
): Promise<MeetingAttachment> {
  const problem = validateAttachmentFile(file);
  if (problem) throw new Error(problem);

  const contentType = guessContentType(file.name, file.type);
  const signed = await api.attachmentUploadUrl(meetingId, {
    file_name: file.name,
    size_bytes: file.size,
    content_type: contentType,
  });
  await putWithProgress(signed.upload_url, file, signed.content_type || contentType, options);
  return api.registerAttachment(meetingId, {
    object_key: signed.object_key,
    file_name: file.name,
    size_bytes: file.size,
    content_type: signed.content_type || contentType,
  });
}

/** نمایش خوانای حجم فایل برای فهرست پیوست‌ها. */
export function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return '—';
  if (bytes < 1024) return `${toPersianDigits(bytes)} بایت`;
  if (bytes < 1024 * 1024) return `${toPersianDigits((bytes / 1024).toFixed(0))} کیلوبایت`;
  return `${toPersianDigits((bytes / (1024 * 1024)).toFixed(1))} مگابایت`;
}

/** بارگذاری فایل در باکت خصوصی با URL امضاشده و سپس ثبت فراداده در بک‌اند. */
export async function uploadMeetingAudio(
  meetingId: number,
  file: File,
  consentAck: boolean,
  options?: UploadOptions,
): Promise<Recording> {
  if (!file.size) {
    throw new Error(`فایل صوتی «${file.name}» خالی است و بارگذاری نمی‌شود.`);
  }
  if (file.size > effectiveLimits.maxAudioBytes) {
    throw new Error(
      `حجم فایل صوتی «${file.name}» (${formatFileSize(file.size)}) بیشتر از سقف ${toPersianDigits(
        effectiveLimits.maxAudioMb,
      )} مگابایت است.`,
    );
  }
  const durationSeconds = await readAudioDuration(file);
  // سقف مدت از تنظیمات سازمان می‌آید؛ پیام خطا پیش از آپلود نمایش داده می‌شود
  // تا کاربر منتظر آپلود کامل و سپس رد شدن از سوی سرور نماند.
  if (durationSeconds && durationSeconds > effectiveLimits.maxAudioMinutes * 60) {
    throw new Error(
      `مدت فایل صوتی (${toPersianDigits(
        Math.round(durationSeconds / 60),
      )} دقیقه) بیشتر از سقف مجاز این سازمان (${toPersianDigits(
        effectiveLimits.maxAudioMinutes,
      )} دقیقه) است. مدیر سازمان می‌تواند این سقف را در تنظیمات سازمان افزایش دهد.`,
    );
  }
  const contentType = file.type || 'audio/mpeg';
  const signed = await api.createUploadUrl({
    meeting_id: meetingId,
    file_name: file.name,
    size_bytes: file.size,
  });
  await putWithProgress(signed.upload_url, file, contentType, options);
  return api.registerRecording({
    meeting_id: meetingId,
    object_key: signed.object_key,
    file_name: file.name,
    mime_type: file.type || 'audio/mpeg',
    size_bytes: file.size,
    duration_seconds: durationSeconds,
    consent_ack: consentAck,
  });
}

/* ------------------------------------------------------------------ */
/* ابزارهای نمایش                                                      */
/* ------------------------------------------------------------------ */

const jalaliDate = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
});

const jalaliDateTime = new Intl.DateTimeFormat('fa-IR-u-ca-persian', {
  year: 'numeric',
  month: 'long',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
});

export function formatDate(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return jalaliDate.format(date);
}

export function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '—';
  return jalaliDateTime.format(date);
}

/** تبدیل ISO به مقدار ورودی datetime-local بر پایهٔ زمان محلی کاربر. */
export function toLocalInput(value?: string | null): string {
  const date = value ? new Date(value) : new Date();
  if (Number.isNaN(date.getTime())) return '';
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(
    date.getHours(),
  )}:${pad(date.getMinutes())}`;
}

export function fromLocalInput(value: string): string {
  if (!value) return '';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString();
}

export function toPersianDigits(value: number | string): string {
  return String(value).replace(/\d/g, (digit) => '۰۱۲۳۴۵۶۷۸۹'[Number(digit)]);
}

export const MEETING_STATUS_LABELS: Record<string, string> = {
  scheduled: 'برنامه‌ریزی‌شده',
  held: 'برگزارشده',
  cancelled: 'لغوشده',
};

export const MINUTES_STATUS_LABELS: Record<string, string> = {
  draft: 'پیش‌نویس',
  in_review: 'در انتظار تأیید',
  approved: 'تأییدشده',
  locked: 'نهایی و قفل‌شده',
};

export const ACTION_STATUS_LABELS: Record<string, string> = {
  open: 'باز',
  in_progress: 'در حال انجام',
  done: 'انجام‌شده',
  overdue: 'دارای تأخیر',
};

export const RSVP_LABELS: Record<string, string> = {
  pending: 'بی‌پاسخ',
  accepted: 'حضور می‌یابم',
  declined: 'حضور ندارم',
  tentative: 'نامطمئن',
};

export const JOB_STATUS_LABELS: Record<string, string> = {
  queued: 'در صف',
  running: 'در حال پردازش',
  succeeded: 'موفق',
  failed: 'ناموفق',
};

export const JOB_TYPE_LABELS: Record<string, string> = {
  transcribe: 'رونویسی صوت',
  minutes_draft: 'پیش‌نویس صورتجلسه',
};

export function formatMinutes(seconds?: number | null): string {
  const total = Math.max(Math.round((seconds || 0) / 60), 0);
  return `${toPersianDigits(total)} دقیقه`;
}
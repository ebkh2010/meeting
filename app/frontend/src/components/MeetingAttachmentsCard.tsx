/**
 * کارت «فایل‌های پیوست دستور جلسه».
 *
 * قواعد:
 * - همهٔ اعضای سازمان فهرست پیوست‌ها را می‌بینند و می‌توانند دانلود کنند.
 * - بارگذاری، حذف و «ارسال دوبارهٔ دستور جلسه و پیوست‌ها» فقط برای مدیر سازمان
 *   یا دبیر همان جلسه فعال است؛ همان قید در بک‌اند نیز اعمال می‌شود.
 * - فایل در باکت خصوصی ذخیره می‌شود؛ دانلود همیشه با پیوند امضاشدهٔ کوتاه‌عمر.
 * - بارگذاری چندفایلی با درصد پیشرفت واقعی، امکان لغو هر فایل و پیام خطای فارسی
 *   برای هر فایل انجام می‌شود تا هیچ آپلودی بی‌صدا شکست نخورد.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Download, Loader2, Paperclip, Send, Trash2, Upload, X } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Progress } from '@/components/ui/progress';
import { Separator } from '@/components/ui/separator';
import {
  api,
  downloadAttachment,
  errorMessage,
  formatDateTime,
  formatFileSize,
  MeetingAttachment,
  toPersianDigits,
  uploadMeetingAttachment,
  validateAttachmentFile,
} from '@/lib/mgmt';

const ACCEPTED_EXTENSIONS =
  '.pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.csv,.png,.jpg,.jpeg,.webp,.zip';

/** وضعیت بارگذاری هر فایل در صف، برای نمایش نوار پیشرفت مستقل. */
interface UploadRow {
  id: string;
  name: string;
  size: number;
  percent: number;
  status: 'waiting' | 'uploading' | 'done' | 'failed' | 'canceled';
  message: string;
  controller: AbortController;
}

interface Props {
  meetingId: number;
  canManage: boolean;
}

export default function MeetingAttachmentsCard({ meetingId, canManage }: Props) {
  const [items, setItems] = useState<MeetingAttachment[]>([]);
  const [loading, setLoading] = useState(true);
  const [queue, setQueue] = useState<UploadRow[]>([]);
  const [uploading, setUploading] = useState(false);
  const [sending, setSending] = useState(false);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await api.listAttachments(meetingId);
      setItems(data.items);
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت فهرست پیوست‌ها ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, [meetingId]);

  useEffect(() => {
    load();
  }, [load]);

  const patchRow = (id: string, patch: Partial<UploadRow>) => {
    setQueue((rows) => rows.map((row) => (row.id === id ? { ...row, ...patch } : row)));
  };

  /** بارگذاری ترتیبی صف؛ هر فایل پیشرفت و پیام مستقل خود را دارد. */
  const handleUpload = async (selected: FileList | null) => {
    const files = Array.from(selected || []);
    if (fileRef.current) fileRef.current.value = '';
    if (files.length === 0) return;

    const rows: UploadRow[] = files.map((file, index) => {
      const problem = validateAttachmentFile(file);
      return {
        id: `${Date.now()}-${index}-${file.name}`,
        name: file.name,
        size: file.size,
        percent: 0,
        status: problem ? 'failed' : 'waiting',
        message: problem,
        controller: new AbortController(),
      };
    });

    setQueue((prev) => [...prev, ...rows]);
    rows.filter((row) => row.status === 'failed').forEach((row) => toast.error(row.message));

    const pending = rows
      .map((row, index) => ({ row, file: files[index] }))
      .filter((pair) => pair.row.status === 'waiting');
    if (pending.length === 0) return;

    setUploading(true);
    let success = 0;
    let failed = 0;

    for (const { row, file } of pending) {
      if (row.controller.signal.aborted) {
        patchRow(row.id, { status: 'canceled', message: 'بارگذاری لغو شد.' });
        continue;
      }
      patchRow(row.id, { status: 'uploading', message: '' });
      try {
        await uploadMeetingAttachment(meetingId, file, {
          signal: row.controller.signal,
          onProgress: (progress) => patchRow(row.id, { percent: progress.percent }),
        });
        success += 1;
        patchRow(row.id, { status: 'done', percent: 100, message: 'با موفقیت ثبت شد.' });
      } catch (err) {
        const message = errorMessage(err, `بارگذاری «${file.name}» ناموفق بود.`);
        if (row.controller.signal.aborted) {
          patchRow(row.id, { status: 'canceled', message: 'بارگذاری لغو شد.' });
        } else {
          failed += 1;
          patchRow(row.id, { status: 'failed', message });
          toast.error(message);
        }
      }
    }

    setUploading(false);
    if (success > 0) {
      toast.success(
        failed > 0
          ? `${toPersianDigits(success)} فایل ثبت شد و ${toPersianDigits(failed)} فایل ناموفق بود.`
          : `${toPersianDigits(success)} فایل پیوست ثبت شد.`,
      );
      await load();
    }
  };

  const handleDownload = async (attachment: MeetingAttachment) => {
    try {
      const result = await downloadAttachment(attachment.id);
      if (result.fallback_url) {
        window.open(result.fallback_url, '_blank', 'noopener');
      }
    } catch (err) {
      toast.error(errorMessage(err, 'دریافت پیوند دانلود ناموفق بود.'));
    }
  };

  const handleDelete = async (attachment: MeetingAttachment) => {
    setDeletingId(attachment.id);
    try {
      await api.deleteAttachment(attachment.id);
      toast.success('فایل پیوست حذف شد.');
      await load();
    } catch (err) {
      toast.error(errorMessage(err, 'حذف فایل پیوست ناموفق بود.'));
    } finally {
      setDeletingId(null);
    }
  };

  const handleResend = async () => {
    setSending(true);
    try {
      const result = await api.resendAgenda(meetingId);
      const attachmentsSent = result.attachments_sent ?? 0;
      const detail = result.detail || `${toPersianDigits(result.email_sent)} ایمیل ارسال شد`;
      toast.success(
        detail +
          (attachmentsSent
            ? `؛ ${toPersianDigits(attachmentsSent)} فایل پیوست به ایمیل ضمیمه شد`
            : ''),
      );
    } catch (err) {
      toast.error(errorMessage(err, 'ارسال دوبارهٔ دستور جلسه ناموفق بود.'));
    } finally {
      setSending(false);
    }
  };

  const statusLabel = (row: UploadRow) => {
    if (row.status === 'uploading') return `${toPersianDigits(row.percent)}٪`;
    if (row.status === 'done') return 'کامل شد';
    if (row.status === 'canceled') return 'لغو شد';
    if (row.status === 'failed') return 'ناموفق';
    return 'در انتظار';
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <Paperclip className="h-4 w-4" />
          فایل‌های پیوست دستور جلسه
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {loading ? (
          <p className="text-sm text-muted-foreground">در حال دریافت فهرست پیوست‌ها…</p>
        ) : items.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            فایلی پیوست نشده است. پیوست‌ها همراه ایمیل دعوت برای حاضران ارسال می‌شوند.
          </p>
        ) : (
          <ul className="space-y-2">
            {items.map((attachment) => (
              <li
                key={attachment.id}
                className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-border p-3"
              >
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium" dir="auto">
                    {attachment.file_name}
                  </p>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {formatFileSize(attachment.size_bytes)}
                    {attachment.uploaded_by_name && ` • ${attachment.uploaded_by_name}`}
                    {attachment.created_at && ` • ${formatDateTime(attachment.created_at)}`}
                  </p>
                </div>
                <div className="flex items-center gap-1">
                  <Button
                    size="icon"
                    variant="ghost"
                    aria-label="دانلود پیوست"
                    onClick={() => handleDownload(attachment)}
                  >
                    <Download className="h-4 w-4" />
                  </Button>
                  {canManage && (
                    <Button
                      size="icon"
                      variant="ghost"
                      aria-label="حذف پیوست"
                      disabled={deletingId === attachment.id}
                      onClick={() => handleDelete(attachment)}
                    >
                      {deletingId === attachment.id ? (
                        <Loader2 className="h-4 w-4 animate-spin" />
                      ) : (
                        <Trash2 className="h-4 w-4" />
                      )}
                    </Button>
                  )}
                </div>
              </li>
            ))}
          </ul>
        )}

        {queue.length > 0 && (
          <div className="space-y-2 rounded-md border border-border bg-muted/40 p-3">
            {queue.map((row) => (
              <div key={row.id} className="space-y-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="min-w-0 truncate text-xs font-medium" dir="auto">
                    {row.name}
                  </span>
                  <span className="flex items-center gap-1 text-xs text-muted-foreground">
                    {statusLabel(row)}
                    {(row.status === 'uploading' || row.status === 'waiting') && (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-6 w-6"
                        aria-label="لغو بارگذاری"
                        onClick={() => row.controller.abort()}
                      >
                        <X className="h-3 w-3" />
                      </Button>
                    )}
                  </span>
                </div>
                <Progress value={row.status === 'done' ? 100 : row.percent} className="h-1.5" />
                {row.message && (
                  <p
                    className={`text-xs ${row.status === 'failed' ? 'text-destructive' : 'text-muted-foreground'}`}
                  >
                    {row.message}
                  </p>
                )}
              </div>
            ))}
            {!uploading && (
              <Button
                size="sm"
                variant="ghost"
                className="h-7 px-2 text-xs"
                onClick={() => setQueue([])}
              >
                پاک کردن فهرست بارگذاری
              </Button>
            )}
          </div>
        )}

        {canManage && (
          <>
            <Separator />
            <input
              ref={fileRef}
              type="file"
              multiple
              className="hidden"
              accept={ACCEPTED_EXTENSIONS}
              onChange={(event) => handleUpload(event.target.files)}
            />
            <div className="flex flex-wrap gap-2">
              <Button
                variant="outline"
                className="gap-2 !bg-transparent"
                disabled={uploading}
                onClick={() => fileRef.current?.click()}
              >
                {uploading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Upload className="h-4 w-4" />
                )}
                افزودن فایل پیوست
              </Button>
              <Button className="gap-2" disabled={sending} onClick={handleResend}>
                {sending ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <Send className="h-4 w-4" />
                )}
                ارسال دوبارهٔ دستور جلسه و پیوست‌ها
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              حداکثر حجم هر فایل ۲۵ مگابایت. نام فارسی فایل پشتیبانی می‌شود. فایل‌های بزرگ‌تر از ۸
              مگابایت به ایمیل ضمیمه نمی‌شوند و فقط نام آن‌ها در متن دعوت می‌آید.
            </p>
          </>
        )}
      </CardContent>
    </Card>
  );
}
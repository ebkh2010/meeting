/**
 * انتخابگر فایل با ظاهر فارسی.
 *
 * چرا لازم است: `<input type="file">` بومی مرورگر برچسبش («Choose File / No file
 * chosen») را از زبان خود مرورگر می‌گیرد و در رابط فارسی هم انگلیسی دیده می‌شود.
 * اینجا ورودی بومی با `sr-only` پنهان می‌شود و یک کلید فارسی جای آن را می‌گیرد.
 */
import { useRef } from 'react';
import { Paperclip } from 'lucide-react';
import { Button } from '@/components/ui/button';

export default function FilePicker({
  id,
  multiple = false,
  accept,
  onSelect,
  disabled = false,
  label = 'انتخاب فایل',
  hint,
}: {
  id?: string;
  multiple?: boolean;
  accept?: string;
  /** فایل‌های انتخاب‌شده؛ ``null`` یعنی کاربر انتخاب را لغو کرد. */
  onSelect: (files: FileList | null) => void;
  disabled?: boolean;
  label?: string;
  /** توضیح کوتاه کنار کلید (مثلاً سقف حجم یا فرمت‌های مجاز). */
  hint?: string;
}) {
  const inputRef = useRef<HTMLInputElement>(null);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <input
        ref={inputRef}
        id={id}
        type="file"
        multiple={multiple}
        accept={accept}
        className="sr-only"
        disabled={disabled}
        onChange={(event) => {
          onSelect(event.target.files);
          // بازنشانی مقدار تا انتخاب دوبارهٔ همان فایل هم رویداد بدهد.
          event.target.value = '';
        }}
      />
      <Button
        type="button"
        variant="outline"
        className="gap-2"
        disabled={disabled}
        onClick={() => inputRef.current?.click()}
      >
        <Paperclip className="h-4 w-4" />
        {label}
      </Button>
      {hint ? <span className="text-xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

/**
 * نمایشگر انتظار با گیف برند.
 *
 * چرا کامپوننت مشترک: چند نقطه از برنامه (آماده‌سازی فضای کاری، ایجاد جلسهٔ جدید،
 * انتظار کارهای AI) به یک حالت انتظار یکسان نیاز دارند. با یک کامپوننت، اندازه و
 * متن کنترل‌شده باقی می‌ماند و گیف در همه‌جا یک‌شکل دیده می‌شود.
 *
 * دسترس‌پذیری: گیف نقش تزئینی/وضعیتی دارد، پس ظرف بیرونی `role="status"` می‌گیرد و
 * متن انتظار برای صفحه‌خوان‌ها خوانده می‌شود.
 */
import { cn } from '@/lib/utils';

/** مسیر گیف در دارایی‌های عمومی؛ فایل توسط کاربر ارائه شده است. */
const LOADER_GIF = '/assets/loader.gif';

const SIZE_CLASS: Record<'sm' | 'md' | 'lg', string> = {
  sm: 'h-16 w-16',
  md: 'h-28 w-28',
  lg: 'h-40 w-40',
};

export interface LoadingGifProps {
  /** متن وضعیت زیر گیف؛ اگر خالی باشد فقط گیف نمایش داده می‌شود. */
  label?: string;
  /** توضیح کمکی زیر متن اصلی. */
  hint?: string;
  size?: 'sm' | 'md' | 'lg';
  className?: string;
}

export default function LoadingGif({
  label = 'در حال آماده‌سازی…',
  hint,
  size = 'md',
  className,
}: LoadingGifProps) {
  return (
    <div
      role="status"
      aria-live="polite"
      dir="rtl"
      className={cn('flex flex-col items-center justify-center gap-3 text-center', className)}
    >
      <img
        src={LOADER_GIF}
        alt=""
        aria-hidden="true"
        className={cn('object-contain', SIZE_CLASS[size])}
      />
      {label && <p className="text-sm font-medium text-foreground">{label}</p>}
      {hint && <p className="max-w-xs text-xs leading-6 text-muted-foreground">{hint}</p>}
    </div>
  );
}
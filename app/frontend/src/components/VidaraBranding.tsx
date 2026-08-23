/**
 * بلوک برندینگ ویدارا: لوگو در کنار عبارت رسمی نسخهٔ آزمایشی.
 * در فوتر لندینگ، پوستهٔ فضای کاری و نمای چاپ استفاده می‌شود.
 */
import { cn } from '@/lib/utils';

const BRANDING_TEXT = 'توسعه داده شده توسط تیم ویدارا. نسخه آزمایشی';

interface VidaraBrandingProps {
  className?: string;
  /** نمای چاپ: رنگ‌های خاکستری تیره روی کاغذ سفید */
  variant?: 'app' | 'print';
}

export default function VidaraBranding({ className, variant = 'app' }: VidaraBrandingProps) {
  const isPrint = variant === 'print';

  return (
    <div
      dir="rtl"
      className={cn(
        'flex flex-row-reverse items-center justify-center gap-2 text-center sm:justify-start sm:text-right',
        className,
      )}
    >
      <span
        className={cn(
          'inline-flex shrink-0 items-center justify-center rounded-md bg-white p-1 ring-1',
          isPrint ? 'ring-border' : 'ring-border/70',
        )}
      >
        <img
          src="/assets/vidara-icon.png"
          alt="لوگوی تیم ویدارا"
          width={22}
          height={22}
          loading="lazy"
          className="h-[22px] w-[22px] object-contain"
        />
      </span>
      <span
        className={cn(
          'text-xs leading-6 sm:text-[13px]',
          isPrint ? 'text-muted-foreground' : 'text-muted-foreground',
        )}
      >
        {BRANDING_TEXT}
      </span>
    </div>
  );
}
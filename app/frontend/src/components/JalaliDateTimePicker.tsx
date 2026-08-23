/**
 * انتخابگر تاریخ و ساعت با تقویم هجری شمسی.
 *
 * قواعد:
 * - نمایش و انتخاب کامل شمسی (نام ماه فارسی، هفته از شنبه، تشخیص «امروز»).
 * - مقدار ورودی/خروجی همیشه ISO است تا قرارداد بک‌اند تغییر نکند.
 * - در موبایل تمام‌عرض و با ناحیهٔ لمسی مناسب رندر می‌شود.
 */
import { useEffect, useMemo, useState } from 'react';
import { CalendarDays, ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import {
  dateToJalali,
  faDigits,
  formatJalaliDateTime,
  isSameDay,
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  jalaliMonthGrid,
  jalaliToDate,
} from '@/lib/jalali';

interface JalaliDateTimePickerProps {
  /** مقدار فعلی به‌صورت ISO (خالی = بدون انتخاب). */
  value: string;
  /** با هر انتخاب، مقدار ISO تازه برگردانده می‌شود. */
  onChange: (iso: string) => void;
  id?: string;
  disabled?: boolean;
  /** نمایش انتخاب ساعت و دقیقه. */
  withTime?: boolean;
  className?: string;
}

const HOURS = Array.from({ length: 24 }, (_, index) => index);
const MINUTES = Array.from({ length: 12 }, (_, index) => index * 5);

export default function JalaliDateTimePicker({
  value,
  onChange,
  id,
  disabled = false,
  withTime = true,
  className,
}: JalaliDateTimePickerProps) {
  const parsed = useMemo(() => {
    if (!value) return null;
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }, [value]);

  const today = useMemo(() => new Date(), []);
  const base = parsed ?? today;
  const [open, setOpen] = useState(false);
  const [view, setView] = useState(() => {
    const [jy, jm] = dateToJalali(base);
    return { year: jy, month: jm };
  });

  useEffect(() => {
    if (!parsed) return;
    const [jy, jm] = dateToJalali(parsed);
    setView({ year: jy, month: jm });
  }, [parsed]);

  const cells = useMemo(() => jalaliMonthGrid(view.year, view.month), [view]);
  const [selectedYear, selectedMonth, selectedDay] = parsed ? dateToJalali(parsed) : [0, 0, 0];

  const shiftMonth = (delta: number) => {
    setView((current) => {
      let month = current.month + delta;
      let year = current.year;
      if (month < 1) {
        month = 12;
        year -= 1;
      } else if (month > 12) {
        month = 1;
        year += 1;
      }
      return { year, month };
    });
  };

  const emit = (date: Date) => onChange(date.toISOString());

  const pickDay = (day: number) => {
    const hours = parsed ? parsed.getHours() : 9;
    const minutes = parsed ? parsed.getMinutes() : 0;
    emit(jalaliToDate(view.year, view.month, day, hours, minutes));
    if (!withTime) setOpen(false);
  };

  const pickToday = () => {
    const hours = parsed ? parsed.getHours() : today.getHours();
    const minutes = parsed ? parsed.getMinutes() : 0;
    const [jy, jm, jd] = dateToJalali(today);
    setView({ year: jy, month: jm });
    emit(jalaliToDate(jy, jm, jd, hours, minutes));
  };

  const setClock = (hours: number, minutes: number) => {
    const source = parsed ?? today;
    const [jy, jm, jd] = dateToJalali(source);
    emit(jalaliToDate(jy, jm, jd, hours, minutes));
  };

  const currentHour = parsed ? parsed.getHours() : 9;
  const currentMinute = parsed ? parsed.getMinutes() : 0;
  const minuteOptions = MINUTES.includes(currentMinute)
    ? MINUTES
    : [...MINUTES, currentMinute].sort((a, b) => a - b);

  return (
    <Popover open={open} onOpenChange={(next) => !disabled && setOpen(next)}>
      <PopoverTrigger asChild>
        <Button
          id={id}
          type="button"
          variant="outline"
          disabled={disabled}
          className={cn(
            '!bg-transparent hover:!bg-transparent h-11 w-full justify-between gap-2 text-right font-normal',
            !parsed && 'text-muted-foreground',
            className,
          )}
        >
          <span className="truncate">
            {parsed
              ? withTime
                ? formatJalaliDateTime(parsed)
                : formatJalaliDateTime(parsed).split(' — ')[0]
              : 'انتخاب تاریخ جلسه'}
          </span>
          <CalendarDays className="h-4 w-4 shrink-0 text-muted-foreground" />
        </Button>
      </PopoverTrigger>
      <PopoverContent align="start" className="w-[19rem] p-3" dir="rtl">
        <div className="mb-2 flex items-center justify-between gap-2">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="ماه بعد"
            onClick={() => shiftMonth(1)}
          >
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <p className="text-sm font-semibold">
            {JALALI_MONTHS[view.month - 1]} {faDigits(view.year)}
          </p>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            aria-label="ماه قبل"
            onClick={() => shiftMonth(-1)}
          >
            <ChevronRight className="h-4 w-4" />
          </Button>
        </div>

        <div className="grid grid-cols-7 gap-1 text-center text-xs text-muted-foreground">
          {JALALI_WEEKDAYS.map((day) => (
            <span key={day} className="py-1">
              {day}
            </span>
          ))}
        </div>

        <div className="mt-1 grid grid-cols-7 gap-1">
          {cells.map((day, index) => {
            if (day === null) return <span key={`empty-${index}`} className="h-9" />;
            const cellDate = jalaliToDate(view.year, view.month, day);
            const isToday = isSameDay(cellDate, today);
            const isSelected =
              parsed !== null &&
              selectedYear === view.year &&
              selectedMonth === view.month &&
              selectedDay === day;
            return (
              <button
                key={`day-${day}`}
                type="button"
                onClick={() => pickDay(day)}
                className={cn(
                  'h-9 rounded-md text-sm transition-colors',
                  isSelected
                    ? 'bg-primary font-semibold text-primary-foreground'
                    : 'hover:bg-accent hover:text-accent-foreground',
                  !isSelected && isToday && 'ring-1 ring-primary/60 font-semibold text-primary',
                )}
              >
                {faDigits(day)}
              </button>
            );
          })}
        </div>

        {withTime && (
          <div className="mt-3 space-y-2 border-t border-border pt-3">
            <p className="text-xs text-muted-foreground">ساعت شروع جلسه</p>
            <div className="flex items-center gap-2">
              <Select
                value={String(currentHour)}
                onValueChange={(next) => setClock(Number(next), currentMinute)}
              >
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-56">
                  {HOURS.map((hour) => (
                    <SelectItem key={hour} value={String(hour)}>
                      {faDigits(String(hour).padStart(2, '0'))}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <span className="text-sm text-muted-foreground">:</span>
              <Select
                value={String(currentMinute)}
                onValueChange={(next) => setClock(currentHour, Number(next))}
              >
                <SelectTrigger className="h-10">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent className="max-h-56">
                  {minuteOptions.map((minute) => (
                    <SelectItem key={minute} value={String(minute)}>
                      {faDigits(String(minute).padStart(2, '0'))}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>
        )}

        <div className="mt-3 flex items-center justify-between gap-2">
          <Button type="button" variant="secondary" size="sm" onClick={pickToday}>
            امروز
          </Button>
          <Button type="button" size="sm" onClick={() => setOpen(false)}>
            تأیید
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
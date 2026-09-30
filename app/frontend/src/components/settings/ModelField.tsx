/**
 * فیلد مشترک «انتخاب مدل» برای همهٔ جاهایی که تنظیمات هوش مصنوعی دارند.
 *
 * مدل از فهرست پیشنهادی انتخاب می‌شود و گزینهٔ «مدل دیگر…» امکان ثبت نام تازه را
 * بدون تغییر کد می‌دهد. مقدار نهایی همان رشتهٔ مدل می‌ماند تا با قرارداد بک‌اند
 * یکی باشد.
 */
import { useState } from 'react';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

export default function ModelField({
  label = 'مدل',
  value,
  options,
  onChange,
  hint,
}: {
  label?: string;
  value: string;
  options: string[];
  onChange: (value: string) => void;
  hint?: string;
}) {
  const known = options.includes(value);
  const [custom, setCustom] = useState(false);
  const showInput = custom || !known;
  return (
    <div className="space-y-1">
      <Label className="text-xs">{label}</Label>
      <Select
        value={known ? value : '__custom__'}
        onValueChange={(next) => {
          if (next === '__custom__') {
            setCustom(true);
            return;
          }
          setCustom(false);
          onChange(next);
        }}
      >
        <SelectTrigger>
          <SelectValue placeholder="انتخاب مدل" />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option} value={option}>
              {option}
            </SelectItem>
          ))}
          <SelectItem value="__custom__">مدل دیگر…</SelectItem>
        </SelectContent>
      </Select>
      {showInput && (
        <Input
          value={value}
          dir="ltr"
          className="text-left"
          placeholder="نام دقیق مدل"
          onChange={(event) => onChange(event.target.value)}
        />
      )}
      {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

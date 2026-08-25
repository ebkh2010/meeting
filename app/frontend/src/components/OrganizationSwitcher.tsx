/**
 * تغییر سازمان فعال نشست بدون خروج کامل از سامانه.
 *
 * فهرست سازمان‌هایی که همین شخص در آن‌ها حساب فعال دارد از بک‌اند خوانده می‌شود.
 * پس از انتخاب سازمان و تأیید رمز عبور همان سازمان، توکن تازه با نقش سازمان
 * مقصد صادر می‌شود؛ بنابراین همهٔ گاردهای دسترسی (از جمله آیکون تنظیمات مدیر)
 * از سازمان جدید خوانده می‌شوند.
 */
import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Building2, Check, RefreshCw } from 'lucide-react';
import { toast } from 'sonner';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
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
import { errorMessage } from '@/lib/mgmt';
import { authApi, type LoginOrganizationOption } from '@/lib/appAuth';

interface OrganizationSwitcherProps {
  /** نام سازمان فعال فعلی برای نمایش در دکمه. */
  currentName: string;
  /** پس از تغییر موفق سازمان صدا زده می‌شود تا دادهٔ فضای کاری بازخوانی شود. */
  onSwitched: () => void;
  /**
   * حالت کنترل‌شده؛ برای بازکردن دیالوگ از منوی همبرگری موبایل استفاده می‌شود تا
   * دیالوگ داخل drawer تودرتو نشود.
   */
  open?: boolean;
  onOpenChange?: (value: boolean) => void;
  /** پنهان‌کردن دکمهٔ trigger در حالت کنترل‌شده. */
  hideTrigger?: boolean;
}

export default function OrganizationSwitcher({
  currentName,
  onSwitched,
  open: controlledOpen,
  onOpenChange,
  hideTrigger = false,
}: OrganizationSwitcherProps) {
  const navigate = useNavigate();
  const [uncontrolledOpen, setUncontrolledOpen] = useState(false);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : uncontrolledOpen;
  const setOpen = useCallback(
    (value: boolean) => {
      if (!isControlled) setUncontrolledOpen(value);
      onOpenChange?.(value);
    },
    [isControlled, onOpenChange],
  );
  const [items, setItems] = useState<LoginOrganizationOption[]>([]);
  const [currentId, setCurrentId] = useState<number | null>(null);
  const [targetId, setTargetId] = useState<number | null>(null);
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await authApi.myOrganizations();
      setItems(data.items || []);
      setCurrentId(data.current_organization_id ?? null);
      const firstOther = (data.items || []).find(
        (item) => item.organization_id !== data.current_organization_id,
      );
      setTargetId(firstOther ? firstOther.organization_id : null);
    } catch (error) {
      toast.error(errorMessage(error, 'دریافت فهرست سازمان‌ها ناموفق بود.'));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      setPassword('');
      load();
    }
  }, [open, load]);

  const submit = async () => {
    if (!targetId) {
      toast.error('سازمان مقصد را انتخاب کنید.');
      return;
    }
    if (!password.trim()) {
      toast.error('رمز عبور حساب خود در سازمان مقصد را وارد کنید.');
      return;
    }
    setBusy(true);
    try {
      const result = await authApi.switchOrganization(targetId, password);
      toast.success(
        `سازمان فعال به «${result.organization.name}» تغییر کرد؛ نقش شما: ${result.user.role_label}`,
      );
      setOpen(false);
      setPassword('');
      // اگر حساب سازمان مقصد را مدیر ساخته باشد و هنوز مشخصات تکمیل نشده، کاربر
      // پیش از فضای کاری باید صفحهٔ تکمیل مشخصات را ببیند.
      if (result.user?.must_change_password) {
        navigate('/complete-profile', { replace: true });
        return;
      }
      onSwitched();
    } catch (error) {
      toast.error(errorMessage(error, 'تغییر سازمان ناموفق بود.'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      {!hideTrigger && (
        <DialogTrigger asChild>
          <Button
            size="sm"
            variant="ghost"
            className="flex items-center gap-1.5"
            title="تغییر سازمان"
          >
            <Building2 className="h-4 w-4" />
            <span className="max-w-[10rem] truncate">{currentName || 'سازمان من'}</span>
          </Button>
        </DialogTrigger>
      )}
      <DialogContent
        className="max-h-[90vh] w-[calc(100vw-1.5rem)] overflow-y-auto sm:max-w-lg"
        dir="rtl"
      >
        <DialogHeader>
          <DialogTitle>تغییر سازمان فعال</DialogTitle>
          <DialogDescription>
            نقش و دسترسی‌های شما همیشه از سازمان فعال نشست خوانده می‌شود. برای تغییر سازمان نیازی
            به خروج کامل نیست.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <Label>سازمان‌های شما</Label>
            <Button size="sm" variant="outline" onClick={load} disabled={loading} className="gap-1.5">
              <RefreshCw className={`h-4 w-4 ${loading ? 'animate-spin' : ''}`} />
              بازخوانی
            </Button>
          </div>

          {items.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              {loading ? 'در حال دریافت…' : 'سازمان دیگری برای شما ثبت نشده است.'}
            </p>
          ) : (
            <div className="space-y-2">
              {items.map((item) => {
                const isCurrent = item.organization_id === currentId;
                const isTarget = item.organization_id === targetId;
                return (
                  <button
                    key={item.organization_id}
                    type="button"
                    disabled={isCurrent}
                    onClick={() => setTargetId(item.organization_id)}
                    className={`flex w-full items-center justify-between gap-2 rounded-md border p-3 text-right transition ${
                      isCurrent
                        ? 'cursor-default border-border bg-muted/50'
                        : isTarget
                          ? 'border-primary bg-primary/5'
                          : 'border-border hover:bg-accent/40'
                    }`}
                  >
                    <span className="min-w-0">
                      <span className="block truncate text-sm font-medium">{item.name}</span>
                      <span className="block text-xs text-muted-foreground">
                        نقش شما: {item.role_label}
                      </span>
                    </span>
                    {isCurrent ? (
                      <Badge variant="secondary" className="shrink-0">
                        سازمان فعال
                      </Badge>
                    ) : (
                      isTarget && <Check className="h-4 w-4 shrink-0 text-primary" />
                    )}
                  </button>
                );
              })}
            </div>
          )}

          {targetId !== null && (
            <div className="space-y-2">
              <Label htmlFor="switch-password">رمز عبور حساب شما در سازمان مقصد</Label>
              <Input
                id="switch-password"
                type="password"
                autoComplete="current-password"
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Enter') submit();
                }}
              />
              <p className="text-xs text-muted-foreground">
                برای جلوگیری از ارتقای ناخواستهٔ دسترسی، رمز عبور همان سازمان بررسی می‌شود.
              </p>
            </div>
          )}
        </div>

        <DialogFooter className="gap-2">
          <Button
            variant="outline"
            className="min-h-11 w-full sm:w-auto"
            onClick={() => setOpen(false)}
            disabled={busy}
          >
            بستن
          </Button>
          <Button
            className="min-h-11 w-full sm:w-auto"
            onClick={submit}
            disabled={busy || targetId === null}
          >
            {busy ? 'در حال تغییر…' : 'تغییر سازمان'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
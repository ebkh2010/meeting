/**
 * فیلدهای اعتبارنامهٔ یک سرویس هوش مصنوعی — مشترک بین همهٔ پنل‌ها.
 *
 * قاعدهٔ تجربهٔ کاربری (خواستهٔ کارفرما): برای سرویس‌های کلیدمحور مثل DeepSeek
 * فقط «توکن» پرسیده می‌شود؛ نشانی سرویس و مدل پیش‌فرض خودکار اعمال می‌شوند و
 * تنظیمات فنی در بخش «تنظیمات پیشرفته» پنهان می‌مانند.
 */
import { KeyRound, Trash2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

export interface AiCredentialState {
  apiKey: string;
  password: string;
  authUsername: string;
  clearApiKey: boolean;
  clearPassword: boolean;
}

export default function AiCredentialFields({
  authMode,
  apiKey,
  password,
  authUsername,
  apiKeyMasked,
  passwordMasked,
  hasApiKey,
  hasPassword,
  clearApiKey,
  clearPassword,
  onChange,
  tokenLabel = 'توکن / کلید API',
}: {
  authMode: string;
  apiKey: string;
  password: string;
  authUsername: string;
  apiKeyMasked: string;
  passwordMasked: string;
  hasApiKey: boolean;
  hasPassword: boolean;
  clearApiKey: boolean;
  clearPassword: boolean;
  onChange: (patch: Partial<AiCredentialState>) => void;
  tokenLabel?: string;
}) {
  const usesLogin = authMode === 'username_password';
  const hasSaved = usesLogin ? hasPassword : hasApiKey;
  const clearing = usesLogin ? clearPassword : clearApiKey;

  return (
    <div className="space-y-2">
      {usesLogin ? (
        <>
          <div className="space-y-1">
            <Label className="text-xs">نام کاربری سرویس</Label>
            <Input
              value={authUsername}
              dir="ltr"
              className="text-left"
              placeholder="نام کاربری سرویس"
              onChange={(event) => onChange({ authUsername: event.target.value })}
            />
          </div>
          <div className="space-y-1">
            <Label className="text-xs">رمز عبور سرویس</Label>
            <Input
              type="password"
              value={password}
              dir="ltr"
              className="text-left"
              placeholder={
                hasPassword
                  ? `ثبت‌شده: ${passwordMasked} — برای تغییر مقدار تازه وارد کنید`
                  : 'رمز سرویس را وارد کنید'
              }
              onChange={(event) => onChange({ password: event.target.value, clearPassword: false })}
            />
          </div>
          <p className="text-[11px] text-muted-foreground">
            این سرویس با نام کاربری و رمز کار می‌کند و توکن جداگانه لازم ندارد.
          </p>
        </>
      ) : (
        <>
          <div className="space-y-1">
            <Label className="text-xs">{tokenLabel}</Label>
            <Input
              type="password"
              value={apiKey}
              dir="ltr"
              className="text-left"
              placeholder={
                hasApiKey
                  ? `ثبت‌شده: ${apiKeyMasked} — برای تغییر مقدار تازه وارد کنید`
                  : 'توکن سرویس را وارد کنید'
              }
              onChange={(event) => onChange({ apiKey: event.target.value, clearApiKey: false })}
            />
          </div>
          <p className="text-[11px] text-muted-foreground">
            فقط همین توکن لازم است؛ نشانی سرویس و مدل به‌صورت پیش‌فرض اعمال می‌شوند.
          </p>
        </>
      )}

      {hasSaved && !clearing && (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <KeyRound className="h-3.5 w-3.5" />
          <span>{usesLogin ? `رمز ثبت‌شده: ${passwordMasked}` : `توکن ثبت‌شده: ${apiKeyMasked}`}</span>
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-destructive"
            onClick={() =>
              usesLogin
                ? onChange({ clearPassword: true, password: '' })
                : onChange({ clearApiKey: true, apiKey: '' })
            }
          >
            <Trash2 className="h-3.5 w-3.5" />
            حذف
          </Button>
        </div>
      )}
      {clearing && (
        <p className="text-xs text-destructive">
          {usesLogin ? 'رمز' : 'توکن'} با ذخیره‌کردن حذف می‌شود و سرویس تا ثبت مقدار تازه غیرفعال
          می‌ماند.
        </p>
      )}
    </div>
  );
}

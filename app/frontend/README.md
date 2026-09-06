# ویدارا — نسخهٔ جلسات (Frontend)

رابط کاربری راست‌به‌چپ (RTL فارسی) سامانهٔ مدیریت جلسات ویدارا.

## پشتهٔ فنی

- Vite 5 + React 18 + TypeScript
- shadcn/ui + Tailwind CSS (توکن‌های برند در `tailwind.config.ts` و `src/index.css`)
- react-router-dom (SPA)، sonner (toast)، markdown-to-jsx، lucide-react

## ساختار پوشه‌ها

- `index.html` — نقطهٔ ورود (متادیتا و فاویکون برند)
- `vite.config.ts` — پیکربندی بیلد و prerender صفحات بلاگ
- `src/main.tsx` — نقطهٔ اجرا + نگهبان خطای chunk + تثبیت برند (`lib/brand.ts`)
- `src/App.tsx` — مسیرها: `/` ورود، `/dashboard`، `/meetings`، `/meetings/:meetingId`، `/settings`، `/account`، `/complete-profile`، `/print/:meetingId`، `/platform` (مدیر پلتفرم)، `/blog/*`
- `src/pages/` — صفحات سامانه
- `src/components/` — پوسته‌ها (`AppShell`، `PlatformShell`)، پنل دستیار، مصرف توکن، و `ui/` (اجزای shadcn)، `settings/`، `blog/`
- `src/lib/` — کلاینت‌های API (`mgmt.ts`، `appAuth.ts`، `platform.ts`، `assistant.ts`، …)، تقویم شمسی (`jalali.ts`)، نشست (`session.ts`) و ابزارها (`utils.ts` شامل نرمال‌سازی فارسی و برجسته‌سازی جست‌وجو)

## توسعه

```bash
pnpm install
pnpm run dev       # سرو توسعهٔ محلی
pnpm run build     # tsc --noEmit + vite build (پریرندر صفحات بلاگ)
pnpm run lint      # eslint
```

نکته‌ها:

- نام محصول «ویدارا - نسخه جلسات» و برند توسط `src/lib/brand.ts` در زمان اجرا تثبیت می‌شود.
- خطاهای API با `errorMessage` به پیام فارسی تبدیل می‌شوند (شامل آرایهٔ خطاهای اعتبارسنجی FastAPI).
- جابه‌جایی بین فضاهای کاری (چندسازمانی) با `OrganizationSwitcher` و گاردهای نقش در `AppShell` انجام می‌شود.

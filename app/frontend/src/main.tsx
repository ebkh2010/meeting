import { createRoot } from 'react-dom/client';
import App from './App.tsx';
import './index.css';
import { loadRuntimeConfig } from './lib/config.ts';
import { lockBrandIdentity } from './lib/brand.ts';

/**
 * اگر بارگذاری یک چانک کد (dynamic import) به خاطر کش کهنهٔ مرورگر/پراکسی با
 * ۴۰۴ شکست بخورد، صفحهٔ سفید می‌ماند؛ در این حالت یک بار خودکار reload می‌کنیم
 * تا نسخهٔ تازه گرفته شود (با محافظ حلقه).
 */
const RELOAD_FLAG = 'vidara.chunk-reload';
function guardChunkLoadFailures() {
  const isChunkError = (message: string) =>
    /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|dynamic import/i.test(
      message,
    );
  const maybeReload = () => {
    try {
      if (window.sessionStorage.getItem(RELOAD_FLAG)) return;
      window.sessionStorage.setItem(RELOAD_FLAG, '1');
      window.location.reload();
    } catch {
      /* حالت مرور خصوصی */
    }
  };
  window.addEventListener('unhandledrejection', (event) => {
    const reason = event.reason;
    const message =
      (reason && typeof reason === 'object' && 'message' in reason
        ? String((reason as { message: unknown }).message)
        : '') || String(reason || '');
    if (isChunkError(message)) maybeReload();
  });
  window.addEventListener('error', (event) => {
    if (isChunkError(event.message || '')) maybeReload();
  });
}

// Load runtime configuration before rendering the app
async function initializeApp() {
  // Prerendered blog pages are served as pure static HTML for SEO.
  // Intentionally skip React mounting so the crawler-facing markup stays
  // lightweight and self-contained — no client-side hydration needed.
  if (
    document
      .querySelector('meta[name="prerender-static-page"]')
      ?.getAttribute('content') === 'blog'
  ) {
    return;
  }

  // تثبیت عنوان و فاویکون برند پیش از رندر، تا بازنویسی لایهٔ میزبان اثر نکند.
  lockBrandIdentity();

  guardChunkLoadFailures();

  try {
    await loadRuntimeConfig();
    console.log('Runtime configuration loaded successfully');
  } catch (error) {
    console.warn(
      'Failed to load runtime configuration, using defaults:',
      error
    );
  }

  // Render the app
  createRoot(document.getElementById('root')!).render(<App />);
}

// Initialize the app
initializeApp();

/**
 * قفل برند زبانهٔ مرورگر.
 *
 * چرا لازم است: لایهٔ میزبان پس از بارگذاری صفحه، عنوان و آیکون را از مقادیر
 * قدیمیِ ذخیره‌شده بازنویسی می‌کرد و نام منسوخ روی زبانهٔ مرورگر می‌ماند.
 * این ماژول عنوان و فاویکون رسمی را تثبیت می‌کند و هر بازنویسی بعدی را برمی‌گرداند.
 */

export const BRAND_NAME = 'ویدارا - نسخه جلسات';
export const BRAND_DESCRIPTION =
  'سامانهٔ هوشمند مدیریت جلسات؛ برنامه‌ریزی، صورتجلسه و پیگیری اقدامات در یک فضای کاری سازمانی.';

const ICON_VERSION = '3';
const ICO_HREF = `/favicon.ico?v=${ICON_VERSION}`;
const PNG_HREF = `/assets/vidara-icon.png?v=${ICON_VERSION}`;

function normalizeHref(href: string): string {
  try {
    return new URL(href, window.location.origin).pathname;
  } catch {
    return href;
  }
}

function upsertLink(
  rel: string,
  href: string,
  type?: string,
  sizes?: string
): void {
  const selector = sizes
    ? `link[rel="${rel}"][sizes="${sizes}"]`
    : `link[rel="${rel}"]:not([sizes])`;
  let link = document.head.querySelector<HTMLLinkElement>(selector);

  if (!link) {
    link = document.createElement('link');
    link.rel = rel;
    if (type) link.type = type;
    if (sizes) link.setAttribute('sizes', sizes);
    document.head.appendChild(link);
  }

  if (link.getAttribute('href') !== href) {
    link.setAttribute('href', href);
  }
}

function upsertMeta(
  attribute: 'name' | 'property',
  key: string,
  content: string
): void {
  let meta = document.head.querySelector<HTMLMetaElement>(
    `meta[${attribute}="${key}"]`
  );

  if (!meta) {
    meta = document.createElement('meta');
    meta.setAttribute(attribute, key);
    document.head.appendChild(meta);
  }

  if (meta.getAttribute('content') !== content) {
    meta.setAttribute('content', content);
  }
}

/** آیکون‌های ناسازگار با برند را از head حذف می‌کند. */
function removeForeignIcons(): void {
  const allowed = new Set([normalizeHref(ICO_HREF), normalizeHref(PNG_HREF)]);
  const iconLinks = document.head.querySelectorAll<HTMLLinkElement>(
    'link[rel~="icon"], link[rel="shortcut icon"], link[rel="apple-touch-icon"]'
  );

  iconLinks.forEach((link) => {
    const href = link.getAttribute('href');
    if (!href || !allowed.has(normalizeHref(href))) {
      link.remove();
    }
  });
}

/** عنوان و آیکون‌های رسمی برند را روی سند اعمال می‌کند. */
function applyBrand(): void {
  if (document.title !== BRAND_NAME) {
    document.title = BRAND_NAME;
  }

  removeForeignIcons();
  upsertLink('icon', ICO_HREF, 'image/x-icon');
  upsertLink('icon', PNG_HREF, 'image/png', '512x512');
  upsertLink('shortcut icon', ICO_HREF, 'image/x-icon');
  upsertLink('apple-touch-icon', PNG_HREF);

  upsertMeta('name', 'description', BRAND_DESCRIPTION);
  upsertMeta('name', 'application-name', BRAND_NAME);
  upsertMeta('name', 'apple-mobile-web-app-title', BRAND_NAME);
  upsertMeta('property', 'og:title', BRAND_NAME);
  upsertMeta('property', 'og:site_name', BRAND_NAME);
  upsertMeta('name', 'twitter:title', BRAND_NAME);
}

/**
 * برند را اعمال و با MutationObserver از بازنویسی توسط اسکریپت‌های میزبان
 * محافظت می‌کند. فراخوانی چندباره بی‌خطر است.
 */
export function lockBrandIdentity(): void {
  if (typeof document === 'undefined') return;

  applyBrand();

  const headObserver = new MutationObserver(() => applyBrand());
  headObserver.observe(document.head, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['href', 'content'],
  });

  const titleElement = document.querySelector('title');
  if (titleElement) {
    const titleObserver = new MutationObserver(() => applyBrand());
    titleObserver.observe(titleElement, {
      childList: true,
      characterData: true,
      subtree: true,
    });
  }

  // شبکهٔ اطمینان برای اسکریپت‌هایی که با تأخیر عنوان را عوض می‌کنند.
  window.setTimeout(applyBrand, 1000);
  window.setTimeout(applyBrand, 3000);
}
/**
 * نمایش متن مارک‌داون با استایل فارسی/RTL (عناوین، فهرست‌ها، بولد و …).
 * هرجا متن تولیدشدهٔ مارک‌داون نمایش داده می‌شود از همین کامپوننت استفاده کنید.
 * با پاس‌دادن `query`، وقوع‌های عبارت جست‌وجو در متن برجسته می‌شوند.
 */
import * as React from 'react';
import Markdown, { type MarkdownToJSX } from 'markdown-to-jsx';
import HighlightText from '@/components/HighlightText';

const TAG_CLASS: Record<string, string> = {
  h1: 'mt-4 mb-2 text-lg font-bold',
  h2: 'mt-3 mb-1 text-base font-bold',
  h3: 'mt-2 mb-1 text-sm font-semibold',
  h4: 'mt-2 mb-1 text-sm font-medium',
  p: 'my-1 leading-7',
  ul: 'my-1 list-disc space-y-1 pr-5',
  ol: 'my-1 list-decimal space-y-1 pr-5',
  li: 'leading-7',
  strong: 'font-bold',
  em: 'italic',
  a: 'text-primary underline',
  code: 'rounded bg-muted px-1 py-0.5 font-mono text-xs',
  // بلوک کد می‌تواند خط بلند داشته باشد؛ قاب اسکرول‌دار خودش را می‌گیرد تا
  // عرض کمینه‌اش به ستون‌های شبکه نشت نکند.
  pre: 'my-2 w-full max-w-full overflow-x-auto rounded bg-muted p-2 font-mono text-xs',
  blockquote: 'my-2 border-r-2 border-border pr-3 text-muted-foreground',
  table: 'my-2 w-full border-collapse text-right',
  th: 'border border-border bg-muted p-2 text-right',
  td: 'border border-border p-2 text-right',
  hr: 'my-3 border-border',
};

/**
 * قاب اسکرول‌دار جدول‌های مارک‌داون.
 *
 * جدول صورتجلسه (چند ستون با متن فارسی) در موبایل از عرض صفحه پهن‌تر است. اگر
 * جدول در قاب اسکرول‌دار نباشد، «عرض کمینه» آن به ستون شبکه یا کارتِ والد نشت
 * می‌کند و کل صفحه را افقی می‌کشد؛ همان چیزی که چیدمان موبایل را به‌هم می‌ریزد.
 */
const TABLE_WRAPPER = 'my-2 w-full max-w-full overflow-x-auto';

export default function MarkdownText({
  text,
  query,
  className,
}: {
  text: string;
  query?: string;
  className?: string;
}) {
  const highlight = (children: React.ReactNode): React.ReactNode => {
    if (!query) return children;
    return React.Children.map(children, (child) => {
      if (typeof child === 'string') return <HighlightText text={child} query={query} />;
      return child;
    });
  };

  const overrides = Object.fromEntries(
    Object.entries(TAG_CLASS).map(([tag, tagClass]) => [
      tag,
      query
        ? {
            component: ({
              children,
              ...props
            }: { children?: React.ReactNode } & Record<string, unknown>) => {
              const Tag = tag as keyof React.JSX.IntrinsicElements;
              return (
                <Tag className={tagClass} {...props}>
                  {highlight(children)}
                </Tag>
              );
            },
          }
        : { props: { className: tagClass } },
    ]),
  ) as MarkdownToJSX.Overrides;

  // جدول همیشه داخل قاب اسکرول‌دار رندر می‌شود (هم در حالت جست‌وجو هم عادی).
  overrides.table = {
    component: ({
      children,
      ...props
    }: { children?: React.ReactNode } & Record<string, unknown>) => (
      <div className={TABLE_WRAPPER}>
        <table className={TAG_CLASS.table} {...props}>
          {query ? highlight(children) : children}
        </table>
      </div>
    ),
  };

  return (
    <div dir="rtl" className={className ?? 'text-sm leading-7'}>
      <Markdown options={{ overrides }}>{text}</Markdown>
    </div>
  );
}

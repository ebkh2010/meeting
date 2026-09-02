/**
 * نمایش متن مارک‌داون با استایل فارسی/RTL (عناوین، فهرست‌ها، بولد و …).
 * هرجا متن تولیدشدهٔ مارک‌داون نمایش داده می‌شود از همین کامپوننت استفاده کنید.
 */
import Markdown from 'markdown-to-jsx';

export default function MarkdownText({ text, className }: { text: string; className?: string }) {
  return (
    <div dir="rtl" className={className ?? 'text-sm leading-7'}>
      <Markdown
        options={{
          overrides: {
            h1: { props: { className: 'mt-4 mb-2 text-lg font-bold' } },
            h2: { props: { className: 'mt-3 mb-1 text-base font-bold' } },
            h3: { props: { className: 'mt-2 mb-1 text-sm font-semibold' } },
            h4: { props: { className: 'mt-2 mb-1 text-sm font-medium' } },
            p: { props: { className: 'my-1 leading-7' } },
            ul: { props: { className: 'my-1 list-disc space-y-1 pr-5' } },
            ol: { props: { className: 'my-1 list-decimal space-y-1 pr-5' } },
            li: { props: { className: 'leading-7' } },
            strong: { props: { className: 'font-bold' } },
            em: { props: { className: 'italic' } },
            a: { props: { className: 'text-primary underline' } },
            code: { props: { className: 'rounded bg-muted px-1 py-0.5 font-mono text-xs' } },
            blockquote: {
              props: { className: 'my-2 border-r-2 border-border pr-3 text-muted-foreground' },
            },
            table: { props: { className: 'my-2 w-full border-collapse text-right' } },
            th: { props: { className: 'border border-border bg-muted p-2 text-right' } },
            td: { props: { className: 'border border-border p-2 text-right' } },
            hr: { props: { className: 'my-3 border-border' } },
          },
        }}
      >
        {text}
      </Markdown>
    </div>
  );
}

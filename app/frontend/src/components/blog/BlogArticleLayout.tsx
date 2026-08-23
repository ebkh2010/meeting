import { Link } from 'react-router-dom';

type BlogArticleLayoutProps = {
  title: string;
  description?: string;
  children: React.ReactNode;
};

/** چیدمان صفحهٔ مقاله؛ رنگ‌ها فقط از توکن‌های تم برند تغذیه می‌شوند. */
const BlogArticleLayout = ({
  title,
  description,
  children,
}: BlogArticleLayoutProps) => (
  <main className="min-h-screen bg-secondary text-foreground">
    <div className="mx-auto max-w-4xl px-6 pt-8">
      <Link
        to="/blog/"
        className="text-sm text-muted-foreground underline-offset-4 hover:text-foreground hover:underline"
      >
        Back to blog
      </Link>
    </div>
    <article className="mx-auto max-w-3xl px-6 py-12">
      <header className="border-b border-border pb-10">
        <p className="text-xs font-semibold uppercase tracking-[0.28em] text-primary">
          Blog Article
        </p>
        <h1 className="mt-4 text-4xl font-bold leading-tight sm:text-5xl">
          {title}
        </h1>
        {description ? (
          <p className="mt-5 max-w-2xl text-lg leading-8 text-muted-foreground">
            {description}
          </p>
        ) : null}
      </header>

      <div className="mt-10">{children}</div>
    </article>
  </main>
);

export default BlogArticleLayout;
import { Link } from 'react-router-dom';
import { blogPosts, getBlogRoute } from '@/lib/blog';

/**
 * فهرست مطالب وبلاگ.
 * همهٔ رنگ‌ها از توکن‌های تم برند خوانده می‌شود (بدون رنگ ثابت hardcode).
 */
const BlogIndexPage = () => (
  <main className="min-h-screen bg-background text-foreground">
    <section className="mx-auto max-w-5xl px-6 py-16 sm:py-20">
      <div className="max-w-3xl space-y-5">
        <p className="text-sm font-semibold uppercase tracking-[0.24em] text-primary">
          Blog Starter
        </p>
        <h1 className="text-4xl font-bold leading-tight sm:text-5xl">
          Start with a blog section that is ready to grow with your SEO site
        </h1>
        <p className="text-lg leading-8 text-muted-foreground">
          This is the starter blog index. Add Markdown files under
          `seo/content/` and the site will automatically generate the list,
          article pages, and prerender routes.
        </p>
      </div>

      <div className="mt-12 grid gap-6">
        {blogPosts.length > 0 ? (
          blogPosts.map((post) => (
            <article
              key={post.slug}
              className="surface-raise p-6 shadow-sm transition-transform duration-200 hover:-translate-y-1"
            >
              <div className="flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
                {post.frontmatter.date ? <span>{post.frontmatter.date}</span> : null}
                {post.frontmatter.tags?.map((tag) => (
                  <span
                    key={tag}
                    className="surface-brand-soft rounded-full px-3 py-1"
                  >
                    {tag}
                  </span>
                ))}
              </div>
              <h2 className="mt-4 text-2xl font-semibold">
                <Link className="hover:text-primary" to={getBlogRoute(post.slug)}>
                  {post.title}
                </Link>
              </h2>
              <p className="mt-3 text-base leading-7 text-muted-foreground">
                {post.description}
              </p>
              <Link
                to={getBlogRoute(post.slug)}
                className="mt-5 inline-flex text-sm font-semibold text-primary underline underline-offset-4"
              >
                Read article
              </Link>
            </article>
          ))
        ) : (
          <section className="surface-subtle rounded-2xl border-dashed p-8">
            <h2 className="text-2xl font-semibold">No articles yet</h2>
            <p className="mt-3 max-w-2xl text-base leading-7 text-muted-foreground">
              Add Markdown files under `seo/content/` and article cards will
              appear here automatically. This keeps the starter clean by default
              while making it easy to begin publishing content for your own SEO
              strategy.
            </p>
          </section>
        )}
      </div>
    </section>
  </main>
);

export default BlogIndexPage;
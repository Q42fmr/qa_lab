import Link from "next/link";
import type { Article, Category } from "@/lib/types";
import { Container } from "@/components/ui/Container";

export interface CategoryTeasersProps {
  categories: Category[];
  /** Sourced for the per-column teaser headlines. */
  articles: Article[];
  title?: string;
  eyebrow?: string;
  subtitle?: string;
}

/**
 * Newspaper-column teasers: a grid of tall "columns", each with a left gutter rule,
 * an uppercase category name and a bulleted teaser list of the latest headlines in
 * that category. Text-forward, image-light — a broadsheet section front.
 */
export function CategoryTeasers({
  categories,
  articles,
  title = "Worüber alle reden",
  eyebrow,
  subtitle,
}: CategoryTeasersProps) {
  if (categories.length === 0) return null;

  return (
    <section className="bg-muted py-10 lg:py-14">
      <Container>
        {eyebrow ? (
          <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
            {eyebrow}
          </p>
        ) : null}
        <h2 className="font-display text-3xl font-bold uppercase tracking-tight text-foreground md:text-4xl">
          {title}
        </h2>
        {subtitle ? (
          <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
            {subtitle}
          </p>
        ) : null}

        <div className="mt-8 grid grid-cols-2 gap-0 md:grid-cols-4">
          {categories.map((category) => {
            const inCategory = articles
              .filter((a) => a.category === category.slug)
              .sort(
                (a, b) =>
                  new Date(b.date).getTime() - new Date(a.date).getTime(),
              )
              .slice(0, 3);

            return (
              <div
                key={category.slug}
                className="border-l border-border px-4 py-2 first:border-l-0 md:px-5"
              >
                <h3 className="border-b-[3px] border-brand pb-2 font-display text-lg font-bold uppercase tracking-tight text-foreground">
                  <Link
                    href={`/blog?kategorie=${category.slug}`}
                    className="transition-colors hover:text-brand"
                  >
                    {category.name}
                  </Link>
                </h3>
                <ul className="mt-3 space-y-3">
                  {inCategory.length > 0 ? (
                    inCategory.map((article) => (
                      <li
                        key={article.slug}
                        className="border-b border-border pb-3 last:border-b-0"
                      >
                        <Link
                          href={`/blog/${article.slug}`}
                          className="font-display text-sm font-bold leading-snug text-foreground transition-colors hover:text-brand"
                        >
                          {article.title}
                        </Link>
                      </li>
                    ))
                  ) : (
                    <li className="text-sm text-muted-foreground">
                      Bald mehr Buzz.
                    </li>
                  )}
                </ul>
                <Link
                  href={`/blog?kategorie=${category.slug}`}
                  className="mt-3 inline-block font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent hover:underline"
                >
                  Mehr →
                </Link>
              </div>
            );
          })}
        </div>
      </Container>
    </section>
  );
}

export default CategoryTeasers;

import Link from "next/link";
import type { Article } from "@/lib/types";
import { Container } from "@/components/ui/Container";
import { Pic } from "@/components/ui/Pic";
import { categoryName } from "@/content/categories";

export interface FeaturedArticlesProps {
  articles: Article[];
  title?: string;
  eyebrow?: string;
  subtitle?: string;
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("de-CH", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

/**
 * Numbered ranking list: an ordered list where each row pairs a giant coral rank
 * numeral, a small square thumbnail and a text column. Rows are separated by rules,
 * no card boxes — a tabloid Top-list, not an image-grid.
 */
export function FeaturedArticles({
  articles,
  title = "Die heissesten Stories der Woche",
  eyebrow,
  subtitle,
}: FeaturedArticlesProps) {
  if (articles.length === 0) return null;

  return (
    <section className="bg-background py-10 lg:py-14">
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

        <ol className="mt-8 border-t border-border">
          {articles.map((article, index) => (
            <li
              key={article.slug}
              className="printers-edge group flex items-center gap-4 border-b border-border bg-background py-5 sm:gap-6"
            >
              <span
                aria-hidden="true"
                className="w-12 shrink-0 text-right font-display text-5xl font-bold leading-none text-accent md:w-16 md:text-7xl"
              >
                {String(index + 1).padStart(2, "0")}
              </span>

              <Link
                href={`/blog/${article.slug}`}
                className="relative block aspect-square w-20 shrink-0 overflow-hidden rounded-[2px] border border-border sm:w-24"
              >
                <Pic
                  image={article.hero}
                  fill
                  sizes="96px"
                  className="object-cover"
                />
              </Link>

              <div className="min-w-0 flex-1">
                <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
                  {categoryName(article.category)}
                </p>
                <h3 className="mt-1 font-display text-lg font-bold leading-snug text-foreground sm:text-xl">
                  <Link
                    href={`/blog/${article.slug}`}
                    className="transition-colors group-hover:text-brand"
                  >
                    {article.title}
                  </Link>
                </h3>
                <div className="mt-2 flex flex-wrap items-center gap-2 font-sans text-xs uppercase tracking-wide text-muted-foreground">
                  <span>{article.author.name}</span>
                  <span aria-hidden="true">·</span>
                  <time dateTime={article.date}>{formatDate(article.date)}</time>
                  <span aria-hidden="true">·</span>
                  <span>{article.readingMinutes} Min.</span>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

export default FeaturedArticles;

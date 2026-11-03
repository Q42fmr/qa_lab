"use client";

import { useState } from "react";
import Link from "next/link";
import type { Article, Category } from "@/lib/types";
import { categoryName } from "@/content/categories";
import { Container } from "@/components/ui/Container";
import { Pic } from "@/components/ui/Pic";

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("de-CH", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

/**
 * Client-side filterable broadsheet front page. The category tabs set local
 * state and filter the lead story + ranking rail in place — works on a static
 * export (no query-string reload).
 */
export function BlogList({
  articles,
  categories,
}: {
  articles: Article[];
  categories: Category[];
}) {
  const [active, setActive] = useState<string>("all");

  const sorted = [...articles].sort(
    (a, b) => new Date(b.date).getTime() - new Date(a.date).getTime(),
  );
  const visible =
    active === "all" ? sorted : sorted.filter((a) => a.category === active);
  const [lead, ...rest] = visible;
  const rail = rest.slice(0, 7);

  const tabActive =
    "relative inline-block py-1 font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground after:absolute after:inset-x-0 after:-bottom-1 after:h-0.5 after:bg-accent";
  const tabInactive =
    "inline-block py-1 font-sans text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-brand";

  return (
    <>
      {/* Category tab strip (client-side) */}
      <section className="border-b border-border bg-background">
        <Container>
          <nav aria-label="Themen filtern" className="overflow-x-auto">
            <ul className="flex min-w-max items-center gap-6 py-3">
              <li>
                <button
                  type="button"
                  onClick={() => setActive("all")}
                  aria-pressed={active === "all"}
                  className={active === "all" ? tabActive : tabInactive}
                >
                  Alle
                </button>
              </li>
              {categories.map((category) => (
                <li key={category.slug}>
                  <button
                    type="button"
                    onClick={() => setActive(category.slug)}
                    aria-pressed={active === category.slug}
                    className={
                      active === category.slug ? tabActive : tabInactive
                    }
                  >
                    {category.name}
                  </button>
                </li>
              ))}
            </ul>
          </nav>
        </Container>
      </section>

      {/* Asymmetric front-page grid */}
      <section className="bg-background py-10 lg:py-14">
        <Container>
          {visible.length === 0 ? (
            <p className="py-12 text-center text-muted-foreground">
              Keine Beiträge in dieser Rubrik.
            </p>
          ) : (
            <div className="grid gap-10 lg:grid-cols-3">
              {/* Lead story — 2/3 */}
              {lead ? (
                <article className="lg:col-span-2">
                  <Link
                    href={`/blog/${lead.slug}`}
                    className="relative block aspect-[16/9] overflow-hidden rounded-[2px] border border-border"
                  >
                    <Pic
                      image={lead.hero}
                      fill
                      priority
                      sizes="(min-width: 1024px) 66vw, 100vw"
                      className="object-cover"
                    />
                    <span className="absolute left-3 top-3 inline-flex items-center rounded-[2px] bg-accent px-2 py-1 font-sans text-[0.65rem] font-bold uppercase tracking-[0.12em] text-foreground">
                      Aufmacher
                    </span>
                  </Link>
                  <p className="mt-4 font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
                    {categoryName(lead.category)}
                  </p>
                  <h2 className="mt-2 font-display text-3xl font-bold leading-tight text-foreground md:text-4xl">
                    <Link
                      href={`/blog/${lead.slug}`}
                      className="transition-colors hover:text-brand"
                    >
                      {lead.title}
                    </Link>
                  </h2>
                  <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
                    {lead.excerpt}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-2 font-sans text-xs uppercase tracking-wide text-muted-foreground">
                    <span>{lead.author.name}</span>
                    <span aria-hidden="true">·</span>
                    <time dateTime={lead.date}>{formatDate(lead.date)}</time>
                    <span aria-hidden="true">·</span>
                    <span>{lead.readingMinutes} Min.</span>
                  </div>
                </article>
              ) : null}

              {/* Ranking rail — 1/3 */}
              <aside className="lg:col-span-1">
                <h2 className="border-b-[3px] border-brand pb-2 font-display text-lg font-bold uppercase tracking-tight text-foreground">
                  Mehr Buzz
                </h2>
                <ol className="mt-3">
                  {rail.map((article, index) => (
                    <li
                      key={article.slug}
                      className="printers-edge group flex items-start gap-3 border-b border-border bg-background py-4"
                    >
                      <span
                        aria-hidden="true"
                        className="w-8 shrink-0 text-right font-display text-3xl font-bold leading-none text-accent"
                      >
                        {String(index + 1).padStart(2, "0")}
                      </span>
                      <div className="min-w-0">
                        <p className="font-sans text-[0.65rem] font-bold uppercase tracking-[0.12em] text-accent">
                          {categoryName(article.category)}
                        </p>
                        <h3 className="mt-1 font-display text-sm font-bold leading-snug text-foreground">
                          <Link
                            href={`/blog/${article.slug}`}
                            className="transition-colors group-hover:text-brand"
                          >
                            {article.title}
                          </Link>
                        </h3>
                      </div>
                    </li>
                  ))}
                </ol>
              </aside>
            </div>
          )}
        </Container>
      </section>
    </>
  );
}

export default BlogList;

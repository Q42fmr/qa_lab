import type { Metadata } from "next";
import { articles } from "@/content/articles";
import { categories } from "@/content/categories";
import { site } from "@/content/site";
import { buildMetadata } from "@/lib/seo";
import { Container } from "@/components/ui/Container";
import { BlogList } from "@/components/sections/BlogList";

export const metadata: Metadata = buildMetadata({
  title: `Stories – ${site.brandName}`,
  description:
    "Alle Stories von bubjtirz.ch: die heissesten Promi-Gerüchte, Glamour, Lifestyle, TV & Streaming und die saftigsten Skandale – klickstark und ohne echte Namen.",
  path: "/blog",
});

/** Broadsheet front page: hero + a client-side filterable lead story + ranking rail. */
export default function BlogIndexPage() {
  return (
    <>
      {/* Page hero / nameplate */}
      <section className="border-b border-border bg-background py-10 lg:py-12">
        <Container>
          <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
            Die Frontseite
          </p>
          <h1 className="font-display text-4xl font-bold uppercase tracking-tight text-foreground sm:text-5xl">
            Alle Stories
          </h1>
          <p className="mt-3 max-w-2xl text-base leading-relaxed text-muted-foreground">
            Der ganze Buzz auf einen Blick – die grosse Aufmacher-Story und die
            heissesten Aufreger der Woche, frisch sortiert.
          </p>
        </Container>
      </section>

      {/* Filter + grid: client-side filtering, but prerendered (all articles in
          the static HTML for SEO/first paint); buttons filter after hydration. */}
      <BlogList articles={articles} categories={categories} />
    </>
  );
}

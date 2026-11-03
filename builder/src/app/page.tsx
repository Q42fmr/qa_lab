import type { Metadata } from "next";
import Link from "next/link";
import { buildMetadata } from "@/lib/seo";
import { site } from "@/content/site";
import { articles } from "@/content/articles";
import { categories } from "@/content/categories";
import { testimonials } from "@/content/testimonials";
import { Container } from "@/components/ui/Container";
import { SectionRule } from "@/components/ui/SectionRule";
import { Hero } from "@/components/sections/Hero";
import { FeaturedArticles } from "@/components/sections/FeaturedArticles";
import { CategoryTeasers } from "@/components/sections/CategoryTeasers";
import { ReaderTestimonials } from "@/components/sections/ReaderTestimonials";
import { NewsletterSignup } from "@/components/sections/NewsletterSignup";
import { CtaBanner } from "@/components/sections/CtaBanner";

export const metadata: Metadata = buildMetadata({
  title: `${site.brandName} – ${site.tagline}`,
  description: site.description,
  path: "/",
  image: articles[0]?.hero
    ? `https://picsum.photos/seed/${articles[0].hero.seed}/1200/630`
    : undefined,
});

export default function HomePage() {
  const [leadArticle, ...rest] = articles;
  const ranked = rest.slice(0, 7);

  return (
    <>
      {leadArticle ? (
        <Hero
          article={leadArticle}
          ctaLabel={site.newsletter.ctaLabel}
          ctaHref="/#newsletter"
        />
      ) : null}

      <FeaturedArticles
        articles={ranked}
        eyebrow="Ranking"
        title="Die heissesten Stories der Woche"
        subtitle="Die meistgeklickten Aufreger aus Promi-Welt, Glamour, TV und Skandalen – jede Woche frisch sortiert."
      />

      <SectionRule eyebrow="Rubriken" title="Worüber alle reden" />

      <CategoryTeasers
        categories={categories}
        articles={articles}
        title="Die Buzz-Ressorts"
        subtitle="Von glamourösen Promi-Gerüchten bis zum nächsten Streaming-Krach – stöber durch die Themen, die gerade für rote Köpfe sorgen."
      />

      <CtaBanner
        title="Verpass keinen Buzz"
        text="Hol dir die heissesten Stories der Woche gratis ins Postfach – jederzeit abbestellbar."
        cta={{ label: site.newsletter.ctaLabel, href: "/#newsletter" }}
      />

      <ReaderTestimonials testimonials={testimonials} />

      <NewsletterSignup />

      {/* About / editorial teaser */}
      <section className="bg-background py-12 lg:py-16">
        <Container>
          <div className="mx-auto max-w-3xl border-t-[3px] border-brand pt-6 text-center">
            <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
              Wer wir sind
            </p>
            <h2 className="mt-1 font-display text-2xl font-bold uppercase tracking-tight text-foreground md:text-3xl">
              Boulevard mit Augenzwinkern
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-base leading-relaxed text-muted-foreground">
              bubjtirz.ch ist das laute, freche Boulevard-Magazin der Schweiz –
              zugespitzt und klickstark, aber sauber: Kein echter Name fällt je,
              nur generische Anspielungen. Lerne die Redaktion hinter dem Buzz
              kennen.
            </p>
            <Link
              href="/ueber-uns"
              className="mt-6 inline-block font-sans text-xs font-bold uppercase tracking-[0.12em] text-brand hover:underline"
            >
              Über uns →
            </Link>
          </div>
        </Container>
      </section>
    </>
  );
}

import Link from "next/link";
import type { Article, ImageRef } from "@/lib/types";
import { Container } from "@/components/ui/Container";
import { Pic } from "@/components/ui/Pic";
import { categoryName } from "@/content/categories";

export interface HeroProps {
  /** Optional lead article — when given, its fields populate the hero. */
  article?: Article;
  eyebrow?: string;
  headline?: string;
  subhead?: string;
  image?: ImageRef;
  /** CTA label; defaults to the free newsletter call to action. */
  ctaLabel?: string;
  /** CTA target; defaults to the newsletter anchor. */
  ctaHref?: string;
}

/**
 * Full-bleed lead-story hero: edge-to-edge image with a dark scrim and a
 * bottom-left overlay headline. A coral "breaking news" bar runs across the top.
 */
export function Hero({
  article,
  eyebrow,
  headline,
  subhead,
  image,
  ctaLabel = "Gratis anmelden",
  ctaHref = "/#newsletter",
}: HeroProps) {
  const resolvedEyebrow =
    eyebrow ??
    (article ? `Exklusiv · ${categoryName(article.category)}` : "Exklusiv · Boulevard");
  const resolvedHeadline = headline ?? article?.title ?? "";
  const resolvedSubhead = subhead ?? article?.excerpt;
  const resolvedImage = image ?? article?.hero;
  const articleHref = article ? `/blog/${article.slug}` : undefined;

  return (
    <section className="relative">
      {/* Breaking-news coral bar */}
      <div className="relative z-20 h-1 w-full bg-accent" aria-hidden="true" />
      <span className="absolute left-4 top-3 z-20 inline-flex items-center rounded-[2px] bg-accent px-2 py-1 font-sans text-[0.65rem] font-bold uppercase tracking-[0.12em] text-foreground sm:left-6 lg:left-8">
        Breaking
      </span>

      <div className="relative h-[70vh] min-h-[480px] w-full overflow-hidden">
        {resolvedImage ? (
          <Pic
            image={resolvedImage}
            fill
            priority
            sizes="100vw"
            className="object-cover"
          />
        ) : (
          <div className="absolute inset-0 bg-foreground" aria-hidden="true" />
        )}

        {/* teal duotone tint to unify the palette */}
        <div
          className="absolute inset-0 bg-brand opacity-[0.12] mix-blend-multiply"
          aria-hidden="true"
        />
        {/* legibility scrim */}
        <div
          className="absolute inset-0"
          style={{
            backgroundImage:
              "linear-gradient(to top, rgb(15 23 42 / 0.85), transparent 60%)",
          }}
          aria-hidden="true"
        />

        <div className="absolute inset-x-0 bottom-0 z-10 pb-10 sm:pb-14 lg:pb-20">
          <Container>
            <div className="max-w-3xl">
              <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
                {resolvedEyebrow}
              </p>
              <h1
                className="mt-3 font-display font-bold text-white"
                style={{ fontSize: "clamp(2.5rem, 6vw, 5rem)", lineHeight: 0.95 }}
              >
                {resolvedHeadline}
              </h1>
              {resolvedSubhead ? (
                <p className="mt-4 max-w-xl text-base leading-relaxed text-white/90 sm:text-lg">
                  {resolvedSubhead}
                </p>
              ) : null}
              <div className="mt-7 flex flex-wrap items-center gap-3">
                <Link
                  href={ctaHref}
                  className="inline-flex items-center justify-center rounded-[2px] bg-brand px-6 py-3 font-sans text-sm font-bold uppercase tracking-[0.08em] text-brand-foreground transition-colors hover:bg-brand/90"
                >
                  {ctaLabel}
                </Link>
                {articleHref ? (
                  <Link
                    href={articleHref}
                    className="inline-flex items-center justify-center rounded-[2px] border border-white/60 px-6 py-3 font-sans text-sm font-bold uppercase tracking-[0.08em] text-white transition-colors hover:bg-white/10"
                  >
                    Story lesen
                  </Link>
                ) : null}
              </div>
            </div>
          </Container>
        </div>
      </div>
    </section>
  );
}

export default Hero;

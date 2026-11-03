import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { Container } from "@/components/ui/Container";
import { Pic } from "@/components/ui/Pic";
import { getLegalPage } from "@/content/legal";
import { site } from "@/content/site";
import { buildMetadata } from "@/lib/seo";
import type { ArticleBlock } from "@/lib/types";

const SLUG = "impressum";

const page = getLegalPage(SLUG);

export const metadata: Metadata = buildMetadata({
  title: `${page?.title ?? "Impressum"} – ${site.brandName}`,
  description:
    "Impressum von bubjtirz.ch mit Angaben zum Herausgeber, zur Verantwortung für die Inhalte sowie zum Haftungsausschluss und Urheberrecht.",
  path: `/${SLUG}`,
});

function LegalBlock({ block }: { block: ArticleBlock }) {
  switch (block.type) {
    case "h2":
      return (
        <h2 className="mt-10 font-display text-2xl font-semibold text-foreground first:mt-0">
          {block.text}
        </h2>
      );
    case "h3":
      return (
        <h3 className="mt-8 font-display text-xl font-semibold text-foreground">
          {block.text}
        </h3>
      );
    case "p":
      return <p className="mt-4 leading-relaxed text-muted-foreground">{block.text}</p>;
    case "list":
      return (
        <ul className="mt-4 space-y-2 pl-5 text-muted-foreground marker:text-brand">
          {block.items.map((item, i) => (
            <li key={i} className="list-disc leading-relaxed">
              {item}
            </li>
          ))}
        </ul>
      );
    case "quote":
      return (
        <blockquote className="mt-6 border-l-4 border-brand pl-4 italic text-foreground">
          <p>{block.text}</p>
          {block.cite ? (
            <cite className="mt-2 block text-sm not-italic text-muted-foreground">
              — {block.cite}
            </cite>
          ) : null}
        </blockquote>
      );
    case "image":
      return (
        <figure className="mt-6 overflow-hidden rounded-[var(--radius)] border border-border">
          <Pic
            image={block.image}
            sizes="(min-width: 768px) 768px, 100vw"
            className="h-auto w-full"
          />
          {block.image.alt ? (
            <figcaption className="px-4 py-3 text-sm text-muted-foreground">
              {block.image.alt}
            </figcaption>
          ) : null}
        </figure>
      );
    default:
      return null;
  }
}

export default function ImpressumPage() {
  if (!page) notFound();

  const updated = new Date(page.updated).toLocaleDateString("de-CH", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });

  return (
    <main className="py-16 sm:py-20">
      <Container className="max-w-3xl">
        <header className="border-b border-border pb-8">
          <h1 className="font-display text-4xl font-bold text-foreground sm:text-5xl">
            {page.title}
          </h1>
          <p className="mt-4 text-sm text-muted-foreground">
            Zuletzt aktualisiert am {updated}
          </p>
        </header>

        <article className="mt-8">
          {page.body.map((block, i) => (
            <LegalBlock key={i} block={block} />
          ))}
        </article>
      </Container>
    </main>
  );
}

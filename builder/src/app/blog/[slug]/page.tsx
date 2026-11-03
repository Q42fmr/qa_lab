import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import type { ArticleBlock } from "@/lib/types";
import { articles, getArticle } from "@/content/articles";
import { categoryName } from "@/content/categories";
import { site } from "@/content/site";
import { buildMetadata } from "@/lib/seo";
import { imageUrl } from "@/lib/images";
import { Container } from "@/components/ui/Container";
import { Badge } from "@/components/ui/Badge";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Pic } from "@/components/ui/Pic";
import { JsonLd } from "@/components/seo/JsonLd";
import { articleSchema, breadcrumbSchema } from "@/components/seo/schema";

interface PageProps {
  params: Promise<{ slug: string }>;
}

export function generateStaticParams() {
  return articles.map((article) => ({ slug: article.slug }));
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) {
    return buildMetadata({
      title: `Beitrag nicht gefunden – ${site.brandName}`,
      description: "Der gesuchte Beitrag ist nicht verfügbar.",
      path: `/blog/${slug}`,
    });
  }
  return buildMetadata({
    title: `${article.title} – ${site.brandName}`,
    description: article.excerpt,
    path: `/blog/${article.slug}`,
    image: imageUrl(article.hero),
  });
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("de-CH", {
    day: "2-digit",
    month: "long",
    year: "numeric",
  });
}

/** Render a single structured rich-text block as semantic markup. */
function Block({ block, dropCap }: { block: ArticleBlock; dropCap?: boolean }) {
  switch (block.type) {
    case "p":
      return (
        <p
          className={`text-base leading-relaxed text-foreground sm:text-lg${
            dropCap ? " drop-cap" : ""
          }`}
        >
          {block.text}
        </p>
      );
    case "h2":
      return (
        <h2 className="font-display text-2xl font-bold leading-tight text-foreground sm:text-3xl">
          {block.text}
        </h2>
      );
    case "h3":
      return (
        <h3 className="font-display text-xl font-bold leading-tight text-foreground sm:text-2xl">
          {block.text}
        </h3>
      );
    case "quote":
      return (
        <blockquote className="border-l-4 border-brand bg-muted py-4 pl-6 pr-4">
          <p className="font-display text-xl italic leading-snug text-foreground">
            “{block.text}”
          </p>
          {block.cite ? (
            <cite className="mt-3 block text-sm not-italic text-muted-foreground">
              — {block.cite}
            </cite>
          ) : null}
        </blockquote>
      );
    case "image":
      return (
        <figure>
          <div className="relative aspect-[16/9] overflow-hidden rounded-lg">
            <Pic
              image={block.image}
              fill
              sizes="(min-width: 768px) 768px, 100vw"
              className="object-cover"
            />
          </div>
          {block.image.alt ? (
            <figcaption className="mt-2 text-center text-sm text-muted-foreground">
              {block.image.alt}
            </figcaption>
          ) : null}
        </figure>
      );
    case "list":
      return (
        <ul className="list-disc space-y-2 pl-6 text-base leading-relaxed text-foreground sm:text-lg">
          {block.items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      );
    default:
      return null;
  }
}

export default async function ArticlePage({ params }: PageProps) {
  const { slug } = await params;
  const article = getArticle(slug);
  if (!article) notFound();

  const relatedPosts = articles
    .filter((a) => a.category === article.category && a.slug !== article.slug)
    .slice(0, 3);

  const breadcrumbs = [
    { name: "Startseite", href: "/" },
    { name: "Magazin", href: "/blog" },
    { name: article.title, href: `/blog/${article.slug}` },
  ];

  return (
    <>
      <JsonLd data={articleSchema(site, article)} />
      <JsonLd data={breadcrumbSchema(breadcrumbs)} />

      <article>
        {/* Header */}
        <header className="border-b border-border bg-muted py-12 lg:py-16">
          <Container>
            <nav aria-label="Brotkrümelnavigation" className="mb-6">
              <ol className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                <li>
                  <Link href="/" className="transition-colors hover:text-brand">
                    Startseite
                  </Link>
                </li>
                <li aria-hidden="true">/</li>
                <li>
                  <Link
                    href="/blog"
                    className="transition-colors hover:text-brand"
                  >
                    Magazin
                  </Link>
                </li>
                <li aria-hidden="true">/</li>
                <li className="text-foreground">
                  {categoryName(article.category)}
                </li>
              </ol>
            </nav>

            <div className="mb-4">
              <Link href={`/blog?kategorie=${article.category}`}>
                <Badge>{categoryName(article.category)}</Badge>
              </Link>
            </div>

            <h1 className="max-w-3xl font-display text-4xl font-bold leading-[1.05] text-foreground md:text-6xl">
              {article.title}
            </h1>
            <p className="mt-4 max-w-2xl text-lg text-muted-foreground">
              {article.excerpt}
            </p>

            <div className="mt-6 flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
              <span className="font-medium text-foreground">
                {article.author.name}
              </span>
              {article.author.role ? (
                <>
                  <span aria-hidden="true">·</span>
                  <span>{article.author.role}</span>
                </>
              ) : null}
              <span aria-hidden="true">·</span>
              <time dateTime={article.date}>{formatDate(article.date)}</time>
              <span aria-hidden="true">·</span>
              <span>{article.readingMinutes} Min. Lesezeit</span>
            </div>
          </Container>
        </header>

        {/* Hero image */}
        <Container className="py-8 lg:py-10">
          <div className="relative aspect-[16/9] overflow-hidden rounded-lg">
            <Pic
              image={article.hero}
              fill
              priority
              sizes="(min-width: 1152px) 1152px, 100vw"
              className="object-cover"
            />
          </div>
        </Container>

        {/* Body */}
        <Container className="pb-12 lg:pb-16">
          <div className="mx-auto max-w-3xl space-y-6">
            {article.body.map((block, index) => (
              <Block
                key={index}
                block={block}
                dropCap={index === 0 && block.type === "p"}
              />
            ))}
          </div>

          {/* Inline newsletter nudge */}
          <div className="mx-auto mt-12 max-w-3xl">
            <Card className="bg-muted p-8 text-center">
              <p className="text-sm font-semibold uppercase tracking-wide text-brand">
                Gratis-Newsletter
              </p>
              <h2 className="mt-2 font-display text-2xl font-bold text-foreground">
                Solche Geschichten direkt ins Postfach?
              </h2>
              <p className="mx-auto mt-3 max-w-xl text-sm leading-relaxed text-muted-foreground sm:text-base">
                Melden Sie sich kostenlos für unseren Newsletter an und
                verpassen Sie keinen Aufreger mehr – gratis und jederzeit
                abbestellbar.
              </p>
              <div className="mt-6 flex flex-wrap justify-center gap-3">
                <Button href="/#newsletter" variant="primary">
                  {site.newsletter.ctaLabel}
                </Button>
                <Button href="/blog" variant="outline">
                  Weitere Beiträge
                </Button>
              </div>
            </Card>
          </div>
        </Container>
      </article>

      {/* Related posts (same category) */}
      {relatedPosts.length > 0 ? (
        <section className="border-t border-border bg-background py-12 lg:py-16">
          <Container>
            <h2 className="mb-8 font-display text-2xl font-bold text-foreground sm:text-3xl">
              Mehr aus {categoryName(article.category)}
            </h2>
            <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-3">
              {relatedPosts.map((post) => (
                <Card key={post.slug} className="flex flex-col overflow-hidden">
                  <Link
                    href={`/blog/${post.slug}`}
                    className="relative block aspect-[16/10] overflow-hidden"
                  >
                    <Pic
                      image={post.hero}
                      fill
                      sizes="(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw"
                      className="object-cover transition-transform duration-300 hover:scale-105"
                    />
                  </Link>
                  <div className="flex flex-1 flex-col p-6">
                    <div className="mb-3">
                      <Badge>{categoryName(post.category)}</Badge>
                    </div>
                    <h3 className="font-display text-lg font-bold leading-snug text-foreground">
                      <Link
                        href={`/blog/${post.slug}`}
                        className="transition-colors hover:text-brand"
                      >
                        {post.title}
                      </Link>
                    </h3>
                    <div className="mt-4 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                      <time dateTime={post.date}>{formatDate(post.date)}</time>
                      <span aria-hidden="true">·</span>
                      <span>{post.readingMinutes} Min. Lesezeit</span>
                    </div>
                  </div>
                </Card>
              ))}
            </div>
          </Container>
        </section>
      ) : null}
    </>
  );
}

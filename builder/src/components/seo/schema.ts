// JSON-LD schema builders for the ch-news-magazine template.
// Pure functions returning plain objects; render them via <JsonLd data={...} />.

import type { Article, SiteConfig } from "@/lib/types";
import { absUrl } from "@/lib/seo";
import { imageUrl } from "@/lib/images";

/** Schema.org Organization describing the publisher. */
export function organizationSchema(site: SiteConfig) {
  return {
    "@context": "https://schema.org",
    "@type": "Organization",
    name: site.brandName,
    url: absUrl("/"),
    description: site.description,
    email: site.contact.email,
    telephone: site.contact.phone,
    address: {
      "@type": "PostalAddress",
      streetAddress: site.contact.address.slice(0, -1).join(", "),
      addressLocality: site.contact.address[site.contact.address.length - 1],
      addressCountry: "CH",
    },
    ...(site.socials && site.socials.length
      ? { sameAs: site.socials.map((s) => s.href) }
      : {}),
  };
}

/** Schema.org WebSite with a SearchAction-free identity entry. */
export function websiteSchema(site: SiteConfig) {
  return {
    "@context": "https://schema.org",
    "@type": "WebSite",
    name: site.brandName,
    url: absUrl("/"),
    description: site.description,
    inLanguage: "de-CH",
    publisher: {
      "@type": "Organization",
      name: site.brandName,
      url: absUrl("/"),
    },
  };
}

/** Schema.org Article (NewsArticle) for a single editorial post. */
export function articleSchema(site: SiteConfig, article: Article) {
  const url = absUrl(`/blog/${article.slug}`);
  return {
    "@context": "https://schema.org",
    "@type": "NewsArticle",
    headline: article.title,
    description: article.excerpt,
    image: [imageUrl(article.hero)],
    datePublished: article.date,
    dateModified: article.date,
    articleSection: article.category,
    inLanguage: "de-CH",
    mainEntityOfPage: { "@type": "WebPage", "@id": url },
    url,
    author: {
      "@type": "Person",
      name: article.author.name,
      ...(article.author.role ? { jobTitle: article.author.role } : {}),
    },
    publisher: {
      "@type": "Organization",
      name: site.brandName,
      url: absUrl("/"),
    },
  };
}

/** Schema.org BreadcrumbList from an ordered list of crumbs. */
export function breadcrumbSchema(items: { name: string; href: string }[]) {
  return {
    "@context": "https://schema.org",
    "@type": "BreadcrumbList",
    itemListElement: items.map((item, index) => ({
      "@type": "ListItem",
      position: index + 1,
      name: item.name,
      item: absUrl(item.href),
    })),
  };
}

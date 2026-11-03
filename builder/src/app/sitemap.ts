import type { MetadataRoute } from "next";
import { absUrl } from "@/lib/seo";
import { articles } from "@/content/articles";
import { legalPages } from "@/content/legal";

// Required for `output: 'export'` — emit a static sitemap.xml at build time.
export const dynamic = "force-static";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();

  const staticRoutes = [
    "/",
    "/blog",
    "/ueber-uns",
    "/kontakt",
  ].map((path) => ({
    url: absUrl(path),
    lastModified: now,
    changeFrequency: "weekly" as const,
    priority: path === "/" ? 1 : 0.8,
  }));

  const articleRoutes = articles.map((article) => ({
    url: absUrl(`/blog/${article.slug}`),
    lastModified: new Date(article.date),
    changeFrequency: "monthly" as const,
    priority: 0.7,
  }));

  const legalRoutes = legalPages.map((page) => ({
    url: absUrl(`/${page.slug}`),
    lastModified: new Date(page.updated),
    changeFrequency: "yearly" as const,
    priority: 0.3,
  }));

  return [...staticRoutes, ...articleRoutes, ...legalRoutes];
}

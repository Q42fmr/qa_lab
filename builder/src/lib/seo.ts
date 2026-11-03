// SEO helpers: absolute URLs + a Next.js Metadata builder.

import type { Metadata } from "next";
import { site } from "@/content/site";

/** Canonical site origin. Override via NEXT_PUBLIC_SITE_URL at deploy time. */
export const SITE_URL: string = (
  process.env.NEXT_PUBLIC_SITE_URL ?? `https://${site.domain}`
).replace(/\/$/, "");

/** Join a path onto SITE_URL, producing an absolute URL. */
export function absUrl(path: string = "/"): string {
  if (/^https?:\/\//i.test(path)) return path;
  const clean = path.startsWith("/") ? path : `/${path}`;
  return `${SITE_URL}${clean}`;
}

export interface BuildMetadataInput {
  title: string;
  description: string;
  /** route path, e.g. "/blog" — used for the canonical URL */
  path?: string;
  /** absolute or relative image URL for OpenGraph/Twitter cards */
  image?: string;
}

/** Build per-page Metadata with canonical + OpenGraph + Twitter. */
export function buildMetadata({
  title,
  description,
  path = "/",
  image,
}: BuildMetadataInput): Metadata {
  const url = absUrl(path);
  const ogImage = image ? absUrl(image) : undefined;

  return {
    title,
    description,
    alternates: { canonical: url },
    openGraph: {
      type: "website",
      siteName: site.brandName,
      title,
      description,
      url,
      locale: "de_CH",
      ...(ogImage ? { images: [{ url: ogImage }] } : {}),
    },
    twitter: {
      card: ogImage ? "summary_large_image" : "summary",
      title,
      description,
      ...(ogImage ? { images: [ogImage] } : {}),
    },
  };
}

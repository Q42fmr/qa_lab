// Seeded Lorem Picsum image helpers.
// A stable seed produces a stable image, so each ImageRef maps to one picture.
// Combining the seed with the site domain keeps images unique per generated site.

import type { ImageRef } from "@/lib/types";
import { site } from "@/content/site";
import { localImages } from "@/lib/local-images";

/** Build a Lorem Picsum URL for a given seed and size. */
export function picsum(seed: string, width: number, height: number): string {
  const safeSeed = encodeURIComponent(seed);
  return `https://picsum.photos/seed/${safeSeed}/${Math.round(width)}/${Math.round(height)}`;
}

/**
 * Build a per-site-unique seed by namespacing the ImageRef seed with the site domain.
 * e.g. domain "magazin.ch" + seed "hero-1" -> "magazin-ch-hero-1".
 */
export function siteSeed(seed: string, domain: string = site.domain): string {
  const ns = domain.replace(/[^a-z0-9]+/gi, "-").toLowerCase();
  return `${ns}-${seed}`;
}

/** Resolve an ImageRef to a final URL: a local library image if one is mapped
 *  for this seed, otherwise the seeded Picsum fallback. */
export function imageUrl(image: ImageRef, domain: string = site.domain): string {
  const local = localImages[image.seed];
  if (local) return local;
  return picsum(siteSeed(image.seed, domain), image.width, image.height);
}

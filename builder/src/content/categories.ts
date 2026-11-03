import type { Category } from "@/lib/types";

export const categories: Category[] = [
  { slug: "stars-geruechte", name: "Stars & Gerüchte" },
  { slug: "lifestyle-glamour", name: "Lifestyle & Glamour" },
  { slug: "tv-streaming", name: "TV & Streaming" },
  { slug: "skandale", name: "Skandale" },
  { slug: "trends", name: "Trends" },
];

export function categoryName(slug: string): string {
  return categories.find((c) => c.slug === slug)?.name ?? slug;
}

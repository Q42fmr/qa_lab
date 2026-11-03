// Content model for the ch-news-magazine master template.
// This is the CONTRACT: components and content files are typed against it.
// Stage-4 briefs vary presentation; this shape stays stable across all generated sites.

export type Locale = "de-CH";

export interface NavItem {
  label: string;
  href: string;
}

export interface SocialLink {
  /** e.g. "instagram", "linkedin" */
  network: string;
  href: string;
}

export interface ContactDetails {
  /** address as display lines, e.g. ["Musterstrasse 1", "8000 Zürich"] */
  address: string[];
  /** E.164-ish, e.g. "+41 44 123 45 67" */
  phone: string;
  email: string;
  /** opening hours, optional */
  hours?: string;
}

/** Free newsletter email signup — the site's only conversion. */
export interface Newsletter {
  intro: string;
  placeholder: string;
  ctaLabel: string;
  successMsg: string;
}

export interface SiteConfig {
  /** brand name — defaults to the domain (e.g. "magazin.ch") */
  brandName: string;
  domain: string;
  tagline: string;
  /** default meta description */
  description: string;
  locale: Locale;
  nav: NavItem[];
  footerNav: NavItem[];
  legalNav: NavItem[];
  contact: ContactDetails;
  socials?: SocialLink[];
  newsletter: Newsletter;
}

/** A seeded Lorem Picsum image reference. URL is built by lib/images.ts. */
export interface ImageRef {
  /** picsum seed, e.g. "hero-1" — combine with site domain for per-site uniqueness */
  seed: string;
  width: number;
  height: number;
  /** German alt text; never empty for content images */
  alt: string;
}

export interface Author {
  name: string;
  role?: string;
  avatar?: ImageRef;
}

export interface Category {
  slug: string;
  name: string;
}

/** Structured rich text so presentation can vary without re-parsing HTML. */
export type ArticleBlock =
  | { type: "p"; text: string }
  | { type: "h2"; text: string }
  | { type: "h3"; text: string }
  | { type: "quote"; text: string; cite?: string }
  | { type: "image"; image: ImageRef }
  | { type: "list"; items: string[] };

export interface Article {
  slug: string;
  title: string;
  excerpt: string;
  category: string;
  author: Author;
  /** ISO date, e.g. "2026-05-12" */
  date: string;
  readingMinutes: number;
  hero: ImageRef;
  body: ArticleBlock[];
}

export interface TeamMember {
  name: string;
  role: string;
  photo: ImageRef;
  bio?: string;
}

export interface Testimonial {
  quote: string;
  name: string;
  city: string;
  avatar?: ImageRef;
}

export interface Stat {
  value: string;
  label: string;
}

export interface LegalPage {
  slug: string;
  title: string;
  /** ISO date last updated */
  updated: string;
  body: ArticleBlock[];
}

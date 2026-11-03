# `ch-news-magazine` — architecture notes

Master template for the site factory: a free Swiss-German online entertainment / boulevard
magazine (leicht provokativ, klickstark — Promi/Star/Lifestyle/Skandal/TV). Built once, then
copied and restyled per art-director brief. Per-site divergence comes from the design tokens
and the typed content, not from the markup.

**Content policy:** no real celebrities, public figures or real names — people are referenced
generically ("ein bekannter Schauspieler", "eine Schweizer Influencerin"). Imagery is generic
stock (seeded Picsum). **Monetization: none** — the only conversion is a free newsletter signup
(footer + inline nudges).

## Stack

- Next.js 15 (App Router), React 19, TypeScript 5, Tailwind CSS 3.4 (PostCSS).
- Static site generation; images via `next/image` from Lorem Picsum (`images.remotePatterns` includes `picsum.photos`).
- Readable Tailwind in the source; class names are hashed only in the production build.
- ESLint via `next lint`; strict TypeScript.

## Design tokens

CSS variables in `src/app/globals.css`, surfaced into Tailwind via `tailwind.config.ts`.
A restyle changes the variable values, not the markup.

- Colors (space-separated RGB for `<alpha-value>`): `--background`, `--foreground`, `--muted`,
  `--muted-foreground`, `--border`, `--brand`, `--brand-foreground`, `--accent`.
- Fonts: `--font-sans` (Inter), `--font-display` (Playfair Display) via `next/font/google`,
  exposed as Tailwind `font-sans` / `font-display`.
- Radius scale `--radius`; container max-width in the `Container` component.

## File layout

```
ch-news-magazine/
  package.json tsconfig.json next.config.mjs postcss.config.mjs
  tailwind.config.ts .eslintrc.json .gitignore README.md
  src/
    lib/
      types.ts          # content model — the stable contract between content and components
      images.ts         # picsum(seed, w, h) -> url; ImageRef helpers
      seo.ts            # buildMetadata(), absolute URL helper, SITE_URL
    content/
      site.ts           # SiteConfig (brand = domain placeholder, newsletter)
      articles.ts       # Article[] — 8 entertainment posts, no real people
      team.ts testimonials.ts stats.ts categories.ts legal.ts
    components/
      ui/        Container Button Card Badge SectionHeading Pic
      seo/       JsonLd schema.ts   # Organization / WebSite / Article / BreadcrumbList
      layout/    Header Footer CookieBanner
      sections/  Hero FeaturedArticles CategoryTeasers SubscribeCTA CtaBanner
                 ReaderTestimonials EditorialTeam Stats NewsletterSignup ContactForm
    app/
      globals.css layout.tsx sitemap.ts robots.ts
      page.tsx                          # home
      blog/page.tsx blog/[slug]/page.tsx
      ueber-uns/page.tsx kontakt/page.tsx
      impressum/ datenschutz/ agb/ cookie-richtlinie/   # de-CH legal pack
```

### Routes

| Route | Purpose |
|-------|---------|
| `/` | Home: lead-story hero + section blocks; CTAs point to `/#newsletter` |
| `/blog` | Article grid + category filters |
| `/blog/[slug]` | Article + NewsArticle JSON-LD + inline newsletter nudge |
| `/ueber-uns` | About / editorial team, mission, values, newsletter CTA |
| `/kontakt` | Contact form + details |
| `/impressum` `/datenschutz` `/agb` `/cookie-richtlinie` | de-CH legal pages |

No `/abo` and no payment pages — the site is free, newsletter-only.

## Component APIs

All content comes from `src/content/*`, typed by `src/lib/types.ts`. Components are
presentational and take typed props; pages pass content in.

- `Container({children, className?})` — centers + max-width + responsive padding.
- `Button({href?, children, variant?: "primary"|"outline"|"ghost", className?})` — `<Link>` if `href`, else `<button>`.
- `Card({children, className?})` — surface with border/radius/shadow.
- `Badge({children})` — category pill.
- `SectionHeading({eyebrow?, title, subtitle?, align?: "left"|"center"})`.
- `Pic({image: ImageRef, fill?, sizes?, className?, priority?})` — wraps `next/image` with a Picsum URL; always emits `alt`.
- `JsonLd({data})` renders `<script type="application/ld+json">`; `schema.ts` exports
  `organizationSchema(site)`, `websiteSchema(site)`, `articleSchema(site, article)`, `breadcrumbSchema(items)`.
- Layout: `Header({site})` (sticky nav, brand, newsletter CTA → `/#newsletter`, mobile menu),
  `Footer({site})` (about blurb, quick links, legal links, contact, newsletter form, optional socials),
  `CookieBanner()` (client component, dismissable via localStorage, links to the cookie policy).
- Sections render a full-width `<section>` each: `Hero`, `FeaturedArticles({articles, title?})`,
  `CategoryTeasers({categories, articles})`, `SubscribeCTA({newsletter, id?})`, `CtaBanner({title, text, cta})`,
  `ReaderTestimonials({testimonials})`, `EditorialTeam({members})`, `Stats({stats})`,
  `NewsletterSignup()` (carries `id="newsletter"`), `ContactForm()` (name · email · phone? · subject · message).

## SEO

- `app/layout.tsx`: `<html lang="de-CH">`, fonts, metadata defaults via `seo.ts`, Organization + WebSite JSON-LD, Header/Footer/CookieBanner.
- Every page exports `metadata` (or `generateMetadata`) with a unique title `"{Page} – {Brand}"`, description, canonical, OpenGraph + Twitter. Articles add Article + BreadcrumbList JSON-LD.
- `sitemap.ts` lists all routes including articles; `robots.ts`.

## Content rules

- All copy in German (de-CH); the brand is a domain-style placeholder (e.g. `magazin.ch`).
- Articles: entertainment / boulevard topics, ~500–600 words as structured `ArticleBlock[]`; no real public figures.
- Legal pages: de-CH boilerplate with `[Platzhalter]` markers for company specifics (Impressum, Datenschutz, AGB, Cookie-Richtlinie).
- Images only through `Pic`, seeded Picsum, generic scenes, German alt text.

## Production build

- Static export: `next.config.mjs` sets `output: 'export'` and `images.unoptimized: true` → a fully static `out/` that hosts anywhere.
- Self-hosted assets: fonts via `next/font` (emitted to `out/_next/static/media`), local CSS + JS; no external runtime requests except images.
- Hashed class names: `scripts/obfuscate.mjs` rewrites Tailwind utilities to short hashes across `out/**/*.{html,js,css}` after the export. Source stays readable; only the shipped output is obfuscated.
- Scripts: `build` (→ `out/`), `obfuscate`, `build:prod` (`build` + `obfuscate`), `generate` (`build:prod` + rename `out/` → `dist/`).

Acceptance for a production build: `out/` is static and the rebuild is green; CSS selectors are hashed and HTML/JS reference the same hashes; `grep out/` finds no `googleapis`/`gstatic`/CDN font or script URLs; serving `out/` renders styled. `npx next build` must pass with zero TS/lint/build errors; the built route set is `/`, `/blog`, `/blog/[slug]` (×8), `/ueber-uns`, `/kontakt` and the four legal pages.

# ch-news-magazine

Factory **master template** — a Swiss-German (de-CH) **online news magazine + subscription**
site built with Next.js 15 (App Router), React 19, TypeScript 5 and Tailwind CSS 3.4.

This is a stage-2 master template for the Site Factory. It is built **once** and then copied &
refactored per art-director brief (stage 4). Per-site divergence is driven mostly by the
**design tokens** (CSS variables in `src/app/globals.css`, surfaced into Tailwind via
`tailwind.config.ts`) and the typed content under `src/content/*`.

## Run

```bash
npm install
npm run dev      # http://localhost:3000
```

Other scripts:

```bash
npm run build    # production build (must be zero TS/lint/build errors)
npm run start    # serve the production build
npm run lint     # next lint
```

## Structure

- `src/lib/types.ts` — the content model (the stable contract).
- `src/lib/images.ts` — seeded Lorem Picsum URL helpers.
- `src/lib/seo.ts` — metadata + canonical/OpenGraph/Twitter helpers.
- `src/content/*` — typed editorial content (site config, articles, team, legal, …).
- `src/components/{ui,layout,sections,seo}` — presentational building blocks.
- `src/app/*` — routes (home, blog, über uns, abo, kontakt, 5 legal pages).

## Notes

- All copy is German (de-CH). Brand is a domain-style placeholder (`magazin.ch`).
- Content is **generic editorial** — no real people. Images are seeded Lorem Picsum via the
  `Pic` component only.
- Legal pages contain `[Platzhalter]` markers for company-specific details.

import Link from "next/link";
import type { SiteConfig } from "@/lib/types";
import { Container } from "@/components/ui/Container";
import { FooterNewsletter } from "@/components/layout/FooterNewsletter";

export interface FooterProps {
  site: SiteConfig;
}

/**
 * "Back page" footer: 4 columns on a muted background, topped by the broadsheet
 * double rule. Col 1 = masthead + tagline, Col 2 = quick links, Col 3 = legal,
 * Col 4 = the free newsletter form + contact. Closes with a folio bar.
 */
export function Footer({ site }: FooterProps) {
  const year = new Date().getFullYear();
  const [word, tld] = site.brandName.includes(".")
    ? [
        site.brandName.slice(0, site.brandName.lastIndexOf(".")),
        site.brandName.slice(site.brandName.lastIndexOf(".")),
      ]
    : [site.brandName, ""];

  return (
    <footer className="mt-16 bg-muted">
      {/* top double rule */}
      <div aria-hidden="true">
        <div className="h-px w-full bg-border" />
        <div className="h-[3px] w-full bg-brand" />
      </div>

      <Container className="py-12 lg:py-16">
        <div className="grid gap-10 md:grid-cols-2 lg:grid-cols-4">
          {/* Col 1 — masthead + about */}
          <div>
            <Link href="/" className="inline-flex items-baseline gap-1">
              <span className="font-display text-2xl font-bold italic tracking-tight text-foreground">
                {word}
              </span>
              <span className="font-sans text-base font-bold not-italic text-brand">
                {tld}
              </span>
            </Link>
            <p className="mt-3 max-w-xs text-sm leading-relaxed text-muted-foreground">
              {site.tagline} {site.description}
            </p>
          </div>

          {/* Col 2 — quick links */}
          <nav aria-label="Footer-Navigation">
            <h2 className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground">
              Magazin
            </h2>
            <ul className="mt-4 space-y-2">
              {site.footerNav.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-brand"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          {/* Col 3 — legal + contact */}
          <div>
            <h2 className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground">
              Rechtliches
            </h2>
            <ul className="mt-4 space-y-2">
              {site.legalNav.map((item) => (
                <li key={item.href}>
                  <Link
                    href={item.href}
                    className="text-sm text-muted-foreground transition-colors hover:text-brand"
                  >
                    {item.label}
                  </Link>
                </li>
              ))}
            </ul>
            <address className="mt-5 space-y-1 text-sm not-italic text-muted-foreground">
              {site.contact.address.map((line) => (
                <div key={line}>{line}</div>
              ))}
              <div>
                <a
                  href={`tel:${site.contact.phone.replace(/\s+/g, "")}`}
                  className="transition-colors hover:text-brand"
                >
                  {site.contact.phone}
                </a>
              </div>
              <div>
                <a
                  href={`mailto:${site.contact.email}`}
                  className="transition-colors hover:text-brand"
                >
                  {site.contact.email}
                </a>
              </div>
            </address>
          </div>

          {/* Col 4 — newsletter form */}
          <div>
            <h2 className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground">
              Newsletter
            </h2>
            <FooterNewsletter newsletter={site.newsletter} />

            {site.socials && site.socials.length > 0 && (
              <ul className="mt-5 flex gap-4">
                {site.socials.map((social) => (
                  <li key={social.network}>
                    <a
                      href={social.href}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-muted-foreground transition-colors hover:text-brand"
                    >
                      {social.network}
                    </a>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>

        {/* Folio bar */}
        <div className="mt-12 flex flex-col gap-3 border-t border-border pt-6 text-xs uppercase tracking-wide text-muted-foreground md:flex-row md:items-center md:justify-between">
          <p>© {year} {site.brandName} · Schweiz</p>
          <nav aria-label="Rechtliches">
            <ul className="flex flex-wrap gap-x-4 gap-y-2">
              <li>
                <Link href="/impressum" className="hover:text-brand">
                  Impressum
                </Link>
              </li>
              <li>
                <Link href="/datenschutz" className="hover:text-brand">
                  Datenschutz
                </Link>
              </li>
            </ul>
          </nav>
        </div>
      </Container>
    </footer>
  );
}

export default Footer;

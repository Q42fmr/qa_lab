"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { SiteConfig } from "@/lib/types";
import { Container } from "@/components/ui/Container";

export interface HeaderProps {
  site: SiteConfig;
}

/** Broadsheet masthead nameplate: "bubjtirz" in Lora italic + ".sbs" in the brand color. */
function Masthead({ brandName }: { brandName: string }) {
  const [word, tld] = brandName.includes(".")
    ? [brandName.slice(0, brandName.lastIndexOf(".")), brandName.slice(brandName.lastIndexOf("."))]
    : [brandName, ""];

  return (
    <Link href="/" className="inline-flex items-baseline gap-2">
      <span
        aria-hidden="true"
        className="inline-flex h-6 w-6 items-center justify-center rounded-[2px] bg-accent text-sm font-bold text-foreground"
      >
        ★
      </span>
      <span className="font-display text-4xl font-bold italic tracking-tight text-foreground sm:text-5xl">
        {word}
      </span>
      <span className="font-sans text-xl font-bold not-italic text-brand sm:text-2xl">
        {tld}
      </span>
    </Link>
  );
}

/**
 * Two-tier broadsheet header.
 * Row 1: centered masthead nameplate on the double rule (scrolls away).
 * Row 2: sticky folio nav bar with a live de-CH date stamp and divided links.
 */
export function Header({ site }: HeaderProps) {
  const [open, setOpen] = useState(false);
  const [today, setToday] = useState("");
  const pathname = usePathname();

  useEffect(() => {
    setToday(
      new Date().toLocaleDateString("de-CH", {
        weekday: "long",
        day: "numeric",
        month: "long",
        year: "numeric",
      }),
    );
  }, []);

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <header className="bg-background">
      {/* Row 1 — masthead nameplate (scrolls away) */}
      <div className="border-b border-border">
        <Container>
          <div className="flex flex-col items-center gap-1 py-5 text-center">
            <Masthead brandName={site.brandName} />
            <p className="font-sans text-xs uppercase tracking-[0.18em] text-muted-foreground">
              {site.tagline}
            </p>
          </div>
        </Container>
        <div className="h-[3px] w-full bg-brand" aria-hidden="true" />
      </div>

      {/* Row 2 — sticky folio nav bar */}
      <div className="sticky top-0 z-50 border-b border-border bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/85">
        <Container>
          <div className="flex h-12 items-center justify-between gap-4">
            <p className="hidden shrink-0 font-sans text-xs uppercase tracking-[0.12em] text-muted-foreground md:block">
              {today || " "}
            </p>

            <nav aria-label="Hauptnavigation" className="hidden md:block">
              <ul className="flex items-center divide-x divide-border">
                {site.nav.map((item) => (
                  <li key={item.href} className="px-4 first:pl-0 last:pr-0">
                    <Link
                      href={item.href}
                      aria-current={isActive(item.href) ? "page" : undefined}
                      className={`relative inline-block py-1 font-sans text-xs font-bold uppercase tracking-[0.12em] transition-colors hover:text-brand ${
                        isActive(item.href)
                          ? "text-foreground after:absolute after:inset-x-0 after:-bottom-0.5 after:h-0.5 after:bg-accent"
                          : "text-muted-foreground"
                      }`}
                    >
                      {item.label}
                    </Link>
                  </li>
                ))}
                <li className="pl-4">
                  <Link
                    href="/#newsletter"
                    className="inline-flex items-center rounded-[2px] bg-accent px-3 py-1 font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground transition-opacity hover:opacity-90"
                  >
                    Newsletter
                  </Link>
                </li>
              </ul>
            </nav>

            {/* Mobile bar: brand short + toggle */}
            <span className="font-display text-lg font-bold italic text-foreground md:hidden">
              {site.brandName}
            </span>
            <button
              type="button"
              className="inline-flex items-center justify-center rounded-[2px] p-2 text-foreground transition-colors hover:bg-muted md:hidden focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              aria-label={open ? "Menü schliessen" : "Menü öffnen"}
              aria-expanded={open}
              aria-controls="mobile-menu"
              onClick={() => setOpen((v) => !v)}
            >
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                {open ? (
                  <>
                    <line x1="18" y1="6" x2="6" y2="18" />
                    <line x1="6" y1="6" x2="18" y2="18" />
                  </>
                ) : (
                  <>
                    <line x1="3" y1="6" x2="21" y2="6" />
                    <line x1="3" y1="12" x2="21" y2="12" />
                    <line x1="3" y1="18" x2="21" y2="18" />
                  </>
                )}
              </svg>
            </button>
          </div>
        </Container>

        {open && (
          <div id="mobile-menu" className="border-t border-border md:hidden">
            <Container>
              <nav aria-label="Mobile Navigation" className="py-4">
                <ul className="flex flex-col gap-1">
                  {site.nav.map((item) => (
                    <li key={item.href}>
                      <Link
                        href={item.href}
                        aria-current={isActive(item.href) ? "page" : undefined}
                        onClick={() => setOpen(false)}
                        className={`block rounded-[2px] px-3 py-2 font-sans text-sm font-bold uppercase tracking-[0.12em] transition-colors hover:bg-muted ${
                          isActive(item.href) ? "text-brand" : "text-foreground"
                        }`}
                      >
                        {item.label}
                      </Link>
                    </li>
                  ))}
                </ul>
                <Link
                  href="/#newsletter"
                  onClick={() => setOpen(false)}
                  className="mt-3 block rounded-[2px] bg-accent px-3 py-2 text-center font-sans text-sm font-bold uppercase tracking-[0.12em] text-foreground"
                >
                  Newsletter
                </Link>
              </nav>
            </Container>
          </div>
        )}
      </div>
    </header>
  );
}

export default Header;

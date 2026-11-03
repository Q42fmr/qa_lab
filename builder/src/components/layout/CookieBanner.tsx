"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Container } from "@/components/ui/Container";

const STORAGE_KEY = "cookie-consent";

/** Cookie consent banner. Dismissal is persisted in localStorage. */
export function CookieBanner() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (window.localStorage.getItem(STORAGE_KEY) !== "accepted") {
        setVisible(true);
      }
    } catch {
      setVisible(true);
    }
  }, []);

  const accept = () => {
    try {
      window.localStorage.setItem(STORAGE_KEY, "accepted");
    } catch {
      /* ignore storage errors (e.g. private mode) */
    }
    setVisible(false);
  };

  if (!visible) return null;

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie-Hinweis"
      className="fixed inset-x-0 bottom-0 z-50 border-t-2 border-brand bg-background"
    >
      <Container className="py-3">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-sm text-brand">
            Wir verwenden Cookies, damit der Buzz reibungslos läuft. Mehr dazu in
            der{" "}
            <Link
              href="/cookie-richtlinie"
              className="font-semibold underline hover:text-foreground"
            >
              Cookie-Richtlinie
            </Link>
            .
          </p>
          <div className="shrink-0">
            <button
              type="button"
              onClick={accept}
              className="inline-flex items-center justify-center rounded-[2px] bg-accent px-5 py-2 font-sans text-sm font-bold uppercase tracking-[0.08em] text-foreground transition-opacity hover:opacity-90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
            >
              Akzeptieren
            </button>
          </div>
        </div>
      </Container>
    </div>
  );
}

export default CookieBanner;

"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import Link from "next/link";
import type { Newsletter } from "@/lib/types";

/**
 * Footer email-only newsletter form (client-side). On submit it swaps to a
 * compact confirmation instead of doing a native browser submit (which would
 * reload the page). Preserves this site's "back page" footer styling.
 */
export function FooterNewsletter({ newsletter }: { newsletter: Newsletter }) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      setDone(true);
      setEmail("");
    }, 700);
  }

  if (done) {
    return (
      <div
        role="status"
        aria-live="polite"
        className="mt-4 rounded-[2px] border border-border bg-background p-4"
      >
        <p className="flex items-center gap-2 text-sm font-medium text-foreground">
          <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand/10 text-brand">
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth={2.5}
              strokeLinecap="round"
              strokeLinejoin="round"
              className="h-3.5 w-3.5"
              aria-hidden="true"
            >
              <path d="M5 13l4 4L19 7" />
            </svg>
          </span>
          {newsletter.successMsg}
        </p>
      </div>
    );
  }

  return (
    <form className="mt-4" aria-label="Newsletter abonnieren" onSubmit={handleSubmit} noValidate>
      <label htmlFor="footer-newsletter-email" className="sr-only">
        E-Mail-Adresse
      </label>
      <div className="flex flex-col gap-2">
        <input
          id="footer-newsletter-email"
          name="email"
          type="email"
          required
          autoComplete="email"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder={newsletter.placeholder}
          className="w-full rounded-[2px] border border-border bg-background px-3 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
        />
        <button
          type="submit"
          disabled={submitting}
          className="rounded-[2px] bg-accent px-4 py-2.5 font-sans text-sm font-bold uppercase tracking-[0.08em] text-foreground transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? "Wird gesendet …" : newsletter.ctaLabel}
        </button>
      </div>
      <p className="mt-2 text-xs text-muted-foreground">
        Mit der Anmeldung stimmst du unserer{" "}
        <Link href="/datenschutz" className="underline hover:text-brand">
          Datenschutzerklärung
        </Link>{" "}
        zu.
      </p>
    </form>
  );
}

export default FooterNewsletter;

"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { site } from "@/content/site";
import { Container } from "@/components/ui/Container";
import { ThankYou } from "@/components/ui/ThankYou";

/** Full-width FREE newsletter signup with an email-only form (client-side, fake submit). */
export function NewsletterSignup() {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const { newsletter } = site;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSubmitting(true);
    setTimeout(() => {
      setSubmitting(false);
      setSubmitted(true);
      setEmail("");
    }, 800);
  }

  return (
    <section id="newsletter" className="bg-muted py-12 sm:py-16">
      <Container>
        <div className="mx-auto max-w-2xl text-center">
          <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
            Newsletter
          </p>
          <h2 className="mt-1 font-display text-3xl font-bold uppercase tracking-tight text-foreground sm:text-4xl">
            Verpass keinen Buzz
          </h2>
          <p className="mx-auto mt-3 max-w-xl text-base leading-relaxed text-muted-foreground">
            {newsletter.intro}
          </p>

          {submitted ? (
            <ThankYou
              title="Anmeldung bestätigt!"
              message={newsletter.successMsg}
              className="mt-6 bg-background text-left sm:text-center"
            />
          ) : (
            <form
              onSubmit={handleSubmit}
              className="mx-auto mt-6 flex max-w-md flex-col gap-3 sm:flex-row"
              noValidate
            >
              <label htmlFor="newsletter-email" className="sr-only">
                E-Mail-Adresse
              </label>
              <input
                id="newsletter-email"
                name="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={newsletter.placeholder}
                autoComplete="email"
                className="w-full flex-1 rounded-[2px] border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              />
              <button
                type="submit"
                disabled={submitting}
                className="shrink-0 rounded-[2px] bg-accent px-6 py-2.5 font-sans text-sm font-bold uppercase tracking-[0.08em] text-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {submitting ? "Wird gesendet …" : newsletter.ctaLabel}
              </button>
            </form>
          )}

          <p className="mt-3 text-xs text-muted-foreground">
            Kostenlos und jederzeit abbestellbar. Mit der Anmeldung stimmst du
            unserer Datenschutzerklärung zu.
          </p>
        </div>
      </Container>
    </section>
  );
}

export default NewsletterSignup;

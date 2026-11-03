"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import type { Newsletter } from "@/lib/types";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { ThankYou } from "@/components/ui/ThankYou";

export interface SubscribeCTAProps {
  newsletter: Newsletter;
  title?: string;
  eyebrow?: string;
  /** Optional anchor id so links like /#newsletter can scroll here. */
  id?: string;
}

/** Free newsletter call-to-action: headline + email-only signup form (no prices/plans). */
export function SubscribeCTA({
  newsletter,
  title = "Nichts mehr verpassen",
  eyebrow = "Newsletter",
  id,
}: SubscribeCTAProps) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

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
    <section id={id} className="bg-background py-16 lg:py-24">
      <Container>
        <div className="mx-auto max-w-2xl">
          <SectionHeading
            eyebrow={eyebrow}
            title={title}
            subtitle={newsletter.intro}
            align="center"
          />

          {submitted ? (
            <ThankYou
              title="Anmeldung bestätigt!"
              message={newsletter.successMsg}
            />
          ) : (
            <form
              onSubmit={handleSubmit}
              className="flex flex-col gap-3 sm:flex-row"
              noValidate
            >
              <label htmlFor="cta-newsletter-email" className="sr-only">
                E-Mail-Adresse
              </label>
              <input
                id="cta-newsletter-email"
                name="email"
                type="email"
                required
                value={email}
                onChange={(event) => setEmail(event.target.value)}
                placeholder={newsletter.placeholder}
                autoComplete="email"
                className="w-full flex-1 rounded border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background"
              />
              <Button type="submit" variant="primary" className="sm:w-auto" disabled={submitting}>
                {submitting ? "Wird gesendet …" : newsletter.ctaLabel}
              </Button>
            </form>
          )}

          <p className="mt-3 text-center text-xs text-muted-foreground">
            Kostenlos und jederzeit abbestellbar. Mit der Anmeldung stimmen Sie
            unserer Datenschutzerklärung zu.
          </p>
        </div>
      </Container>
    </section>
  );
}

export default SubscribeCTA;

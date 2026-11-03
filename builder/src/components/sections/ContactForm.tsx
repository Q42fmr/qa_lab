"use client";

import { useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import { Container } from "@/components/ui/Container";
import { Button } from "@/components/ui/Button";
import { ThankYou } from "@/components/ui/ThankYou";

interface ContactFields {
  name: string;
  email: string;
  phone: string;
  subject: string;
  message: string;
}

type FieldErrors = Partial<Record<keyof ContactFields, string>>;

const EMPTY: ContactFields = {
  name: "",
  email: "",
  phone: "",
  subject: "",
  message: "",
};

const fieldClasses =
  "w-full rounded border border-border bg-background px-4 py-2.5 text-sm text-foreground placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand focus-visible:ring-offset-2 focus-visible:ring-offset-background";

/** Full-width contact form (client-side validation + fake submit). */
export function ContactForm() {
  const [values, setValues] = useState<ContactFields>(EMPTY);
  const [errors, setErrors] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [submitted, setSubmitted] = useState(false);

  function update(field: keyof ContactFields) {
    return (
      event: ChangeEvent<HTMLInputElement | HTMLTextAreaElement>,
    ) => {
      setValues((prev) => ({ ...prev, [field]: event.target.value }));
    };
  }

  function validate(fields: ContactFields): FieldErrors {
    const next: FieldErrors = {};
    if (!fields.name.trim()) next.name = "Bitte geben Sie Ihren Namen an.";
    if (!fields.email.trim()) {
      next.email = "Bitte geben Sie Ihre E-Mail-Adresse an.";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(fields.email.trim())) {
      next.email = "Bitte geben Sie eine gültige E-Mail-Adresse an.";
    }
    if (!fields.subject.trim()) next.subject = "Bitte geben Sie einen Betreff an.";
    if (!fields.message.trim()) {
      next.message = "Bitte schreiben Sie uns eine Nachricht.";
    }
    return next;
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const nextErrors = validate(values);
    setErrors(nextErrors);
    if (Object.keys(nextErrors).length > 0) return;
    setSubmitting(true);
    // simulate a request, then swap the form for the thank-you panel
    setTimeout(() => {
      setSubmitting(false);
      setSubmitted(true);
      setValues(EMPTY);
    }, 800);
  }

  if (submitted) {
    return (
      <section className="bg-background py-16 sm:py-20">
        <Container>
          <ThankYou
            title="Nachricht gesendet!"
            message="Vielen Dank für Ihre Anfrage. Unser Team meldet sich in Kürze bei Ihnen."
          />
        </Container>
      </section>
    );
  }

  return (
    <section className="bg-background py-16 sm:py-20">
      <Container>
        <form
          onSubmit={handleSubmit}
          noValidate
          className="mx-auto grid max-w-2xl grid-cols-1 gap-5"
        >
          <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <label htmlFor="contact-name" className="text-sm font-medium text-foreground">
                Name <span className="text-brand">*</span>
              </label>
              <input
                id="contact-name"
                name="name"
                type="text"
                value={values.name}
                onChange={update("name")}
                autoComplete="name"
                aria-required="true"
                aria-invalid={errors.name ? "true" : undefined}
                aria-describedby={errors.name ? "contact-name-error" : undefined}
                className={fieldClasses}
              />
              {errors.name ? (
                <p id="contact-name-error" className="text-xs text-red-600">
                  {errors.name}
                </p>
              ) : null}
            </div>

            <div className="flex flex-col gap-1.5">
              <label htmlFor="contact-email" className="text-sm font-medium text-foreground">
                E-Mail <span className="text-brand">*</span>
              </label>
              <input
                id="contact-email"
                name="email"
                type="email"
                value={values.email}
                onChange={update("email")}
                autoComplete="email"
                aria-required="true"
                aria-invalid={errors.email ? "true" : undefined}
                aria-describedby={errors.email ? "contact-email-error" : undefined}
                className={fieldClasses}
              />
              {errors.email ? (
                <p id="contact-email-error" className="text-xs text-red-600">
                  {errors.email}
                </p>
              ) : null}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="contact-phone" className="text-sm font-medium text-foreground">
              Telefon <span className="text-muted-foreground">(optional)</span>
            </label>
            <input
              id="contact-phone"
              name="phone"
              type="tel"
              value={values.phone}
              onChange={update("phone")}
              autoComplete="tel"
              className={fieldClasses}
            />
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="contact-subject" className="text-sm font-medium text-foreground">
              Betreff <span className="text-brand">*</span>
            </label>
            <input
              id="contact-subject"
              name="subject"
              type="text"
              value={values.subject}
              onChange={update("subject")}
              aria-required="true"
              aria-invalid={errors.subject ? "true" : undefined}
              aria-describedby={errors.subject ? "contact-subject-error" : undefined}
              className={fieldClasses}
            />
            {errors.subject ? (
              <p id="contact-subject-error" className="text-xs text-red-600">
                {errors.subject}
              </p>
            ) : null}
          </div>

          <div className="flex flex-col gap-1.5">
            <label htmlFor="contact-message" className="text-sm font-medium text-foreground">
              Nachricht <span className="text-brand">*</span>
            </label>
            <textarea
              id="contact-message"
              name="message"
              rows={6}
              value={values.message}
              onChange={update("message")}
              aria-required="true"
              aria-invalid={errors.message ? "true" : undefined}
              aria-describedby={errors.message ? "contact-message-error" : undefined}
              className={`${fieldClasses} resize-y`}
            />
            {errors.message ? (
              <p id="contact-message-error" className="text-xs text-red-600">
                {errors.message}
              </p>
            ) : null}
          </div>

          <div>
            <Button type="submit" variant="primary" disabled={submitting}>
              {submitting ? "Wird gesendet …" : "Nachricht senden"}
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            Mit <span className="text-brand">*</span> markierte Felder sind
            Pflichtfelder.
          </p>
        </form>
      </Container>
    </section>
  );
}

export default ContactForm;

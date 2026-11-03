import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { ContactForm } from "@/components/sections/ContactForm";
import { site } from "@/content/site";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: `Kontakt – ${site.brandName}`,
  description:
    "Nimm Kontakt mit der Redaktion von bubjtirz.ch auf: Schreib uns über das Kontaktformular oder erreiche uns per Telefon, E-Mail und Post.",
  path: "/kontakt",
});

const { contact } = site;

export default function KontaktPage() {
  return (
    <main>
      <section className="border-b border-border bg-muted py-16 sm:py-20">
        <Container>
          <div className="mx-auto max-w-3xl text-center">
            <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand">
              Kontakt
            </p>
            <h1 className="font-display text-4xl font-bold leading-tight text-foreground sm:text-5xl">
              Wir freuen uns auf Ihre Nachricht
            </h1>
            <p className="mt-5 text-lg text-muted-foreground">
              Haben Sie einen heissen Tipp, eine Frage zum Newsletter oder
              Feedback zu einem Artikel? Schreiben Sie uns – wir melden uns so
              rasch wie möglich zurück.
            </p>
          </div>
        </Container>
      </section>

      <section className="bg-background pt-16 sm:pt-20">
        <Container>
          <SectionHeading
            eyebrow="So erreichen Sie uns"
            title="Kontaktangaben"
            align="center"
          />
          <dl className="mx-auto grid max-w-4xl grid-cols-1 gap-6 sm:grid-cols-3">
            <div className="rounded-lg border border-border bg-muted p-6">
              <dt className="text-sm font-semibold uppercase tracking-wide text-brand">
                Adresse
              </dt>
              <dd className="mt-3 text-sm not-italic leading-relaxed text-muted-foreground">
                <address className="not-italic">
                  {contact.address.map((line) => (
                    <span key={line} className="block">
                      {line}
                    </span>
                  ))}
                </address>
              </dd>
            </div>

            <div className="rounded-lg border border-border bg-muted p-6">
              <dt className="text-sm font-semibold uppercase tracking-wide text-brand">
                Telefon &amp; E-Mail
              </dt>
              <dd className="mt-3 space-y-2 text-sm leading-relaxed text-muted-foreground">
                <a
                  href={`tel:${contact.phone.replace(/\s+/g, "")}`}
                  className="block hover:text-brand"
                >
                  {contact.phone}
                </a>
                <a
                  href={`mailto:${contact.email}`}
                  className="block break-all hover:text-brand"
                >
                  {contact.email}
                </a>
              </dd>
            </div>

            <div className="rounded-lg border border-border bg-muted p-6">
              <dt className="text-sm font-semibold uppercase tracking-wide text-brand">
                Öffnungszeiten
              </dt>
              <dd className="mt-3 text-sm leading-relaxed text-muted-foreground">
                {contact.hours ?? "Nach Vereinbarung"}
              </dd>
            </div>
          </dl>
        </Container>
      </section>

      <ContactForm />
    </main>
  );
}

import type { Metadata } from "next";
import { Container } from "@/components/ui/Container";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { Button } from "@/components/ui/Button";
import { EditorialTeam } from "@/components/sections/EditorialTeam";
import { Stats } from "@/components/sections/Stats";
import { site } from "@/content/site";
import { team } from "@/content/team";
import { stats } from "@/content/stats";
import { buildMetadata } from "@/lib/seo";

export const metadata: Metadata = buildMetadata({
  title: `Über uns – ${site.brandName}`,
  description:
    "Lern die Redaktion von bubjtirz.ch kennen: unsere Mission für lauten, frechen Boulevard, unsere Werte und das Team hinter den heissesten Stories.",
  path: "/ueber-uns",
});

const values: { title: string; text: string }[] = [
  {
    title: "Unterhaltung",
    text: "Wir glauben, dass Information Spass machen darf. Bei uns gibt es die grossen und kleinen Geschichten frech, frisch und immer ein bisschen augenzwinkernd.",
  },
  {
    title: "Fairness",
    text: "Auch beim Boulevard gilt: Wir nennen keine echten Personen beim Namen und respektieren die Privatsphäre. Unsere Geschichten sind unterhaltsam, aber anständig.",
  },
  {
    title: "Aktualität",
    text: "Was heute alle bewegt, lesen Sie bei uns als Erstes. Wir haben den Puls von Promi-Welt, Lifestyle und TV stets am Ohr.",
  },
  {
    title: "Nähe",
    text: "Wir schreiben für die Schweiz – über die Trends, die Aufreger und die Gesprächsthemen, die hier wirklich für rote Köpfe sorgen.",
  },
];

const mission: string[] = [
  "bubjtirz.ch ist aus der Lust am lauten, frechen Boulevard entstanden. Wir wollen das Kioskblatt um 7 Uhr morgens sein – zugespitzt, klickstark und jeden Tag neu, aber immer mit einem Augenzwinkern und nie auf Kosten echter Menschen.",
  "Unsere Redaktion bewegt sich quer durch Stars & Gerüchte, Lifestyle & Glamour, TV & Streaming, Skandale und Trends. Dabei halten wir uns an eine eiserne Regel: Wir erzählen anonymisiert und nennen nie einen realen Namen – nur „eine bekannte Schweizer Moderatorin“, „ein TV-Star“ oder „ein anonymer Influencer“.",
  "Finanziert ist unser Magazin so, dass du nie einen Franken zahlst: Alle Inhalte sind gratis. Wer noch näher dran sein will, abonniert einfach unseren kostenlosen Newsletter und bekommt die heissesten Stories der Woche direkt ins Postfach.",
];

export default function UeberUnsPage() {
  return (
    <main>
      <section className="border-b border-border bg-muted py-16 sm:py-20">
        <Container>
          <div className="mx-auto max-w-3xl text-center">
            <p className="mb-3 text-sm font-semibold uppercase tracking-wide text-brand">
              Über uns
            </p>
            <h1 className="font-display text-4xl font-bold leading-tight text-foreground sm:text-5xl">
              Freche Unterhaltung für die Schweiz
            </h1>
            <p className="mt-5 text-lg text-muted-foreground">
              {site.description}
            </p>
          </div>
        </Container>
      </section>

      <section className="bg-background py-16 sm:py-20">
        <Container className="max-w-3xl">
          <SectionHeading
            eyebrow="Unsere Mission"
            title="Warum es bubjtirz.ch gibt"
          />
          <div className="space-y-5">
            {mission.map((paragraph, i) => (
              <p key={i} className="text-base leading-relaxed text-muted-foreground sm:text-lg">
                {paragraph}
              </p>
            ))}
          </div>
        </Container>
      </section>

      <section className="bg-muted py-16 sm:py-20">
        <Container>
          <SectionHeading
            eyebrow="Unsere Werte"
            title="Wofür wir stehen"
            subtitle="Vier Grundsätze prägen unsere tägliche Arbeit – und sorgen dafür, dass Unterhaltung bei uns nie auf Kosten von echten Menschen geht."
            align="center"
          />
          <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2">
            {values.map((value) => (
              <li
                key={value.title}
                className="rounded-lg border border-border bg-background p-6 shadow-sm"
              >
                <h3 className="font-display text-xl font-bold text-foreground">
                  {value.title}
                </h3>
                <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
                  {value.text}
                </p>
              </li>
            ))}
          </ul>
        </Container>
      </section>

      <EditorialTeam members={team} />

      <Stats stats={stats} />

      <section className="bg-background py-16 sm:py-20">
        <Container>
          <div className="mx-auto max-w-2xl rounded-lg border border-border bg-muted p-8 text-center sm:p-12">
            <h2 className="font-display text-3xl font-bold text-foreground sm:text-4xl">
              Immer als Erste Bescheid wissen
            </h2>
            <p className="mt-4 text-base text-muted-foreground sm:text-lg">
              Holen Sie sich die heissesten Geschichten der Woche mit unserem
              kostenlosen Newsletter – gratis und jederzeit abbestellbar.
            </p>
            <div className="mt-8 flex flex-wrap justify-center gap-4">
              <Button href="/#newsletter" variant="primary">
                {site.newsletter.ctaLabel}
              </Button>
              <Button href="/kontakt" variant="outline">
                Kontakt aufnehmen
              </Button>
            </div>
          </div>
        </Container>
      </section>
    </main>
  );
}

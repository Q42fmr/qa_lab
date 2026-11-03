import type { LegalPage } from "@/lib/types";

export const legalPages: LegalPage[] = [
  {
    slug: "impressum",
    title: "Impressum",
    updated: "2026-01-01",
    body: [
      { type: "h2", text: "Angaben zum Herausgeber" },
      {
        type: "p",
        text: "Diese Website wird betrieben von [Platzhalter Firmenname], [Platzhalter Rechtsform], mit Sitz in [Platzhalter Ort]. Die nachfolgenden Angaben gelten für sämtliche Inhalte von bubjtirz.sbs.",
      },
      {
        type: "list",
        items: [
          "Firma: [Platzhalter Firmenname]",
          "Adresse: Kreuzstrasse 26, 8008 Zürich",
          "Telefon: +41 44 987 65 43",
          "E-Mail: redaktion@bubjtirz.sbs",
          "Handelsregister-Nr.: [Platzhalter CHE-Nummer]",
          "Mehrwertsteuer-Nr.: [Platzhalter MWST-Nummer]",
        ],
      },
      { type: "h2", text: "Vertretungsberechtigte Personen" },
      {
        type: "p",
        text: "Verantwortlich für den Inhalt: [Platzhalter Vor- und Nachname], [Platzhalter Funktion]. Die redaktionelle Verantwortung im Sinne des Presserechts trägt die Chefredaktion.",
      },
      { type: "h2", text: "Haftungsausschluss" },
      {
        type: "p",
        text: "Die Inhalte dieser Website werden mit grösstmöglicher Sorgfalt erstellt. Für die Richtigkeit, Vollständigkeit und Aktualität der Inhalte wird jedoch keine Gewähr übernommen. Für Inhalte externer Links sind ausschliesslich deren Betreiber verantwortlich.",
      },
      { type: "h2", text: "Urheberrecht" },
      {
        type: "p",
        text: "Sämtliche auf dieser Website veröffentlichten Inhalte sind urheberrechtlich geschützt. Jede Verwendung ausserhalb der Grenzen des Urheberrechts bedarf der vorherigen schriftlichen Zustimmung von [Platzhalter Firmenname].",
      },
    ],
  },
  {
    slug: "datenschutz",
    title: "Datenschutzerklärung",
    updated: "2026-01-01",
    body: [
      { type: "h2", text: "Verantwortliche Stelle" },
      {
        type: "p",
        text: "Verantwortlich für die Bearbeitung von Personendaten im Sinne des revidierten Schweizer Datenschutzgesetzes (DSG) ist [Platzhalter Firmenname], [Platzhalter Adresse]. Bei Fragen zum Datenschutz erreichen Sie uns unter datenschutz@bubjtirz.sbs.",
      },
      { type: "h2", text: "Welche Daten wir bearbeiten" },
      {
        type: "p",
        text: "Wir bearbeiten Personendaten, die Sie uns aktiv mitteilen, sowie Daten, die beim Besuch der Website automatisch anfallen. Dazu gehören insbesondere folgende Kategorien:",
      },
      {
        type: "list",
        items: [
          "Kontaktdaten (Name, E-Mail-Adresse), die Sie uns über das Kontaktformular oder bei der Newsletter-Anmeldung mitteilen",
          "Nutzungsdaten (besuchte Seiten, Zugriffszeitpunkt, Verweisquelle)",
          "Technische Daten (IP-Adresse, Browsertyp, Geräteinformationen)",
        ],
      },
      { type: "h2", text: "Zwecke der Bearbeitung" },
      {
        type: "p",
        text: "Wir verwenden Ihre Daten, um die Website bereitzustellen, den kostenlosen Newsletter zu versenden, Anfragen zu beantworten und unser Angebot zu verbessern. Eine Bearbeitung erfolgt nur, soweit dies gesetzlich zulässig ist oder Sie eingewilligt haben.",
      },
      { type: "h2", text: "Weitergabe an Dritte" },
      {
        type: "p",
        text: "Eine Weitergabe Ihrer Daten erfolgt nur an sorgfältig ausgewählte Dienstleister, etwa für den Newsletter-Versand oder das Hosting, und ausschliesslich im notwendigen Umfang. Mit diesen Dienstleistern bestehen entsprechende Vereinbarungen zum Datenschutz.",
      },
      { type: "h2", text: "Ihre Rechte" },
      {
        type: "p",
        text: "Sie haben das Recht auf Auskunft, Berichtigung, Löschung sowie auf Einschränkung der Bearbeitung Ihrer Personendaten. Wenden Sie sich dazu an [Platzhalter Kontaktadresse]. Es steht Ihnen zudem frei, sich bei der zuständigen Aufsichtsbehörde zu beschweren.",
      },
    ],
  },
  {
    slug: "agb",
    title: "Allgemeine Geschäftsbedingungen",
    updated: "2026-01-01",
    body: [
      { type: "h2", text: "1. Geltungsbereich" },
      {
        type: "p",
        text: "Diese Allgemeinen Geschäftsbedingungen (AGB) regeln das Verhältnis zwischen [Platzhalter Firmenname] (nachfolgend «Anbieterin») und den Nutzerinnen und Nutzern von bubjtirz.sbs. Die Inhalte des Online-Magazins stehen kostenlos zur Verfügung.",
      },
      { type: "h2", text: "2. Kostenlose Nutzung" },
      {
        type: "p",
        text: "Sämtliche redaktionellen Inhalte von bubjtirz.sbs sind frei zugänglich. Es besteht kein kostenpflichtiges Abonnement und es fallen für die Nutzung der Website keine Gebühren an. Die einzige optionale Anmeldung betrifft den kostenlosen Newsletter.",
      },
      { type: "h2", text: "3. Newsletter" },
      {
        type: "p",
        text: "Der Newsletter ist kostenlos und freiwillig. Die Anmeldung erfolgt über die Angabe Ihrer E-Mail-Adresse und kann jederzeit über den Abmeldelink in jeder E-Mail oder durch eine Nachricht an [Platzhalter Kontaktadresse] widerrufen werden.",
      },
      { type: "h2", text: "4. Inhalte und Verfügbarkeit" },
      {
        type: "list",
        items: [
          "Die Anbieterin bemüht sich um eine möglichst unterbrechungsfreie Verfügbarkeit der Website, schuldet diese aber nicht.",
          "Die redaktionellen Inhalte dienen der Unterhaltung; ein Anspruch auf Vollständigkeit oder dauerhafte Verfügbarkeit einzelner Beiträge besteht nicht.",
          "Die Anbieterin behält sich vor, Inhalte jederzeit zu ändern, zu ergänzen oder zu entfernen.",
        ],
      },
      { type: "h2", text: "5. Pflichten der Nutzenden" },
      {
        type: "p",
        text: "Die Nutzung der Website hat im Rahmen der geltenden Gesetze zu erfolgen. Eine missbräuchliche oder automatisierte Nutzung sowie die unzulässige Weiterverwendung von Inhalten sind untersagt.",
      },
      { type: "h2", text: "6. Anwendbares Recht und Gerichtsstand" },
      {
        type: "p",
        text: "Es gilt ausschliesslich Schweizer Recht. Gerichtsstand ist [Platzhalter Gerichtsstand], soweit keine zwingenden gesetzlichen Bestimmungen entgegenstehen.",
      },
    ],
  },
  {
    slug: "cookie-richtlinie",
    title: "Cookie-Richtlinie",
    updated: "2026-01-01",
    body: [
      { type: "h2", text: "Was sind Cookies?" },
      {
        type: "p",
        text: "Cookies sind kleine Textdateien, die beim Besuch unserer Website auf Ihrem Gerät gespeichert werden. Sie helfen uns, die Website funktionsfähig zu halten, die Nutzung zu verstehen und Ihr Erlebnis zu verbessern.",
      },
      { type: "h2", text: "Welche Cookies wir verwenden" },
      {
        type: "list",
        items: [
          "Notwendige Cookies: erforderlich für den Betrieb der Website, etwa für die Anmeldung.",
          "Funktionale Cookies: speichern Einstellungen wie Ihre bevorzugte Ansicht.",
          "Statistik-Cookies: helfen uns zu verstehen, wie die Website genutzt wird.",
        ],
      },
      { type: "h2", text: "Einwilligung und Verwaltung" },
      {
        type: "p",
        text: "Beim ersten Besuch informieren wir Sie über den Einsatz von Cookies. Nicht notwendige Cookies werden nur mit Ihrer Einwilligung gesetzt. Sie können Ihre Einstellungen jederzeit anpassen oder Cookies in Ihrem Browser löschen.",
      },
      { type: "h2", text: "Cookies von Dritten" },
      {
        type: "p",
        text: "In bestimmten Fällen setzen wir Dienste Dritter ein, etwa zur Reichweitenmessung. Diese können eigene Cookies setzen. Weitere Angaben finden Sie in unserer Datenschutzerklärung. Für Rückfragen wenden Sie sich an [Platzhalter Kontaktadresse].",
      },
    ],
  },
];

export function getLegalPage(slug: string): LegalPage | undefined {
  return legalPages.find((p) => p.slug === slug);
}

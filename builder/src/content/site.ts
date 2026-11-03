import type { SiteConfig } from "@/lib/types";

export const site: SiteConfig = {
  brandName: "bubjtirz",
  domain: "bubjtirz.sbs",
  tagline: "Der Schweizer Buzz — laut, frech, jeden Tag neu.",
  description:
    "bubjtirz.sbs ist das laute, freche Boulevard-Magazin der Schweiz: die heissesten Promi-Gerüchte, Lifestyle, Glamour, TV & Streaming und die saftigsten Skandale – zugespitzt, klickstark und jeden Tag neu. Kostenlos und ohne echte Namen.",
  locale: "de-CH",
  nav: [
    { label: "Start", href: "/" },
    { label: "Stories", href: "/blog" },
    { label: "Über uns", href: "/ueber-uns" },
    { label: "Kontakt", href: "/kontakt" },
  ],
  footerNav: [
    { label: "Start", href: "/" },
    { label: "Stories", href: "/blog" },
    { label: "Über uns", href: "/ueber-uns" },
    { label: "Kontakt", href: "/kontakt" },
  ],
  legalNav: [
    { label: "Impressum", href: "/impressum" },
    { label: "Datenschutz", href: "/datenschutz" },
    { label: "AGB", href: "/agb" },
    { label: "Cookie-Richtlinie", href: "/cookie-richtlinie" },
  ],
  contact: {
    address: ["Redaktion bubjtirz.sbs", "Kreuzstrasse 26", "8008 Zürich"],
    phone: "+41 44 987 65 43",
    email: "redaktion@bubjtirz.sbs",
    hours: "Montag bis Freitag, 08:00 – 18:00 Uhr",
  },
  socials: [
    { network: "instagram", href: "https://instagram.com/" },
    { network: "tiktok", href: "https://tiktok.com/" },
    { network: "facebook", href: "https://facebook.com/" },
  ],
  newsletter: {
    intro:
      "Verpass keinen Buzz: Der kostenlose Newsletter von bubjtirz.sbs knallt dir die heissesten Promi-Gerüchte, Glamour-Stories und TV-Aufreger der Woche direkt ins Postfach – gratis und jederzeit abbestellbar.",
    placeholder: "deine@e-mail.sbs",
    ctaLabel: "Gratis anmelden",
    successMsg:
      "Geschafft! Bestätige deine Anmeldung über den Link in der E-Mail, die wir dir soeben geschickt haben – dann bist du beim Buzz dabei.",
  },
};

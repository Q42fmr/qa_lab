import type { Testimonial } from "@/lib/types";

export const testimonials: Testimonial[] = [
  {
    quote:
      "Schon süchtig. Mein erster Griff am Morgen geht nicht zum Kaffee, sondern zu bubjtirz.sbs. Laut, frech und immer für einen Aufreger gut.",
    name: "Andrea M.",
    city: "Bern",
    avatar: {
      seed: "testimonial-andrea",
      width: 160,
      height: 160,
      alt: "Porträtfoto einer lachenden Leserin",
    },
  },
  {
    quote:
      "Hier erfahre ich als Erster, worüber morgen alle reden. Der Gratis-Newsletter knallt – und das ohne dass je jemand blossgestellt wird.",
    name: "Thomas R.",
    city: "Luzern",
    avatar: {
      seed: "testimonial-thomas",
      width: 160,
      height: 160,
      alt: "Porträtfoto eines Lesers mit Smartphone",
    },
  },
  {
    quote:
      "Endlich Boulevard, der Spass macht und trotzdem Stil hat. Frech, schnell, klickstark – genau mein Humor!",
    name: "Petra L.",
    city: "St. Gallen",
    avatar: {
      seed: "testimonial-petra",
      width: 160,
      height: 160,
      alt: "Porträtfoto einer gut gelaunten Leserin",
    },
  },
];

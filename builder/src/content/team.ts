import type { TeamMember } from "@/lib/types";

export const team: TeamMember[] = [
  {
    name: "Lena Brunner",
    role: "Chefredaktorin",
    photo: {
      seed: "team-lena",
      width: 480,
      height: 480,
      alt: "Porträt der Chefredaktorin in der Redaktion",
    },
    bio: "Lena führt die Redaktion mit dem Gespür eines Kioskblatts um 7 Uhr morgens: laut, frech, immer am Puls – aber stets fair und ohne je einen echten Namen zu nennen.",
  },
  {
    name: "Marco Steiner",
    role: "Ressortleiter Stars & Gerüchte",
    photo: {
      seed: "team-marco",
      width: 480,
      height: 480,
      alt: "Porträt des Ressortleiters vor einer Fensterfront",
    },
    bio: "Marco hat den heissesten Draht zur Glamour-Welt und weiss meist schon vor allen anderen, worüber morgen alle reden – natürlich anonymisiert.",
  },
  {
    name: "Sophie Favre",
    role: "Redaktorin Lifestyle & Glamour",
    photo: {
      seed: "team-sophie",
      width: 480,
      height: 480,
      alt: "Porträt einer Redaktorin mit Notizbuch in einem hellen Büro",
    },
    bio: "Sophie spürt Trends und Glamour-Geschichten auf, bevor sie zum Hype werden. Mode, Beauty und der grosse Auftritt sind ihr Revier.",
  },
  {
    name: "David Keller",
    role: "Redaktor TV & Streaming",
    photo: {
      seed: "team-david",
      width: 480,
      height: 480,
      alt: "Porträt eines Redaktors vor einer Pinnwand mit Notizen",
    },
    bio: "David kennt jede Serie, jede Show und jeden Streaming-Aufreger. Er verrät, was den Hype wert ist – und worüber sich das Streiten lohnt.",
  },
];

import type { TeamMember } from "@/lib/types";
import { Container } from "@/components/ui/Container";
import { Card } from "@/components/ui/Card";
import { SectionHeading } from "@/components/ui/SectionHeading";
import { Pic } from "@/components/ui/Pic";

export interface EditorialTeamProps {
  members: TeamMember[];
}

/** Full-width section introducing the editorial team. */
export function EditorialTeam({ members }: EditorialTeamProps) {
  if (members.length === 0) return null;

  return (
    <section className="bg-background py-16 sm:py-20">
      <Container>
        <SectionHeading
          eyebrow="Redaktion"
          title="Unser Redaktionsteam"
          subtitle="Erfahrene Journalistinnen und Journalisten, die täglich für unabhängige und gründlich recherchierte Berichterstattung sorgen."
          align="center"
        />

        <ul className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {members.map((member) => (
            <li key={member.name}>
              <Card className="flex h-full flex-col overflow-hidden">
                <div className="relative aspect-[4/5] w-full bg-muted">
                  <Pic
                    image={member.photo}
                    fill
                    className="object-cover"
                    sizes="(min-width: 1024px) 25vw, (min-width: 640px) 50vw, 100vw"
                  />
                </div>
                <div className="flex flex-1 flex-col gap-2 p-5">
                  <h3 className="font-display text-lg font-bold text-foreground">
                    {member.name}
                  </h3>
                  <p className="text-sm font-semibold uppercase tracking-wide text-brand">
                    {member.role}
                  </p>
                  {member.bio ? (
                    <p className="mt-1 text-sm leading-relaxed text-muted-foreground">
                      {member.bio}
                    </p>
                  ) : null}
                </div>
              </Card>
            </li>
          ))}
        </ul>
      </Container>
    </section>
  );
}

export default EditorialTeam;

import type { Stat } from "@/lib/types";
import { Container } from "@/components/ui/Container";

export interface StatsProps {
  stats: Stat[];
}

/** Full-width band of key figures about the magazine. */
export function Stats({ stats }: StatsProps) {
  if (stats.length === 0) return null;

  return (
    <section className="bg-brand py-14 text-brand-foreground sm:py-16">
      <Container>
        <dl className="grid grid-cols-2 gap-8 text-center lg:grid-cols-4">
          {stats.map((stat) => (
            <div key={stat.label} className="flex flex-col items-center gap-1">
              <dt className="sr-only">{stat.label}</dt>
              <dd className="font-display text-4xl font-bold leading-none sm:text-5xl">
                {stat.value}
              </dd>
              <p className="text-sm font-medium uppercase tracking-wide text-brand-foreground/80">
                {stat.label}
              </p>
            </div>
          ))}
        </dl>
      </Container>
    </section>
  );
}

export default Stats;

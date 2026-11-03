import { Container } from "@/components/ui/Container";

export interface SectionRuleProps {
  /** Centered title sitting astride the rule. */
  title: string;
  /** Optional uppercase coral kicker above the title. */
  eyebrow?: string;
}

/**
 * Broadsheet column-rule divider: a full-width double rule (1px border over 3px brand)
 * with a centered uppercase Lora title cutting through it — the masthead under-rule
 * motif reused as a section separator.
 */
export function SectionRule({ title, eyebrow }: SectionRuleProps) {
  return (
    <Container>
      <div className="relative py-8 text-center">
        {/* double rule */}
        <div
          aria-hidden="true"
          className="absolute inset-x-0 top-1/2 flex -translate-y-1/2 flex-col gap-[2px]"
        >
          <span className="block h-px w-full bg-border" />
          <span className="block h-[3px] w-full bg-brand" />
        </div>
        <div className="relative inline-block bg-background px-6">
          {eyebrow ? (
            <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
              {eyebrow}
            </p>
          ) : null}
          <h2 className="font-display text-2xl font-bold uppercase tracking-tight text-foreground md:text-3xl">
            {title}
          </h2>
        </div>
      </div>
    </Container>
  );
}

export default SectionRule;

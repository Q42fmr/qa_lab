import Link from "next/link";
import { Container } from "@/components/ui/Container";

export interface CtaBannerProps {
  title: string;
  text: string;
  cta: { label: string; href: string };
}

/** Loud full-width banner with coral top/bottom edges and a teal newsletter CTA. */
export function CtaBanner({ title, text, cta }: CtaBannerProps) {
  return (
    <section className="border-y-4 border-accent bg-foreground py-12 lg:py-14">
      <Container>
        <div className="flex flex-col items-center gap-6 text-center lg:flex-row lg:justify-between lg:text-left">
          <div className="max-w-2xl">
            <h2 className="font-display text-3xl font-bold uppercase tracking-tight text-background sm:text-4xl">
              {title}
            </h2>
            <p className="mt-3 text-base leading-relaxed text-background/80 sm:text-lg">
              {text}
            </p>
          </div>
          <div className="shrink-0">
            <Link
              href={cta.href}
              className="inline-flex items-center justify-center rounded-[2px] bg-brand px-7 py-3 font-sans text-sm font-bold uppercase tracking-[0.08em] text-brand-foreground transition-colors hover:bg-brand/90"
            >
              {cta.label}
            </Link>
          </div>
        </div>
      </Container>
    </section>
  );
}

export default CtaBanner;

import type { Testimonial } from "@/lib/types";
import { Container } from "@/components/ui/Container";

export interface ReaderTestimonialsProps {
  testimonials: Testimonial[];
}

/**
 * Letters-to-the-editor: reader quotes set as broadsheet pull-quotes in columns,
 * each topped by a giant Lora quotation mark and a top brand rule.
 */
export function ReaderTestimonials({ testimonials }: ReaderTestimonialsProps) {
  if (testimonials.length === 0) return null;

  return (
    <section className="bg-background py-10 lg:py-14">
      <Container>
        <p className="font-sans text-xs font-bold uppercase tracking-[0.12em] text-accent">
          Leserbriefe
        </p>
        <h2 className="font-display text-3xl font-bold uppercase tracking-tight text-foreground md:text-4xl">
          Das sagt die Buzz-Community
        </h2>

        <div className="mt-8 grid grid-cols-1 gap-px overflow-hidden border border-border bg-border md:grid-cols-3">
          {testimonials.map((testimonial) => (
            <figure
              key={`${testimonial.name}-${testimonial.city}`}
              className="flex flex-col bg-background p-6"
            >
              <span
                aria-hidden="true"
                className="font-display text-6xl font-bold leading-none text-brand"
              >
                „
              </span>
              <blockquote className="-mt-3 flex-1 font-display text-lg italic leading-snug text-foreground">
                {testimonial.quote}
              </blockquote>
              <figcaption className="mt-5 border-t border-border pt-3 font-sans text-xs uppercase tracking-[0.12em] text-muted-foreground">
                <span className="font-bold text-foreground">
                  {testimonial.name}
                </span>
                {" · "}
                {testimonial.city}
              </figcaption>
            </figure>
          ))}
        </div>
      </Container>
    </section>
  );
}

export default ReaderTestimonials;

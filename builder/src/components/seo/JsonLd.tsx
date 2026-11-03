// Renders a JSON-LD <script> tag for structured data.

export interface JsonLdProps {
  /** A schema.org object (or array of objects) to serialise. */
  data: unknown;
}

/** Emits a <script type="application/ld+json"> with the given data. */
export function JsonLd({ data }: JsonLdProps) {
  return (
    <script
      type="application/ld+json"
      dangerouslySetInnerHTML={{ __html: JSON.stringify(data) }}
    />
  );
}

export default JsonLd;

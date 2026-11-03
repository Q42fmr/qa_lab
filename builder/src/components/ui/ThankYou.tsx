/**
 * Thank-you panel shown in place of a form after a successful submit
 * (mirrors the source sites' pattern: the form is swapped for a confirmation
 * card with a check icon + heading + reassurance line). Token-based classes so
 * it picks up each site's palette/typography automatically.
 */
export function ThankYou({
  title = "Vielen Dank!",
  message,
  className = "",
}: {
  title?: string;
  message: string;
  className?: string;
}) {
  return (
    <div
      role="status"
      aria-live="polite"
      className={`mx-auto flex max-w-2xl flex-col items-center gap-4 rounded-lg border border-border bg-muted p-8 text-center sm:p-10 ${className}`}
    >
      <span className="flex h-14 w-14 items-center justify-center rounded-full bg-brand/10 text-brand">
        <svg
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
          className="h-7 w-7"
          aria-hidden="true"
        >
          <path d="M5 13l4 4L19 7" />
        </svg>
      </span>
      <h3 className="font-display text-2xl font-bold text-foreground">{title}</h3>
      <p className="max-w-md text-base text-muted-foreground">{message}</p>
    </div>
  );
}

export default ThankYou;

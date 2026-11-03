import type { ReactNode } from "react";

export interface BadgeProps {
  children: ReactNode;
  className?: string;
}

/** A small category pill. */
export function Badge({ children, className }: BadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-[2px] bg-accent px-2.5 py-1 font-sans text-xs font-bold uppercase tracking-[0.12em] text-foreground${
        className ? ` ${className}` : ""
      }`}
    >
      {children}
    </span>
  );
}

export default Badge;

import type { ReactNode } from "react";

export interface CardProps {
  children: ReactNode;
  className?: string;
}

/** A surface with border, rounded corners and a subtle shadow. */
export function Card({ children, className }: CardProps) {
  return (
    <div
      className={`printers-edge rounded-[2px] border border-border bg-background${
        className ? ` ${className}` : ""
      }`}
    >
      {children}
    </div>
  );
}

export default Card;

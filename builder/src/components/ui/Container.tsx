import type { ReactNode } from "react";

export interface ContainerProps {
  children: ReactNode;
  className?: string;
}

/** Centers content with a max-width and responsive horizontal padding. */
export function Container({ children, className }: ContainerProps) {
  return (
    <div
      className={`mx-auto w-full max-w-6xl px-4 sm:px-6 lg:px-8${
        className ? ` ${className}` : ""
      }`}
    >
      {children}
    </div>
  );
}

export default Container;

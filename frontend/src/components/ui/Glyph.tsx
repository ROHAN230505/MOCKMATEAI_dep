import type { ReactNode } from "react";

/**
 * Wrapper for the app's inline stroke icons.
 *
 * Every glyph in the product is drawn on the same 24-unit grid with the same
 * stroke weight and joins, and inherits `currentColor` — which is what keeps an
 * icon set assembled by hand from looking assembled by hand, and means no
 * icon needs a light/dark variant.
 */
export function Glyph({ children, className = "h-[1.125rem] w-[1.125rem]" }: { children: ReactNode; className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      className={`shrink-0 ${className}`}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.7"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      {children}
    </svg>
  );
}

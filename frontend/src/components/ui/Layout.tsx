import type { ReactNode } from "react";

/**
 * The page grid. One measure, one rhythm, applied everywhere.
 *
 * Nineteen pages previously chose between ten different `max-w-*` values and
 * used the shared header on nine of them, so the content column changed width
 * and the title moved as you navigated. Nothing about that is visible on any
 * single screen and all of it is visible in use — it is the difference between
 * a set of pages and a product.
 *
 * `measure` is not a decorative choice either. Reading comfort tops out around
 * 70-80 characters; `read` holds a paragraph near that, `work` is for tables
 * and side-by-side panels that genuinely need the width.
 */
export function Page({
  children,
  measure = "work",
}: {
  children: ReactNode;
  measure?: "read" | "work" | "full";
}) {
  const width = measure === "read" ? "max-w-2xl" : measure === "work" ? "max-w-5xl" : "max-w-none";
  return <div className={`mx-auto w-full px-6 py-10 sm:px-10 sm:py-16 ${width}`}>{children}</div>;
}

/**
 * A titled region.
 *
 * Structure comes from a rule and a label, not from a box. A border encloses
 * one thing; a rule separates two — and an interface assembled from enclosures
 * is the rectangle-inside-a-rectangle look that makes dashboards
 * interchangeable. The eyebrow carries the category so the title itself can
 * stay a plain sentence instead of shouting in capitals.
 */
export function Section({
  title,
  eyebrow,
  aside,
  children,
}: {
  title?: string;
  eyebrow?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="mt-16 first:mt-0">
      {(title || aside) && (
        <div className="mb-6 flex items-baseline justify-between gap-6">
          <div>
            {eyebrow && (
              <p className="mb-1.5 text-micro font-medium tracking-[0.12em] text-text-subtle uppercase">
                {eyebrow}
              </p>
            )}
            {title && <h2 className="text-title leading-tight font-medium text-text">{title}</h2>}
          </div>
          {aside && <div className="shrink-0 text-small text-text-muted">{aside}</div>}
        </div>
      )}
      {children}
    </section>
  );
}

/**
 * The editorial split: a wide column of content with a narrow margin beside it,
 * the way a printed page carries marginalia.
 *
 * Deliberately asymmetric. An even two-column split gives both halves equal
 * weight and so states no priority; this one says which is the subject and
 * which is the annotation. Collapses to a single column below `lg`, with the
 * margin *after* the content — on a narrow screen the annotation should not
 * come before the thing it annotates.
 */
export function Split({ children, margin }: { children: ReactNode; margin: ReactNode }) {
  return (
    <div className="grid gap-10 lg:grid-cols-[minmax(0,1fr)_15rem] lg:gap-16">
      <div className="min-w-0">{children}</div>
      <aside className="min-w-0 lg:pt-1">{margin}</aside>
    </div>
  );
}

/** A hairline division. Fades at both ends, so it reads as a break, not an edge. */
export function Rule({ className = "" }: { className?: string }) {
  return <div aria-hidden="true" className={`hairline h-px w-full ${className}`} />;
}

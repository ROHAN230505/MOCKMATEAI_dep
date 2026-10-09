import type { ReactNode } from "react";

/**
 * The heading block every in-app screen opens with.
 *
 * Centralised so the eyebrow / title / description rhythm and the trailing
 * action slot are identical across Dashboard, Setup, History and Feedback —
 * consistent vertical rhythm across screens is most of what makes a product
 * feel like one product.
 */
export function PageHeader({
  eyebrow,
  title,
  description,
  actions,
  className = "",
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <header
      className={`flex flex-wrap items-end justify-between gap-4 border-b border-border pb-5 ${className}`}
    >
      <div className="min-w-0">
        {eyebrow && <p className="marker mb-1.5 text-accent">{eyebrow}</p>}
        <h1 className="text-title leading-[var(--mm-leading-tight)] font-semibold tracking-[-0.022em] text-text">
          {title}
        </h1>
        {description && <p className="mt-1.5 max-w-2xl text-text-muted">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}

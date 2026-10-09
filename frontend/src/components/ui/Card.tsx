import type { HTMLAttributes, ReactNode } from "react";

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  /** "panel" is the default sheet; "flat" drops the blur/shadow for dense lists; "glow" adds an accent rim for hero cards. */
  tone?: "panel" | "flat" | "glow";
  /** Adds a hover lift + border brighten. Use only when the whole card is a link or button. */
  interactive?: boolean;
  padded?: boolean;
}

// `panel` carries the veil, so the galaxy field reads through it — see the note
// on `.panel` in index.css for the alpha and for why there is no blur. `flat`
// stays fully opaque, which is exactly what makes it right for dense lists: a
// long scrolling table over a moving field is the one case where show-through
// costs more than it gives.
const TONE_CLASSES: Record<NonNullable<CardProps["tone"]>, string> = {
  panel: "panel",
  flat: "border border-border bg-surface",
  // The one emphasised region per screen. A tinted ground rather than a glow —
  // at this density a shadow would fight the hairline borders around it.
  glow: "panel panel-raised",
};

export function Card({
  tone = "panel",
  interactive = false,
  padded = true,
  className = "",
  ...rest
}: CardProps) {
  return (
    <div
      className={`rounded-card ${TONE_CLASSES[tone]} ${padded ? "p-4" : ""} ${
        interactive
          ? "cursor-pointer transition-colors duration-150 hover:border-border-strong hover:bg-surface-raised"
          : ""
      } ${className}`}
      {...rest}
    />
  );
}

/**
 * A card's title row. Exists so headings, optional eyebrow labels and trailing
 * actions line up identically on every screen instead of each page inventing
 * its own header markup.
 */
export function CardHeader({
  eyebrow,
  title,
  description,
  action,
  className = "",
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  description?: ReactNode;
  action?: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-5 flex flex-wrap items-start justify-between gap-4 ${className}`}>
      <div className="min-w-0">
        {eyebrow && (
          <p className="mb-1.5 text-[0.6875rem] font-semibold tracking-[0.14em] text-text-subtle uppercase">
            {eyebrow}
          </p>
        )}
        <h2 className="text-base font-semibold text-text">{title}</h2>
        {description && <p className="mt-1.5 text-sm leading-relaxed text-text-muted">{description}</p>}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}

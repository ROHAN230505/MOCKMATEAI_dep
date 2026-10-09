import type { ReactNode } from "react";

type Tone = "neutral" | "accent" | "success" | "danger" | "warning";

const TONE_CLASSES: Record<Tone, string> = {
  neutral: "border-border bg-surface-raised text-text-muted",
  accent: "border-accent/40 bg-accent-soft text-accent",
  success: "border-success/40 bg-success/10 text-success",
  danger: "border-danger/40 bg-danger/10 text-danger",
  warning: "border-warning/40 bg-warning/10 text-warning",
};

/** Small status pill. Also used for the "skipped" marker, which must read as neutral, not as a failure (Section 4.8). */
export function Badge({
  tone = "neutral",
  children,
  className = "",
  dot = false,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  /** Leading status dot, for live/lifecycle states. */
  dot?: boolean;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-pill border px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONE_CLASSES[tone]} ${className}`}
    >
      {dot && <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-current" />}
      {children}
    </span>
  );
}

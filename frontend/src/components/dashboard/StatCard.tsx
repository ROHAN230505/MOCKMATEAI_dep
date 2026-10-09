import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { useCountUp } from "../../hooks/useCountUp";

/**
 * A single analytics tile.
 *
 * Two deliberate constraints:
 *
 * - **The counter only animates a real number.** When `value` is null the tile
 *   shows an em dash and the reason, rather than counting up to zero — a number
 *   climbing to 0 reads as a measured result, and "not attempted" isn't one.
 * - **No trend unless a trend exists.** `delta` is optional and only passed when
 *   the backend actually returns comparable history. The product has no
 *   week-over-week series today, so most tiles render without one instead of
 *   inventing "+4.8% this week".
 */
export function StatCard({
  label,
  value,
  suffix,
  emptyNote,
  delta,
  icon,
  index = 0,
}: {
  label: string;
  /** null renders as "not measured" rather than as 0. */
  value: number | null;
  suffix?: string;
  emptyNote?: string;
  /** Signed change vs. a previous real measurement. Omit when none exists. */
  delta?: number | null;
  icon: ReactNode;
  index?: number;
}) {
  const prefersReducedMotion = useReducedMotion();
  const animated = useCountUp(value ?? 0);

  return (
    <motion.div
      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
      className="group panel relative overflow-hidden rounded-card p-4 transition-colors duration-200 hover:border-border-strong"
    >
      {/* Accent bloom on hover — the one flourish, and it sits under the content
          rather than over it. */}
      <span
        aria-hidden="true"
        className="pointer-events-none absolute -top-12 -right-10 h-28 w-28 rounded-full opacity-0 blur-2xl transition-opacity duration-500 group-hover:opacity-60"
        style={{ background: "radial-gradient(circle, var(--grad-a), transparent 70%)" }}
      />

      <div className="relative flex items-start justify-between gap-3">
        <p className="marker text-text-subtle">{label}</p>
        <span
          aria-hidden="true"
          className="text-text-subtle transition-colors duration-300 group-hover:text-accent"
        >
          {icon}
        </span>
      </div>

      <div className="relative mt-3 flex items-baseline gap-1.5">
        {value === null ? (
          <span className="stat text-2xl text-text-subtle">—</span>
        ) : (
          <>
            <span className="stat text-2xl text-text">{Math.round(animated)}</span>
            {suffix && <span className="text-[0.75rem] text-text-subtle">{suffix}</span>}
          </>
        )}
      </div>

      <div className="relative mt-1.5 flex items-center gap-2">
        {value === null ? (
          <span className="text-[0.6875rem] text-text-subtle">{emptyNote ?? "Not attempted"}</span>
        ) : delta !== undefined && delta !== null ? (
          <span
            className={`inline-flex items-center gap-1 text-[0.6875rem] font-medium ${
              delta > 0 ? "text-success" : delta < 0 ? "text-danger" : "text-text-subtle"
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.4" aria-hidden="true">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d={delta > 0 ? "M12 19V5m0 0-6 6m6-6 6 6" : delta < 0 ? "M12 5v14m0 0 6-6m-6 6-6-6" : "M5 12h14"}
              />
            </svg>
            {delta > 0 ? "+" : ""}
            {Math.round(delta)} vs. previous
          </span>
        ) : (
          <span className="text-[0.6875rem] text-text-subtle">{emptyNote ?? ""}</span>
        )}
      </div>
    </motion.div>
  );
}

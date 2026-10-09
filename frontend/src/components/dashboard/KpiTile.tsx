import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { motion, useReducedMotion } from "framer-motion";
import { useCountUp } from "../../hooks/useCountUp";

/**
 * A KPI in the top strip.
 *
 * Three rules it enforces so the strip stays honest:
 *
 * - **`value: null` is not zero.** It renders an em dash and the reason, and the
 *   counter doesn't animate — a number climbing to 0 reads as a measured result.
 * - **`delta` is optional and never invented.** It's only passed where the
 *   backend genuinely returns a comparable previous figure (the report's own
 *   before/after block). Most tiles have no series behind them and correctly
 *   show none.
 * - **A sparkline needs three real points.** Below that it's a line through
 *   noise, so it's omitted rather than padded.
 */
export function KpiTile({
  label,
  value,
  suffix,
  note,
  delta,
  spark,
  href,
  icon,
  index = 0,
}: {
  label: string;
  value: number | null;
  suffix?: string;
  note: string;
  /** Signed change vs. a real previous measurement. */
  delta?: number | null;
  /** Recent real values, oldest first. Rendered only when ≥3 exist. */
  spark?: number[];
  href: string;
  icon: ReactNode;
  index?: number;
}) {
  const prefersReducedMotion = useReducedMotion();
  const animated = useCountUp(value ?? 0);
  const showSpark = (spark?.length ?? 0) >= 3;

  return (
    <motion.div
      initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.45, delay: index * 0.05, ease: [0.16, 1, 0.3, 1] }}
    >
      <Link
        to={href}
        className="group panel flex h-full flex-col justify-between gap-3 rounded-card p-4 transition-colors duration-150 hover:border-border-strong"
      >
        <div className="flex items-start justify-between gap-2">
          <span className="marker text-text-subtle">{label}</span>
          <span
            aria-hidden="true"
            className="text-text-subtle transition-colors duration-200 group-hover:text-accent"
          >
            {icon}
          </span>
        </div>

        <div>
          <div className="flex items-baseline gap-1.5">
            {value === null ? (
              <span className="stat text-2xl text-text-subtle">—</span>
            ) : (
              <>
                <span className="stat text-2xl text-text">{Math.round(animated)}</span>
                {suffix && <span className="text-[0.6875rem] text-text-subtle">{suffix}</span>}
              </>
            )}
            {delta !== undefined && delta !== null && value !== null && (
              <span
                className={`ml-auto inline-flex items-center gap-0.5 text-[0.6875rem] font-medium ${
                  delta > 0 ? "text-success" : delta < 0 ? "text-danger" : "text-text-subtle"
                }`}
              >
                <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="2.6" aria-hidden="true">
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    d={delta > 0 ? "M12 19V5m0 0-6 6m6-6 6 6" : delta < 0 ? "M12 5v14m0 0 6-6m-6 6-6-6" : "M5 12h14"}
                  />
                </svg>
                {delta > 0 ? "+" : ""}
                {Math.round(delta)}
              </span>
            )}
          </div>

          {showSpark ? <Sparkline values={spark!} /> : <p className="mt-1.5 truncate text-[0.6875rem] text-text-subtle">{note}</p>}
        </div>
      </Link>
    </motion.div>
  );
}

/** A bare trend line. No axes, no labels — shape only, at a glance. */
function Sparkline({ values }: { values: number[] }) {
  const w = 100;
  const h = 20;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;

  const points = values.map((value, index) => ({
    x: (index / (values.length - 1)) * w,
    y: h - ((value - min) / range) * (h - 3) - 1.5,
  }));

  const d = points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x} ${p.y}`).join(" ");
  const rising = values[values.length - 1] >= values[0];

  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="mt-2 w-full" preserveAspectRatio="none" aria-hidden="true">
      <path
        d={d}
        fill="none"
        stroke={rising ? "var(--color-success)" : "var(--color-danger)"}
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}

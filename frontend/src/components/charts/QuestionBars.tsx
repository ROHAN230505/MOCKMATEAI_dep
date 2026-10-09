import { motion, useReducedMotion } from "framer-motion";
import { useState } from "react";

export interface QuestionDatum {
  number: number;
  questionText: string;
  isFollowup: boolean;
  isSkipped: boolean;
  /** 0-10 from the live evaluation. null when the turn was skipped or unscored. */
  relevance: number | null;
  completeness: number | null;
}

/**
 * Per-question performance across a single interview.
 *
 * Paired bars per turn — relevance and completeness — because they're the two
 * axes the live evaluator actually scored, and seeing them apart is what tells
 * you whether an answer missed the question or just under-delivered on it.
 *
 * A skipped turn renders as a dashed empty slot, not a zero-height bar. Section
 * 9.8 excludes skips from the scoring average entirely; drawing them at zero
 * here would contradict the number the rest of the page reports.
 */
export function QuestionBars({ data }: { data: QuestionDatum[] }) {
  const prefersReducedMotion = useReducedMotion();
  const [hover, setHover] = useState<number | null>(null);

  if (data.length === 0) {
    return <p className="py-6 text-center text-text-subtle">No questions recorded.</p>;
  }

  const active = hover !== null ? data.find((d) => d.number === hover) ?? null : null;

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-end gap-1.5" style={{ height: 116 }}>
        {data.map((turn) => {
          const isActive = hover === turn.number;
          return (
            <div
              key={turn.number}
              className="group flex h-full min-w-0 flex-1 cursor-default flex-col justify-end gap-1"
              onMouseEnter={() => setHover(turn.number)}
              onMouseLeave={() => setHover(null)}
            >
              {turn.isSkipped || turn.relevance === null ? (
                <div
                  className="w-full rounded-t-[3px] border border-dashed border-border-strong"
                  style={{ height: "22%" }}
                  aria-label={`Question ${turn.number}: skipped`}
                />
              ) : (
                <div className="flex h-full w-full items-end gap-[2px]">
                  <motion.div
                    className="flex-1 rounded-t-[3px]"
                    style={{ background: "var(--color-accent)" }}
                    initial={prefersReducedMotion ? false : { height: 0 }}
                    animate={{ height: `${(turn.relevance / 10) * 100}%` }}
                    transition={{ duration: 0.6, delay: turn.number * 0.03, ease: [0.16, 1, 0.3, 1] }}
                  />
                  <motion.div
                    className="flex-1 rounded-t-[3px]"
                    style={{ background: "var(--color-accent-2)", opacity: isActive ? 1 : 0.65 }}
                    initial={prefersReducedMotion ? false : { height: 0 }}
                    animate={{ height: `${((turn.completeness ?? 0) / 10) * 100}%` }}
                    transition={{ duration: 0.6, delay: turn.number * 0.03 + 0.05, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              )}
              <span
                className={`text-center text-[0.625rem] tabular-nums ${
                  isActive ? "text-text" : "text-text-subtle"
                }`}
              >
                {turn.isFollowup ? "↳" : turn.number}
              </span>
            </div>
          );
        })}
      </div>

      {/* Legend + readout share a fixed row so hovering never shifts the layout. */}
      <div className="flex min-h-[2.25rem] items-start justify-between gap-3 border-t border-border pt-2.5">
        {active ? (
          <p className="min-w-0 flex-1 truncate text-[0.75rem] text-text-muted">
            <span className="font-medium text-text">Q{active.number}</span> {active.questionText}
          </p>
        ) : (
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1.5 text-[0.6875rem] text-text-subtle">
              <span className="h-2 w-2 rounded-[2px]" style={{ background: "var(--color-accent)" }} />
              Relevance
            </span>
            <span className="flex items-center gap-1.5 text-[0.6875rem] text-text-subtle">
              <span className="h-2 w-2 rounded-[2px]" style={{ background: "var(--color-accent-2)" }} />
              Completeness
            </span>
            <span className="flex items-center gap-1.5 text-[0.6875rem] text-text-subtle">
              <span className="h-2 w-2 rounded-[2px] border border-dashed border-border-strong" />
              Skipped
            </span>
          </div>
        )}
        {active && !active.isSkipped && active.relevance !== null && (
          <span className="stat shrink-0 text-[0.75rem] text-text">
            {active.relevance}/10 · {active.completeness}/10
          </span>
        )}
      </div>
    </div>
  );
}

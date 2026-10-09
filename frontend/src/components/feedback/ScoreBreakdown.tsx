import { motion, useReducedMotion } from "framer-motion";
import type { CategoryScore } from "../../types/feedback";
import type { InterviewMode } from "../../types/interview";

/**
 * Section 10.2's four category scores.
 *
 * The important behaviour here is the `measured: false` case. A category with
 * no inputs renders as a dashed empty track with an em dash and an explicit
 * "not measured" note — never as a 0-width bar, which would read as a score of
 * zero for something nobody observed. Measured rows also show the weight
 * actually applied, so a candidate can see how the overall was assembled rather
 * than being handed a number to trust.
 *
 * The note is per category, because since Phase 5 the four fail for different
 * reasons and any one of them can now be the only one missing. A single line
 * saying "no voice-tone or video signal was recorded" under a blank body-language
 * row would be telling a candidate whose voice *was* analysed something untrue.
 */

const UNMEASURED_REASON: Record<string, string> = {
  content: "No answers were scored in this session, so there is nothing to measure against.",
  communication: "No transcript was captured in this session, so there is nothing to measure.",
  confidence:
    "No voice-tone signal was recorded in this session — the microphone was muted, or too little was spoken to measure — so this is left blank rather than estimated.",
  body_language:
    "No usable video signal was recorded in this session — the camera was off, the face wasn't visible, or the device couldn't run the analysis — so this is left blank rather than estimated.",
};

const UNMEASURED_FALLBACK =
  "Not measured in this session, so this is left blank rather than estimated.";

/**
 * Categories a modality has no signal for at all, and why.
 *
 * A different sentence from the ones above, because a different thing happened.
 * "No voice-tone signal was recorded — the microphone was muted" describes a
 * fault to go and fix; a signed interview has no audio track by design, and
 * there is nothing for the candidate to do about it or feel bad about.
 */
const INAPPLICABLE_REASON: Partial<Record<InterviewMode, Record<string, string>>> = {
  sign: {
    confidence:
      "Not scored in a signed interview — voice-tone analysis needs audio, and a signed interview has none. That's by design, not a gap in this session.",
  },
};
export function ScoreBreakdown({
  scores,
  mode = "voice",
}: {
  scores: CategoryScore[];
  mode?: InterviewMode;
}) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <ul className="flex flex-col gap-5">
      {scores.map((row, index) => {
        const measured = row.measured && row.score !== null;
        return (
          <li key={row.category}>
            <div className="mb-2 flex items-baseline justify-between gap-3">
              <span className={`text-sm font-medium ${measured ? "text-text" : "text-text-subtle"}`}>
                {row.label}
              </span>
              <span className="flex items-baseline gap-2.5">
                {measured && row.weight !== null && (
                  <span className="text-xs text-text-subtle">{Math.round(row.weight * 100)}% of overall</span>
                )}
                <span
                  className={`tnum text-base font-semibold ${measured ? "text-text" : "text-text-subtle"}`}
                >
                  {measured ? Math.round(row.score!) : "—"}
                </span>
              </span>
            </div>

            {measured ? (
              <div className="h-2 w-full overflow-hidden rounded-pill bg-surface-raised">
                <motion.div
                  className="h-full rounded-pill"
                  style={{ background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))" }}
                  initial={{ width: 0 }}
                  animate={{ width: `${Math.max(2, Math.min(100, row.score!))}%` }}
                  transition={{
                    duration: prefersReducedMotion ? 0 : 0.7,
                    delay: prefersReducedMotion ? 0 : index * 0.08,
                    ease: [0.22, 1, 0.36, 1],
                  }}
                />
              </div>
            ) : (
              <>
                {/* A dashed empty track reads as "no data", where a filled bar
                    at 0% would read as "you scored nothing". */}
                <div className="h-2 w-full rounded-pill border border-dashed border-border" />
                <p className="mt-2 text-xs leading-relaxed text-text-subtle">
                  {INAPPLICABLE_REASON[mode]?.[row.category] ??
                    UNMEASURED_REASON[row.category] ??
                    UNMEASURED_FALLBACK}
                </p>
              </>
            )}
          </li>
        );
      })}
    </ul>
  );
}

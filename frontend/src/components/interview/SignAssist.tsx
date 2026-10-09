import type { ArmingControl, PendingLetter, SignRecognitionStatus } from "../../hooks/useSignRecognition";
import { COVERED_LETTERS, EXCLUDED_LETTERS } from "../../lib/fingerspelling";

/**
 * The hand-recognition panel in sign mode.
 *
 * Its job is as much disclosure as control. Everything this panel drives is
 * assistive — the answer field beside it stays the authoritative input — so the
 * panel's real work is making sure the candidate always knows what the camera
 * thinks it is seeing, and never has a letter or an action appear without having
 * watched it coming.
 *
 * Hence: the pending letter is shown *with its confidence and a filling bar*
 * before it commits, control gestures show their arming progress, and the letters
 * the classifier cannot read are listed in the open rather than left for the
 * candidate to discover by failing to spell their own name.
 */

const CONTROL_COPY: Record<ArmingControl["action"], { icon: string; label: string }> = {
  submit: { icon: "✋", label: "Submit answer" },
  skip: { icon: "👎", label: "Skip question" },
};

function ProgressRing({ progress }: { progress: number }) {
  const circumference = 2 * Math.PI * 14;
  return (
    <svg viewBox="0 0 32 32" className="h-8 w-8 -rotate-90" aria-hidden="true">
      <circle cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2.5" className="text-border" />
      <circle
        cx="16" cy="16" r="14" fill="none" stroke="currentColor" strokeWidth="2.5"
        strokeLinecap="round"
        strokeDasharray={circumference}
        strokeDashoffset={circumference * (1 - Math.max(0, Math.min(1, progress)))}
        className="text-accent transition-[stroke-dashoffset] duration-100 ease-linear"
      />
    </svg>
  );
}

export function SignAssist({
  status,
  pending,
  arming,
  handPresent,
  fingerspelling,
  onToggleFingerspelling,
}: {
  status: SignRecognitionStatus;
  pending: PendingLetter | null;
  arming: ArmingControl | null;
  handPresent: boolean;
  fingerspelling: boolean;
  onToggleFingerspelling: () => void;
}) {
  if (status.state === "idle" || status.state === "loading") {
    return (
      <p className="mt-3 text-xs text-text-subtle">
        {status.state === "loading" ? "Starting hand recognition…" : null}
      </p>
    );
  }

  if (status.state === "unavailable") {
    // Not an error state. Typing is the primary input and works regardless; hand
    // recognition is the extra, so its absence is a note, not a warning.
    return (
      <p className="mt-3 text-xs leading-relaxed text-text-subtle">
        Hand recognition is off — {status.reason} You can type your answer as normal.
      </p>
    );
  }

  return (
    <div className="mt-3 flex flex-col gap-3 rounded-control border border-border bg-surface-raised/50 p-3">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className="flex items-center gap-2 text-xs font-medium text-text-muted">
          <span
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${handPresent ? "bg-success" : "bg-text-subtle"}`}
          />
          {handPresent ? "Hand detected" : "No hand in view"}
        </span>
        <button
          type="button"
          onClick={onToggleFingerspelling}
          aria-pressed={fingerspelling}
          className={`rounded-pill border px-3 py-1.5 text-xs font-medium transition-colors duration-200 ${
            fingerspelling
              ? "border-accent/50 bg-accent/12 text-accent"
              : "border-border text-text-muted hover:border-border-strong hover:text-text"
          }`}
        >
          Fingerspelling {fingerspelling ? "on" : "off"}
        </button>
      </div>

      {fingerspelling ? (
        <div className="flex items-center gap-3">
          {pending ? (
            <>
              <div className="relative flex items-center justify-center">
                <ProgressRing progress={pending.progress} />
                <span className="absolute text-sm font-semibold text-text">{pending.letter}</span>
              </div>
              <span className="min-w-0 text-xs leading-relaxed text-text-muted">
                {pending.describe} · confidence {Math.round(pending.confidence * 100)}%
                {pending.progress >= 1 && <span className="text-success"> · added</span>}
              </span>
            </>
          ) : (
            <span className="text-xs leading-relaxed text-text-subtle">
              {handPresent
                ? "That shape doesn't clearly match one of the letters below — hold it more definitely, or type instead."
                : "Hold a letter shape in view of the camera to add it."}
            </span>
          )}
        </div>
      ) : (
        <div className="flex items-center gap-3">
          {arming ? (
            <>
              <div className="relative flex items-center justify-center">
                <ProgressRing progress={arming.progress} />
                <span className="absolute text-xs">{CONTROL_COPY[arming.action].icon}</span>
              </div>
              <span className="text-xs text-text-muted">Keep holding to {CONTROL_COPY[arming.action].label.toLowerCase()}…</span>
            </>
          ) : (
            <span className="text-xs leading-relaxed text-text-subtle">
              Hold <span className="text-text">✋ an open palm</span> to submit, or{" "}
              <span className="text-text">👎 thumb down</span> to skip. Turn fingerspelling on to spell
              letters instead.
            </span>
          )}
        </div>
      )}

      <details className="group">
        <summary className="cursor-pointer list-none text-xs text-text-subtle underline decoration-dotted underline-offset-2">
          What this can and can't read
        </summary>
        <div className="mt-2 flex flex-col gap-2 text-xs leading-relaxed text-text-subtle">
          <p>
            Reads {COVERED_LETTERS.length} ASL letters from the shape of your hand:{" "}
            <span className="text-text-muted">{COVERED_LETTERS.join(" ")}</span>. It matches hand
            geometry against written descriptions of each letter — it is not a trained model, and its
            accuracy has not been measured against real signers.
          </p>
          <p>
            It is not a translator. ASL has its own grammar and is not fingerspelled English, so this
            spells words letter by letter and nothing more. Your typed answer is what gets submitted;
            fingerspelling just types for you.
          </p>
          <p>
            The other {Object.keys(EXCLUDED_LETTERS).length} letters are deliberately not read, because
            guessing them would produce wrong letters rather than none — {" "}
            <span className="text-text-muted">{Object.keys(EXCLUDED_LETTERS).join(" ")}</span> either
            share a handshape with a letter above, hide the thumb from the camera, or need movement.
          </p>
        </div>
      </details>
    </div>
  );
}

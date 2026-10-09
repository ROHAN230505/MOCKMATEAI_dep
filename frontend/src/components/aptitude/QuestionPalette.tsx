import type { PaletteState } from "../../types/practice";

/**
 * Section 4.14's question palette: a numbered grid you can jump from.
 *
 * ## Colour is never the only signal
 *
 * Section 4.14 specifies answered/unanswered/marked-for-review as green/grey/
 * yellow, and Section 17 names this exact screen when it says colour must never
 * be the sole indicator of state. So each state also carries a distinct shape —
 * a filled disc, an open ring, a corner flag — and its own `aria-label`.
 *
 * That is not decoration: roughly one man in twelve cannot reliably separate the
 * green and the yellow, and this grid is how a candidate decides what to revisit
 * with two minutes left.
 */

const STATE_STYLES: Record<PaletteState, string> = {
  answered: "border-success/50 bg-success/15 text-success",
  unanswered: "border-border text-text-subtle",
  review: "border-warning/50 bg-warning/15 text-warning",
};

const STATE_LABELS: Record<PaletteState, string> = {
  answered: "answered",
  unanswered: "not answered",
  review: "marked for review",
};

function StateMark({ state }: { state: PaletteState }) {
  if (state === "unanswered") {
    // An open ring: visibly hollow, not merely a different hue.
    return (
      <span
        aria-hidden="true"
        className="absolute right-0.5 bottom-0.5 h-1.5 w-1.5 rounded-full border border-current"
      />
    );
  }
  if (state === "answered") {
    return (
      <span aria-hidden="true" className="absolute right-0.5 bottom-0.5 h-1.5 w-1.5 rounded-full bg-current" />
    );
  }
  // Marked for review: a corner flag, unmistakable against a disc or a ring.
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 6 6"
      className="absolute top-0.5 right-0.5 h-1.5 w-1.5 fill-current"
    >
      <path d="M0 0h6L0 6z" />
    </svg>
  );
}

export function QuestionPalette({
  states,
  current,
  onJump,
}: {
  states: PaletteState[];
  current: number;
  onJump: (index: number) => void;
}) {
  const counts = states.reduce<Record<PaletteState, number>>(
    (acc, state) => ({ ...acc, [state]: acc[state] + 1 }),
    { answered: 0, unanswered: 0, review: 0 },
  );

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-6 gap-1.5 sm:grid-cols-8" role="list">
        {states.map((state, index) => (
          <button
            key={index}
            type="button"
            role="listitem"
            onClick={() => onJump(index)}
            aria-label={`Question ${index + 1}, ${STATE_LABELS[state]}`}
            aria-current={index === current ? "true" : undefined}
            className={`tnum relative flex h-9 items-center justify-center rounded-control border text-xs font-medium transition-colors duration-150 ${
              STATE_STYLES[state]
            } ${index === current ? "ring-2 ring-accent/50" : "hover:border-border-strong"}`}
          >
            {index + 1}
            <StateMark state={state} />
          </button>
        ))}
      </div>

      <ul className="flex flex-wrap gap-x-4 gap-y-1.5 text-[0.6875rem] text-text-subtle">
        {(["answered", "unanswered", "review"] as PaletteState[]).map((state) => (
          <li key={state} className="flex items-center gap-1.5">
            <span
              className={`relative flex h-4 w-4 items-center justify-center rounded-[3px] border ${STATE_STYLES[state]}`}
            >
              <StateMark state={state} />
            </span>
            {STATE_LABELS[state]} ({counts[state]})
          </li>
        ))}
      </ul>
    </div>
  );
}

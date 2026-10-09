import { useCallback, useEffect, useRef, useState } from "react";

/** Pacing targets, in minutes. `null` is the default: measure, do not pace. */
const TARGETS: { label: string; minutes: number | null }[] = [
  { label: "No target", minutes: null },
  { label: "20 min", minutes: 20 },
  { label: "30 min", minutes: 30 },
  { label: "45 min", minutes: 45 },
];

function clock(totalSeconds: number): string {
  const s = Math.max(0, Math.floor(totalSeconds));
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n: number) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${pad(m)}:${pad(sec)}`;
}

/**
 * A stopwatch for untimed practice, with an optional pacing target.
 *
 * ## Why elapsed rather than a countdown
 *
 * The aptitude mock test counts *down*, and correctly: it has a duration the
 * server owns, so there is a real deadline to display and a real reason to
 * submit at zero. DSA practice has neither. Inventing a per-problem limit and
 * counting down against it would be presenting a made-up number as a rule —
 * and the one thing this product does not do is show a figure that looks like
 * a measurement it never took.
 *
 * So the default is a plain elapsed clock, which is a real measurement of a
 * real thing. A target is opt-in, and when set it is described as a target:
 * the display turns amber as it approaches and stays visible past zero rather
 * than stopping, because knowing you took 41 minutes on a 30-minute target is
 * the useful fact. **Nothing is auto-submitted.** A countdown that takes your
 * editor away mid-thought teaches you to fear the clock rather than to use it.
 *
 * ## Why it does not pause when the tab is hidden
 *
 * Tempting, and wrong. Wall-clock time is what an interview costs you, and a
 * clock that stops while you read the answer somewhere else is not measuring
 * anything. It is driven off a start timestamp rather than an accumulating
 * counter for the same reason: a throttled background tab fires its interval
 * late and far less often, so a counter that adds a second per tick silently
 * under-reports. Recomputing from `Date.now()` cannot drift.
 */
export function PracticeTimer({
  /** Changing this restarts the clock — pass the problem or question id. */
  resetKey,
  className = "",
}: {
  resetKey?: string;
  className?: string;
}) {
  const startedAtRef = useRef(Date.now());
  const [elapsed, setElapsed] = useState(0);
  const [targetMinutes, setTargetMinutes] = useState<number | null>(null);
  const [running, setRunning] = useState(true);
  // Time already banked across pauses, so a pause does not rewrite history.
  const bankedRef = useRef(0);

  useEffect(() => {
    startedAtRef.current = Date.now();
    bankedRef.current = 0;
    setElapsed(0);
    setRunning(true);
  }, [resetKey]);

  useEffect(() => {
    if (!running) return;
    // Derived from a timestamp, never accumulated — see the docblock.
    const tick = () => setElapsed(bankedRef.current + (Date.now() - startedAtRef.current) / 1000);
    tick();
    const id = window.setInterval(tick, 1000);
    return () => window.clearInterval(id);
  }, [running]);

  const toggle = useCallback(() => {
    setRunning((wasRunning) => {
      if (wasRunning) {
        bankedRef.current += (Date.now() - startedAtRef.current) / 1000;
      } else {
        startedAtRef.current = Date.now();
      }
      return !wasRunning;
    });
  }, []);

  const reset = useCallback(() => {
    startedAtRef.current = Date.now();
    bankedRef.current = 0;
    setElapsed(0);
    setRunning(true);
  }, []);

  const targetSeconds = targetMinutes === null ? null : targetMinutes * 60;
  const over = targetSeconds !== null && elapsed > targetSeconds;
  const closing = targetSeconds !== null && !over && elapsed > targetSeconds * 0.8;
  const shown = targetSeconds === null ? elapsed : Math.abs(targetSeconds - elapsed);

  return (
    <div className={`flex flex-wrap items-center gap-2 ${className}`}>
      <div
        className={`flex items-center gap-2 rounded-control border px-2.5 py-1 ${
          over
            ? "border-danger/40 bg-danger/10"
            : closing
              ? "border-warning/40 bg-warning/10"
              : "border-border bg-surface"
        }`}
        // The value changes every second; announcing each tick would make a
        // screen reader unusable. The label carries the meaning instead.
        aria-label={
          targetSeconds === null
            ? `Elapsed time ${clock(elapsed)}`
            : `${over ? "Over target by" : "Remaining against target"} ${clock(shown)}`
        }
      >
        <span
          aria-hidden="true"
          className={`h-1.5 w-1.5 shrink-0 rounded-full ${
            !running ? "bg-text-subtle" : over ? "bg-danger" : closing ? "bg-warning" : "bg-accent"
          }`}
        />
        <span
          className={`tnum text-small font-medium ${
            over ? "text-danger" : closing ? "text-warning" : "text-text"
          }`}
        >
          {over ? "+" : ""}
          {clock(shown)}
        </span>
        {targetSeconds !== null && (
          <span className="text-micro text-text-subtle">
            {over ? "over" : "left"} of {targetMinutes}m
          </span>
        )}
      </div>

      <select
        value={targetMinutes === null ? "" : String(targetMinutes)}
        onChange={(event) => setTargetMinutes(event.target.value === "" ? null : Number(event.target.value))}
        aria-label="Pacing target"
        className="rounded-control border border-border bg-surface px-2 py-1 text-micro text-text-muted"
      >
        {TARGETS.map((t) => (
          <option key={t.label} value={t.minutes === null ? "" : String(t.minutes)}>
            {t.label}
          </option>
        ))}
      </select>

      <button
        type="button"
        onClick={toggle}
        className="rounded-control border border-border px-2 py-1 text-micro text-text-muted transition-colors duration-150 hover:border-border-strong hover:text-text"
      >
        {running ? "Pause" : "Resume"}
      </button>
      <button
        type="button"
        onClick={reset}
        className="rounded-control border border-border px-2 py-1 text-micro text-text-muted transition-colors duration-150 hover:border-border-strong hover:text-text"
      >
        Reset
      </button>

      {/* Said once, plainly, because the aptitude mock test *does* submit at
          zero and a user who has met that will reasonably expect this to. */}
      {targetSeconds !== null && (
        <span className="text-micro text-text-subtle">Nothing is submitted automatically.</span>
      )}
    </div>
  );
}

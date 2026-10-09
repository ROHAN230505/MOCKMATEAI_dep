/**
 * When a spoken answer is over — as a decision table, not as event handlers.
 *
 * ## Why this is a separate, pure module
 *
 * The browser recogniser reports a turn's life through four channels (`result`,
 * `end`, `error`, and our own silence clock) and *none of them means what it
 * sounds like*. `end` fires when Chrome's internal silence timer expires, not
 * when the candidate stops talking. `error: "aborted"` fires when an instance
 * is torn down, including by its own replacement. `error: "network"` fires on a
 * blip and recovers by itself. Deciding "the answer is finished" from any one
 * of them in isolation is how this went wrong twice:
 *
 *  1. `end` was treated as the end of the answer, so a candidate who paused to
 *     think before their first word had an empty turn submitted for them.
 *  2. Fixing that introduced restarts, which meant a superseded instance's
 *     late `aborted` could finalise a turn a healthy instance was still
 *     serving — so the interview asked all six questions in seconds and ended
 *     without listening to anyone.
 *
 * Both were one-line judgements buried in a callback, invisible to review and
 * untestable without a browser and a microphone. Here they are data, and
 * `scripts/verify-asr-turn.mjs` walks every combination.
 */

/**
 * Errors that no amount of retrying will fix.
 *
 * Only refused permission qualifies. `aborted`, `network`, `audio-capture` and
 * `no-speech` are all routine — treating them as terminal is the bug above.
 */
export const FATAL_ERRORS: ReadonlySet<string> = new Set(["not-allowed", "service-not-allowed"]);

/**
 * After speech, how long a gap means the answer is over.
 *
 * Raised from 1800ms. Under two seconds is a *conversational* pause, not the
 * end of an answer: people stop for that long mid-sentence while they retrieve
 * a number or decide how to phrase something, and cutting them off there is
 * the single most irritating thing an automated interviewer can do. 2600ms is
 * long enough to survive thinking and still short enough that finishing feels
 * responsive — and it is no longer the only way to end a turn, because the
 * candidate now has an explicit "done" control.
 */
export const SILENCE_TIMEOUT_MS = 2600;

/**
 * No turn may be finalised incidentally before this.
 *
 * Now a floor on *every* incidental finish rather than only on empty ones, and
 * empty ones are refused outright regardless -- see `canFinish`. What this
 * guards is the case where a single stray word is captured in the first
 * moments and something then tries to close the turn on it.
 */
export const MIN_LISTEN_MS = 2500;

/** Upper bound on total silence, so a dead microphone ends a turn rather than hanging the interview. */
export const EMPTY_TURN_TIMEOUT_MS = 25000;

/**
 * Loop guard. A broken mic re-ends instantly, and unbounded restarts would spin.
 *
 * Note what running out of budget now means: STOP RESTARTING. It does not mean
 * the answer is over. Conflating those two was a real bug -- see `canFinish`.
 */
export const MAX_AUTO_RESTARTS = 12;

/**
 * Minimum gap between restarts.
 *
 * Without pacing, the budget above is not a budget at all. A recogniser that
 * errors the instant it starts -- which is what `network` and `audio-capture`
 * do when something is actually wrong -- burns all twelve restarts inside two
 * seconds, and every one of them is wasted because the underlying condition
 * has not had time to change. Spacing them out turns twelve attempts into
 * several seconds of genuine retrying.
 */
export const MIN_RESTART_GAP_MS = 400;

export interface TurnSnapshot {
  /** Already handed up; every channel must go quiet. */
  finished: boolean;
  /** Muted by the candidate — `resumeListening` owns the next instance. */
  paused: boolean;
  /** We asked the recogniser to stop: Skip, time up, or the silence clock. */
  closing: boolean;
  /** False for an instance that a restart has already replaced. */
  isCurrent: boolean;
  /** Finalised text so far. Empty means nothing has been captured this turn. */
  transcript: string;
  startedAt: number;
  lastResultAt: number;
  restarts: number;
  /** When the last restart was issued, so retries can be paced rather than burned. */
  lastRestartAt: number;
}

export type TurnAction =
  /** Not ours, or not meaningful. Change nothing. */
  | { type: "ignore" }
  /** Keep the turn open on a fresh recogniser instance. */
  | { type: "restart" }
  /** Hand the transcript up. `deliberate` bypasses the empty-turn floor. */
  | { type: "finish"; deliberate: boolean }
  /** Hand up, and tell the candidate — they have to act on this one. */
  | { type: "fatal" };

const IGNORE: TurnAction = { type: "ignore" };

/** Events from an instance that is muted, spent or superseded are never acted on. */
function isMute(snapshot: TurnSnapshot): boolean {
  return snapshot.paused || snapshot.finished || !snapshot.isCurrent;
}

/** What to do about a recogniser error. */
export function onErrorAction(error: string, snapshot: TurnSnapshot): TurnAction {
  // Checked before `isCurrent`, because a pause aborts the instance on purpose
  // and that abort arrives as an error on the instance we still consider live.
  if (snapshot.paused) return IGNORE;
  if (snapshot.finished || !snapshot.isCurrent) return IGNORE;
  // Silence is the clock's business, not an error condition.
  if (error === "no-speech") return IGNORE;
  if (FATAL_ERRORS.has(error)) return { type: "fatal" };
  return { type: "restart" };
}

/**
 * What to do when the recogniser ends.
 *
 * The pivotal case is the last one: Chrome ending on its own is not evidence
 * that the candidate finished, so the turn restarts and the clock keeps
 * running. Only `closing` — something we or the candidate initiated — ends an
 * answer here.
 */
export function onEndAction(snapshot: TurnSnapshot): TurnAction {
  if (isMute(snapshot)) return IGNORE;
  if (snapshot.closing) return { type: "finish", deliberate: true };
  return { type: "restart" };
}

/**
 * What the silence clock decides.
 *
 * Both of its outcomes are deliberate: one has heard speech and waited out the
 * gap, the other has waited out a long silence from the start. This is the only
 * channel allowed to end an empty turn, which is what keeps "the interview
 * moved on without me" a decision made on a clock in one place.
 */
export function watchdogAction(snapshot: TurnSnapshot, now: number): TurnAction {
  if (isMute(snapshot)) return IGNORE;
  const hasSpoken = snapshot.transcript.trim().length > 0;
  if (hasSpoken && now - snapshot.lastResultAt > SILENCE_TIMEOUT_MS) {
    return { type: "finish", deliberate: true };
  }
  if (!hasSpoken && now - snapshot.startedAt > EMPTY_TURN_TIMEOUT_MS) {
    return { type: "finish", deliberate: true };
  }
  return IGNORE;
}

/**
 * Whether another restart is allowed *right now*.
 *
 * Two conditions, and the second is what makes the first mean anything: a
 * budget with no pacing is spent in the time it takes an error to fire twelve
 * times.
 */
export function canRestart(snapshot: TurnSnapshot, now: number): boolean {
  if (snapshot.restarts >= MAX_AUTO_RESTARTS) return false;
  return now - snapshot.lastRestartAt >= MIN_RESTART_GAP_MS;
}

/**
 * Whether the microphone looks genuinely broken, as opposed to merely quiet.
 *
 * The distinction the interview needs: a candidate thinking in silence must be
 * waited for, while a candidate whose microphone is not working needs to be
 * *told*, because they will otherwise sit through an entire interview being
 * scored on empty answers. Both look identical from inside the recogniser --
 * no results -- so the tell is that the engine kept falling over while
 * producing nothing at all.
 */
export function micLooksDead(snapshot: TurnSnapshot): boolean {
  return snapshot.restarts >= MAX_AUTO_RESTARTS && snapshot.transcript.trim().length === 0;
}

/**
 * The floor, applied at the one point every path converges on.
 *
 * **An empty turn can only ever be ended deliberately.** That is the whole
 * rule, and the previous version of it was wrong in a way that shipped a
 * serious bug.
 *
 * It used to allow an incidental finish once the turn was `MIN_LISTEN_MS`
 * old, reasoning that 2.5 seconds was long enough to have started speaking.
 * It is not -- and worse, it interacted with the restart budget. A recogniser
 * erroring on start burned all twelve restarts inside a second or two; the
 * exhausted path then called this function without `deliberate`; the turn was
 * by now 2.5 seconds old; so an empty answer was submitted and scored, and
 * the interview moved to its next question. Repeat that and the whole
 * interview is over in seconds with nothing recorded, which is exactly what
 * was reported.
 *
 * So silence is now ended by a clock or by a person, and by nothing else:
 *
 *   - the silence watchdog, once speech has actually been captured
 *   - the empty-turn timeout, after 25 seconds of genuine nothing
 *   - Skip, time running out, or the candidate saying they have finished
 *   - a refused microphone, which cannot recover and is reported as such
 *
 * A spent restart budget is none of those. It means *stop retrying*, and the
 * turn stays open for the clock to close.
 */
export function canFinish(snapshot: TurnSnapshot, deliberate: boolean, now: number): boolean {
  if (deliberate) return true;
  // Something was heard, so there is a real answer to submit and the only
  // question was whether the pause was long enough -- which the caller judged.
  if (snapshot.transcript.trim().length > 0) return now - snapshot.startedAt >= MIN_LISTEN_MS;
  return false;
}

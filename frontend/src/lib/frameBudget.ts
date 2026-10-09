/**
 * Frame pacing for the vision models, with self-measurement.
 *
 * ## The problem this solves
 *
 * Sign mode runs two MediaPipe models over the same camera feed on the same
 * thread: the Face Landmarker for Section 9.7's body-language signals, and the
 * Gesture Recognizer for hand recognition. Both were paced by a fixed 12fps
 * interval, which has two faults on a machine that cannot afford it.
 *
 * First, two independent timers drift into alignment and stay there, so both
 * models run inside the same animation frame and the interview stutters at their
 * combined cost rather than at either one's. A fixed phase offset keeps them
 * apart deliberately instead of leaving it to luck.
 *
 * Second, and more importantly: 12fps was a guess about how expensive inference
 * is. On a laptop where each pass takes 40ms rather than 8ms, a fixed interval
 * keeps demanding the same rate and the frame budget simply overruns — the
 * candidate gets a janky interview so that a signal can be sampled more often
 * than it needs to be. So this measures what inference actually costs on the
 * device it is running on and backs the rate off until it fits, rather than
 * trusting a number chosen on a developer's machine.
 *
 * Backing off is close to free for what it measures. Eye contact is a proportion
 * over minutes, posture episodes last seconds, and a fingerspelled letter is held
 * for 600ms — none of them need 12 samples a second, and all of them survive 6.
 * The interview not stuttering matters more.
 */

/** Never sample slower than this — below it a 600ms held letter could be missed. */
const FLOOR_FPS = 5;

export interface FrameBudgetOptions {
  /** The rate to aim for when the device can afford it. */
  targetFps: number;
  /** The slowest acceptable rate. Clamped to at least `FLOOR_FPS`. */
  minFps?: number;
  /**
   * How much of each interval the work may occupy before the rate is reduced.
   * At 0.5, inference taking longer than half the gap between runs is treated as
   * too expensive — leaving the rest of the interval for everything else sharing
   * the thread (React, TTS, the WebSocket, a WebGL background).
   *
   * Allowances add up, so this has to be set with the other consumers in mind.
   * Two models each granted 0.5 can between them claim the entire thread and
   * neither will ever consider itself the problem. Sign mode therefore gives
   * each of its two models 0.35, capping their combined draw near 70% and
   * leaving the rest for the interview itself.
   */
  maxLoadFraction?: number;
  /**
   * Shifts this consumer's slots away from another's. Two consumers given
   * different offsets interleave instead of colliding in the same frame.
   */
  phaseOffsetMs?: number;
}

export interface FrameBudget {
  /** Whether a run is due. Advances the schedule when it returns true. */
  due(now: number): boolean;
  /** Report how long the last run took, in ms. Adapts the rate. */
  record(durationMs: number): void;
  /** The interval currently targeted, in ms. */
  readonly intervalMs: number;
  /** The rate currently targeted, rounded for display. */
  readonly fps: number;
  /** Rolling mean cost of a run, in ms. Null before the first measurement. */
  readonly meanCostMs: number | null;
}

/** How sharply the rolling mean follows the most recent measurement. */
const SMOOTHING = 0.2;
/** Multiplicative step when backing off, and when recovering. */
const BACK_OFF = 1.25;
const RECOVER = 0.92;

export function createFrameBudget(options: FrameBudgetOptions): FrameBudget {
  const targetInterval = 1000 / options.targetFps;
  const slowestInterval = 1000 / Math.max(FLOOR_FPS, options.minFps ?? FLOOR_FPS);
  const maxLoad = options.maxLoadFraction ?? 0.5;

  let interval = targetInterval;
  let nextDueAt = -Infinity;
  let mean: number | null = null;
  // The offset is applied to the first slot only; after that the interval keeps
  // the two consumers apart on its own.
  let pendingOffset = options.phaseOffsetMs ?? 0;

  return {
    due(now: number): boolean {
      if (nextDueAt === -Infinity) {
        nextDueAt = now + pendingOffset;
        pendingOffset = 0;
        return false;
      }
      if (now < nextDueAt) return false;
      // Scheduled from `now` rather than from `nextDueAt`: after a long stall
      // (a backgrounded tab), catching up on every missed slot would run the
      // model dozens of times in a row for no benefit.
      nextDueAt = now + interval;
      return true;
    },

    record(durationMs: number): void {
      if (!Number.isFinite(durationMs) || durationMs < 0) return;
      mean = mean === null ? durationMs : mean * (1 - SMOOTHING) + durationMs * SMOOTHING;

      const load = mean / interval;
      if (load > maxLoad) {
        interval = Math.min(slowestInterval, interval * BACK_OFF);
      } else if (load < maxLoad * 0.5) {
        // Recover more slowly than we back off, so a single cheap frame does not
        // undo a reduction that a sustained cost earned.
        interval = Math.max(targetInterval, interval * RECOVER);
      }
    },

    get intervalMs() {
      return interval;
    },
    get fps() {
      return Math.round((1000 / interval) * 10) / 10;
    },
    get meanCostMs() {
      return mean === null ? null : Math.round(mean * 100) / 100;
    },
  };
}

/**
 * Grading logic for DSA runs (Phase 7).
 *
 * Separated from the Pyodide plumbing in `useDsaRunner` because it is pure: given
 * a set of case outcomes it decides what passed and what to say about it, with no
 * WASM, no Python and no clock. That is what `npm run verify:dsagrading` checks.
 *
 * ## Comparison is structural, not `===`
 *
 * A Python function returning `[0, 1]` arrives as a JavaScript array, and
 * `[0,1] === [0,1]` is false. Naive equality would fail every list-returning
 * problem in the bank, so `deepEqual` below walks the structure. It also treats
 * `1` and `1.0` as equal, because Python has no distinction there and a candidate
 * who returned an int where the expected value happens to be written as a float
 * has not made a mistake.
 *
 * ## What gets shown when a case fails
 *
 * Sample cases show their arguments and both values, because the candidate can
 * already see them in the problem statement — there is nothing to protect.
 * Hidden cases show only that they failed. Not because the values are secret
 * (grading runs in the candidate's own browser, so they could read them from
 * devtools, and the UI says as much) but because printing them turns "your
 * solution is wrong" into "here is the input to special-case", which is not
 * practice.
 */

export interface TestCase {
  args: unknown[];
  expected: unknown;
}

export type CaseOutcome =
  | { kind: "passed"; index: number; hidden: boolean; durationMs: number }
  | { kind: "failed"; index: number; hidden: boolean; durationMs: number; actual: unknown }
  | { kind: "error"; index: number; hidden: boolean; message: string }
  | { kind: "timeout"; index: number; hidden: boolean };

export interface RunSummary {
  outcomes: CaseOutcome[];
  passedCount: number;
  totalCount: number;
  /** Sum of the per-case durations for cases that actually ran. */
  runtimeMs: number;
  /** True only when every case passed. The server decides `status`; this is for the UI. */
  allPassed: boolean;
}

/**
 * Structural equality, with Python's number model in mind.
 *
 * `NaN` is treated as equal to itself: a problem whose expected value is NaN
 * would otherwise be unpassable, and `NaN !== NaN` is a JavaScript artefact
 * rather than anything a candidate did.
 */
export function deepEqual(a: unknown, b: unknown): boolean {
  if (a === b) return true;

  if (typeof a === "number" && typeof b === "number") {
    if (Number.isNaN(a) && Number.isNaN(b)) return true;
    // Both are finite and unequal at this point, so the only remaining question
    // is float representation. An exact comparison is right for the integer
    // answers in this bank; a tolerance would let a wrong answer through.
    return false;
  }

  if (Array.isArray(a) || Array.isArray(b)) {
    if (!Array.isArray(a) || !Array.isArray(b) || a.length !== b.length) return false;
    return a.every((item, index) => deepEqual(item, b[index]));
  }

  if (a && b && typeof a === "object" && typeof b === "object") {
    const left = a as Record<string, unknown>;
    const right = b as Record<string, unknown>;
    const leftKeys = Object.keys(left);
    const rightKeys = Object.keys(right);
    if (leftKeys.length !== rightKeys.length) return false;
    return leftKeys.every((key) => key in right && deepEqual(left[key], right[key]));
  }

  return false;
}

export function summarise(outcomes: CaseOutcome[]): RunSummary {
  const passedCount = outcomes.filter((outcome) => outcome.kind === "passed").length;
  const runtimeMs = outcomes.reduce(
    (total, outcome) => total + ("durationMs" in outcome ? outcome.durationMs : 0),
    0,
  );
  return {
    outcomes,
    passedCount,
    totalCount: outcomes.length,
    runtimeMs: Math.round(runtimeMs),
    allPassed: outcomes.length > 0 && passedCount === outcomes.length,
  };
}

/** One line per case, for the results panel. Hidden failures stay opaque. */
export function describeOutcome(outcome: CaseOutcome, testCase: TestCase | undefined): string {
  const label = outcome.hidden ? `Hidden test ${outcome.index + 1}` : `Example ${outcome.index + 1}`;

  switch (outcome.kind) {
    case "passed":
      return `${label}: passed`;
    case "timeout":
      return `${label}: timed out — your solution is probably looping forever or is too slow`;
    case "error":
      return `${label}: your code raised ${outcome.message}`;
    case "failed":
      if (outcome.hidden || testCase === undefined) {
        return `${label}: wrong answer`;
      }
      return (
        `${label}: for ${format(testCase.args)} expected ${format([testCase.expected])
          .slice(1, -1)} but got ${format([outcome.actual]).slice(1, -1)}`
      );
  }
}

/** Compact rendering for argument lists and values shown back to the candidate. */
export function format(value: unknown): string {
  if (value === null) return "None";
  if (value === undefined) return "None";
  if (typeof value === "boolean") return value ? "True" : "False";
  if (typeof value === "string") return JSON.stringify(value);
  if (Array.isArray(value)) return `(${value.map(format).join(", ")})`;
  if (typeof value === "object") {
    return `{${Object.entries(value as Record<string, unknown>)
      .map(([key, item]) => `${JSON.stringify(key)}: ${format(item)}`)
      .join(", ")}}`;
  }
  return String(value);
}

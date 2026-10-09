/**
 * Verification for DSA grading (`src/lib/dsaGrading.ts`).
 *
 *   npm run verify:dsagrading
 *
 * Fully checkable: the input is a set of case outcomes and the output is a
 * verdict, with no Python or WASM in the way. The checks that matter are the ones
 * about *not* being wrong in the candidate's favour or against them — structural
 * comparison of the list answers this bank is full of, and hidden failures
 * staying opaque.
 */
import { deepEqual, describeOutcome, format, summarise } from "../src/lib/dsaGrading.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

console.log();
console.log("structural comparison: the bank is full of list answers");
check("equal arrays compare equal", deepEqual([0, 1], [0, 1]));
// Held in variables so this is a real comparison rather than one the linter can
// fold away - the point being demonstrated is that reference equality fails here.
const listA = [0, 1];
const listB = [0, 1];
check("and would have failed under ===", (listA === listB) === false);
check("order matters", !deepEqual([1, 0], [0, 1]));
check("length matters", !deepEqual([0, 1], [0, 1, 2]));
check("nested arrays work", deepEqual([[1, 2], [3]], [[1, 2], [3]]));
check("empty arrays are equal", deepEqual([], []));
check("an array is not a scalar", !deepEqual([1], 1));

console.log();
console.log("scalars");
check("integers", deepEqual(6, 6));
check("Python's int/float sameness", deepEqual(1, 1.0));
check("booleans", deepEqual(true, true) && !deepEqual(true, false));
check("strings", deepEqual("blue is sky the", "blue is sky the"));
check("wrong string fails", !deepEqual("the sky is blue", "blue is sky the"));
check("None", deepEqual(null, null));
check("None is not 0", !deepEqual(null, 0));
check("None is not False", !deepEqual(null, false));
check("-1 is not 1", !deepEqual(-1, 1));
check("NaN equals itself, so a NaN answer is reachable", deepEqual(NaN, NaN));

console.log();
console.log("objects");
check("equal objects", deepEqual({ a: 1, b: [2] }, { a: 1, b: [2] }));
check("key order does not matter", deepEqual({ a: 1, b: 2 }, { b: 2, a: 1 }));
check("extra keys matter", !deepEqual({ a: 1 }, { a: 1, b: 2 }));

console.log();
console.log("summary arithmetic");
{
  const outcomes = [
    { kind: "passed", index: 0, hidden: false, durationMs: 1.4 },
    { kind: "passed", index: 1, hidden: false, durationMs: 2.1 },
    { kind: "failed", index: 0, hidden: true, durationMs: 1.0, actual: [9, 9] },
  ];
  const summary = summarise(outcomes);
  check("counts passes", summary.passedCount === 2, `-> ${summary.passedCount}`);
  check("counts total", summary.totalCount === 3, `-> ${summary.totalCount}`);
  check("sums runtime", summary.runtimeMs === 5, `-> ${summary.runtimeMs}ms`);
  check("allPassed is false with a failure", summary.allPassed === false);
}
{
  const all = summarise([
    { kind: "passed", index: 0, hidden: false, durationMs: 1 },
    { kind: "passed", index: 1, hidden: true, durationMs: 1 },
  ]);
  check("allPassed is true only when every case passed", all.allPassed === true);
}
{
  // No cases run is not a pass. A misconfigured problem must not read as solved.
  const none = summarise([]);
  check("an empty run is not a pass", none.allPassed === false);
  check("and reports zero, not NaN", none.passedCount === 0 && none.runtimeMs === 0);
}
{
  const errored = summarise([{ kind: "error", index: 0, hidden: false, message: "NameError" }]);
  check("an error is not a pass", errored.allPassed === false && errored.passedCount === 0);
  check("an errored case contributes no runtime", errored.runtimeMs === 0);
}
{
  const timedOut = summarise([{ kind: "timeout", index: 0, hidden: true }]);
  check("a timeout is not a pass", timedOut.allPassed === false);
}

console.log();
console.log("hidden failures stay opaque");
{
  const testCase = { args: [[2, 7, 11, 15], 9], expected: [0, 1] };
  const shown = describeOutcome(
    { kind: "failed", index: 0, hidden: false, durationMs: 1, actual: [1, 2] },
    testCase,
  );
  check("a sample failure shows the values", shown.includes("expected") && shown.includes("got"),
    `-> ${shown}`);
  check("because they are already in the problem statement", shown.includes("2, 7, 11, 15"));

  const hidden = describeOutcome(
    { kind: "failed", index: 3, hidden: true, durationMs: 1, actual: [1, 2] },
    testCase,
  );
  check("a hidden failure names no values", hidden === "Hidden test 4: wrong answer", `-> ${hidden}`);
  check("not even the arguments", !hidden.includes("2, 7"));
  check("nor the expected answer", !hidden.includes("0, 1"));

  const missingCase = describeOutcome(
    { kind: "failed", index: 0, hidden: false, durationMs: 1, actual: 5 },
    undefined,
  );
  check("a sample with no case data degrades safely", missingCase.includes("wrong answer"),
    `-> ${missingCase}`);
}
{
  const timeout = describeOutcome({ kind: "timeout", index: 0, hidden: false }, undefined);
  check("a timeout says what to look for", timeout.includes("looping forever"), `-> ${timeout}`);
  const error = describeOutcome(
    { kind: "error", index: 1, hidden: false, message: "NameError: name 'x' is not defined" },
    undefined,
  );
  check("an error surfaces the exception", error.includes("NameError"), `-> ${error}`);
}

console.log();
console.log("values are rendered in Python's spelling, not JavaScript's");
check("None, not null", format(null) === "None", `-> ${format(null)}`);
check("True, not true", format(true) === "True", `-> ${format(true)}`);
check("False, not false", format(false) === "False", `-> ${format(false)}`);
check("argument lists read like a call", format([[1, 2], 3]) === "((1, 2), 3)", `-> ${format([[1, 2], 3])}`);
check("strings are quoted", format("abc") === '"abc"', `-> ${format("abc")}`);
check("undefined does not leak the word", format(undefined) === "None");

console.log(failures === 0 ? "\nall DSA grading checks passed\n" : `\n${failures} DSA grading check(s) FAILED\n`);
process.exitCode = failures === 0 ? 0 : 1;

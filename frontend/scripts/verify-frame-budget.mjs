/**
 * Verification for the adaptive frame budget (`src/lib/frameBudget.ts`).
 *
 *   npm run verify:framebudget
 *
 * This one is fully checkable, unlike the classifiers it paces: the input is a
 * sequence of measured costs and the output is an interval, with no camera and no
 * model in the way. So the checks here are about the control loop's behaviour —
 * that it backs off under sustained load, recovers when load drops, respects both
 * bounds, interleaves two consumers, and cannot be pushed into running a model
 * dozens of times to "catch up" after a backgrounded tab.
 */
import { createFrameBudget } from "../src/lib/frameBudget.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

/** Drive a budget for `runs` slots, each costing `costMs`. Returns the timeline. */
function simulate(budget, { runs, costMs, startAt = 1000 }) {
  const slots = [];
  let now = startAt;
  // Step at 60fps, the rate an animation frame actually arrives at.
  while (slots.length < runs && now < startAt + 600_000) {
    if (budget.due(now)) {
      slots.push(now);
      budget.record(typeof costMs === "function" ? costMs(slots.length) : costMs);
    }
    now += 1000 / 60;
  }
  return slots;
}

console.log("\nan affordable device keeps the target rate");
{
  const budget = createFrameBudget({ targetFps: 12, maxLoadFraction: 0.5 });
  simulate(budget, { runs: 60, costMs: 6 });
  check("12fps target held when inference costs 6ms", budget.fps >= 11.5, `-> ${budget.fps}fps`);
  check("cost is reported, not assumed", budget.meanCostMs !== null && budget.meanCostMs > 4,
    `-> mean ${budget.meanCostMs}ms`);
}

console.log("\na struggling device backs itself off");
{
  const budget = createFrameBudget({ targetFps: 12, minFps: 5, maxLoadFraction: 0.5 });
  simulate(budget, { runs: 80, costMs: 55 });
  check("rate drops when inference costs 55ms", budget.fps < 9, `-> ${budget.fps}fps`);
  check("but never below the floor", budget.fps >= 5, `-> ${budget.fps}fps`);
  check("and the interval respects minFps exactly", budget.intervalMs <= 1000 / 5 + 1e-6,
    `-> ${budget.intervalMs.toFixed(1)}ms`);
}

console.log();
console.log("the load allowance is what decides, not the raw cost");
{
  // 30ms per pass is load 0.36 at 12fps. Whether that is affordable is entirely
  // a question of how much of the thread this consumer is entitled to -- which is
  // the difference between running alone and sharing with a second model.
  const alone = createFrameBudget({ targetFps: 12, minFps: 4, maxLoadFraction: 0.5 });
  simulate(alone, { runs: 200, costMs: 30 });
  check("30ms holds the target at a 0.5 allowance", alone.fps >= 11.5, `-> ${alone.fps}fps`);

  const shared = createFrameBudget({ targetFps: 12, minFps: 4, maxLoadFraction: 0.35 });
  simulate(shared, { runs: 200, costMs: 30 });
  check("the same 30ms backs off at the 0.35 allowance two models share",
    shared.fps < 11.5, `-> ${shared.fps}fps`);
  check("and settles well above the floor rather than bottoming out",
    shared.fps > 4.5, `-> ${shared.fps}fps`);
}

console.log("\nit recovers when the device frees up");
{
  const budget = createFrameBudget({ targetFps: 12, minFps: 5, maxLoadFraction: 0.5 });
  simulate(budget, { runs: 60, costMs: 60 });
  const backedOff = budget.fps;
  simulate(budget, { runs: 400, costMs: 4, startAt: 100_000 });
  check("returns toward the target once inference is cheap again",
    budget.fps > backedOff && budget.fps >= 11.5, `-> ${backedOff}fps then ${budget.fps}fps`);
  check("and never exceeds the target", budget.fps <= 12, `-> ${budget.fps}fps`);
}

console.log("\nrecovery is slower than back-off");
{
  const budget = createFrameBudget({ targetFps: 12, minFps: 5, maxLoadFraction: 0.5 });
  simulate(budget, { runs: 6, costMs: 70 });
  const afterSixExpensive = budget.intervalMs;
  const control = createFrameBudget({ targetFps: 12, minFps: 5, maxLoadFraction: 0.5 });
  simulate(control, { runs: 60, costMs: 70 });
  simulate(control, { runs: 6, costMs: 1, startAt: 100_000 });
  check("a few cheap frames do not undo a sustained reduction",
    control.intervalMs > afterSixExpensive * 0.5,
    `-> ${control.intervalMs.toFixed(1)}ms still reduced`);
}

console.log("\ntwo consumers interleave instead of colliding");
{
  const face = createFrameBudget({ targetFps: 12, phaseOffsetMs: 0 });
  const hands = createFrameBudget({ targetFps: 12, phaseOffsetMs: 1000 / 24 });
  const faceSlots = [];
  const handSlots = [];
  let now = 1000;
  for (let i = 0; i < 900; i += 1) {
    if (face.due(now)) { faceSlots.push(now); face.record(6); }
    if (hands.due(now)) { handSlots.push(now); hands.record(6); }
    now += 1000 / 60;
  }
  const collisions = faceSlots.filter((t) => handSlots.includes(t)).length;
  check("both consumers get their slots", faceSlots.length > 100 && handSlots.length > 100,
    `-> ${faceSlots.length} face, ${handSlots.length} hand`);
  check("they never share an animation frame", collisions === 0, `-> ${collisions} collisions`);
}

console.log("\na backgrounded tab does not cause a catch-up burst");
{
  const budget = createFrameBudget({ targetFps: 12 });
  budget.due(1000);
  budget.due(1200);
  // Five minutes with no animation frames, then one arrives.
  let runs = 0;
  if (budget.due(1200 + 300_000)) runs += 1;
  if (budget.due(1200 + 300_000)) runs += 1;
  if (budget.due(1200 + 300_016)) runs += 1;
  check("one missed slot is claimed, not three hundred", runs === 1, `-> ${runs} run(s)`);
}

console.log("\nnonsense measurements are ignored, not absorbed");
{
  const budget = createFrameBudget({ targetFps: 12 });
  simulate(budget, { runs: 20, costMs: 6 });
  const before = budget.intervalMs;
  budget.record(NaN);
  budget.record(-5);
  budget.record(Infinity);
  check("NaN, negative and infinite costs leave the rate alone",
    budget.intervalMs === before, `-> ${budget.intervalMs.toFixed(2)}ms unchanged`);
}

console.log(failures === 0 ? "\nall frame budget checks passed\n" : `\n${failures} frame budget check(s) FAILED\n`);
process.exitCode = failures === 0 ? 0 : 1;

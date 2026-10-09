/**
 * Verification for when a spoken answer ends (`src/lib/asrTurn.ts`).
 *
 *   npm run verify:asr
 *
 * This harness exists because of two shipped bugs, both silent, both severe,
 * and both a single line of judgement inside a browser callback:
 *
 *  1. `end` was read as "the candidate finished". Chrome fires it on its own
 *     internal silence timer, so anyone who paused to think before their first
 *     word had an empty answer submitted for them.
 *  2. Fixing that added restarts, and a superseded instance's late `aborted`
 *     error could then finalise a turn a healthy instance was still serving.
 *     The interview asked all six questions in a few seconds and ended without
 *     listening to anybody.
 *
 * Neither was reachable without a browser, a microphone and a person willing
 * to sit in silence. As a decision table both are ordinary assertions, and the
 * cases below are written as the scenarios that broke rather than as coverage
 * of the functions.
 */
import {
  canFinish,
  canRestart,
  micLooksDead,
  MIN_RESTART_GAP_MS,
  EMPTY_TURN_TIMEOUT_MS,
  FATAL_ERRORS,
  MAX_AUTO_RESTARTS,
  MIN_LISTEN_MS,
  onEndAction,
  onErrorAction,
  SILENCE_TIMEOUT_MS,
  watchdogAction,
} from "../src/lib/asrTurn.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const NOW = 1_000_000;

/** A live turn that has just started and heard nothing. */
const fresh = (over = {}) => ({
  finished: false,
  paused: false,
  closing: false,
  isCurrent: true,
  transcript: "",
  startedAt: NOW,
  lastResultAt: NOW,
  restarts: 0,
  lastRestartAt: 0,
  ...over,
});

console.log("\nasr turn lifecycle\n");
console.log("--- regression 1: Chrome ending on its own is not the end of an answer ---");

check(
  "a spontaneous end restarts instead of finishing",
  onEndAction(fresh()).type === "restart",
  "this is the bug that submitted empty answers for anyone who paused to think",
);
check(
  "a spontaneous end restarts even after speech was captured",
  onEndAction(fresh({ transcript: "I led a team of four" })).type === "restart",
  "the silence clock decides that, not the browser",
);
check(
  "a stop WE asked for does finish, deliberately",
  JSON.stringify(onEndAction(fresh({ closing: true }))) === JSON.stringify({ type: "finish", deliberate: true }),
);

console.log("\n--- regression 2: routine errors are not the end of an answer ---");

// The exact errors Chrome raises in normal operation. Each one used to finalise
// the turn, which advanced the interview to the next question.
for (const error of ["aborted", "network", "audio-capture"]) {
  check(
    `"${error}" restarts rather than finishing`,
    onErrorAction(error, fresh()).type === "restart",
    "finishing here is what asked six questions in five seconds",
  );
}
check("\"no-speech\" is ignored — the clock owns silence", onErrorAction("no-speech", fresh()).type === "ignore");

for (const error of ["not-allowed", "service-not-allowed"]) {
  check(`"${error}" is fatal and reported`, onErrorAction(error, fresh()).type === "fatal");
}
check(
  "only refused permission is fatal",
  FATAL_ERRORS.size === 2 && FATAL_ERRORS.has("not-allowed") && FATAL_ERRORS.has("service-not-allowed"),
  `${[...FATAL_ERRORS].join(", ")}`,
);
check(
  "an unknown future error restarts rather than ending the interview",
  onErrorAction("some-error-chrome-adds-in-2027", fresh()).type === "restart",
  "an unrecognised error must not be treated as a finished answer",
);

console.log("\n--- a superseded instance cannot act on the turn ---");

// The second bug's mechanism: a replaced recogniser keeps emitting, and its
// late events used to reach the shared turn.
const stale = fresh({ isCurrent: false });
check("a stale instance's error is ignored", onErrorAction("aborted", stale).type === "ignore");
check("a stale instance's end is ignored", onEndAction(stale).type === "ignore");
check("a stale instance's clock tick is ignored", watchdogAction(stale, NOW + 999_999).type === "ignore");
check(
  "a stale instance cannot even finish a closing turn",
  onEndAction(fresh({ isCurrent: false, closing: true })).type === "ignore",
  "otherwise the replacement's turn ends when the old instance drains",
);

console.log("\n--- a finished or muted turn goes quiet on every channel ---");

for (const [label, snap] of [["finished", fresh({ finished: true })], ["paused", fresh({ paused: true })]]) {
  check(`${label}: error ignored`, onErrorAction("network", snap).type === "ignore");
  check(`${label}: end ignored`, onEndAction(snap).type === "ignore");
  check(`${label}: clock ignored`, watchdogAction(snap, NOW + 999_999).type === "ignore");
}
check(
  "a pause's own abort is ignored even though the instance is still current",
  onErrorAction("aborted", fresh({ paused: true })).type === "ignore",
  "pauseListening aborts on purpose; that arrives as an error",
);
console.log("");
console.log("--- the floor: silence is never scored, at any age ---");

check(
  "an empty turn is refused an incidental finish while young",
  canFinish(fresh(), false, NOW + MIN_LISTEN_MS - 1) === false,
);
check(
  "an empty turn is STILL refused long afterwards",
  canFinish(fresh(), false, NOW + 10 * 60 * 1000) === false,
  "the regression: allowed after 2.5s, a spent restart budget then submitted an empty answer",
);
check(
  "a turn with speech in it may finish once past the floor",
  canFinish(fresh({ transcript: "I led a team" }), false, NOW + MIN_LISTEN_MS) === true,
);
check(
  "but not before the floor, even with speech",
  canFinish(fresh({ transcript: "um" }), false, NOW + 10) === false,
);
check(
  "a deliberate finish always proceeds, even empty",
  canFinish(fresh(), true, NOW + 10) === true,
  "Skip, time up, refused permission, and the candidate pressing Done",
);


console.log("\n--- the clock is the only channel that ends an empty turn ---");

check(
  "silence after speech finishes the turn",
  watchdogAction(fresh({ transcript: "I led a team", lastResultAt: NOW }), NOW + SILENCE_TIMEOUT_MS + 1).type === "finish",
);
check(
  "silence after speech waits out the full gap first",
  watchdogAction(fresh({ transcript: "I led a team", lastResultAt: NOW }), NOW + SILENCE_TIMEOUT_MS - 1).type === "ignore",
);
check(
  "total silence eventually finishes, so a dead mic cannot hang the interview",
  watchdogAction(fresh(), NOW + EMPTY_TURN_TIMEOUT_MS + 1).type === "finish",
);
check(
  "total silence is given real thinking time first",
  watchdogAction(fresh(), NOW + EMPTY_TURN_TIMEOUT_MS - 1).type === "ignore",
  `${EMPTY_TURN_TIMEOUT_MS / 1000}s`,
);
check(
  "every clock-driven finish is deliberate",
  watchdogAction(fresh(), NOW + EMPTY_TURN_TIMEOUT_MS + 1).deliberate === true
    && watchdogAction(fresh({ transcript: "x", lastResultAt: NOW }), NOW + SILENCE_TIMEOUT_MS + 1).deliberate === true,
  "otherwise the floor would block the very timer meant to enforce it",
);
check(
  "the empty-turn timeout leaves room for the floor",
  EMPTY_TURN_TIMEOUT_MS > MIN_LISTEN_MS,
  `${EMPTY_TURN_TIMEOUT_MS} > ${MIN_LISTEN_MS}`,
);

console.log("\n--- restarts are bounded ---");

check("a fresh turn may restart", canRestart(fresh(), NOW) === true);
check(
  "restarts stop at the limit rather than spinning",
  canRestart(fresh({ restarts: MAX_AUTO_RESTARTS }), NOW) === false,
  "a mic that re-ends instantly would otherwise loop forever",
);
check(
  "a restart is refused until the pacing gap has passed",
  canRestart(fresh({ restarts: 1, lastRestartAt: NOW }), NOW + MIN_RESTART_GAP_MS - 1) === false,
  "without pacing, twelve retries are spent in the time an error fires twelve times",
);
check(
  "and allowed once it has",
  canRestart(fresh({ restarts: 1, lastRestartAt: NOW }), NOW + MIN_RESTART_GAP_MS) === true,
);
check(
  "a dead mic is distinguishable from a thinking candidate",
  micLooksDead(fresh({ restarts: MAX_AUTO_RESTARTS })) === true
    && micLooksDead(fresh({ restarts: MAX_AUTO_RESTARTS, transcript: "I led a team" })) === false
    && micLooksDead(fresh()) === false,
  "restarts exhausted AND nothing heard — silence alone must never trigger it",
);

console.log(failures === 0 ? "\nall asr turn checks passed\n" : `\n${failures} asr turn check(s) FAILED\n`);
process.exit(failures === 0 ? 0 : 1);

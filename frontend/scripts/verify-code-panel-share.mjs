/**
 * Verification for the code panel's share decision (`src/lib/codePanelShare.ts`).
 *
 *   npm run verify:codepanel
 *
 * The panel itself needs a browser, but the question of *what reaches the server*
 * does not: it is a function of what the server is holding and what the panel now
 * looks like. That is the part with consequences — a stale snapshot means the
 * interviewer reads code the candidate has since un-shared, and a redundant send
 * spends the Section 12.1A event budget for nothing.
 */
import { applyShareAction, nextShareAction } from "../src/lib/codePanelShare.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

/** Replays a sequence of panel states, returning every action that would be sent. */
function replay(steps, start = { shared: true, sent: null }) {
  let server = start;
  const sent = [];
  for (const step of steps) {
    const action = nextShareAction(server, step);
    if (action.kind !== "none") sent.push(action);
    server = applyShareAction(server, action);
  }
  return { sent, server };
}

console.log("\ncode panel share decision\n");

// An untouched panel is not an event. The candidate opened it and typed nothing.
{
  const { sent } = replay([{ shared: true, code: "" }, { shared: true, code: "" }]);
  check("an empty shared panel sends nothing", sent.length === 0, `sent ${sent.length}`);
}

// Typing sends once per settled state, not once per state seen.
{
  const { sent } = replay([
    { shared: true, code: "def f(" },
    { shared: true, code: "def f(x)" },
    { shared: true, code: "def f(x):" },
    { shared: true, code: "def f(x):" },
  ]);
  check(
    "each distinct snapshot sends once, repeats send nothing",
    sent.length === 3 && sent.at(-1).code === "def f(x):",
    `sent ${sent.length}`,
  );
}

// The falling edge of the toggle must clear, or the interviewer keeps reading
// code the candidate has withdrawn.
{
  const { sent, server } = replay([
    { shared: true, code: "secret" },
    { shared: false, code: "secret" },
  ]);
  check(
    "turning sharing off clears what the server holds",
    sent.length === 2 && sent[1].kind === "clear" && server.sent === null,
    JSON.stringify(sent.map((a) => a.kind)),
  );
}

// ...but only on the edge. Typing on with the toggle off is private, and must
// not re-send the clear per keystroke.
{
  const { sent } = replay([
    { shared: true, code: "a" },
    { shared: false, code: "a" },
    { shared: false, code: "ab" },
    { shared: false, code: "abc" },
    { shared: false, code: "abcd" },
  ]);
  const clears = sent.filter((a) => a.kind === "clear").length;
  check("sharing stays off without re-sending the clear", clears === 1, `${clears} clears`);
}

// Turning it back on has to send even when the text is byte-for-byte what was
// sent before the toggle went off, because the server no longer holds it.
{
  const { sent, server } = replay([
    { shared: true, code: "same" },
    { shared: false, code: "same" },
    { shared: true, code: "same" },
  ]);
  check(
    "re-sharing unchanged text sends again",
    sent.length === 3 && sent[2].kind === "send" && server.sent === "same",
    JSON.stringify(sent.map((a) => a.kind)),
  );
}

// Everything typed while the toggle was off goes up in one snapshot when it
// comes back on -- the interviewer sees the current panel, not a replay.
{
  const { sent } = replay([
    { shared: true, code: "one" },
    { shared: false, code: "one" },
    { shared: false, code: "one two" },
    { shared: false, code: "one two three" },
    { shared: true, code: "one two three" },
  ]);
  check(
    "work done while private goes up as one snapshot",
    sent.at(-1).kind === "send" && sent.at(-1).code === "one two three",
    JSON.stringify(sent.at(-1)),
  );
}

// Deleting everything is a real change: the server is holding code that is no
// longer on the candidate's screen.
{
  const { sent } = replay([
    { shared: true, code: "draft" },
    { shared: true, code: "" },
  ]);
  check(
    "emptying a shared panel sends the empty snapshot",
    sent.length === 2 && sent[1].kind === "send" && sent[1].code === "",
    JSON.stringify(sent.map((a) => a.kind)),
  );
}

// A panel that starts un-shared has nothing to clear.
{
  const { sent } = replay([{ shared: false, code: "" }], { shared: false, sent: null });
  check("an already-private panel sends no clear on mount", sent.length === 0, `sent ${sent.length}`);
}

console.log(
  failures === 0
    ? "\nall code panel share checks passed\n"
    : `\n${failures} code panel share check(s) FAILED\n`,
);
process.exitCode = failures === 0 ? 0 : 1;

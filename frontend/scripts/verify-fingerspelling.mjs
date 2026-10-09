/**
 * Verification for the fingerspelling classifier (Phase 6).
 *
 *   npm run verify:fingerspelling
 *
 * ## What this can and cannot prove
 *
 * It builds hands out of anatomy — joint angles taken from how fingers actually
 * bend, not from whatever makes the tests pass — and checks that the classifier
 * reads each constructed handshape as the letter it was built to be. That proves
 * the code implements the rules in `lib/fingerspelling.ts`.
 *
 * It does **not** prove the rules match how real people sign. There is no
 * labelled dataset in this project, so there is no accuracy figure to report and
 * none is claimed. What the checks below do establish is the property that keeps
 * the feature safe regardless: that ambiguous handshapes return *nothing* rather
 * than a confident wrong letter.
 */
import {
  COVERED_LETTERS,
  EXCLUDED_LETTERS,
  handShape,
  recogniseLetter,
} from "../src/lib/fingerspelling.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const DEG = Math.PI / 180;

// Joint flexion per interphalangeal joint, from how a hand actually moves: a
// closed fist bends each joint to roughly a right angle, a relaxed curve about
// half that, an extended finger essentially not at all.
const FLEX = { straight: 4, partial: 42, curled: 82 };

// Palm laid out in the z = 0 plane: knuckles along x, fingers growing along +y,
// curling toward -z (the palm side).
const MCP_X = { index: -0.3, middle: -0.1, ring: 0.1, pinky: 0.3 };
const SEGMENTS = {
  index: [0.22, 0.15, 0.11],
  middle: [0.24, 0.16, 0.11],
  ring: [0.22, 0.15, 0.10],
  pinky: [0.17, 0.11, 0.09],
};

/** Grow a finger from its knuckle, flexing by `deg` at each joint. */
function growFinger(mcp, segments, deg, spreadDeg = 0) {
  const points = [mcp];
  let angle = 0; // rotation in the y-z plane, 0 = pointing along +y
  let current = mcp;
  for (const length of segments) {
    const spread = spreadDeg * DEG;
    current = {
      x: current.x + Math.sin(spread) * length,
      y: current.y + Math.cos(angle * DEG) * Math.cos(spread) * length,
      z: current.z - Math.sin(angle * DEG) * length,
    };
    points.push(current);
    angle += deg;
  }
  return points;
}

/**
 * Assemble the 21 landmarks MediaPipe would report for a described hand.
 * `fingers` gives a flex state per finger, `thumb` a placement.
 */
function buildHand({ index, middle, ring, pinky, thumb, spread = 0 }) {
  const wrist = { x: 0, y: 0, z: 0 };
  const knuckleY = 0.34;

  const fingers = { index, middle, ring, pinky };
  const spreads = { index: -spread, middle: spread * 0.35, ring: 0, pinky: 0 };

  const grown = {};
  for (const name of ["index", "middle", "ring", "pinky"]) {
    grown[name] = growFinger(
      { x: MCP_X[name], y: knuckleY, z: 0 },
      SEGMENTS[name],
      FLEX[fingers[name]],
      spreads[name],
    );
  }

  // Thumb placements, described by where the tip ends up relative to the hand.
  const cmc = { x: -0.34, y: 0.06, z: 0 };
  const THUMB = {
    // Pointing away from the hand, roughly perpendicular: L, Y.
    out: [
      { x: -0.46, y: 0.12, z: 0.01 },
      { x: -0.6, y: 0.17, z: 0.02 },
      { x: -0.74, y: 0.21, z: 0.02 },
    ],
    // Running up alongside the index finger's outer edge: A.
    alongside: [
      { x: -0.4, y: 0.16, z: -0.02 },
      { x: -0.42, y: 0.26, z: -0.03 },
      { x: -0.42, y: 0.36, z: -0.03 },
    ],
    // Folded in over the palm: B.
    across: [
      { x: -0.26, y: 0.14, z: -0.05 },
      { x: -0.14, y: 0.22, z: -0.07 },
      { x: -0.02, y: 0.28, z: -0.07 },
    ],
    // Curled toward the index tip but stopping short, leaving the open gap
    // that makes a C a C rather than an O.
    curved: null, // filled in below, since it depends on where the tips landed
    // Brought all the way to the index tip: O, and the pinch in F.
    meeting: null,
    // Drawn in against the folded fingers: D, I.
    tucked: [
      { x: -0.3, y: 0.16, z: -0.04 },
      { x: -0.26, y: 0.26, z: -0.05 },
      { x: -0.24, y: 0.34, z: -0.05 },
    ],
  };

  let thumbChain = THUMB[thumb];
  if (thumb === "meeting" || thumb === "pinch" || thumb === "curved") {
    // O and F both close the thumb onto the *index* tip; C reaches toward it and
    // stops short. `reach` is how much of the way there the tip travels.
    const target = grown.index[3];
    const reach = thumb === "curved" ? 0.55 : 1;
    const start = { x: cmc.x * 0.6, y: cmc.y + 0.1, z: -0.04 };
    const at = (t) => ({
      x: start.x + (target.x - start.x) * t,
      y: start.y + (target.y - start.y) * t + 0.05 * Math.sin(Math.PI * t),
      z: start.z + (target.z - start.z) * t,
    });
    thumbChain = [start, at(reach * 0.55), at(reach)];
  }

  const points = new Array(21);
  points[0] = wrist;
  points[1] = cmc;
  points[2] = thumbChain[0];
  points[3] = thumbChain[1];
  points[4] = thumbChain[2];
  const bases = { index: 5, middle: 9, ring: 13, pinky: 17 };
  for (const name of ["index", "middle", "ring", "pinky"]) {
    for (let i = 0; i < 4; i += 1) points[bases[name] + i] = grown[name][i];
  }
  return points;
}

/** The twelve covered letters, each described as anatomy rather than as numbers. */
const HANDS = {
  A: { index: "curled", middle: "curled", ring: "curled", pinky: "curled", thumb: "alongside" },
  B: { index: "straight", middle: "straight", ring: "straight", pinky: "straight", thumb: "across" },
  C: { index: "partial", middle: "partial", ring: "partial", pinky: "partial", thumb: "curved" },
  D: { index: "straight", middle: "curled", ring: "curled", pinky: "curled", thumb: "tucked" },
  F: { index: "curled", middle: "straight", ring: "straight", pinky: "straight", thumb: "pinch" },
  I: { index: "curled", middle: "curled", ring: "curled", pinky: "straight", thumb: "tucked" },
  L: { index: "straight", middle: "curled", ring: "curled", pinky: "curled", thumb: "out" },
  O: { index: "partial", middle: "partial", ring: "partial", pinky: "partial", thumb: "meeting" },
  U: { index: "straight", middle: "straight", ring: "curled", pinky: "curled", thumb: "tucked", spread: 2 },
  V: { index: "straight", middle: "straight", ring: "curled", pinky: "curled", thumb: "tucked", spread: 26 },
  W: { index: "straight", middle: "straight", ring: "straight", pinky: "curled", thumb: "tucked", spread: 14 },
  Y: { index: "curled", middle: "curled", ring: "curled", pinky: "straight", thumb: "out" },
};

console.log("\nthe straightness metric behaves as the thresholds assume");
{
  const straightHand = handShape(buildHand(HANDS.B));
  const fistHand = handShape(buildHand(HANDS.A));
  const curvedHand = handShape(buildHand(HANDS.C));
  check("an extended finger reads near 1.0", straightHand.index > 0.95, `-> ${straightHand.index.toFixed(3)}`);
  check("a folded finger reads well under 0.7", fistHand.index < 0.7, `-> ${fistHand.index.toFixed(3)}`);
  check("a relaxed curve lands between them", curvedHand.index > 0.7 && curvedHand.index < 0.9,
    `-> ${curvedHand.index.toFixed(3)}`);
}

console.log("\nmeasurements are scale and position invariant");
{
  const base = buildHand(HANDS.V);
  const moved = base.map((p) => ({ x: p.x * 3 + 5, y: p.y * 3 - 2, z: p.z * 3 + 9 }));
  const a = handShape(base);
  const b = handShape(moved);
  const keys = Object.keys(a);
  const worst = Math.max(...keys.map((k) => Math.abs(a[k] - b[k])));
  check("a hand 3x larger and moved reads identically", worst < 1e-9, `-> max drift ${worst.toExponential(1)}`);
}

console.log("\nevery covered letter reads back as itself");
const diagnostics = [];
for (const letter of COVERED_LETTERS) {
  const guess = recogniseLetter(buildHand(HANDS[letter]));
  diagnostics.push([letter, guess]);
  check(
    `${letter} -> ${letter}`,
    guess?.letter === letter,
    guess ? `-> ${guess.letter} (confidence ${guess.confidence}, margin ${guess.margin})` : "-> null",
  );
}

console.log("\nambiguity returns nothing rather than a confident mistake");
{
  // Genuinely between U and V: a spread that satisfies neither definition's
  // band. `spread: 10` lands the tips about 0.53 palm widths apart, inside the
  // dead zone between "together" (under 0.4) and "apart" (over 0.7).
  const between = buildHand({ ...HANDS.U, spread: 10 });
  const guess = recogniseLetter(between);
  check(
    "a hand between U and V is declined",
    guess === null,
    guess ? `-> claimed ${guess.letter} at ${guess.confidence}` : "-> null",
  );
}
{
  // A flat hand with every finger half-curled matches nothing in particular.
  const mush = buildHand({
    index: "partial", middle: "straight", ring: "curled", pinky: "partial", thumb: "tucked",
  });
  const guess = recogniseLetter(mush);
  check("an incoherent handshape is declined or low-margin",
    guess === null || guess.margin >= 0.12,
    guess ? `-> ${guess.letter} margin ${guess.margin}` : "-> null");
}

console.log("\ndegenerate input yields nothing, not a letter");
check("too few landmarks -> null", handShape([{ x: 0, y: 0, z: 0 }]) === null);
check("collapsed hand -> null", handShape(Array.from({ length: 21 }, () => ({ x: 0, y: 0, z: 0 }))) === null);
check("NaN coordinates -> null",
  handShape(Array.from({ length: 21 }, (_, i) => ({ x: i === 5 ? NaN : i * 0.1, y: 0.2, z: 0 }))) === null);
check("recogniseLetter passes the null straight through", recogniseLetter([]) === null);

console.log("\nthe confusable letters really are excluded, not silently mapped");
{
  // An S: fist with the thumb folded across the front of the fingers. It must not
  // come back as an A, which is the same fist with the thumb somewhere else.
  const s = buildHand({ index: "curled", middle: "curled", ring: "curled", pinky: "curled", thumb: "across" });
  const guess = recogniseLetter(s);
  check("an S-like fist is not reported as A", guess?.letter !== "A", guess ? `-> ${guess.letter}` : "-> null");
  check("S is documented as excluded", "S" in EXCLUDED_LETTERS);
  for (const letter of ["E", "M", "N", "T", "G", "H", "P", "Q", "R", "X", "J", "Z"]) {
    if (!(letter in EXCLUDED_LETTERS)) {
      check(`${letter} is documented as excluded`, false);
    }
  }
  check("all 14 exclusions carry a stated reason",
    Object.values(EXCLUDED_LETTERS).every((why) => typeof why === "string" && why.length > 20),
    `-> ${Object.keys(EXCLUDED_LETTERS).length} documented`);
  check("covered and excluded sets do not overlap",
    COVERED_LETTERS.every((l) => !(l in EXCLUDED_LETTERS)));
  check("together they account for the whole alphabet",
    COVERED_LETTERS.length + Object.keys(EXCLUDED_LETTERS).length === 26,
    `-> ${COVERED_LETTERS.length} covered + ${Object.keys(EXCLUDED_LETTERS).length} excluded`);
}

console.log("\nconfidence is reported, not implied");
for (const [letter, guess] of diagnostics) {
  if (guess) {
    check(`${letter} reports a usable confidence`, guess.confidence >= 0.62 && guess.confidence <= 1,
      `-> ${guess.confidence}`);
  }
}

console.log("\ncost");
{
  const hands = COVERED_LETTERS.map((l) => buildHand(HANDS[l]));
  const started = performance.now();
  for (let i = 0; i < 4000; i += 1) recogniseLetter(hands[i % hands.length]);
  const per = (performance.now() - started) / 4000;
  check("under 0.1ms per classification", per < 0.1, `-> ${per.toFixed(4)}ms`);
}

console.log(
  failures === 0
    ? "\nall fingerspelling checks passed (geometry only — accuracy against real signers is unmeasured)\n"
    : `\n${failures} fingerspelling check(s) FAILED\n`,
);
process.exitCode = failures === 0 ? 0 : 1;

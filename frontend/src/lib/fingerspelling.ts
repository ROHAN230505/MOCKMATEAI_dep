/**
 * ASL fingerspelling from hand landmark geometry (Phase 6, sign recognition).
 *
 * ## What this is, precisely
 *
 * A **geometric classifier**, not a trained model. It measures per-finger
 * straightness and thumb placement from MediaPipe's 21 hand landmarks and
 * matches them against hand-authored definitions of ASL letter handshapes. It is
 * described this way everywhere it surfaces, because the distinction matters: a
 * trained model has a measured accuracy on held-out data, and this has no such
 * number.
 *
 * ## What it does not do
 *
 * It does not translate sign language. ASL is not fingerspelled English — it has
 * its own grammar, and continuous sign translation is an open research problem.
 * This recognises individual static letters, which is a genuinely useful subset
 * (names, technical terms, acronyms) and nothing more than that.
 *
 * ## Which letters, and why not the rest
 *
 * Twelve letters are covered. The exclusions are deliberate, and each is
 * excluded because including it would produce *wrong* letters rather than no
 * letters:
 *
 * - **E, M, N, S, T** — the closed-fist family. All five are a fist differing
 *   only in where the thumb sits among the curled fingers, which is exactly
 *   where the thumb is most often occluded from the camera. A is included only
 *   because its thumb sits clearly outside the fist; the others would trade
 *   silence for confident mistakes.
 * - **G, H, P, Q** — these share a handshape with a covered letter and differ
 *   only by palm orientation (H is U rotated, P is K rotated, Q is G rotated).
 *   This classifier is deliberately orientation-independent so that a hand held
 *   at a natural angle still reads, which costs exactly these four.
 * - **R, X** — crossed and hooked fingers. Both are measurable in principle and
 *   both sit within landmark noise of a covered letter (R of U, X of D).
 * - **J, Z** — these are *movements*, not handshapes. A static frame cannot
 *   contain them.
 *
 * ## The honest limitation
 *
 * The thresholds below are derived from the geometry of each handshape, not
 * fitted to recordings of signers, and there is no labelled dataset in this
 * project to measure them against. `npm run verify:fingerspelling` proves the
 * code implements these rules on constructed hands; it cannot prove the rules
 * match how real people sign. Treat the numbers as a starting calibration.
 *
 * That is also why nothing here is authoritative: `useSignRecognition` requires
 * a letter to be held before it commits, shows the candidate each letter and its
 * confidence as it lands, and appends into a text field that stays fully
 * editable. A misread costs one keystroke, never a wrong answer.
 */

// MediaPipe's hand landmark indices.
const WRIST = 0;
const THUMB_CMC = 1;
const THUMB_MCP = 2;
const THUMB_IP = 3;
const THUMB_TIP = 4;
const INDEX_MCP = 5;
const INDEX_PIP = 6;
const INDEX_DIP = 7;
const INDEX_TIP = 8;
const MIDDLE_MCP = 9;
const MIDDLE_PIP = 10;
const MIDDLE_DIP = 11;
const MIDDLE_TIP = 12;
const RING_MCP = 13;
const RING_PIP = 14;
const RING_DIP = 15;
const RING_TIP = 16;
const PINKY_MCP = 17;
const PINKY_PIP = 18;
const PINKY_DIP = 19;
const PINKY_TIP = 20;

/**
 * The three flexion regimes, as straightness ratios.
 *
 * A fully extended finger's tip sits almost the summed length of its own
 * segments from its knuckle, so the ratio approaches 1; a folded one brings the
 * tip back toward the knuckle and it collapses. Measured on hands built from
 * anatomical joint angles, the three regimes land at roughly 0.99 extended, 0.84
 * relaxed-curve, 0.47 folded, and these bands bracket those.
 *
 * The bands are deliberately non-overlapping. An earlier single threshold pair
 * scored a 0.84 curved finger as 70% "straight", which was enough for F — three
 * fingers *extended* over a thumb-index pinch — to outscore O, which is the same
 * pinch with those fingers *curved*. The whole difference between the two letters
 * lives in this distinction, so it cannot be a soft one.
 */
const STRAIGHT_FROM = 0.88;
const STRAIGHT_FULL = 0.96;
const CURL_FROM = 0.78;
const CURL_FULL = 0.6;
const PARTIAL_LO = 0.78;
const PARTIAL_HI = 0.88;

/** A letter must beat the runner-up by this much before it is reported at all. */
const MIN_MARGIN = 0.12;
/** And clear this on its own terms. */
const MIN_CONFIDENCE = 0.62;

export interface Landmark3 {
  x: number;
  y: number;
  z: number;
}

/** The covered alphabet. Everything outside this set reads as no letter. */
export type Letter = "A" | "B" | "C" | "D" | "F" | "I" | "L" | "O" | "U" | "V" | "W" | "Y";

export const COVERED_LETTERS: readonly Letter[] = [
  "A", "B", "C", "D", "F", "I", "L", "O", "U", "V", "W", "Y",
];

/** Letters this classifier deliberately declines, and why — surfaced in the UI. */
export const EXCLUDED_LETTERS: Readonly<Record<string, string>> = {
  E: "fist shape, told apart from A/M/N/S/T only by a thumb the camera usually cannot see",
  M: "fist shape, thumb hidden under the fingers",
  N: "fist shape, thumb hidden under the fingers",
  S: "fist shape, thumb hidden in front of the fingers",
  T: "fist shape, thumb hidden between the fingers",
  G: "same handshape as another letter, differing only by palm orientation",
  H: "U rotated sideways — same handshape",
  P: "K rotated downward — same handshape",
  Q: "G rotated downward — same handshape",
  K: "V with the thumb pushed up between the fingers — within landmark noise of V",
  R: "crossed fingers, within landmark noise of U",
  X: "hooked index, within landmark noise of D",
  J: "requires movement, not a single handshape",
  Z: "requires movement, not a single handshape",
};

/**
 * The measurements every letter definition is written against.
 *
 * Distances are in palm widths rather than metres, so the same numbers hold for
 * a large hand near the camera and a small one further back. Straightness is
 * already a ratio and needs no scaling.
 */
export interface HandShape {
  /** Per-digit straightness, roughly 0.3 (fully curled) to 1.0 (straight). */
  thumb: number;
  index: number;
  middle: number;
  ring: number;
  pinky: number;
  /** Index-tip to middle-tip separation. Tells V from U. */
  indexMiddleSpread: number;
  /** Thumb tip to index tip. Near zero means pinched, as in F and O. */
  thumbIndexGap: number;
  /** Thumb tip to palm centre. Small means folded across the palm, as in B. */
  thumbToPalm: number;
  /** How far to the side of the index knuckle the thumb tip sits. Large in A and L. */
  thumbLateral: number;
  /** Mean of all four fingertips' distance to the thumb tip. Small in O. */
  tipsToThumb: number;
}

const distance = (a: Landmark3, b: Landmark3): number =>
  Math.hypot(a.x - b.x, a.y - b.y, a.z - b.z);

/**
 * How straight a digit is, independent of where the hand is or which way it
 * points: the direct knuckle-to-tip distance over the path length through its
 * own joints. A rotation of the whole hand changes neither.
 */
function straightness(points: readonly Landmark3[], chain: readonly number[]): number {
  let path = 0;
  for (let i = 1; i < chain.length; i += 1) path += distance(points[chain[i - 1]], points[chain[i]]);
  if (path <= 0) return 0;
  return distance(points[chain[0]], points[chain[chain.length - 1]]) / path;
}

/**
 * Reduce 21 landmarks to the handful of measurements the letter table needs.
 *
 * Pass MediaPipe's `worldLandmarks` rather than the normalised ones: they are
 * metric and centred on the hand itself, so nothing here depends on where in the
 * frame the hand happens to be or on the video's aspect ratio.
 *
 * Returns null for a landmark array that is not a hand — a collapsed or partial
 * set yields no shape rather than a shape of zeroes, which would match some
 * letter by accident.
 */
export function handShape(points: readonly Landmark3[]): HandShape | null {
  if (points.length < 21) return null;
  for (const point of points) {
    if (!Number.isFinite(point.x) || !Number.isFinite(point.y) || !Number.isFinite(point.z)) return null;
  }

  // Palm width, the scale everything else is expressed in. Knuckle span rather
  // than wrist-to-fingertip, because it does not change as fingers curl.
  const palm = distance(points[INDEX_MCP], points[PINKY_MCP]);
  if (palm <= 1e-6) return null;

  const palmCentre: Landmark3 = {
    x: (points[WRIST].x + points[INDEX_MCP].x + points[PINKY_MCP].x) / 3,
    y: (points[WRIST].y + points[INDEX_MCP].y + points[PINKY_MCP].y) / 3,
    z: (points[WRIST].z + points[INDEX_MCP].z + points[PINKY_MCP].z) / 3,
  };

  const tips = [INDEX_TIP, MIDDLE_TIP, RING_TIP, PINKY_TIP];
  const tipsToThumb =
    tips.reduce((sum, tip) => sum + distance(points[tip], points[THUMB_TIP]), 0) / (tips.length * palm);

  return {
    thumb: straightness(points, [THUMB_CMC, THUMB_MCP, THUMB_IP, THUMB_TIP]),
    index: straightness(points, [INDEX_MCP, INDEX_PIP, INDEX_DIP, INDEX_TIP]),
    middle: straightness(points, [MIDDLE_MCP, MIDDLE_PIP, MIDDLE_DIP, MIDDLE_TIP]),
    ring: straightness(points, [RING_MCP, RING_PIP, RING_DIP, RING_TIP]),
    pinky: straightness(points, [PINKY_MCP, PINKY_PIP, PINKY_DIP, PINKY_TIP]),
    indexMiddleSpread: distance(points[INDEX_TIP], points[MIDDLE_TIP]) / palm,
    thumbIndexGap: distance(points[THUMB_TIP], points[INDEX_TIP]) / palm,
    thumbToPalm: distance(points[THUMB_TIP], palmCentre) / palm,
    thumbLateral: distance(points[THUMB_TIP], points[INDEX_MCP]) / palm,
    tipsToThumb,
  };
}

// --- Soft membership --------------------------------------------------------
// Hard thresholds make a classifier flip between letters on a landmark jitter of
// a fraction of a millimetre. Ramps let a near-miss score 0.8 instead of 0, so
// the margin test below can tell "clearly a V" from "somewhere between U and V"
// and decline the second case.
const rampUp = (x: number, lo: number, hi: number): number =>
  Math.max(0, Math.min(1, (x - lo) / (hi - lo)));
const rampDown = (x: number, lo: number, hi: number): number => 1 - rampUp(x, lo, hi);
/** 1 well inside [lo, hi], falling off outside it. */
const band = (x: number, lo: number, hi: number): number =>
  Math.min(rampUp(x, lo - (hi - lo) * 0.5, lo), rampDown(x, hi, hi + (hi - lo) * 0.5));

const straight = (s: number): number => rampUp(s, STRAIGHT_FROM, STRAIGHT_FULL);
const curled = (s: number): number => rampUp(s, CURL_FROM, CURL_FULL);
/** Bent but not folded — the C and O family. */
const partial = (s: number): number => band(s, PARTIAL_LO, PARTIAL_HI);

/**
 * A weighted average of soft tests.
 *
 * Weighting is not decoration. Several letters differ from a neighbour by *one*
 * measurement — D from L only by where the thumb sits, U from V only by finger
 * spread, I from Y only by the thumb again. With every test counted equally, that
 * single discriminator was outvoted four-to-one by the finger tests the two
 * letters share, and both letters scored so close together that the margin gate
 * threw the answer away. The discriminating test has to carry the weight its job
 * deserves.
 */
type Test = readonly [value: number, weight?: number];

function weighted(tests: readonly Test[]): number {
  let sum = 0;
  let total = 0;
  for (const [value, weight = 1] of tests) {
    sum += value * weight;
    total += weight;
  }
  return total > 0 ? sum / total : 0;
}

interface LetterShape {
  letter: Letter;
  /** Shown in the UI beside the letter, so a candidate can see what it looked for. */
  describe: string;
  score: (s: HandShape) => number;
}

/**
 * The letter table.
 *
 * Each entry is a weighted set of soft tests. Every test is a statement about the
 * documented handshape — "in a V the index and middle are straight and apart, and
 * the ring and pinky are folded" — rather than a fitted coefficient, which is why
 * they are readable and also why they are unvalidated against real signers.
 */
const LETTER_SHAPES: readonly LetterShape[] = [
  {
    letter: "A",
    describe: "fist, thumb alongside the index",
    score: (s) =>
      weighted([
        [curled(s.index)], [curled(s.middle)], [curled(s.ring)], [curled(s.pinky)],
        // A *band*, not a ramp: in A the thumb rests against the side of the
        // index finger, so its tip sits a moderate distance from that knuckle.
        // Rewarding ever-larger values scored an L — whose thumb points away from
        // the hand entirely — as a better A than an A.
        [band(s.thumbLateral, 0.2, 0.55), 2],
        // Outside the palm, which is what separates A from the S/E/M/N/T fists.
        [rampUp(s.thumbToPalm, 0.45, 0.75), 2],
      ]),
  },
  {
    letter: "B",
    describe: "four fingers up together, thumb across the palm",
    score: (s) =>
      weighted([
        [straight(s.index)], [straight(s.middle)], [straight(s.ring)], [straight(s.pinky)],
        [rampDown(s.thumbToPalm, 0.35, 0.7), 2],
        [rampDown(s.indexMiddleSpread, 0.15, 0.5)],
      ]),
  },
  {
    letter: "C",
    describe: "curved hand, open gap",
    score: (s) =>
      weighted([
        [partial(s.index)], [partial(s.middle)], [partial(s.ring)], [partial(s.pinky)],
        // The open aperture is the whole of what separates C from O.
        [band(s.thumbIndexGap, 0.4, 0.9), 3],
      ]),
  },
  {
    letter: "D",
    describe: "index up, thumb meeting the folded fingers",
    score: (s) =>
      weighted([
        [straight(s.index)], [curled(s.middle)], [curled(s.ring)], [curled(s.pinky)],
        // Thumb drawn in rather than flung out. This alone is what stops a D from
        // scoring as an L, so it outweighs any single finger test.
        [rampDown(s.thumbLateral, 0.35, 0.7), 3],
      ]),
  },
  {
    letter: "F",
    describe: "thumb and index pinched, three fingers up",
    score: (s) =>
      weighted([
        [rampDown(s.thumbIndexGap, 0.1, 0.35), 3],
        // Genuinely extended, not merely uncurled: O is this same pinch with
        // these three fingers curved, so they must count for as much as the pinch.
        [straight(s.middle), 2], [straight(s.ring), 2], [straight(s.pinky), 2],
      ]),
  },
  {
    letter: "I",
    describe: "pinky only",
    score: (s) =>
      weighted([
        [straight(s.pinky)], [curled(s.index)], [curled(s.middle)], [curled(s.ring)],
        // I and Y are the same folded fingers with the same pinky out; only the
        // thumb differs, so it has to count for as much as the rest together.
        [rampDown(s.thumbLateral, 0.35, 0.7), 3],
      ]),
  },
  {
    letter: "L",
    describe: "index up, thumb out",
    score: (s) =>
      weighted([
        [straight(s.index)], [straight(s.thumb)],
        [rampUp(s.thumbLateral, 0.5, 0.85), 3],
        [curled(s.middle)], [curled(s.ring)], [curled(s.pinky)],
      ]),
  },
  {
    letter: "O",
    describe: "fingertips meeting the thumb",
    score: (s) =>
      weighted([
        [partial(s.index)], [partial(s.middle)], [partial(s.ring)], [partial(s.pinky)],
        [rampDown(s.thumbIndexGap, 0.1, 0.35), 3],
        [rampDown(s.tipsToThumb, 0.2, 0.6), 2],
      ]),
  },
  {
    letter: "U",
    describe: "index and middle up, together",
    score: (s) =>
      weighted([
        // Weighted, because the spread test below is heavy: with both fingers
        // counted singly, an L — index alone up, so its "spread" to a folded
        // middle finger reads wide — scored as a V.
        [straight(s.index), 2], [straight(s.middle), 2], [curled(s.ring)], [curled(s.pinky)],
        [rampDown(s.indexMiddleSpread, 0.4, 0.62), 3],
      ]),
  },
  {
    letter: "V",
    describe: "index and middle up, apart",
    score: (s) =>
      weighted([
        // Weighted, because the spread test below is heavy: with both fingers
        // counted singly, an L — index alone up, so its "spread" to a folded
        // middle finger reads wide — scored as a V.
        [straight(s.index), 2], [straight(s.middle), 2], [curled(s.ring)], [curled(s.pinky)],
        [rampUp(s.indexMiddleSpread, 0.45, 0.7), 3],
      ]),
  },
  {
    letter: "W",
    describe: "three fingers up",
    score: (s) =>
      weighted([
        [straight(s.index)], [straight(s.middle)], [straight(s.ring)],
        // The folded pinky is all that separates W from B.
        [curled(s.pinky), 2],
      ]),
  },
  {
    letter: "Y",
    describe: "thumb and pinky out",
    score: (s) =>
      weighted([
        [straight(s.thumb)],
        [rampUp(s.thumbLateral, 0.5, 0.85), 3],
        [straight(s.pinky)],
        [curled(s.index)], [curled(s.middle)], [curled(s.ring)],
      ]),
  },
];

export interface FingerspellingGuess {
  letter: Letter;
  /** 0-1, the winning definition's own score. Not a probability. */
  confidence: number;
  /** How far clear of the runner-up it was. */
  margin: number;
  describe: string;
}

/**
 * The best-matching letter, or null when nothing matches clearly enough.
 *
 * Two gates, and the margin is the important one. A hand halfway between U and V
 * scores well on both, and picking the higher would produce a confident letter
 * from an ambiguous handshape — which is the failure mode that would make this
 * feature worse than typing. Ambiguity returns null, and the candidate simply
 * holds the shape more definitely or uses the keyboard.
 */
export function scoreLetters(shape: HandShape): { letter: Letter; value: number }[] {
  return LETTER_SHAPES.map((entry) => ({ letter: entry.letter, value: entry.score(shape) })).sort(
    (a, b) => b.value - a.value,
  );
}

export function classifyFingerspelling(shape: HandShape): FingerspellingGuess | null {
  const scored = LETTER_SHAPES.map((entry) => ({ entry, value: entry.score(shape) })).sort(
    (a, b) => b.value - a.value,
  );

  const best = scored[0];
  const runnerUp = scored[1];
  if (!best || best.value < MIN_CONFIDENCE) return null;

  const margin = best.value - (runnerUp?.value ?? 0);
  if (margin < MIN_MARGIN) return null;

  return {
    letter: best.entry.letter,
    confidence: Math.round(best.value * 1000) / 1000,
    margin: Math.round(margin * 1000) / 1000,
    describe: best.entry.describe,
  };
}

/** Convenience for callers holding raw landmarks. */
export function recogniseLetter(points: readonly Landmark3[]): FingerspellingGuess | null {
  const shape = handShape(points);
  return shape === null ? null : classifyFingerspelling(shape);
}

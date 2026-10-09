/**
 * Verification for the nebula's geometry (`src/components/room/particleField.ts`).
 *
 *   npm run verify:nebula
 *
 * The renderer needs a GPU; the distribution does not. And the distribution is
 * where the design decisions live — three populations at different densities is
 * what separates a structure from a spray, and none of that is checkable by
 * looking at a still frame.
 *
 * The checks that matter here are the ones that fail silently on screen: a NaN
 * position drops a particle to the origin where it is invisible among thousands,
 * and an unseeded generator reshuffles the whole picture on every mount so the
 * composition reviewed is never the composition shipped.
 */
import { buildField, DEFAULT_FIELD, INK } from "../src/components/room/particleField.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const field = buildField();
const { coreCount, armCount, haloCount, radius } = DEFAULT_FIELD;
const total = coreCount + armCount + haloCount;

console.log("\nnebula particle field\n");

check("every particle is accounted for", field.count === total, `${field.count} of ${total}`);
check("buffers are the right length", field.positions.length === total * 3 && field.colors.length === total * 3 && field.scales.length === total);

// A single NaN sinks a particle to the origin, where it is invisible among
// thousands — so this never shows up as a visual bug, only as a wrong render.
const finite = [...field.positions].every(Number.isFinite) && [...field.colors].every(Number.isFinite);
check("no NaN or Infinity anywhere", finite);

const channels = [...field.colors];
check("colours stay in range", Math.min(...channels) >= 0 && Math.max(...channels) <= 1,
  `${Math.min(...channels).toFixed(2)}..${Math.max(...channels).toFixed(2)}`);

/** Planar distance from the axis, for particle `n`. */
const rOf = (n) => Math.hypot(field.positions[n * 3], field.positions[n * 3 + 2]);
const mean = (values) => values.reduce((a, b) => a + b, 0) / values.length;

const coreR = Array.from({ length: coreCount }, (_, n) => rOf(n));
const armR = Array.from({ length: armCount }, (_, n) => rOf(coreCount + n));
const haloR = Array.from({ length: haloCount }, (_, n) => rOf(coreCount + armCount + n));

check("the core is tighter than the arms", mean(coreR) < mean(armR) * 0.4,
  `core ${mean(coreR).toFixed(2)} vs arms ${mean(armR).toFixed(2)}`);
check("the halo sits outside the arms", Math.min(...haloR) > mean(armR),
  `halo min ${Math.min(...haloR).toFixed(2)} vs arms mean ${mean(armR).toFixed(2)}`);
check("nothing escapes the stated radius", Math.max(...haloR) <= radius * 1.6,
  `max ${Math.max(...haloR).toFixed(2)}`);

// Density has to *fall off* from the centre, not merely start small: a cubed
// radius bias is the difference between a bright hub and a flat disc.
const inner = coreR.filter((r) => r < radius * 0.05).length;
const outer = coreR.filter((r) => r >= radius * 0.05 && r < radius * 0.1).length;
check("core density falls off from the centre", inner > outer, `${inner} inside vs ${outer} in the next shell`);

// The core should read brighter, which is carried by per-particle scale.
const coreScale = mean(Array.from({ length: coreCount }, (_, n) => field.scales[n]));
const armScale = mean(Array.from({ length: armCount }, (_, n) => field.scales[coreCount + n]));
check("core particles are drawn larger", coreScale > armScale, `${coreScale.toFixed(2)} vs ${armScale.toFixed(2)}`);

// The ramps are a stated requirement -- ROSE on the dark theme, GOLD on the
// light one, single-family at every stop -- and they are the thing most likely
// to be quietly broken by a refactor of the colour helpers.
//
// Asserted as channel ORDER rather than as values, which is what lets the
// palette be retuned without editing this file while still catching the
// failure that matters: a stop drifting out of its family. Rose is red-leading
// with blue ahead of green; gold is red-leading with green ahead of blue.
// Those two orderings are mutually exclusive, so neither ramp can silently
// become the other, and nothing can go cool.
//
// This replaced a check for a cool rim and a white mid-band. Both existed to
// stop a gold-to-cyan interpolation passing through olive at its midpoint, and
// no ramp spans distant hues any more, so there is no midpoint to defend.
const rgbAt = (n) => [field.colors[n * 3], field.colors[n * 3 + 1], field.colors[n * 3 + 2]];
const avg = (list) => list.reduce((a, b) => [a[0] + b[0] / list.length, a[1] + b[1] / list.length, a[2] + b[2] / list.length], [0, 0, 0]);

const coreRgb = avg(Array.from({ length: coreCount }, (_, n) => rgbAt(n)));
const rimRgb = avg(Array.from({ length: haloCount }, (_, n) => rgbAt(coreCount + armCount + n)));
check(
  "the core is warm (red over blue)",
  coreRgb[0] > coreRgb[2],
  `r ${coreRgb[0].toFixed(2)} vs b ${coreRgb[2].toFixed(2)}`,
);
check(
  "the rim is warm too (red over blue)",
  rimRgb[0] > rimRgb[2],
  `r ${rimRgb[0].toFixed(2)} vs b ${rimRgb[2].toFixed(2)}`,
);

// Every particle, not just the averages. One cool stop left in by accident
// would average away against 14,800 warm ones and never show up above.
const armRgb = Array.from({ length: armCount }, (_, n) => rgbAt(coreCount + n));
const all = [
  ...Array.from({ length: coreCount }, (_, n) => rgbAt(n)),
  ...armRgb,
  ...Array.from({ length: haloCount }, (_, n) => rgbAt(coreCount + armCount + n)),
];
const cool = all.filter((c) => c[2] >= c[0]).length;
check("not one particle is cool", cool === 0, `${cool} with blue >= red`);

// Rose specifically, rather than merely warm: red leads and blue sits ahead of
// green. A red-over-blue check alone would pass for gold, rust or plain red.
const rose = all.filter((c) => c[0] > c[2] && c[2] > c[1]).length;
check("every luminous stop is rose (r > b > g)", rose === all.length, `${rose} of ${all.length}`);
// And a real spread, so "rose" cannot be satisfied by a near-grey.
const separated = all.filter((c) => c[0] - c[1] > 0.1).length;
check("the rose has actual chroma in it", separated === all.length, `${separated} of ${all.length}`);

// Density has to fall off outward in BOTH themes, and the two do it in opposite
// directions: additive light is brightest at the hub, printing ink is darkest
// there. So this asserts the hub is the extreme, whichever extreme that is.
const lum = (c) => 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
const inkField = buildField({ ...DEFAULT_FIELD, palette: INK });
const inkAt = (n) => [inkField.colors[n * 3], inkField.colors[n * 3 + 1], inkField.colors[n * 3 + 2]];
const inkCore = avg(Array.from({ length: coreCount }, (_, n) => inkAt(n)));
const inkRim = avg(Array.from({ length: haloCount }, (_, n) => inkAt(coreCount + armCount + n)));
check("luminous: the hub is the brightest part", lum(coreRgb) > lum(rimRgb),
  `${lum(coreRgb).toFixed(3)} vs ${lum(rimRgb).toFixed(3)}`);
check("ink: the hub is the darkest part", lum(inkCore) < lum(inkRim),
  `${lum(inkCore).toFixed(3)} vs ${lum(inkRim).toFixed(3)}`);
const inkAll = Array.from({ length: inkField.count }, (_, n) => inkAt(n));
check("ink: every stop is gold (r > g > b)", inkAll.length > 0 && inkAll.every((c) => c[0] > c[1] && c[1] > c[2]),
  `${inkAll.filter((c) => c[0] > c[1] && c[1] > c[2]).length} of ${inkAll.length}`);
// The two families must stay mutually exclusive, or a future edit could make
// both themes the same picture without either check above noticing.
check("the two ramps are different families", inkAll.every((c) => !(c[0] > c[2] && c[2] > c[1])));

// Determinism. Without it the composition shipped is never the one reviewed.
const again = buildField();
const identical = field.positions.every((value, index) => value === again.positions[index]);
check("the same seed builds the same field", identical);
const shifted = buildField({ ...DEFAULT_FIELD, seed: DEFAULT_FIELD.seed + 1 });
check("a different seed builds a different field", !field.positions.every((v, i) => v === shifted.positions[i]));

console.log(failures === 0 ? "\nall nebula field checks passed\n" : `\n${failures} nebula field check(s) FAILED\n`);
process.exitCode = failures === 0 ? 0 : 1;

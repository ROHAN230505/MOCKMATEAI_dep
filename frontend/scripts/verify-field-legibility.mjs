/**
 * Verification for reading the interface while the galaxy shows through it.
 *
 *   npm run verify:field
 *
 * Two numbers in `index.css` decide whether this product stays legible:
 * `--mm-veil` (how opaque a panel is) and `--mm-field` (a ceiling on the canvas
 * opacity). Both are tempting to nudge, because the field always looks better a
 * little stronger, and the cost of nudging them is invisible until someone
 * cannot read a timestamp. So the arithmetic lives here and fails the build.
 *
 * The worst case is not the average case, and this checks the worst:
 *
 *  - The field ACCUMULATES. Where thousands of points overlap, additive
 *    blending clips every channel at 1.0 and the hub converges on pure white;
 *    normal blending converges on the source colour, so an ink hub converges on
 *    the darkest stop in the palette. Either extreme is reached in practice, in
 *    the middle of the viewport, which is exactly where panels sit.
 *  - So this composites TEXT over PANEL over THAT EXTREME, rather than over the
 *    page ground, and requires the result to clear WCAG AA.
 *
 * The palettes are imported rather than restated, so changing a colour stop in
 * `particleField.ts` re-runs the proof instead of silently invalidating it.
 */
import { readFileSync } from "node:fs";
import { INK, LUMINOUS } from "../src/components/room/particleField.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const hex = (h) => {
  const n = parseInt(h.slice(1), 16);
  return [((n >> 16) & 255) / 255, ((n >> 8) & 255) / 255, (n & 255) / 255];
};
const lin = (c) => (c <= 0.03928 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4));
const relL = (c) => 0.2126 * lin(c[0]) + 0.7152 * lin(c[1]) + 0.0722 * lin(c[2]);
const ratio = (a, b) => {
  const x = relL(a), y = relL(b);
  return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
};
const over = (fg, alpha, bg) => fg.map((c, i) => alpha * c + (1 - alpha) * bg[i]);

/*
 * How the canvas reaches the page.
 *
 * `material.premultipliedAlpha` is left at its default of false, so three sets
 *   additive: blendFunc(SRC_ALPHA, ONE)                    rgb += tint*a ; a += a
 *   normal  : blendFuncSeparate(SRC_ALPHA, 1-SRC_ALPHA,
 *                               ONE,       1-SRC_ALPHA)    rgb -> tint   ; a -> 1
 * and the renderer's own `premultipliedAlpha: true` then has the browser
 * composite the finished buffer as
 *   out = canvas.rgb + page * (1 - canvas.a)
 */
const OVERLAPS = 12; // the hub is far denser than this; twelve already saturates
const accumulate = (tint, a, additive) => {
  let rgb = [0, 0, 0], al = 0;
  for (let i = 0; i < OVERLAPS; i += 1) {
    rgb = additive
      ? rgb.map((c, k) => Math.min(1, c + tint[k] * a))
      : rgb.map((c, k) => tint[k] * a + c * (1 - a));
    al = additive ? Math.min(1, al + a) : a + al * (1 - a);
  }
  return { rgb, a: al };
};
const onPage = (canvas, page) => canvas.rgb.map((c, k) => Math.min(1, c + page[k] * (1 - canvas.a)));

const PEAK_SHADER_ALPHA = 0.9; // the uOpacity ceiling in Nebula.tsx

const css = readFileSync(new URL("../src/index.css", import.meta.url), "utf8");
const lines = css.split(/\r?\n/);

/** Declarations inside one rule, matched by line so no regex escaping is involved. */
function block(selector) {
  const open = lines.findIndex((l) => l.trim() === selector + " {");
  if (open < 0) throw new Error("rule not found: " + selector);
  let close = open + 1;
  while (close < lines.length && lines[close].trim() !== "}") close += 1;
  const out = {};
  for (let i = open + 1; i < close; i += 1) {
    const line = lines[i].trim();
    if (!line.startsWith("--")) continue;
    const colon = line.indexOf(":");
    if (colon < 0) continue;
    let value = line.slice(colon + 1).trim();
    if (value.endsWith(";")) value = value.slice(0, -1).trim();
    out[line.slice(0, colon).trim()] = value;
  }
  return out;
}

const light = block(":root");
const dark = block(".dark");
const pct = (v) => Number(String(v).replace("%", "")) / 100;

console.log("\nfield legibility\n");

const THEMES = [
  // Ink on paper, drawn with NormalBlending, so the extreme is the DARKEST stop.
  { name: "light", tokens: light, palette: INK, additive: false, extremeStop: "core" },
  // Luminous on near-black, drawn additively, so the extreme is pure white.
  { name: "dark", tokens: dark, palette: LUMINOUS, additive: true, extremeStop: "mid" },
];

for (const theme of THEMES) {
  const t = theme.tokens;
  const veil = pct(t["--mm-veil"]);
  const cap = Number(t["--mm-field"]);
  const ground = hex(t["--mm-bg"]);
  const surface = hex(t["--mm-surface"]);

  console.log(`\n${theme.name.toUpperCase()}  veil ${(veil * 100).toFixed(0)}%  field cap ${cap}`);
  check(`${theme.name}: veil is a percentage in range`, Number.isFinite(veil) && veil > 0 && veil <= 1, String(t["--mm-veil"]));
  check(`${theme.name}: field cap is a number in range`, Number.isFinite(cap) && cap > 0 && cap <= 1, String(t["--mm-field"]));

  // The brightest (or darkest) pixel the field can ever put behind a panel.
  const saturated = onPage(accumulate(theme.palette[theme.extremeStop], PEAK_SHADER_ALPHA, theme.additive), ground);
  const worstBackdrop = over(saturated, cap, ground);
  const panelWorst = over(surface, veil, worstBackdrop);
  const panelResting = over(surface, veil, ground);

  for (const [token, floor] of [
    ["--mm-text", 4.5],
    ["--mm-text-muted", 4.5],
    // Subtle is meta text -- timestamps, key hints -- so it is held to the
    // non-essential floor rather than to body AA.
    ["--mm-text-subtle", 3.0],
  ]) {
    const r = ratio(hex(t[token]), panelWorst);
    check(`${theme.name}: ${token.slice(2)} on a field-lit panel`, r >= floor, `${r.toFixed(2)}:1 (needs ${floor})`);
  }

  /*
   * The panel's own edge -- the check that caught a real defect.
   *
   * A hairline one step off a FIXED ground is fine. Over a variable one it is
   * not: the panel's luminance sweeps through the border's own as the field
   * brightens behind it, and at the crossing the edge vanishes outright. It
   * measured 1.00:1 with `--mm-border`, which is why `.panel` uses the strong one.
   */
  const edge = ratio(hex(t["--mm-border-strong"]), panelWorst);
  check(`${theme.name}: panel edge survives the field behind it`, edge >= 1.15, `${edge.toFixed(2)}:1 (needs 1.15)`);

  // And the point of the whole exercise: the field has to actually be visible.
  const bare = ratio(worstBackdrop, ground);
  const through = ratio(panelWorst, panelResting);
  check(`${theme.name}: field is visible on the bare ground`, bare >= 1.5, `${bare.toFixed(2)}:1 (needs 1.5)`);
  check(`${theme.name}: field reads through a panel`, through >= 1.1, `${through.toFixed(2)}:1 (needs 1.1)`);
}

/*
 * Why light mode cannot simply reuse the luminous palette.
 *
 * Kept as an assertion rather than a comment because it is the one genuinely
 * non-obvious fact in this file. "Just use one palette for both themes" is an
 * invisible simplification in review and a disaster on screen, and the reason
 * is subtle: a single luminous point DOES darken paper measurably. It is the
 * overlap that kills it -- additive clipping drags the dense hub to white, and
 * white on warm stone is nothing at all.
 */
const paperGround = hex(light["--mm-bg"]);
const luminousOnPaper = onPage(accumulate(LUMINOUS.mid, PEAK_SHADER_ALPHA, true), paperGround);
const inkOnPaper = onPage(accumulate(INK.core, PEAK_SHADER_ALPHA, false), paperGround);
console.log("");
check(
  "the luminous palette really is invisible on paper",
  ratio(luminousOnPaper, paperGround) < 1.2,
  `${ratio(luminousOnPaper, paperGround).toFixed(2)}:1 — additive clipping sends the hub to white`,
);
check(
  "the ink palette really is visible on paper",
  ratio(inkOnPaper, paperGround) >= 4.5,
  `${ratio(inkOnPaper, paperGround).toFixed(2)}:1`,
);

console.log(failures === 0 ? "\nall field legibility checks passed\n" : `\n${failures} field legibility check(s) failed\n`);
process.exit(failures === 0 ? 0 : 1);

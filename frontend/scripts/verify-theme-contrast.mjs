/**
 * Verification for the theme's colour contract (`src/index.css`).
 *
 *   npm run verify:theme
 *
 * Reads the `--mm-*` tokens straight out of the stylesheet rather than
 * duplicating them here, so this cannot drift from what actually ships: change a
 * swatch and this harness re-checks the new one.
 *
 * Two things are checked, because they fail for different reasons:
 *
 *  - WCAG contrast, for "can this text be read at 13px".
 *  - Perceptual distance in CIE Lab, *including simulated dichromacy*, for "can
 *    these two states be told apart". A WCAG ratio cannot answer the second
 *    question at all: two colours of identical lightness and opposite hue score
 *    1.0 against each other and are trivially distinguishable, while a red and a
 *    green a deuteranope sees as the same colour can score well.
 *
 * Section 17's rule that state must never rest on colour alone is not decorative
 * caution. Green and red converge for a red-green dichromat no matter which
 * green and which red are chosen — the best pair reachable in this palette still
 * only separates by dE 15 — so pass/fail carries a text label in every place it
 * is shown, and the colour is reinforcement.
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const CSS = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "src", "index.css");
const css = fs.readFileSync(CSS, "utf8");

/** Pulls the `--mm-*` / `--grad-*` declarations out of one selector's block. */
function tokensIn(selector) {
  // Located as a rule, not as text. The file header mentions `.dark` in prose,
  // and a plain indexOf finds that sentence first and parses zero tokens out of
  // it -- which surfaces later as an unreadable "undefined" colour, not as a
  // missing-selector error. Line-based so there are no escapes to get wrong.
  const lines = css.split(/\r?\n/);
  const head = lines.findIndex((l) => {
    const t = l.trim();
    return t.startsWith(selector) && t.endsWith("{");
  });
  if (head < 0) throw new Error(`selector ${selector} not found as a rule in index.css`);
  const open = css.indexOf("{", css.indexOf(lines[head]));
  let depth = 0;
  let end = open;
  for (let i = open; i < css.length; i += 1) {
    if (css[i] === "{") depth += 1;
    else if (css[i] === "}") {
      depth -= 1;
      if (depth === 0) { end = i; break; }
    }
  }
  const body = css.slice(open, end);
  const out = {};
  for (const m of body.matchAll(/--((?:mm|grad)-[a-z0-9-]+)\s*:\s*(#[0-9a-fA-F]{6})\s*;/g)) {
    out[m[1]] = m[2].toLowerCase();
  }
  return out;
}

const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
const lin = (c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4);
const lum = (h) => { const [r, g, b] = hex(h).map(lin); return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((m, n) => n - m); return (x + 0.05) / (y + 0.05); };

const mul = (M, v) => M.map((r) => r[0] * v[0] + r[1] * v[1] + r[2] * v[2]);
const lab = (c) => {
  const X = 0.4124 * c[0] + 0.3576 * c[1] + 0.1805 * c[2];
  const Y = 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
  const Z = 0.0193 * c[0] + 0.1192 * c[1] + 0.9505 * c[2];
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116);
  const [fx, fy, fz] = [f(X / 0.95047), f(Y), f(Z / 1.08883)];
  return [116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)];
};
const deltaE = (a, b) => { const A = lab(a), B = lab(b); return Math.hypot(A[0] - B[0], A[1] - B[1], A[2] - B[2]); };

// Viénot-Brettel-Mollon dichromacy simulation.
const RGB2LMS = [[0.31399022, 0.63951294, 0.04649755], [0.15537241, 0.75789446, 0.08670142], [0.01775239, 0.10944209, 0.87256922]];
const LMS2RGB = [[5.47221206, -4.6419601, 0.16963708], [-1.1252419, 2.29317094, -0.1678952], [0.02980165, -0.19318073, 1.16364789]];
const DEUTAN = [[1, 0, 0], [0.9513092, 0, 0.04866992], [0, 0, 1]];
const PROTAN = [[0, 1.05118294, -0.05116099], [0, 1, 0], [0, 0, 1]];
const simulate = (h, M) => mul(LMS2RGB, mul(M, mul(RGB2LMS, hex(h).map(lin))));

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

/** Body text and UI labels: WCAG AA at normal size. */
const readable = (t, fg, bg, min = 4.5) => {
  const r = ratio(t[fg], t[bg]);
  check(`${fg} on ${bg}`, r >= min, `${r.toFixed(2)}:1 (needs ${min})`);
};
/** Surfaces and hairlines: enough of a step to be seen, nowhere near text levels. */
const separated = (t, a, b, min) => {
  const r = ratio(t[a], t[b]);
  check(`${a} steps off ${b}`, r >= min, `${r.toFixed(2)}:1 (needs ${min})`);
};
/** Two states a user must tell apart, checked with normal and dichromatic vision. */
const distinct = (t, a, b, min) => {
  const normal = deltaE(hex(t[a]).map(lin), hex(t[b]).map(lin));
  const d = deltaE(simulate(t[a], DEUTAN), simulate(t[b], DEUTAN));
  const p = deltaE(simulate(t[a], PROTAN), simulate(t[b], PROTAN));
  check(`${a} vs ${b}`, Math.min(normal, d, p) >= min,
    `dE normal ${normal.toFixed(0)} / deuteran ${d.toFixed(0)} / protan ${p.toFixed(0)} (needs ${min})`);
};

/*
 * The far end of a GRADIENT button.
 *
 * A gap this file had from the day the action gradient was added. It checked
 * the label against mm-accent, which is only the ramp's starting colour; the
 * other end is a 58/42 mix with mm-accent-2, and nothing ever looked at it.
 * So a perfectly legible button could be unreadable across its own right-hand
 * half and every check here would still pass.
 *
 * That was not hypothetical: the palette this replaced put mm-accent-2 well
 * below mm-accent in luminance, which took the far end to 3.46:1 against its
 * own label. A fail that shipped, because no assertion described it.
 *
 * Mixed in sRGB, matching what color-mix(in srgb, ...) actually does, so this
 * measures the button the browser paints rather than an idealised one.
 */
const gradientFarEnd = (t, pa = 0.58) => {
  const a = hex(t["mm-accent"]);
  const b = hex(t["mm-accent-2"]);
  const mixed = a.map((c, i) => pa * c + (1 - pa) * b[i]);
  return "#" + mixed.map((c) => Math.round(c * 255).toString(16).padStart(2, "0")).join("");
};

for (const [label, selector] of [["DARK", ".dark"], ["LIGHT", ":root"]]) {
  const t = tokensIn(selector);
  console.log(`\n${label} (${selector})\n`);

  readable(t, "mm-text", "mm-bg");
  readable(t, "mm-text", "mm-surface");
  readable(t, "mm-text", "mm-surface-raised");
  readable(t, "mm-text-muted", "mm-surface");
  readable(t, "mm-text-muted", "mm-bg");
  readable(t, "mm-text-subtle", "mm-surface", 3);
  readable(t, "mm-accent", "mm-surface");
  readable(t, "mm-accent", "mm-bg");
  // The label printed *on* a filled accent button -- the one that silently
  // breaks when an accent is lightened.
  readable(t, "mm-accent-contrast", "mm-accent");
  // ...and that same label at the other end of the gradient it sits on.
  {
    const far = gradientFarEnd(t);
    const r = ratio(t["mm-accent-contrast"], far);
    check("mm-accent-contrast on the gradient far end " + far, r >= 4.5,
      r.toFixed(2) + ":1 (needs 4.5)");
  }
  readable(t, "mm-accent", "mm-accent-soft");
  readable(t, "mm-danger", "mm-surface");
  readable(t, "mm-success", "mm-surface");
  readable(t, "mm-warning", "mm-surface");

  separated(t, "mm-border", "mm-surface", 1.15);
  separated(t, "mm-border-strong", "mm-surface", 1.4);
  separated(t, "mm-surface", "mm-bg", 1.05);

  // Status hues. The threshold is what this palette can actually reach; the
  // point of the check is that a future edit cannot quietly make it worse.
  distinct(t, "mm-success", "mm-danger", 10);
  distinct(t, "mm-success", "mm-warning", 22);
  distinct(t, "mm-danger", "mm-warning", 22);
}

console.log(
  failures === 0 ? "\nall theme contrast checks passed\n" : `\n${failures} theme contrast check(s) FAILED\n`,
);
process.exitCode = failures === 0 ? 0 : 1;

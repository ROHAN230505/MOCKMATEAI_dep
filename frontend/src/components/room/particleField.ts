/**
 * The nebula's geometry: where every particle sits, and what colour it is.
 *
 * Deliberately pure and separate from the renderer. This is the part with
 * decisions in it — a distribution that looks like a structure rather than a
 * cloud — and being pure means `verify:nebula` can assert those decisions hold
 * without a GPU, a canvas or a browser.
 *
 * Three populations, because a single one always reads as spray:
 *
 *   1. **core** — a tight, bright concentration. Radius biased by a cubed
 *      random so density falls off sharply from the centre; a uniform random
 *      would give a flat disc with no focus.
 *   2. **arms** — particles on logarithmic spiral arms with angular scatter.
 *      This is what makes it read as *rotating* even before it moves.
 *   3. **halo** — sparse rings well outside the arms, on a shallower plane,
 *      which is what gives the whole thing a sense of scale.
 */

export interface FieldOptions {
  coreCount: number;
  armCount: number;
  haloCount: number;
  /** Number of spiral arms. */
  arms: number;
  /** How far the arms wind, in turns. */
  windings: number;
  radius: number;
  seed: number;
  /** Which ramp to colour the field with. Defaults to the luminous one. */
  palette?: Palette;
}

export const DEFAULT_FIELD: FieldOptions = {
  coreCount: 3200,
  armCount: 9000,
  haloCount: 2600,
  arms: 4,
  windings: 1.65,
  radius: 26,
  seed: 20260902,
};

export interface Field {
  positions: Float32Array;
  colors: Float32Array;
  /** Per-particle size multiplier, so the core reads brighter and tighter. */
  scales: Float32Array;
  count: number;
}

/**
 * A seeded generator (mulberry32).
 *
 * `Math.random` would reshuffle the nebula on every mount, so a layout that
 * looked balanced in review would be a different picture on load — and the
 * verification harness could not assert anything about it.
 */
function rng(seed: number): () => number {
  let state = seed >>> 0;
  return () => {
    state = (state + 0x6d2b79f5) >>> 0;
    let t = state;
    t = Math.imul(t ^ (t >>> 15), t | 1);
    t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/*
 * The gradient, as three stops rather than two.
 *
 * Three stops survived several changes of palette, and the original argument
 * for them did not: it was about avoiding the muddy midpoint of an
 * interpolation between two distant hues, and neither ramp spans distant
 * hues any more. What three stops still buy is a *rate*. Two give a linear
 * fall-off; the mid stop lets the hub hold its colour a little way out
 * before the rim takes over, so the core does not end abruptly at its own
 * edge.
 *
 * Both ramps now come from the interface palette rather than from beside it —
 * rose on the near-black, gold on the cream, each one the theme's own accent
 * family at the lightness that theme can actually show.
 */
export type Stop = [number, number, number];

export interface Palette {
  core: Stop;
  mid: Stop;
  edge: Stop;
}

/**
 * The luminous ramp, for the near-black ground. Rose at every stop.
 *
 * Taken from the dark theme's own palette rather than invented beside it: the
 * mid stop IS the accent, and the rim is the deepest plum in the ramp. A
 * single-family ramp also sidesteps the problem that forced an earlier
 * three-stop design — interpolating between two distant hues passes through
 * their muddy average at the midpoint — so the mid stop is free to be the
 * richest colour in the picture, which matters, because the arms are 9000 of
 * the 14,800 particles and are therefore what "the dots" means.
 *
 * The hub still blooms to white and that is not a compromise. Additive light
 * clips at 1.0 per channel, so anywhere thousands of points overlap goes white
 * no matter what colour they are; a hot white centre with gold arms is what a
 * bright object actually looks like. The alternative — holding the hub gold —
 * would mean thinning the core until it stopped reading as a core.
 */
export const LUMINOUS: Palette = {
  core: [0.949, 0.769, 0.847], // pale hot rose, blooms white where it is densest
  mid: [0.808, 0.482, 0.631], // #D384A8 — the arms, and most of the field
  edge: [0.416, 0.118, 0.333], // #6A1E55, falls off into the near-black
};

/**
 * The ink ramp, for a light ground -- and the reason it has to exist.
 *
 * A luminous field cannot be seen on paper, and not for the obvious reason.
 * It is not that additive blending has nothing to add to: the canvas is
 * transparent, so the browser composites it over the page and a single
 * translucent point does darken the paper, measurably. The problem is what
 * happens where points overlap. Additive accumulation clips each channel at
 * 1.0, so the dense hub -- the most striking part of the picture -- converges
 * on white, and white on warm stone is 1.14:1. Invisible, and invisible
 * exactly where the composition is strongest. Swapping the hues for dark ones
 * does not fix it; they clip to white just the same.
 *
 * So light mode is drawn with NormalBlending, which converges on the source
 * colour instead of summing past it, and the palette becomes ink: the hub is
 * the DARKEST point rather than the brightest, and density falls off toward a
 * lighter rim exactly as printed ink does.
 *
 * All three stops are the light theme's own gold. On cream that has to mean
 * *antique* gold rather than the palette's #C8A96B, and the constraint is not
 * stylistic: #C8A96B measures 2.05:1 against the #F7F4ED page, so a literally
 * golden dot there is invisible however many of them there are. Darkening it
 * until it reads is the only way "golden" and "noticeable" are both true at
 * once — hence a hub at 7.01:1 that is unmistakably gold in hue and dark
 * enough to see. It is the same reasoning, and very nearly the same value, as
 * the light theme accent: #C8A96B could not be a link either.
 */
export const INK: Palette = {
  core: [0.42, 0.306, 0.078], // #6b4e14 deep antique gold, 7.01:1 on the paper
  mid: [0.522, 0.396, 0.149], // #856526 — the light theme accent itself
  edge: [0.663, 0.522, 0.267], // #a98544 light gold, fades into the cream
};

function mix(a: Stop, b: Stop, t: number): Stop {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

/**
 * Arm colour by normalised radius, across both halves of the gradient.
 *
 * Gold survives a little way out of the hub before white takes over, so the
 * core does not end abruptly at its own edge.
 */
function armColour(t: number, p: Palette): Stop {
  return t < 0.42 ? mix(p.core, p.mid, t / 0.42) : mix(p.mid, p.edge, (t - 0.42) / 0.58);
}

export function buildField(options: FieldOptions = DEFAULT_FIELD): Field {
  const { coreCount, armCount, haloCount, arms, windings, radius, seed } = options;
  const palette = options.palette ?? LUMINOUS;
  const count = coreCount + armCount + haloCount;
  const positions = new Float32Array(count * 3);
  const colors = new Float32Array(count * 3);
  const scales = new Float32Array(count);
  const random = rng(seed);
  let i = 0;

  const write = (x: number, y: number, z: number, colour: Stop, scale: number) => {
    positions[i * 3] = x;
    positions[i * 3 + 1] = y;
    positions[i * 3 + 2] = z;
    colors[i * 3] = colour[0];
    colors[i * 3 + 1] = colour[1];
    colors[i * 3 + 2] = colour[2];
    scales[i] = scale;
    i += 1;
  };

  // --- core ---------------------------------------------------------------
  for (let n = 0; n < coreCount; n += 1) {
    // Cubed so density collapses toward the centre instead of spreading evenly.
    const r = Math.pow(random(), 3) * radius * 0.22;
    const theta = random() * Math.PI * 2;
    const phi = Math.acos(2 * random() - 1);
    write(
      r * Math.sin(phi) * Math.cos(theta),
      r * Math.cos(phi) * 0.55,
      r * Math.sin(phi) * Math.sin(theta),
      mix(palette.core, palette.mid, random() * 0.3),
      1.25 + random() * 0.5,
    );
  }

  // --- arms ---------------------------------------------------------------
  for (let n = 0; n < armCount; n += 1) {
    const t = Math.pow(random(), 0.62);
    const r = 0.14 * radius + t * radius * 0.86;
    const arm = Math.floor(random() * arms);
    const base = (arm / arms) * Math.PI * 2 + t * windings * Math.PI * 2;
    // Scatter widens with radius: arms are tight at the hub and diffuse at the
    // rim, which is what stops them looking like drawn lines.
    const scatter = (random() - 0.5) * (0.16 + t * 0.55);
    const theta = base + scatter;
    write(
      Math.cos(theta) * r + (random() - 0.5) * 0.6,
      (random() - 0.5) * (1.1 + t * 1.6),
      Math.sin(theta) * r + (random() - 0.5) * 0.6,
      armColour(t, palette),
      0.7 + random() * 0.5,
    );
  }

  // --- halo ---------------------------------------------------------------
  for (let n = 0; n < haloCount; n += 1) {
    const r = radius * (1.02 + random() * 0.5);
    const theta = random() * Math.PI * 2;
    write(
      Math.cos(theta) * r,
      (random() - 0.5) * 3.4,
      Math.sin(theta) * r * 0.86,
      mix(palette.edge, palette.mid, random() * 0.25),
      0.45 + random() * 0.35,
    );
  }

  return { positions, colors, scales, count };
}

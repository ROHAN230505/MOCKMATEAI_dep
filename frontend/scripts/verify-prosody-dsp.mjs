/**
 * Numeric verification of the prosody pitch maths (Section 9.7).
 *
 *   npm run verify:prosody
 *
 * Why a script and not a unit test: the frontend has no test runner, and adding
 * one to check three functions would be a heavier change than the thing being
 * checked. Node strips the type annotations off `src/lib/prosodyDsp.ts` on
 * import, so this runs the real module against synthetic signals of known pitch
 * with no bundler and no new dependency -- and the numbers are real.
 *
 * It earned its place. The first implementation here used plain autocorrelation
 * with an overlap correction, and this harness is what caught it reporting 75Hz
 * for a 150Hz vowel. A candidate's confidence score is computed from these
 * numbers, so "it looked right" is not a standard they can be held to.
 */
import { decimate, detectPitch, scorePitchVariance } from "../src/lib/prosodyDsp.ts";

process.exitCode = run({ detectPitch, decimate, scorePitchVariance });

function run({ detectPitch, decimate, scorePitchVariance }) {
  const RATE = 48000;
  const N = 2048;
  let failures = 0;

  const check = (name, passed, detail = "") => {
    if (!passed) failures += 1;
    console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
  };

  /** A glottal-ish vowel: a fundamental plus decaying harmonics, like voiced speech. */
  const vowel = (f0, amp = 0.25, phase = 0) => {
    const buffer = new Float32Array(N);
    for (let i = 0; i < N; i += 1) {
      const t = i / RATE;
      let value = 0;
      for (let h = 1; h <= 8; h += 1) value += (1 / h) * Math.sin(2 * Math.PI * f0 * h * t + phase * h);
      buffer[i] = amp * value * 0.5;
    }
    return buffer;
  };

  // Deterministic LCG rather than Math.random, so a failure is reproducible.
  const noiseInto = (buffer, amp, seed) => {
    let state = seed;
    for (let i = 0; i < buffer.length; i += 1) {
      state = (state * 1103515245 + 12345) & 0x7fffffff;
      buffer[i] += ((state / 0x7fffffff) * 2 - 1) * amp;
    }
    return buffer;
  };

  console.log("\npitch accuracy across the speaking range");
  for (const f0 of [80, 100, 120, 150, 180, 220, 260, 300, 350]) {
    const detected = detectPitch(vowel(f0), RATE);
    const error = detected === null ? Infinity : (Math.abs(detected - f0) / f0) * 100;
    check(`${f0}Hz`, error < 3, detected === null ? "-> null" : `-> ${detected.toFixed(1)}Hz (${error.toFixed(2)}% error)`);
  }

  console.log("\nno octave errors (the failure this harness was written to catch)");
  for (const f0 of [110, 130, 150, 165, 200, 220, 240, 275, 330]) {
    const detected = detectPitch(vowel(f0), RATE);
    const halved = detected !== null && Math.abs(detected - f0 / 2) < f0 * 0.06;
    const doubled = detected !== null && Math.abs(detected - f0 * 2) < f0 * 0.12;
    check(`${f0}Hz is not read as a sub-harmonic`, !halved && !doubled, `-> ${detected?.toFixed(1) ?? "null"}Hz`);
  }

  console.log("\nrobustness");
  const loud = detectPitch(vowel(150, 0.6), RATE);
  const quiet = detectPitch(vowel(150, 0.03), RATE);
  check(
    "a quiet speaker reads the same pitch as a loud one",
    loud !== null && quiet !== null && Math.abs(loud - quiet) < 2,
    `-> ${loud?.toFixed(1)} vs ${quiet?.toFixed(1)}Hz`,
  );
  const noisy = detectPitch(noiseInto(vowel(160, 0.25), 0.04, 7), RATE);
  check("survives added noise", noisy !== null && Math.abs(noisy - 160) < 8, `-> ${noisy?.toFixed(1) ?? "null"}Hz`);

  console.log("\nrejection: nothing pitched, nothing reported");
  check("white noise -> null", detectPitch(noiseInto(new Float32Array(N), 0.3, 3), RATE) === null);
  check("silence -> null", detectPitch(new Float32Array(N), RATE) === null);

  console.log("\ndecimation");
  const decimated = decimate(vowel(150), RATE);
  check("48kHz decimates to 12kHz", Math.abs(decimated.rate - 12000) < 1, `-> ${decimated.rate}Hz, ${decimated.buffer.length} samples`);
  const untouched = decimate(vowel(150), 16000);
  check("16kHz passes through untouched", untouched.rate === 16000 && untouched.buffer.length === N);

  console.log("\nvariance scoring, end to end through detectPitch");
  /** Speak `contour` on a loop, detect each frame's pitch, and score the spread. */
  const speak = (contour, frames = 300) => {
    const readings = [];
    for (let i = 0; i < frames; i += 1) {
      const pitch = detectPitch(vowel(contour[i % contour.length], 0.25, i * 0.37), RATE);
      if (pitch !== null) readings.push(12 * Math.log2(pitch / 100));
    }
    return { score: scorePitchVariance(readings), detected: readings.length };
  };

  const monotone = speak([150, 151, 149, 150.5]);
  check("a monotone delivery scores low", monotone.score !== null && monotone.score < 15, `-> ${monotone.score} (${monotone.detected} readings)`);

  const moderate = speak([140, 155, 172, 150, 163, 145]);
  check("a moderate delivery lands mid-scale", moderate.score > 15 && moderate.score < 85, `-> ${moderate.score}`);

  const expressive = speak([110, 145, 190, 250, 130, 210, 165, 95]);
  check("an expressive delivery scores high", expressive.score !== null && expressive.score > 60, `-> ${expressive.score}`);

  check("the scale is ordered", monotone.score < moderate.score && moderate.score < expressive.score,
    `-> ${monotone.score} < ${moderate.score} < ${expressive.score}`);

  check("too few readings -> null", scorePitchVariance([1, 2, 3]) === null);

  // One octave error in an otherwise flat delivery must not flip the verdict.
  const flat = Array.from({ length: 396 }, (_, i) => 12 * Math.log2([150, 151, 149, 150.5][i % 4] / 100));
  const withOutliers = flat.concat([300, 300, 75, 75].map((f) => 12 * Math.log2(f / 100)));
  const robust = scorePitchVariance(withOutliers);
  check("trimming absorbs stray octave outliers", robust !== null && robust < 25, `-> ${robust}`);

  console.log("\ncost on the UI thread, beside a live interview");
  const frames = Array.from({ length: 600 }, (_, i) => vowel(100 + (i % 200), 0.25, i * 0.31));
  const startedAt = performance.now();
  for (const frame of frames) detectPitch(frame, RATE);
  const perFrame = (performance.now() - startedAt) / frames.length;
  // The hook analyses ~20 frames a second, so the budget is 50ms per frame.
  // Anything approaching that would be visible as jank next to TTS and ASR.
  check("under 2ms per analysed frame", perFrame < 2, `-> ${perFrame.toFixed(3)}ms (${(perFrame * 20).toFixed(2)}% of one core at 20Hz)`);

  console.log(failures === 0 ? "\nall prosody DSP checks passed\n" : `\n${failures} prosody DSP check(s) FAILED\n`);
  return failures === 0 ? 0 : 1;
}

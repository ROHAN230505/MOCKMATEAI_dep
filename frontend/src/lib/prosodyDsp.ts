/**
 * The pitch-analysis maths behind Section 9.7's prosody signals.
 *
 * Split out of `useProsodyAnalyser` because it is pure: given a buffer of
 * samples it returns a number, with no audio graph, no React and no clock. That
 * makes it the part of the prosody pipeline that can actually be checked against
 * known input, which matters for a measurement the candidate's confidence score
 * is computed from.
 */

// --- Pitch ------------------------------------------------------------------
// The human speaking range, generously bounded: ~70Hz covers a low male voice,
// ~400Hz a high female one. Searching wider mostly finds harmonics.
const MIN_PITCH_HZ = 70;
const MAX_PITCH_HZ = 400;
// Below this the periodicity peak is not distinct enough to be a pitch -- it is
// noise, an unvoiced consonant, or two people talking. NSDF (below) tops out at
// 1.0 for a perfectly periodic frame and runs 0.7-0.95 for clean voiced speech,
// so this sits well under real speech and well over noise.
const MIN_CLARITY = 0.55;

// How close a periodicity peak has to come to the strongest one before it is
// preferred for being *earlier*.
//
// This constant is the whole defence against octave errors, which are the
// characteristic failure of every autocorrelation-family pitch detector: a
// periodic signal correlates almost as well against itself at twice its period
// as at its period, so a naive "take the tallest peak" search reports 75Hz for a
// 150Hz voice roughly whenever noise tips the balance. The fundamental is by
// definition the *shortest* period that fits, so taking the earliest peak that
// is within 10% of the tallest picks it and skips its sub-harmonics.
const PEAK_PREFERENCE = 0.9;

// Autocorrelation is O(lags x window), and at 48kHz that is ~1M multiply-adds
// per frame -- enough to visibly compete with TTS, ASR and the video preview on
// the same thread. Two cuts bring it to a rounding error. The first is here:
// decimate to ~12kHz, since nothing above 400Hz matters and 48kHz is 4x more
// resolution than the measurement can use. The second lives in the hook, which
// only calls this every third animation frame.
const TARGET_PITCH_SAMPLE_RATE = 12_000;

/** Semitone-spread anchors for the 0-100 score -- see `scorePitchVariance`. */
const MONOTONE_SEMITONES = 0.6;
const EXPRESSIVE_SEMITONES = 4.0;

/** Fewer readings than this and the spread describes the sample, not the speaker. */
const MIN_PITCH_READINGS = 30;

/**
 * Decimate to roughly `TARGET_PITCH_SAMPLE_RATE` by averaging runs of samples.
 *
 * Averaging rather than plain sample-dropping because the boxcar it amounts to
 * is at least a crude low-pass, which keeps some of the high-frequency fricative
 * energy from folding down into the band being searched. It is not a proper
 * anti-aliasing filter and is not claimed to be one -- but a spurious component
 * would have to land inside 70-400Hz *and* be periodic there to survive the
 * clarity threshold above, which is why a filter this cheap is enough.
 *
 * Returns the decimated buffer and its effective sample rate.
 */
export function decimate(samples: Float32Array, sampleRate: number): { buffer: Float32Array; rate: number } {
  const factor = Math.max(1, Math.floor(sampleRate / TARGET_PITCH_SAMPLE_RATE));
  if (factor === 1) return { buffer: samples, rate: sampleRate };

  const length = Math.floor(samples.length / factor);
  const buffer = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    let sum = 0;
    const base = i * factor;
    for (let j = 0; j < factor; j += 1) sum += samples[base + j];
    buffer[i] = sum / factor;
  }
  return { buffer, rate: sampleRate / factor };
}

/**
 * Normalised square difference function over the searchable lag range.
 *
 * `nsdf(t) = 2 * sum(x[i] * x[i+t]) / sum(x[i]^2 + x[i+t]^2)`, the periodicity
 * measure behind YIN and the McLeod Pitch Method. Two properties earn it its
 * place over plain autocorrelation, which this function replaced after a plain
 * version reported 75Hz for a 150Hz vowel:
 *
 * 1. **Bounded in [-1, 1]**, and 1.0 only for a perfectly periodic frame — so
 *    the peak height doubles as the clarity figure, comparable across loud and
 *    quiet speakers with no extra normalisation.
 * 2. **No systematic bias along the lag axis.** Raw autocorrelation shrinks with
 *    lag because fewer sample pairs overlap; dividing that out to compensate
 *    over-corrects and makes sub-harmonics *win*. NSDF normalises by the energy
 *    actually inside each window instead, so peaks at the true period and at
 *    twice it are on a level footing and the tie is broken deliberately, by
 *    `PEAK_PREFERENCE`, rather than by whichever way the arithmetic leaned.
 *
 * Indexed from `minLag`, i.e. `out[t - minLag]` is the value at lag `t`.
 */
function nsdf(samples: Float32Array, minLag: number, maxLag: number): Float32Array {
  const n = samples.length;

  // Prefix sums of squares, so each lag's energy terms are two lookups rather
  // than another pass over the window.
  const prefix = new Float64Array(n + 1);
  for (let i = 0; i < n; i += 1) prefix[i + 1] = prefix[i] + samples[i] * samples[i];

  const out = new Float32Array(maxLag - minLag + 1);
  for (let lag = minLag; lag <= maxLag; lag += 1) {
    const limit = n - lag;
    let correlation = 0;
    for (let i = 0; i < limit; i += 1) correlation += samples[i] * samples[i + lag];
    // Energy of the leading window plus energy of the lagged window.
    const energy = prefix[limit] + (prefix[n] - prefix[lag]);
    out[lag - minLag] = energy > 0 ? (2 * correlation) / energy : 0;
  }
  return out;
}

/**
 * Fundamental frequency of one frame, or null when the frame has no clear pitch.
 *
 * Time-domain NSDF rather than a spectral method: this runs on the UI thread
 * beside a live interview, and after decimation it is cheap and accurate enough
 * for a variance statistic aggregated over hundreds of frames. The exact f0 of
 * any single frame does not matter; the spread across all of them does.
 */
export function detectPitch(rawSamples: Float32Array, rawRate: number): number | null {
  const { buffer: samples, rate } = decimate(rawSamples, rawRate);

  const minLag = Math.floor(rate / MAX_PITCH_HZ);
  const maxLag = Math.min(Math.floor(rate / MIN_PITCH_HZ), samples.length - 1);
  // Two clear periods, or the "periodicity" is an artefact of a short window.
  if (maxLag <= minLag || samples.length < 2 * minLag) return null;

  const curve = nsdf(samples, minLag, maxLag);

  // Interior local maxima. The range ends are excluded on purpose: a value at
  // the boundary may be the rising or falling flank of a peak whose apex lies
  // outside the searchable range, and treating a flank as a peak is how a pitch
  // pinned exactly at 70 or 400Hz gets invented.
  const peaks: number[] = [];
  for (let i = 1; i < curve.length - 1; i += 1) {
    if (curve[i] > curve[i - 1] && curve[i] >= curve[i + 1] && curve[i] > 0) peaks.push(i);
  }
  if (peaks.length === 0) return null;

  let strongest = 0;
  for (const i of peaks) if (curve[i] > strongest) strongest = curve[i];
  if (strongest < MIN_CLARITY) return null;

  // The earliest peak that comes within `PEAK_PREFERENCE` of the strongest —
  // the shortest period that explains the frame, which is the fundamental.
  const chosen = peaks.find((i) => curve[i] >= strongest * PEAK_PREFERENCE);
  if (chosen === undefined) return null;

  // Parabolic interpolation across the peak's neighbours. Lag is a whole number
  // of samples, which quantises f0 badly at the top of the range -- at 12kHz,
  // lag 30 vs 31 is 400Hz vs 387Hz -- and interpolating recovers the resolution
  // the variance statistic needs.
  const prev = curve[chosen - 1];
  const peak = curve[chosen];
  const next = curve[chosen + 1];
  const denominator = 2 * (2 * peak - prev - next);
  const shift = denominator !== 0 ? (next - prev) / denominator : 0;
  const refinedLag = minLag + chosen + Math.max(-1, Math.min(1, shift));

  const frequency = rate / refinedLag;
  if (frequency < MIN_PITCH_HZ || frequency > MAX_PITCH_HZ) return null;
  return frequency;
}

/** Standard deviation of a sample, in whatever unit it arrives in. */
function standardDeviation(values: number[]): number {
  const mean = values.reduce((a, b) => a + b, 0) / values.length;
  const variance = values.reduce((sum, v) => sum + (v - mean) * (v - mean), 0) / values.length;
  return Math.sqrt(variance);
}

/**
 * Semitone spread mapped onto Section 9.7's 0-100 scale.
 *
 * Anchored on how speech actually behaves: a flat, monotone delivery sits under
 * a semitone of standard deviation, an animated one runs to around four. Those
 * two become 0 and 100 and everything between is linear. They are a judgement
 * call about English speech rather than a measurement, which is exactly why they
 * are two named constants at the top of this file and not magic numbers here.
 *
 * The middle 90% of readings are used and the tails discarded first. Octave
 * errors are autocorrelation's characteristic failure -- a frame occasionally
 * locks onto a harmonic and reports double or half the true f0 -- and one such
 * outlier is a full 12 semitones out, enough on its own to make a monotone
 * speaker look expressive.
 */
export function scorePitchVariance(semitones: number[]): number | null {
  if (semitones.length < MIN_PITCH_READINGS) return null;

  const sorted = [...semitones].sort((a, b) => a - b);
  const cut = Math.floor(sorted.length * 0.05);
  const trimmed = cut > 0 ? sorted.slice(cut, sorted.length - cut) : sorted;
  if (trimmed.length < 2) return null;

  const spread = standardDeviation(trimmed);
  const normalized = (spread - MONOTONE_SEMITONES) / (EXPRESSIVE_SEMITONES - MONOTONE_SEMITONES);
  return Math.round(Math.max(0, Math.min(1, normalized)) * 1000) / 10;
}

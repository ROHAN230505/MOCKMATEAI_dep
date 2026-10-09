import { useCallback, useEffect, useRef } from "react";
import { detectPitch, scorePitchVariance } from "../lib/prosodyDsp";

/**
 * Browser-side voice prosody measurement (Section 9.7).
 *
 * Two of Section 9.7's four prosody signals -- pitch variance and pause
 * patterns -- can only be read off the waveform, and Phase 2 established that
 * the candidate's audio never leaves the browser. So the analysis happens here
 * and only the aggregate leaves: two floats plus how much voiced audio they were
 * measured over. No audio, no frames, nothing reconstructible.
 *
 * The other two (speaking pace, filler words) are derived server-side from the
 * transcript the server already holds -- see `app/services/prosody_service.py`
 * for why the split falls where it does.
 *
 * ## What it measures
 *
 * One `AnalyserNode` on the live mic stream, sampled per animation frame:
 *
 * - **Voiced / unvoiced.** RMS against a threshold with hysteresis, so a
 *   waveform hovering at the boundary doesn't chatter between the two states and
 *   shred one utterance into dozens of fake pauses.
 * - **Pitch.** Time-domain periodicity analysis across the human vocal range
 *   (`lib/prosodyDsp.ts`). Reported only when the periodicity peak is sharp
 *   enough to trust; an ambiguous frame contributes nothing rather than a guess.
 * - **Pauses.** Runs of unvoiced frames bounded by speech on both sides. Leading
 *   and trailing silence are not pauses in the delivery, they are the candidate
 *   not talking yet, so they are excluded.
 *
 * ## What it deliberately does not do
 *
 * It never invents a measurement. Every accumulator starts empty and stays empty
 * if the microphone was muted, the sample was too short, or the correlation was
 * never clean enough -- and `measure()` returns null for those fields, which is
 * how the backend keeps the confidence score NULL instead of scoring noise. The
 * honest failure mode here is "no data", never "zero".
 */

// --- Voice activity ---------------------------------------------------------
// Two thresholds, not one: cross the upper to start counting as speech, and fall
// below the lower to stop. A single threshold at a level a quiet speaker sits
// right on top of flickers every few frames.
const VOICE_RMS_ON = 0.02;
const VOICE_RMS_OFF = 0.012;

// --- Pauses -----------------------------------------------------------------
// Under ~250ms a silence is articulation (a stop consonant, a breath), not a
// pause in the delivery. Over ~4s the candidate has stopped answering rather
// than paused within an answer, and averaging those in would drag the mean into
// meaninglessness.
const MIN_PAUSE_MS = 250;
const MAX_PAUSE_MS = 4000;

// `requestAnimationFrame` stops in a background tab, so elapsed wall time
// between frames can be arbitrarily large. Clamping means a backgrounded
// interview under-counts voiced seconds instead of crediting minutes of silence
// as speech -- and under-counting fails safe, because too little voiced audio
// makes the backend discard the sample rather than trust it.
const MAX_FRAME_DT_MS = 100;

const FFT_SIZE = 2048;

// The second of the two cost cuts described in `lib/prosodyDsp.ts`: pitch is
// analysed every third frame (~20Hz), which is ample for a variance statistic
// and keeps the pitch analysis off the critical path of a live interview.
const PITCH_FRAME_STRIDE = 3;

export interface ProsodyMeasurement {
  /** 0-100. Null when no frame ever produced a trustworthy pitch reading. */
  pitchVarianceScore: number | null;
  /** Null when the candidate never paused between utterances long enough to count. */
  avgPauseDurationMs: number | null;
  /** How much voiced audio everything above was measured over. */
  voicedSeconds: number;
}

export interface AnswerTiming {
  /** Seconds from the session epoch to the first voiced frame of the answer. */
  startedAt: number;
  /** Seconds from the session epoch to the last voiced frame of the answer. */
  endedAt: number;
}

/**
 * The shortest speech span that can carry a words-per-minute figure. Under a
 * second, the recogniser's own segmentation latency is a large fraction of the
 * measurement and the resulting pace is an artefact.
 */
const MIN_ANSWER_SPAN_SECONDS = 1.0;

interface Accumulators {
  voicedSeconds: number;
  /** Fundamental frequencies, in semitones relative to 100Hz. */
  semitones: number[];
  pauseDurationsMs: number[];
  /** Whether the previous frame counted as speech, for run detection. */
  wasVoiced: boolean;
  /** Length of the unvoiced run in progress, in ms. */
  silenceRunMs: number;
  /** Whether any speech has been heard at all -- keeps leading silence out of the pause set. */
  heardSpeech: boolean;
  /** Session-relative seconds of the first and last voiced frame of the current answer. */
  turnFirstVoiceAt: number | null;
  turnLastVoiceAt: number | null;
}

function emptyAccumulators(): Accumulators {
  return {
    voicedSeconds: 0,
    semitones: [],
    pauseDurationsMs: [],
    wasVoiced: false,
    silenceRunMs: 0,
    heardSpeech: false,
    turnFirstVoiceAt: null,
    turnLastVoiceAt: null,
  };
}

/**
 * @param stream  the live microphone stream, or null before it is granted
 * @param paused  suspends accumulation without discarding it. The orchestrator
 *                passes `isMuted`: a muted candidate's speech never reaches the
 *                transcript, so measuring its prosody would describe audio the
 *                rest of the report knows nothing about.
 */
export function useProsodyAnalyser(stream: MediaStream | null, paused: boolean) {
  const accumulatorsRef = useRef<Accumulators>(emptyAccumulators());
  const pausedRef = useRef(paused);
  pausedRef.current = paused;
  // The session epoch that answer timings are expressed against. Set on the
  // first frame rather than at mount, so it lines up with the first moment the
  // microphone was actually being listened to.
  const epochRef = useRef<number | null>(null);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!stream) return;

    const AudioCtx =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;

    let audioContext: AudioContext;
    try {
      audioContext = new AudioCtx();
    } catch {
      // No Web Audio, no prosody. The interview is unaffected and the report
      // says confidence is unmeasured, which is the truth.
      return;
    }

    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = FFT_SIZE;
    source.connect(analyser);

    const samples = new Float32Array(analyser.fftSize);
    const { sampleRate } = audioContext;
    let lastFrameAt = performance.now();
    let frameIndex = 0;

    const tick = () => {
      frameRef.current = requestAnimationFrame(tick);

      const now = performance.now();
      const dtMs = Math.min(now - lastFrameAt, MAX_FRAME_DT_MS);
      lastFrameAt = now;

      if (pausedRef.current) return;
      if (epochRef.current === null) epochRef.current = now;
      frameIndex += 1;

      analyser.getFloatTimeDomainData(samples);

      let sumSquares = 0;
      for (let i = 0; i < samples.length; i += 1) sumSquares += samples[i] * samples[i];
      const rms = Math.sqrt(sumSquares / samples.length);

      const acc = accumulatorsRef.current;
      // Hysteresis: which threshold applies depends on the state we are in.
      const isVoiced = acc.wasVoiced ? rms > VOICE_RMS_OFF : rms > VOICE_RMS_ON;

      if (isVoiced) {
        // Close out the silence that just ended. It counts as a pause only if
        // speech preceded it -- otherwise this is the run-up before the
        // candidate started talking, which is not part of their delivery.
        if (acc.heardSpeech && acc.silenceRunMs >= MIN_PAUSE_MS && acc.silenceRunMs <= MAX_PAUSE_MS) {
          acc.pauseDurationsMs.push(acc.silenceRunMs);
        }
        acc.silenceRunMs = 0;
        acc.heardSpeech = true;
        acc.voicedSeconds += dtMs / 1000;

        const elapsed = (now - epochRef.current) / 1000;
        if (acc.turnFirstVoiceAt === null) acc.turnFirstVoiceAt = elapsed;
        acc.turnLastVoiceAt = elapsed;

        if (frameIndex % PITCH_FRAME_STRIDE === 0) {
          const pitch = detectPitch(samples, sampleRate);
          if (pitch !== null) {
            // Semitones, not hertz. Pitch is perceived logarithmically, so a
            // 20Hz wobble means something quite different at 90Hz than at
            // 300Hz; a standard deviation in hertz would score a deep voice as
            // monotone for varying exactly as much as a high one.
            acc.semitones.push(12 * Math.log2(pitch / 100));
          }
        }
      } else {
        acc.silenceRunMs += dtMs;
      }
      acc.wasVoiced = isVoiced;
    };

    frameRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameRef.current);
      source.disconnect();
      analyser.disconnect();
      audioContext.close().catch(() => {});
    };
  }, [stream]);

  /**
   * The session aggregate so far, in the shape the API accepts.
   *
   * Called once per turn, because prosody is submitted as a running aggregate
   * (see the `prosody_update` branch in `app/routers/interviews.py` for why it
   * cannot wait for the end). It reads the accumulators without clearing them:
   * every call describes the whole session up to that instant.
   */
  const measure = useCallback((): ProsodyMeasurement => {
    const { voicedSeconds, semitones, pauseDurationsMs } = accumulatorsRef.current;

    return {
      pitchVarianceScore: scorePitchVariance(semitones),
      avgPauseDurationMs:
        pauseDurationsMs.length > 0
          ? Math.round(pauseDurationsMs.reduce((a, b) => a + b, 0) / pauseDurationsMs.length)
          : null,
      voicedSeconds: Number(voicedSeconds.toFixed(2)),
    };
  }, []);

  /** Marks the start of a new answer, clearing the previous turn's markers. */
  const startAnswer = useCallback(() => {
    accumulatorsRef.current.turnFirstVoiceAt = null;
    accumulatorsRef.current.turnLastVoiceAt = null;
  }, []);

  /**
   * The span of speech since the last `startAnswer()`, or null.
   *
   * Null when the candidate never audibly spoke, or spoke for less than a
   * second: the session then genuinely has no timing for this answer, and the
   * backend leaves its speaking pace unmeasured rather than dividing a word
   * count by a window that was mostly silence.
   *
   * Bracketing the answer by *speech* rather than by the listening window is the
   * point. The window starts when the interviewer stops talking and ends when
   * the silence watchdog fires, so it includes however long the candidate spent
   * thinking first and 1.8 seconds of silence at the end -- both of which would
   * deflate a words-per-minute figure that claimed to describe how fast they
   * talk.
   */
  const takeAnswerTiming = useCallback((): AnswerTiming | null => {
    const acc = accumulatorsRef.current;
    const startedAt = acc.turnFirstVoiceAt;
    const endedAt = acc.turnLastVoiceAt;
    acc.turnFirstVoiceAt = null;
    acc.turnLastVoiceAt = null;

    if (startedAt === null || endedAt === null) return null;
    if (endedAt - startedAt < MIN_ANSWER_SPAN_SECONDS) return null;
    return { startedAt: Number(startedAt.toFixed(2)), endedAt: Number(endedAt.toFixed(2)) };
  }, []);

  return { measure, startAnswer, takeAnswerTiming };
}

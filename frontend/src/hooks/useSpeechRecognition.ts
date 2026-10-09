import { useCallback, useRef, useState } from "react";
import { useAsrStore } from "../store/asrStore";

/*
 * The turn lifecycle lives in `lib/asrTurn.ts` as a pure decision table.
 *
 * It is not here because it could not be tested here: deciding when a spoken
 * answer has ended requires reading four browser channels that each mean
 * something other than what they are named, and getting it wrong has twice
 * produced a silent, severe failure. As data it is walked exhaustively by
 * `scripts/verify-asr-turn.mjs`; as callbacks it needed a microphone and a
 * person to review.
 *
 * This module keeps the imperative half: instances, timers, and the mic.
 */
import {
  canFinish,
  canRestart,
  micLooksDead,
  MIN_RESTART_GAP_MS,
  onEndAction,
  onErrorAction,
  watchdogAction,
  type TurnSnapshot,
} from "../lib/asrTurn";

const WATCHDOG_INTERVAL_MS = 300;

/*
 * Below this, a turn is reported as probably misheard.
 *
 * Not a tuned threshold and not presented as one: Chrome's `confidence` is an
 * opaque number with no published scale, so this is a conservative line drawn
 * to catch the obvious cases. The wording it drives says "may have misheard"
 * rather than claiming a measurement.
 */
const LOW_CONFIDENCE_THRESHOLD = 0.65;

interface SpeechRecognitionCallbacks {
  onInterimTranscript?: (text: string) => void;
  onTurnComplete: (transcript: string, confidenceAvg: number | null) => void;
  onError?: (message: string) => void;
}

function getRecognitionConstructor(): SpeechRecognitionConstructor | null {
  return window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
}

export function isSpeechRecognitionSupported(): boolean {
  return getRecognitionConstructor() !== null;
}

/**
 * Wraps the browser's native SpeechRecognition (Phase 2's ASR adapter —
 * see MASTER_PROMPT.md Phase 2 notes) behind an event-driven interface:
 * continuous recognition + a silence watchdog that calls `onTurnComplete`
 * once the candidate appears to have finished answering, without requiring
 * an explicit "I'm done" action.
 *
 * Also exposes `pauseListening`/`resumeListening` for the Mute control
 * (Section 4.8): the Web Speech API has no concept of an externally muted
 * input stream, so "mute while listening" is implemented as abort-without
 * -finalizing + later restarting a fresh recognition instance that appends
 * to the transcript already captured, rather than losing it.
 */
/**
 * Whether a turn's average confidence is low enough to warn about.
 *
 * Exported so the live caption and the feedback report cannot drift apart on
 * what "probably misheard" means. `null` is not low — it is unmeasured, and
 * saying otherwise would flag every turn on an engine that reports nothing.
 */
export function isLowConfidence(confidenceAvg: number | null | undefined): boolean {
  return typeof confidenceAvg === "number" && Number.isFinite(confidenceAvg) && confidenceAvg > 0
    && confidenceAvg < LOW_CONFIDENCE_THRESHOLD;
}

export function useSpeechRecognition(callbacks: SpeechRecognitionCallbacks) {
  const [isListening, setIsListening] = useState(false);
  // Surfaced live, not just in the report. A candidate who can see the engine
  // is mishearing them can slow down or fix their language setting on the
  // spot; one who finds out afterwards can only dispute a score.
  const [lowConfidence, setLowConfidence] = useState(false);
  const recognitionRef = useRef<SpeechRecognition | null>(null);
  const watchdogRef = useRef<number | undefined>(undefined);
  const finalTranscriptRef = useRef("");
  const confidencesRef = useRef<number[]>([]);
  const lastResultAtRef = useRef(0);
  const finishedRef = useRef(true);
  const pausedRef = useRef(false);
  // Set by stop()/finishTurn() so onend can tell "we asked for this" from
  // "Chrome ended on its own", which are indistinguishable from the event.
  const closingRef = useRef(false);
  const restartsRef = useRef(0);
  const lastRestartAtRef = useRef(0);
  const retryTimerRef = useRef<number | undefined>(undefined);
  const deadMicReportedRef = useRef(false);
  const turnStartedAtRef = useRef(0);
  const langRef = useRef(useAsrStore.getState().lang);
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  /** The state the decision table reads. `isCurrent` is supplied per instance. */
  const snapshot = useCallback(
    (isCurrent: boolean): TurnSnapshot => ({
      finished: finishedRef.current,
      paused: pausedRef.current,
      closing: closingRef.current,
      isCurrent,
      transcript: finalTranscriptRef.current,
      startedAt: turnStartedAtRef.current,
      lastResultAt: lastResultAtRef.current,
      restarts: restartsRef.current,
      lastRestartAt: lastRestartAtRef.current,
    }),
    [],
  );

  const clearWatchdog = useCallback(() => {
    if (watchdogRef.current !== undefined) {
      window.clearInterval(watchdogRef.current);
      watchdogRef.current = undefined;
    }
  }, []);

  /**
   * End the turn and hand the transcript up.
   *
   * `deliberate` means a clock or a person decided: the silence watchdog, the
   * empty-turn timeout, Skip, time running out, or a refused microphone. Left
   * false — the recogniser-error and restart-exhausted paths — an EMPTY turn
   * is refused until `MIN_LISTEN_MS` has passed.
   *
   * That single condition is what makes the six-questions-in-five-seconds
   * failure structurally impossible rather than merely fixed. Whatever new way
   * the recogniser finds to fall over, it cannot cause a question to be
   * answered, scored and advanced past before the candidate could speak; the
   * worst it can do is leave the turn open for the watchdog to close on time.
   */
  const finishTurn = useCallback((deliberate = false) => {
    if (finishedRef.current) return;
    if (!canFinish(snapshot(true), deliberate, Date.now())) return;
    finishedRef.current = true;
    // Otherwise a queued retry starts a recogniser into the *next* question.
    window.clearTimeout(retryTimerRef.current);
    clearWatchdog();
    setIsListening(false);
    recognitionRef.current?.stop();

    const transcript = finalTranscriptRef.current.trim();
    /*
     * Only real numbers are averaged.
     *
     * Not every engine populates `confidence`: some return 0 for every result
     * and some omit it. Averaging those in would report a confident answer as
     * near-worthless, which is a fabricated measurement in the direction that
     * does the most damage — it would flag good answers as misheard. An
     * unmeasured turn has to stay null all the way to the report.
     */
    const confidences = confidencesRef.current.filter((c) => Number.isFinite(c) && c > 0);
    const avgConfidence =
      confidences.length > 0 ? confidences.reduce((a, b) => a + b, 0) / confidences.length : null;
    callbacksRef.current.onTurnComplete(transcript, avgConfidence);
  }, [clearWatchdog, snapshot]);

  const startWatchdog = useCallback(() => {
    clearWatchdog();
    watchdogRef.current = window.setInterval(() => {
      // The clock is the only channel permitted to end an EMPTY turn, and both
      // of its outcomes are deliberate: one waited out a gap after speech, the
      // other waited out a long silence from the start.
      const action = watchdogAction(snapshot(true), Date.now());
      if (action.type === "finish") finishTurn(true);
    }, WATCHDOG_INTERVAL_MS);
  }, [clearWatchdog, finishTurn, snapshot]);

  const createRecognitionRef = useRef<(() => SpeechRecognition | null) | null>(null);
  // Lets start() hand a failed launch to the same retry path every other
  // channel uses, instead of inventing a second one.
  const keepListeningRef = useRef<(() => void) | null>(null);

  const createRecognition = useCallback((): SpeechRecognition | null => {
    const Constructor = getRecognitionConstructor();
    if (!Constructor) {
      callbacksRef.current.onError?.("Speech recognition isn't supported in this browser.");
      return null;
    }
    const recognition = new Constructor();
    recognition.continuous = true;
    recognition.interimResults = true;
    /*
     * The locale, and the single most consequential line in this file.
     *
     * The recogniser does not detect language — it scores the audio against
     * whichever locale's model it was given. A mismatch does not error or
     * degrade gracefully; it returns fluent, well-formed, completely different
     * words. This was pinned to "en-US" for every user on earth.
     */
    recognition.lang = langRef.current;
    /*
     * Ask for alternatives even though we read [0].
     *
     * [0] is already the engine's best hypothesis, so this does not improve
     * the text. What it does is stop the engine from committing to a single
     * path early on some implementations, and it costs nothing.
     */
    recognition.maxAlternatives = 3;

    /*
     * Every handler below is scoped to THIS instance.
     *
     * A restart leaves the previous recogniser still emitting: its end event,
     * and its aborted error, arrive after the replacement is already
     * listening. Unguarded, those late events act on the shared turn and can
     * finalise it while a perfectly healthy instance is running — which is
     * exactly how a stray abort submitted an empty answer mid-question.
     */
    const isCurrent = () => recognitionRef.current === recognition;

    /*
     * Keep the turn alive on a fresh instance. Never end it.
     *
     * The old version of this finished the turn when the restart budget ran
     * out, and that single line was the bug behind an interview asking every
     * question in a handful of seconds: an error storm spent twelve restarts
     * almost instantly, the turn was then finalised with an empty transcript,
     * and the next question followed immediately.
     *
     * Running out of retries means the recogniser will not come back right
     * now. It does not mean the candidate has stopped talking, and those are
     * not the same fact. So the turn is left open, the watchdog's empty-turn
     * timeout remains the only clock that can close it, and if nothing at all
     * has been heard by then the candidate is told their microphone is not
     * producing speech -- because sitting through an interview being scored on
     * silence is a far worse outcome than a visible warning.
     */
    const keepListening = () => {
      if (finishedRef.current || pausedRef.current) return;
      const now = Date.now();
      if (!canRestart(snapshot(true), now)) {
        if (micLooksDead(snapshot(true)) && !deadMicReportedRef.current) {
          deadMicReportedRef.current = true;
          callbacksRef.current.onError?.(
            "Your microphone isn't producing any speech. Check that the right input is selected and that this tab still has permission -- the interview will keep waiting.",
          );
        }
        // Paced out rather than abandoned: try again after the gap, so a
        // condition that clears on its own still recovers mid-answer.
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = window.setTimeout(keepListening, MIN_RESTART_GAP_MS);
        return;
      }
      restartsRef.current += 1;
      lastRestartAtRef.current = now;
      const next = createRecognitionRef.current?.();
      if (!next) return; // no constructor; the clock still owns the turn
      recognitionRef.current = next;
      try {
        next.start();
      } catch {
        // Already-started, or a start that raced its own teardown. Retry on
        // the gap rather than giving up on the turn.
        window.clearTimeout(retryTimerRef.current);
        retryTimerRef.current = window.setTimeout(keepListening, MIN_RESTART_GAP_MS);
      }
    };
    keepListeningRef.current = keepListening;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      if (!isCurrent()) return;
      lastResultAtRef.current = Date.now();
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i++) {
        const result = event.results[i];
        const alternative = result[0];
        if (result.isFinal) {
          finalTranscriptRef.current += `${alternative.transcript} `;
          confidencesRef.current.push(alternative.confidence);
          // Speech arrived, so the recogniser is healthy: give this answer its
          // full retry budget back. A four-minute answer with six thinking
          // pauses should not run out of restarts halfway through.
          restartsRef.current = 0;
          deadMicReportedRef.current = false;
          const measured = confidencesRef.current.filter((c) => Number.isFinite(c) && c > 0);
          if (measured.length > 0) {
            setLowConfidence(isLowConfidence(measured.reduce((a, b) => a + b, 0) / measured.length));
          }
        } else {
          interim += alternative.transcript;
        }
      }
      callbacksRef.current.onInterimTranscript?.((finalTranscriptRef.current + interim).trim());
    };

    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      const action = onErrorAction(event.error, snapshot(isCurrent()));
      if (action.type === "fatal") {
        // The one error the candidate has to act on, and the only one worth
        // interrupting them for. Everything else recovers on a restart, and
        // announcing a network blip mid-sentence would alarm them about
        // something that has already fixed itself.
        callbacksRef.current.onError?.(
          "Microphone access is blocked, so nothing can be transcribed. Allow it from the icon in your browser address bar, then reload.",
        );
        finishTurn(true);
        return;
      }
      if (action.type === "restart") keepListening();
    };

    recognition.onend = () => {
      const action = onEndAction(snapshot(isCurrent()));
      // `finish` here means something we or the candidate initiated: Skip,
      // time up, or the silence clock. Chrome ending on its own arrives as
      // `restart`, because it is not evidence the answer is over.
      if (action.type === "finish") finishTurn(action.deliberate);
      else if (action.type === "restart") keepListening();
    };

    return recognition;
  }, [finishTurn, snapshot]);
  createRecognitionRef.current = createRecognition;

  const start = useCallback(() => {
    finalTranscriptRef.current = "";
    confidencesRef.current = [];
    lastResultAtRef.current = Date.now();
    finishedRef.current = false;
    pausedRef.current = false;
    closingRef.current = false;
    restartsRef.current = 0;
    lastRestartAtRef.current = 0;
    deadMicReportedRef.current = false;
    window.clearTimeout(retryTimerRef.current);
    turnStartedAtRef.current = Date.now();
    setLowConfidence(false);
    // Read once per turn rather than per render, so changing the language mid
    // interview takes effect on the next question instead of tearing the
    // current one in half.
    langRef.current = useAsrStore.getState().lang;

    const recognition = createRecognition();
    if (!recognition) return;
    recognitionRef.current = recognition;

    /*
     * Guarded, and this was a real and total failure.
     *
     * Chrome permits one live SpeechRecognition per page, and `start()` throws
     * `InvalidStateError` when another has not finished releasing the
     * microphone. The device-check screen runs its own recogniser for the
     * "test my voice" button, and `abort()` on it returns before the engine
     * has actually let go -- so walking from the precheck into the interview
     * lands exactly in that window.
     *
     * Unguarded, the throw escaped this callback. Neither `setIsListening` nor
     * `startWatchdog` ran, so no recogniser was listening, no clock was
     * watching, and every turn of the interview submitted an empty transcript.
     * The candidate saw an interviewer asking questions and heard nothing come
     * back; the report said "No answer recorded" for a session they had spoken
     * their way through.
     *
     * Retrying on the pacing gap is the right recovery: the condition is
     * transient by nature, and `keepListening` already owns the retry budget.
     */
    try {
      recognition.start();
    } catch {
      callbacksRef.current.onError?.(
        "Starting the microphone took a moment — if this question records nothing, reload the page.",
      );
      window.setTimeout(() => {
        if (!finishedRef.current && !pausedRef.current) keepListeningRef.current?.();
      }, MIN_RESTART_GAP_MS);
    }
    setIsListening(true);
    startWatchdog();
  }, [createRecognition, startWatchdog]);

  /**
   * The candidate saying they have finished, and the answer to the complaint
   * that the interviewer talks over people.
   *
   * Deliberate, so it submits whatever has been captured immediately without
   * waiting out the silence window -- and it works on an empty turn too, which
   * is then indistinguishable from a skip and recorded as an unanswered
   * question rather than as a wrong one.
   */
  const finishAnswer = useCallback(() => {
    closingRef.current = true;
    window.clearTimeout(retryTimerRef.current);
    recognitionRef.current?.stop();
    finishTurn(true);
  }, [finishTurn]);

  /** Manual stop (e.g. Skip button, or time running out) — still finalizes via onend -> finishTurn. */
  const stop = useCallback(() => {
    // Marks the onend that follows as one we asked for, so it finalises the
    // turn instead of restarting into it.
    closingRef.current = true;
    recognitionRef.current?.stop();
  }, []);

  /** Discards whatever was captured without calling onTurnComplete — used on unmount/navigation away. */
  const cancel = useCallback(() => {
    finishedRef.current = true;
    closingRef.current = true;
    pausedRef.current = false;
    window.clearTimeout(retryTimerRef.current);
    clearWatchdog();
    recognitionRef.current?.abort();
    setIsListening(false);
  }, [clearWatchdog]);

  /** Mute: stops listening without finalizing/submitting — see module docstring. */
  const pauseListening = useCallback(() => {
    if (finishedRef.current || pausedRef.current) return;
    pausedRef.current = true;
    window.clearTimeout(retryTimerRef.current);
    clearWatchdog();
    recognitionRef.current?.abort();
    setIsListening(false);
  }, [clearWatchdog]);

  /** Unmute: resumes into the same turn, appending to whatever was already captured. */
  const resumeListening = useCallback(() => {
    if (finishedRef.current || !pausedRef.current) return;
    pausedRef.current = false;
    lastResultAtRef.current = Date.now();
    langRef.current = useAsrStore.getState().lang;

    const recognition = createRecognition();
    if (!recognition) return;
    recognitionRef.current = recognition;

    /*
     * Guarded, and this was a real and total failure.
     *
     * Chrome permits one live SpeechRecognition per page, and `start()` throws
     * `InvalidStateError` when another has not finished releasing the
     * microphone. The device-check screen runs its own recogniser for the
     * "test my voice" button, and `abort()` on it returns before the engine
     * has actually let go -- so walking from the precheck into the interview
     * lands exactly in that window.
     *
     * Unguarded, the throw escaped this callback. Neither `setIsListening` nor
     * `startWatchdog` ran, so no recogniser was listening, no clock was
     * watching, and every turn of the interview submitted an empty transcript.
     * The candidate saw an interviewer asking questions and heard nothing come
     * back; the report said "No answer recorded" for a session they had spoken
     * their way through.
     *
     * Retrying on the pacing gap is the right recovery: the condition is
     * transient by nature, and `keepListening` already owns the retry budget.
     */
    try {
      recognition.start();
    } catch {
      callbacksRef.current.onError?.(
        "Starting the microphone took a moment — if this question records nothing, reload the page.",
      );
      window.setTimeout(() => {
        if (!finishedRef.current && !pausedRef.current) keepListeningRef.current?.();
      }, MIN_RESTART_GAP_MS);
    }
    setIsListening(true);
    startWatchdog();
  }, [createRecognition, startWatchdog]);

  return { isListening, lowConfidence, start, stop, finishAnswer, cancel, pauseListening, resumeListening };
}

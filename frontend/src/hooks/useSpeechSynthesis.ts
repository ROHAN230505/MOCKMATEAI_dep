import { useCallback, useRef, useState } from "react";

export function isSpeechSynthesisSupported(): boolean {
  return "speechSynthesis" in window;
}

interface SpeechSynthesisCallbacks {
  /** `charOffset` is only non-null when `wasInterrupted` — Section 4.8A's `interrupted_at_char_offset`. */
  onSpeechEnd: (wasInterrupted: boolean, charOffset: number | null) => void;
  onBoundary?: (charIndex: number) => void;
}

/**
 * Wraps the browser's speechSynthesis (Phase 2's TTS adapter) with clean
 * interrupt semantics for barge-in (Section 4.8A/9.2A: "TTS playback must
 * be interruptible mid-stream"). Chrome fires `onerror` (error:
 * "interrupted") rather than `onend` when `.cancel()` is called mid-speech
 * — both paths are normalized here into a single `onSpeechEnd` callback.
 */
export function useSpeechSynthesis(callbacks: SpeechSynthesisCallbacks) {
  const [isSpeaking, setIsSpeaking] = useState(false);
  const lastCharIndexRef = useRef<number | null>(null);
  const cancelledRef = useRef(false);
  const finishedRef = useRef(true);
  const callbacksRef = useRef(callbacks);
  callbacksRef.current = callbacks;

  const finish = useCallback((interrupted: boolean) => {
    if (finishedRef.current) return;
    finishedRef.current = true;
    setIsSpeaking(false);
    callbacksRef.current.onSpeechEnd(interrupted, interrupted ? lastCharIndexRef.current : null);
  }, []);

  const speak = useCallback(
    (text: string) => {
      window.speechSynthesis.cancel(); // clear any stray queued utterance defensively
      finishedRef.current = false;
      cancelledRef.current = false;
      lastCharIndexRef.current = null;

      const utterance = new SpeechSynthesisUtterance(text);
      utterance.rate = 1.0;
      utterance.onboundary = (event) => {
        lastCharIndexRef.current = event.charIndex;
        callbacksRef.current.onBoundary?.(event.charIndex);
      };
      utterance.onend = () => finish(cancelledRef.current);
      utterance.onerror = () => finish(true);

      setIsSpeaking(true);
      window.speechSynthesis.speak(utterance);
    },
    [finish],
  );

  /** Barge-in: stop mid-utterance and report the last known character offset. */
  const cancel = useCallback(() => {
    if (finishedRef.current) return;
    cancelledRef.current = true;
    window.speechSynthesis.cancel();
  }, []);

  /**
   * True pause/resume (not cancel+restart) for the Pause Interview control
   * (Section 4.8) — native `speechSynthesis.pause/resume` hold the
   * utterance mid-word rather than restarting the question from the top.
   * No-ops harmlessly if nothing is currently speaking.
   */
  const pause = useCallback(() => {
    if (!finishedRef.current) window.speechSynthesis.pause();
  }, []);

  const resume = useCallback(() => {
    if (!finishedRef.current) window.speechSynthesis.resume();
  }, []);

  return { isSpeaking, speak, cancel, pause, resume };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { ASR_LANGUAGES, useAsrStore } from "../../store/asrStore";

type TestState = "idle" | "listening" | "done" | "unsupported" | "error";

/**
 * Choose the speech-recognition language, and hear what the recogniser
 * actually heard.
 *
 * ## Why this is a control and not a constant
 *
 * The recogniser was pinned to `en-US`. The Web Speech API does not detect
 * language — it scores audio against the model for whichever locale it is
 * handed — and a mismatch does not error or degrade visibly. It returns
 * fluent, confident, completely different words. For a product whose entire
 * input is speech, that made one hardcoded string the largest correctness bug
 * in it.
 *
 * ## Why the test is the important half
 *
 * A dropdown alone would move the guess from us to the candidate, which is not
 * obviously better — few people know which English model fits their accent,
 * and the failure is silent either way. So the picker carries a live test: say
 * one sentence, read back exactly what the engine returned. That converts an
 * unanswerable question into a two-second experiment, and it happens here in
 * the precheck rather than four questions into a scored interview.
 *
 * The test runs its own short-lived recogniser instance and never touches the
 * interview's. It is deliberately not `continuous` — this is one utterance,
 * not a turn.
 */
export function SpeechLanguagePicker() {
  const lang = useAsrStore((s) => s.lang);
  const inferred = useAsrStore((s) => s.inferred);
  const setLang = useAsrStore((s) => s.setLang);

  const [state, setState] = useState<TestState>("idle");
  const [heard, setHeard] = useState("");
  const [confidence, setConfidence] = useState<number | null>(null);
  const recognitionRef = useRef<SpeechRecognition | null>(null);

  /*
   * Release the microphone the moment this leaves the screen.
   *
   * Chrome allows one live SpeechRecognition per page, and a test left running
   * -- or still winding down -- makes the interview's own `start()` throw
   * `InvalidStateError`. That produced an interview which recorded nothing at
   * all, so this cleanup is load-bearing rather than tidy.
   *
   * `stop()` then `abort()`: stop asks for a graceful end and lets any final
   * result land, abort guarantees the handle is gone even if stop is ignored.
   * Handlers are detached first so a late event from the dying instance cannot
   * call setState on an unmounted component.
   */
  useEffect(
    () => () => {
      const instance = recognitionRef.current;
      if (!instance) return;
      recognitionRef.current = null;
      instance.onresult = null;
      instance.onerror = null;
      instance.onend = null;
      try {
        instance.stop();
      } catch {
        // Already stopped; abort below is the belt to this braces.
      }
      try {
        instance.abort();
      } catch {
        // Nothing to abort. Either way the reference is dropped.
      }
    },
    [],
  );

  const runTest = useCallback(() => {
    const Constructor = window.SpeechRecognition ?? window.webkitSpeechRecognition ?? null;
    if (!Constructor) {
      setState("unsupported");
      return;
    }
    recognitionRef.current?.abort();
    setHeard("");
    setConfidence(null);
    setState("listening");

    const recognition = new Constructor();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = lang;
    recognition.maxAlternatives = 3;

    let best = "";
    let bestConfidence: number | null = null;

    recognition.onresult = (event: SpeechRecognitionEvent) => {
      let interim = "";
      for (let i = event.resultIndex; i < event.results.length; i += 1) {
        const result = event.results[i];
        const alternative = result[0];
        if (result.isFinal) {
          best += `${alternative.transcript} `;
          // Same rule as the interview hook: an engine that reports no
          // confidence must not be shown as a low one.
          if (Number.isFinite(alternative.confidence) && alternative.confidence > 0) {
            bestConfidence = alternative.confidence;
          }
        } else {
          interim += alternative.transcript;
        }
      }
      setHeard(`${best}${interim}`.trim());
    };
    recognition.onerror = (event: SpeechRecognitionErrorEvent) => {
      if (event.error === "no-speech") return;
      setState("error");
    };
    recognition.onend = () => {
      setConfidence(bestConfidence);
      setState((current) => (current === "error" ? current : "done"));
    };

    recognitionRef.current = recognition;
    try {
      recognition.start();
    } catch {
      setState("error");
    }
  }, [lang]);

  const stopTest = useCallback(() => {
    recognitionRef.current?.stop();
  }, []);

  const active = ASR_LANGUAGES.find((l) => l.tag === lang);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <p className="text-xs font-medium text-text-muted">Speech recognition language</p>
          <p className="mt-0.5 text-xs leading-relaxed text-text-subtle">
            Pick the one closest to your accent — not your nationality. The wrong choice does not fail
            loudly; it returns confident, wrong words.
          </p>
        </div>
        {inferred && (
          <span className="rounded-pill border border-border px-2 py-0.5 text-micro text-text-subtle">
            Detected — worth testing
          </span>
        )}
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <select
          value={lang}
          onChange={(event) => {
            setLang(event.target.value);
            setState("idle");
            setHeard("");
            setConfidence(null);
          }}
          aria-label="Speech recognition language"
          className="rounded-control border border-border bg-surface px-2.5 py-1.5 text-small text-text"
        >
          {ASR_LANGUAGES.map((option) => (
            <option key={option.tag} value={option.tag}>
              {option.label} — {option.hint}
            </option>
          ))}
        </select>

        <button
          type="button"
          onClick={state === "listening" ? stopTest : runTest}
          className="rounded-control border border-border-strong px-3 py-1.5 text-small font-medium text-text transition-colors duration-150 hover:bg-surface-raised"
        >
          {state === "listening" ? "Stop" : "Test my voice"}
        </button>
      </div>

      {state === "listening" && (
        <p className="text-xs text-text-muted" aria-live="polite">
          <span className="mr-1.5 inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-accent align-middle" />
          Listening — say a full sentence, something like &ldquo;I led a team of four on a payments
          migration last summer.&rdquo;
        </p>
      )}

      {state === "unsupported" && (
        <p className="text-xs text-danger">
          This browser has no speech recognition, so an interview here cannot transcribe you. Chrome or Edge
          will work.
        </p>
      )}

      {state === "error" && (
        <p className="text-xs text-danger">
          The test could not run. Check that this page is allowed to use your microphone.
        </p>
      )}

      {(state === "done" || (state === "listening" && heard)) && (
        <div className="rounded-control border border-border bg-surface-sunken px-3 py-2">
          <p className="text-micro font-medium tracking-[0.1em] text-text-subtle uppercase">
            {active?.label ?? lang} heard
          </p>
          <p className="mt-1 text-small text-text">
            {heard || <span className="text-text-subtle italic">nothing audible</span>}
          </p>
          {state === "done" && (
            <p className="mt-1.5 text-micro text-text-subtle">
              {/* Only stated when the engine actually reported a number. */}
              {confidence === null
                ? "This browser reports no confidence score, so there is nothing to show here."
                : `Engine confidence ${Math.round(confidence * 100)}%.`}{" "}
              {heard
                ? "If that is not what you said, try a different language above."
                : "Nothing was transcribed — check your microphone, then try again."}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

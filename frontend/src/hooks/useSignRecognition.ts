import { useCallback, useEffect, useRef, useState } from "react";
import type { GestureRecognizer } from "@mediapipe/tasks-vision";
import type { FingerspellingGuess } from "../lib/fingerspelling";
import { recogniseLetter } from "../lib/fingerspelling";
import { createFrameBudget } from "../lib/frameBudget";

/**
 * Hand recognition for sign mode (Phase 6).
 *
 * One MediaPipe bundle, two genuinely different capabilities, and it is worth
 * being precise about which is which:
 *
 * 1. **Control gestures** come from Google's trained gesture classifier that
 *    ships inside `gesture_recognizer.task`. A real model with real training
 *    behind it, recognising seven fixed gestures.
 * 2. **Fingerspelled letters** come from `lib/fingerspelling.ts`, which is a
 *    geometric classifier over the same bundle's hand landmarks — hand-authored
 *    rules, no training, no measured accuracy. See that file's header.
 *
 * Neither is sign-language translation, and nothing here claims to be. ASL has
 * its own grammar and is not fingerspelled English; continuous sign translation
 * is an open research problem. What this provides is letter-at-a-time spelling
 * (useful for names, acronyms and technical terms) and hands-free control.
 *
 * ## Why the two modes are exclusive
 *
 * The canned gestures collide with the letter shapes, badly. Pointing_Up is the
 * same handshape as D, Victory is V, Open_Palm is close to B, Closed_Fist is the
 * whole A/S/E/M/N/T family. Running both interpretations at once would mean every
 * V the candidate spells could fire a control action, so only one is ever live:
 * gestures while fingerspelling is off, letters while it is on. The toggle is a
 * button rather than a gesture for the same reason — a gesture to leave gesture
 * mode would have to not collide with anything, and there is no such gesture.
 *
 * ## Nothing here is authoritative
 *
 * Letters append into a text field that stays fully editable, after a deliberate
 * hold, with the candidate watching the pending letter and its confidence before
 * it lands. Control gestures need a longer hold still and show their progress as
 * they arm. A misread costs a keystroke, never an answer — which is the only
 * basis on which an unvalidated classifier belongs anywhere near a candidate's
 * interview.
 */

const MANIFEST_URL = "/mediapipe/manifest.json";
const WASM_PATH = "/mediapipe/wasm";

// Matches the expression analyser's target. Fingerspelling needs enough
// temporal resolution to catch a held shape, and 12fps gives a 600ms hold seven
// frames to agree on — ample, and still five at the 8fps this may back off to.
const TARGET_FPS = 12;
/**
 * This model always shares the thread with the expression analyser in sign mode,
 * so it never claims more than a third of each interval. Allowances add up: two
 * consumers each granted half the thread will between them take all of it.
 */
const MAX_LOAD = 0.35;
/**
 * Half an interval, so this consumer's slots fall between the expression
 * analyser's rather than drifting into alignment with them — at which point the
 * interview stutters at their combined cost instead of at either one alone.
 */
const PHASE_OFFSET_MS = 1000 / (TARGET_FPS * 2);

/** How long a letter must be held before it is appended. */
const LETTER_HOLD_MS = 600;
/**
 * Longer for controls, because the cost of a mistake is higher: an accidental
 * letter is a backspace, an accidental submit ends the candidate's turn.
 */
const CONTROL_HOLD_MS = 1200;
/** Below this the trained classifier is not confident enough to act on. */
const MIN_GESTURE_SCORE = 0.6;

const MIN_CORES = 4;

/**
 * The two control gestures, chosen for not colliding with any covered letter.
 *
 * A flat open hand and a thumb-down are the two of Google's seven that no
 * fingerspelled letter in `COVERED_LETTERS` looks like — and they are also the
 * two whose everyday meaning matches the action, which matters when a candidate
 * has to remember them mid-interview.
 */
const CONTROL_GESTURES: Readonly<Record<string, SignControl>> = {
  Open_Palm: "submit",
  Thumb_Down: "skip",
};

export type SignControl = "submit" | "skip";

export type SignRecognitionStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready" }
  | { state: "unavailable"; reason: string };

export interface PendingLetter extends FingerspellingGuess {
  /** 0-1 toward committing. Shown so a letter never appears without warning. */
  progress: number;
}

export interface ArmingControl {
  action: SignControl;
  progress: number;
}

interface Options {
  /** Interpret landmarks as letters. Mutually exclusive with gesture control. */
  fingerspelling: boolean;
  /** Watch for the two control gestures. Ignored while `fingerspelling` is on. */
  gestures: boolean;
  onLetter: (letter: string) => void;
  onControl: (action: SignControl) => void;
}

interface Manifest {
  gestureReady?: boolean;
  gestureModelPath?: string;
}

async function loadManifest(): Promise<Manifest | null> {
  try {
    const response = await fetch(MANIFEST_URL, { cache: "no-store" });
    if (!response.ok) return null;
    const manifest = (await response.json()) as Manifest;
    return manifest.gestureReady && manifest.gestureModelPath ? manifest : null;
  } catch {
    return null;
  }
}

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement("canvas");
    return Boolean(canvas.getContext("webgl2") ?? canvas.getContext("webgl"));
  } catch {
    return false;
  }
}

export function useSignRecognition(video: HTMLVideoElement | null, options: Options) {
  const [status, setStatus] = useState<SignRecognitionStatus>({ state: "idle" });
  const [pending, setPending] = useState<PendingLetter | null>(null);
  const [arming, setArming] = useState<ArmingControl | null>(null);
  const [handPresent, setHandPresent] = useState(false);

  // Held in a ref so the frame loop always sees the current callbacks and flags
  // without the effect tearing the model down and reloading it every time the
  // candidate toggles fingerspelling.
  const optionsRef = useRef(options);
  optionsRef.current = options;

  useEffect(() => {
    if (!video) {
      setStatus({ state: "idle" });
      return;
    }

    let cancelled = false;
    let frameHandle = 0;
    let recognizer: GestureRecognizer | null = null;

    const unavailable = (reason: string) => {
      if (!cancelled) setStatus({ state: "unavailable", reason });
    };

    (async () => {
      if ((navigator.hardwareConcurrency ?? 4) < MIN_CORES) {
        return unavailable("This device is too small to run hand recognition during an interview.");
      }
      if (!webglAvailable()) return unavailable("WebGL is unavailable in this browser.");

      setStatus({ state: "loading" });

      const manifest = await loadManifest();
      if (cancelled) return;
      if (!manifest?.gestureModelPath) {
        return unavailable(
          "The hand model is not installed. Run `npm run setup:mediapipe` in frontend/ to fetch it.",
        );
      }

      let vision: typeof import("@mediapipe/tasks-vision");
      try {
        vision = await import("@mediapipe/tasks-vision");
      } catch {
        return unavailable("The vision library failed to load.");
      }
      if (cancelled) return;

      let fileset: Awaited<ReturnType<typeof vision.FilesetResolver.forVisionTasks>>;
      try {
        fileset = await vision.FilesetResolver.forVisionTasks(WASM_PATH);
      } catch {
        return unavailable("The vision runtime failed to load.");
      }
      if (cancelled) return;

      const create = (delegate: "GPU" | "CPU") =>
        vision.GestureRecognizer.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: manifest.gestureModelPath!, delegate },
          runningMode: "VIDEO",
          // One hand. ASL fingerspelling is one-handed, and a second hand would
          // double the cost of a model already sharing this thread with the
          // expression analyser.
          numHands: 1,
        });

      try {
        recognizer = await create("GPU");
      } catch {
        try {
          recognizer = await create("CPU");
        } catch {
          return unavailable("The hand model failed to initialise.");
        }
      }
      if (cancelled) {
        recognizer?.close();
        recognizer = null;
        return;
      }

      setStatus({ state: "ready" });
      startLoop();
    })();

    function startLoop() {
      const budget = createFrameBudget({
        targetFps: TARGET_FPS,
        maxLoadFraction: MAX_LOAD,
        phaseOffsetMs: PHASE_OFFSET_MS,
      });
      let lastVideoTime = -1;
      let lastFrameAt = performance.now();

      // Hold trackers. `committed` blocks the same shape from firing twice while
      // it is still being held — a candidate spelling "LL" breaks the shape
      // between the two letters, which is how fingerspelling works anyway.
      let heldLetter: string | null = null;
      let letterHeldMs = 0;
      let committed: string | null = null;

      let heldControl: SignControl | null = null;
      let controlHeldMs = 0;

      const resetLetter = () => {
        heldLetter = null;
        letterHeldMs = 0;
        setPending(null);
      };
      const resetControl = () => {
        heldControl = null;
        controlHeldMs = 0;
        setArming(null);
      };

      const tick = () => {
        frameHandle = requestAnimationFrame(tick);
        if (cancelled || recognizer === null) return;

        const now = performance.now();
        if (!budget.due(now)) return;
        const dtMs = Math.min(now - lastFrameAt, 250);
        lastFrameAt = now;

        if (video === null || video.readyState < 2 || video.videoWidth === 0) return;
        if (video.currentTime === lastVideoTime) return;
        lastVideoTime = video.currentTime;

        let result;
        const startedAt = performance.now();
        try {
          result = recognizer.recognizeForVideo(video, now);
          budget.record(performance.now() - startedAt);
        } catch {
          cancelled = true;
          cancelAnimationFrame(frameHandle);
          setStatus({ state: "unavailable", reason: "Hand recognition stopped unexpectedly." });
          return;
        }

        const landmarks = result.worldLandmarks?.[0];
        const present = Boolean(landmarks && landmarks.length >= 21);
        setHandPresent(present);

        if (!present) {
          // A hand that has left the frame abandons whatever it was holding
          // rather than resuming the count when it returns.
          resetLetter();
          resetControl();
          committed = null;
          return;
        }

        const { fingerspelling, gestures, onLetter, onControl } = optionsRef.current;

        if (fingerspelling) {
          resetControl();
          const guess = recogniseLetter(landmarks!);

          if (guess === null) {
            resetLetter();
            // An unreadable shape is the gap between two letters, so the next
            // recognisable one is allowed to commit even if it repeats.
            committed = null;
            return;
          }

          if (guess.letter !== heldLetter) {
            heldLetter = guess.letter;
            letterHeldMs = 0;
            if (guess.letter !== committed) committed = null;
          } else {
            letterHeldMs += dtMs;
          }

          if (guess.letter === committed) {
            // Still holding the letter just appended. Shown as complete rather
            // than as progress, so the display does not look like it is about to
            // fire again.
            setPending({ ...guess, progress: 1 });
            return;
          }

          if (letterHeldMs >= LETTER_HOLD_MS) {
            committed = guess.letter;
            letterHeldMs = 0;
            setPending({ ...guess, progress: 1 });
            onLetter(guess.letter);
            return;
          }

          setPending({ ...guess, progress: Math.min(1, letterHeldMs / LETTER_HOLD_MS) });
          return;
        }

        resetLetter();
        if (!gestures) {
          resetControl();
          return;
        }

        const top = result.gestures?.[0]?.[0];
        const action =
          top && top.score >= MIN_GESTURE_SCORE ? CONTROL_GESTURES[top.categoryName] : undefined;

        if (!action) {
          resetControl();
          return;
        }

        if (action !== heldControl) {
          heldControl = action;
          controlHeldMs = 0;
        } else {
          controlHeldMs += dtMs;
        }

        if (controlHeldMs >= CONTROL_HOLD_MS) {
          resetControl();
          onControl(action);
          return;
        }

        setArming({ action, progress: Math.min(1, controlHeldMs / CONTROL_HOLD_MS) });
      };

      frameHandle = requestAnimationFrame(tick);
    }

    return () => {
      cancelled = true;
      cancelAnimationFrame(frameHandle);
      recognizer?.close();
      recognizer = null;
    };
  }, [video]);

  const reset = useCallback(() => {
    setPending(null);
    setArming(null);
  }, []);

  return { status, pending, arming, handPresent, reset };
}

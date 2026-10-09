import { useCallback, useEffect, useRef, useState } from "react";
import type { FaceLandmarker } from "@mediapipe/tasks-vision";
import type { ExpressionMeasurement } from "../lib/expressionMetrics";
import { createFrameBudget } from "../lib/frameBudget";
import {
  createExpressionAccumulator,
  faceCentre,
  gazeFromBlendshapes,
  headPoseFromLandmarks,
} from "../lib/expressionMetrics";

/**
 * Browser-side expression measurement (Section 9.7, Phase 5B).
 *
 * Runs MediaPipe's Face Landmarker over the candidate's own camera preview and
 * reduces each frame to Section 9.7's three signals: eye contact, smile
 * frequency, posture flags. The maths lives in `lib/expressionMetrics.ts`, which
 * is verified by `npm run verify:expression`; this hook is the plumbing around
 * it — model lifecycle, frame pacing, and knowing when not to report.
 *
 * ## Video never leaves the device
 *
 * The frame goes from the camera into WASM and is discarded. What crosses the
 * network is three numbers and two coverage figures. There is no frame buffer, no
 * upload, no landmark payload and nothing retained after the frame is scored —
 * the face is biometric data, and the only defensible place to process it is the
 * machine it was captured on.
 *
 * ## Model and runtime are served from our own origin
 *
 * MediaPipe's examples fetch both the WASM and the `.task` model from Google's
 * CDN at page load. This app serves them itself from `/mediapipe/*`, put there by
 * `scripts/setup-mediapipe.mjs`: the WASM is copied out of the pinned
 * `@mediapipe/tasks-vision` package and the model is fetched once against a
 * pinned SHA-256. An interview cannot be at the mercy of a third-party host, and
 * a demo that fails because a CDN was slow is a demo that failed.
 *
 * ## When it declines to report
 *
 * Every one of these ends with `expression_signals` left NULL and the report
 * saying body language was not measured, which is the honest outcome:
 *
 * - no camera, or the camera was revoked mid-interview
 * - the assets are not on disk (setup never ran, or ran without network)
 * - no WebGL/WASM, or the model fails to initialise
 * - a device too weak to run a vision model alongside a live interview
 * - a runtime failure part-way through
 * - under 30 seconds analysed, or a face found in under a quarter of it
 *
 * The last two are enforced in `lib/expressionMetrics.ts`; the rest here. In no
 * case is a plausible-looking number substituted for a measurement that was not
 * taken.
 */

/** Where the pipeline is, and if it is nowhere, why. */
export type ExpressionStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "measuring"; delegate: "GPU" | "CPU" }
  | { state: "unavailable"; reason: string };

const MANIFEST_URL = "/mediapipe/manifest.json";
const WASM_PATH = "/mediapipe/wasm";

// ~12fps to aim for, but adaptively: the model is the expensive thing on this
// thread and it shares the machine with TTS, ASR, the prosody analyser, a WebGL
// background and — in sign mode — a second vision model. Eye contact is a
// proportion over minutes and posture episodes are measured in seconds, so
// neither gains anything from 60fps, and both survive the rate being cut on a
// device that cannot afford 12. `lib/frameBudget.ts` measures what inference
// actually costs here and backs off rather than trusting this number.
const TARGET_FPS = 12;
/**
 * Share of the interval this model may occupy. Lower when a second vision model
 * is running, since allowances add up and two consumers each granted half the
 * thread will between them take all of it.
 */
const SOLO_LOAD = 0.5;
const SHARED_LOAD = 0.35;

// Same clamp, and the same reasoning, as the prosody analyser: a backgrounded
// tab must not have its idle minutes credited as analysed video.
const MAX_FRAME_DT_MS = 250;

/**
 * Two cores is not enough to run a vision model next to a live interview. The
 * interview matters more than the signal, so on a machine this size the signal
 * is the thing that gives way.
 */
const MIN_CORES = 4;

interface AssetManifest {
  ready: boolean;
  modelPath: string;
}

async function loadManifest(): Promise<AssetManifest | null> {
  try {
    const response = await fetch(MANIFEST_URL, { cache: "no-store" });
    if (!response.ok) return null;
    const manifest = (await response.json()) as AssetManifest;
    return manifest.ready && manifest.modelPath ? manifest : null;
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

/**
 * @param video   the candidate's own preview element. Reused rather than given a
 *                second hidden video on the same stream: that would decode the
 *                camera twice, and the point of running at 12fps was to keep this
 *                cheap.
 * @param paused  suspends analysis without discarding what has been accumulated.
 */
export function useExpressionAnalyser(
  video: HTMLVideoElement | null,
  paused: boolean,
  /** True when hand recognition is running on the same thread (sign mode). */
  sharingThread = false,
) {
  const [status, setStatus] = useState<ExpressionStatus>({ state: "idle" });
  const accumulatorRef = useRef(createExpressionAccumulator());
  const pausedRef = useRef(paused);
  pausedRef.current = paused;

  useEffect(() => {
    if (!video) {
      setStatus({ state: "idle" });
      return;
    }

    // Cancellation flag rather than an AbortController: the model load is a
    // multi-step async sequence and every step has to check whether the
    // interview moved on, including after `close()` would be meaningless.
    let cancelled = false;
    let frameHandle = 0;
    let landmarker: FaceLandmarker | null = null;

    const unavailable = (reason: string) => {
      if (!cancelled) setStatus({ state: "unavailable", reason });
    };

    (async () => {
      const cores = navigator.hardwareConcurrency ?? 4;
      if (cores < MIN_CORES) return unavailable("This device is too small to analyse video during an interview.");
      if (!webglAvailable()) return unavailable("WebGL is unavailable in this browser.");

      setStatus({ state: "loading" });

      const manifest = await loadManifest();
      if (cancelled) return;
      if (!manifest) {
        return unavailable(
          "The face model is not installed. Run `npm run setup:mediapipe` in frontend/ to fetch it.",
        );
      }

      // Dynamic import so the library lands in its own chunk: a device that bails
      // out above never downloads it at all.
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

      // GPU first, CPU as the fallback. On a machine with no usable GPU path the
      // CPU delegate still runs, just slower -- which the frame pacing absorbs.
      let delegate: "GPU" | "CPU" = "GPU";
      const create = (which: "GPU" | "CPU") =>
        vision.FaceLandmarker.createFromOptions(fileset, {
          baseOptions: { modelAssetPath: manifest.modelPath, delegate: which },
          runningMode: "VIDEO",
          numFaces: 1,
          outputFaceBlendshapes: true,
          // Not requested: the transformation matrix. `expressionMetrics` derives
          // head pose from landmark geometry instead, because that can be
          // verified against known rotations -- see that module's header.
          outputFacialTransformationMatrixes: false,
        });

      try {
        landmarker = await create("GPU");
      } catch {
        try {
          landmarker = await create("CPU");
          delegate = "CPU";
        } catch {
          return unavailable("The face model failed to initialise.");
        }
      }
      if (cancelled) {
        landmarker?.close();
        landmarker = null;
        return;
      }

      setStatus({ state: "measuring", delegate });
      startLoop();
    })();

    function startLoop() {
      let lastAnalysedAt = performance.now();
      const budget = createFrameBudget({
        targetFps: TARGET_FPS,
        maxLoadFraction: sharingThread ? SHARED_LOAD : SOLO_LOAD,
        // No offset: this is the consumer the hand recogniser offsets *from*.
        phaseOffsetMs: 0,
      });
      // `detectForVideo` requires strictly increasing timestamps, and the preview
      // is not guaranteed to have advanced a frame between two animation frames.
      let lastVideoTime = -1;

      const tick = () => {
        frameHandle = requestAnimationFrame(tick);
        if (cancelled || pausedRef.current || landmarker === null) return;

        const now = performance.now();
        if (!budget.due(now)) return;

        const dtMs = Math.min(now - lastAnalysedAt, MAX_FRAME_DT_MS);
        lastAnalysedAt = now;

        // A stalled or not-yet-sized preview is not analysed video. Skipping the
        // accumulator entirely — rather than logging it as a frame with no face —
        // keeps "the camera was off" out of the eye-contact denominator, where it
        // would read as the candidate looking away.
        if (video === null || video.readyState < 2 || video.videoWidth === 0) return;
        if (video.currentTime === lastVideoTime) return;
        lastVideoTime = video.currentTime;

        let result;
        const startedAt = performance.now();
        try {
          result = landmarker.detectForVideo(video, now);
          budget.record(performance.now() - startedAt);
        } catch {
          // A mid-session failure stops analysis and reports why. The accumulated
          // seconds stand: they were really analysed, and the coverage gate in
          // `expressionMetrics` decides whether they add up to a measurement.
          cancelled = true;
          cancelAnimationFrame(frameHandle);
          setStatus({ state: "unavailable", reason: "Video analysis stopped unexpectedly." });
          return;
        }

        const landmarks = result.faceLandmarks?.[0];
        const blendshapes = result.faceBlendshapes?.[0];
        if (!landmarks || landmarks.length === 0 || !blendshapes) {
          accumulatorRef.current.observeNoFace(dtMs);
          return;
        }

        const pose = headPoseFromLandmarks(landmarks, video.videoHeight / video.videoWidth);
        if (pose === null) {
          // Landmarks arrived but the basis was degenerate. Not a face we can
          // reason about, so it is treated as no face rather than as a pose of
          // zero, which would read as perfect eye contact.
          accumulatorRef.current.observeNoFace(dtMs);
          return;
        }

        const centre = faceCentre(landmarks);
        accumulatorRef.current.observeFace(
          {
            pose,
            gaze: gazeFromBlendshapes(blendshapes.categories),
            centreX: centre.x,
            centreY: centre.y,
          },
          dtMs,
        );
      };

      frameHandle = requestAnimationFrame(tick);
    }

    return () => {
      cancelled = true;
      cancelAnimationFrame(frameHandle);
      landmarker?.close();
      landmarker = null;
    };
  }, [video, sharingThread]);

  /**
   * The session aggregate so far, in the shape the API accepts.
   *
   * Read-only, like the prosody analyser's: expression is submitted as a running
   * aggregate on every turn, so each call describes the whole session up to that
   * instant without consuming anything.
   */
  const measure = useCallback((): ExpressionMeasurement => accumulatorRef.current.result(), []);

  return { measure, status };
}

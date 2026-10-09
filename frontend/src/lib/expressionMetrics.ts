/**
 * The maths behind Section 9.7's expression signals: eye contact, smile
 * frequency and posture flags.
 *
 * Pure by design, and separated from `useExpressionAnalyser` for the same reason
 * `prosodyDsp` is separated from its hook -- given landmarks and blendshape
 * scores these functions return numbers, with no camera, no WASM, no React and
 * no clock. That makes the part of the pipeline a candidate is actually scored on
 * checkable against constructed input, which `npm run verify:expression` does.
 *
 * ## Nothing here sees a video frame
 *
 * MediaPipe reduces each frame to landmark coordinates and blendshape scores
 * inside the browser, and this module reduces those to three aggregate numbers.
 * No pixels, no landmarks and no per-frame data ever leave the device -- what
 * reaches the server is three scores and two coverage figures. The face is
 * biometric data; keeping the whole pipeline client-side is the point, not a
 * side effect of it.
 *
 * ## Head pose from landmark geometry
 *
 * MediaPipe also returns a 4x4 facial transformation matrix, which would be the
 * obvious source for head angles. This module builds a face basis out of three
 * documented landmarks instead, because that can be validated: a synthetic face
 * rotated by a known angle must read back at that angle, and the harness checks
 * exactly that. Deriving Euler angles from a matrix whose row/column order is
 * assumed rather than verified would put an untested assumption underneath every
 * eye-contact percentage the product reports.
 */

// --- Landmark indices, from MediaPipe's canonical face mesh ------------------
// A long baseline in each direction: the outer eye corners across, and forehead
// to chin down. Closely spaced points would make the basis noisy.
const RIGHT_EYE_OUTER = 33; // the subject's right, so image-left in a mirror-less feed
const LEFT_EYE_OUTER = 263;
const FOREHEAD = 10;
const CHIN = 152;

// --- Eye contact ------------------------------------------------------------
// A candidate looks at the *interviewer on their screen*, not at the lens above
// it. So the window is deliberately asymmetric in pitch: a little downward tilt
// is what attentive looks like on a laptop, while the same angle upward means
// they are looking past the screen at the ceiling.
const MAX_YAW_DEG = 22;
const MAX_PITCH_UP_DEG = 12;
const MAX_PITCH_DOWN_DEG = 24;
// Blendshape gaze, 0-1. Generous on downward gaze for the same screen-below-lens
// reason, tighter on sideways and upward gaze.
const MAX_GAZE_OFF_AXIS = 0.5;
const MAX_GAZE_DOWN = 0.7;
const BLINK_THRESHOLD = 0.5;

// --- Smiles -----------------------------------------------------------------
// Counted as events, not as a fraction of time: "frequency" is what Section 9.7
// asks for, and one long grin is not the same signal as warming up repeatedly
// through an interview.
const SMILE_ON = 0.35;
// A smile has to relax below this before the next rise counts, so a score
// hovering on the threshold registers once rather than forty times.
const SMILE_OFF = 0.2;
// Saturation anchor: roughly three smiles a minute reads as a warm delivery.
// A judgement call about interviews, which is why it is one named constant.
const SMILES_PER_MINUTE_FOR_FULL_SCORE = 3;

// --- Posture ----------------------------------------------------------------
const MAX_ROLL_DEG = 12; // head cocked to one side
const SLOUCH_PITCH_DEG = -28; // looking well down, at notes or a second screen
const MAX_CENTRE_OFFSET = 0.22; // drifted out of the middle of frame
const MAX_CENTRE_LOW = 0.72; // sunk toward the bottom of frame
// A deviation has to hold this long to be a posture issue rather than a glance
// or a shift in the chair.
const POSTURE_HOLD_MS = 2000;
// Nobody is served by a report that says "47 posture flags". Past this the
// message is the same and the number stops being informative.
const MAX_POSTURE_FLAGS = 20;

// --- Coverage gates ---------------------------------------------------------
/** Under this much analysed video there is no measurement, only a sample. */
const MIN_ANALYSED_SECONDS = 30;
/**
 * If a face was found in less than this share of the analysed time, the result
 * is withheld entirely.
 *
 * The reasoning is that below this point "no face" stops being evidence about
 * the candidate and starts being evidence about the room: a dark office, a
 * camera pointed at the ceiling, a laptop lid half closed. Those are
 * indistinguishable from someone sitting outside frame, and reporting 4% eye
 * contact for a broken camera would be a fabricated measurement.
 */
const MIN_FACE_COVERAGE = 0.25;

export interface Point3 {
  x: number;
  y: number;
  z: number;
}

export interface HeadPose {
  /** Degrees. Positive turns the face toward image-right (the subject's left). */
  yawDeg: number;
  /** Degrees. Positive is looking up. */
  pitchDeg: number;
  /** Degrees. Positive tilts the subject's left eye downward. */
  rollDeg: number;
}

/** The blendshape scores this module reads, extracted from MediaPipe's 52. */
export interface GazeSignals {
  /** 0-1. Sideways or upward gaze -- away from the screen in any direction. */
  offAxis: number;
  /** 0-1. Downward gaze, which is partly normal on a laptop. */
  down: number;
  /** 0-1. Peak of the two smile blendshapes. */
  smile: number;
  /** Mid-blink, so this frame is evidence of nothing either way. */
  blinking: boolean;
}

export interface FaceObservation {
  pose: HeadPose;
  gaze: GazeSignals;
  /** Face centre in normalised image coordinates, y measured downward. */
  centreX: number;
  centreY: number;
}

export interface ExpressionMeasurement {
  eyeContactPercentage: number | null;
  smileFrequencyScore: number | null;
  postureFlagCount: number | null;
  /** Seconds of video the analyser actually looked at. */
  analysedSeconds: number;
  /** Of those, the seconds a face was found in. */
  faceDetectedSeconds: number;
}

const RAD_TO_DEG = 180 / Math.PI;

const subtract = (a: Point3, b: Point3): Point3 => ({ x: a.x - b.x, y: a.y - b.y, z: a.z - b.z });

const cross = (a: Point3, b: Point3): Point3 => ({
  x: a.y * b.z - a.z * b.y,
  y: a.z * b.x - a.x * b.z,
  z: a.x * b.y - a.y * b.x,
});

function normalize(v: Point3): Point3 | null {
  const length = Math.hypot(v.x, v.y, v.z);
  if (length < 1e-9) return null;
  return { x: v.x / length, y: v.y / length, z: v.z / length };
}

/**
 * Head orientation from the face mesh.
 *
 * MediaPipe normalises x by image width and y by image height *independently*, so
 * on any non-square frame the raw coordinates live in a stretched space and an
 * angle read straight off them would be wrong by the aspect ratio. `aspect`
 * (height / width) squares them up first.
 *
 * Two long baselines make a face basis: outer-eye-corner to outer-eye-corner
 * across, forehead to chin down. Their cross product is the direction the face
 * points. Returns null if the landmarks are degenerate — a collapsed basis means
 * no pose, not a pose of zero.
 */
export function headPoseFromLandmarks(landmarks: readonly Point3[], aspect: number): HeadPose | null {
  const needed = [RIGHT_EYE_OUTER, LEFT_EYE_OUTER, FOREHEAD, CHIN];
  if (needed.some((index) => landmarks[index] === undefined)) return null;

  // Into square-pixel space. z is already documented as roughly x's scale.
  const square = (p: Point3): Point3 => ({ x: p.x, y: p.y * aspect, z: p.z });
  const rightEye = square(landmarks[RIGHT_EYE_OUTER]);
  const leftEye = square(landmarks[LEFT_EYE_OUTER]);
  const forehead = square(landmarks[FOREHEAD]);
  const chin = square(landmarks[CHIN]);

  // Toward the subject's left, and toward the subject's chin.
  const across = normalize(subtract(leftEye, rightEye));
  const down = normalize(subtract(chin, forehead));
  if (!across || !down) return null;

  // Out of the face, toward the camera. MediaPipe's z decreases toward the
  // lens, so a face looking straight at the camera gives facing = (0, 0, -1).
  const facing = normalize(cross(down, across));
  if (!facing) return null;

  return {
    yawDeg: Math.atan2(facing.x, -facing.z) * RAD_TO_DEG,
    pitchDeg: Math.atan2(-facing.y, Math.hypot(facing.x, facing.z)) * RAD_TO_DEG,
    rollDeg: Math.atan2(across.y, across.x) * RAD_TO_DEG,
  };
}

/**
 * The four signals this module needs, out of MediaPipe's 52 blendshapes.
 *
 * Gaze is read from the eye-look shapes rather than from the head pose because
 * they are different things: someone can face the camera squarely and still be
 * reading something off to the side. Left/right are combined across both eyes --
 * one eye's "in" is the other's "out" for the same direction of gaze -- so a
 * partly occluded eye degrades the estimate instead of inverting it.
 */
export function gazeFromBlendshapes(
  categories: readonly { categoryName: string; score: number }[],
): GazeSignals {
  const score = (name: string): number => {
    const match = categories.find((category) => category.categoryName === name);
    return match ? match.score : 0;
  };

  const towardSubjectsRight = (score("eyeLookOutRight") + score("eyeLookInLeft")) / 2;
  const towardSubjectsLeft = (score("eyeLookOutLeft") + score("eyeLookInRight")) / 2;
  const upward = (score("eyeLookUpLeft") + score("eyeLookUpRight")) / 2;

  return {
    offAxis: Math.max(towardSubjectsRight, towardSubjectsLeft, upward),
    down: (score("eyeLookDownLeft") + score("eyeLookDownRight")) / 2,
    smile: Math.max(score("mouthSmileLeft"), score("mouthSmileRight")),
    blinking: Math.max(score("eyeBlinkLeft"), score("eyeBlinkRight")) > BLINK_THRESHOLD,
  };
}

/** Whether this frame counts as looking at the interviewer. */
export function isLookingAtCamera({ pose, gaze }: FaceObservation): boolean {
  if (Math.abs(pose.yawDeg) > MAX_YAW_DEG) return false;
  if (pose.pitchDeg > MAX_PITCH_UP_DEG) return false;
  if (pose.pitchDeg < -MAX_PITCH_DOWN_DEG) return false;
  if (gaze.offAxis > MAX_GAZE_OFF_AXIS) return false;
  if (gaze.down > MAX_GAZE_DOWN) return false;
  return true;
}

export type PostureIssue = "tilted" | "slouched" | "off_centre";

/** The posture problem visible in this frame, if any. */
export function classifyPosture({ pose, centreX, centreY }: FaceObservation): PostureIssue | null {
  if (pose.pitchDeg < SLOUCH_PITCH_DEG) return "slouched";
  if (Math.abs(pose.rollDeg) > MAX_ROLL_DEG) return "tilted";
  if (Math.abs(centreX - 0.5) > MAX_CENTRE_OFFSET || centreY > MAX_CENTRE_LOW) return "off_centre";
  return null;
}

/** Mean of the landmark cloud — a cheap, stable stand-in for the face centre. */
export function faceCentre(landmarks: readonly Point3[]): { x: number; y: number } {
  let sumX = 0;
  let sumY = 0;
  for (const point of landmarks) {
    sumX += point.x;
    sumY += point.y;
  }
  const count = landmarks.length || 1;
  return { x: sumX / count, y: sumY / count };
}

export interface ExpressionAccumulator {
  /** A frame in which a face was found. */
  observeFace(observation: FaceObservation, dtMs: number): void;
  /** A frame that was analysed but held no detectable face. */
  observeNoFace(dtMs: number): void;
  /** The session aggregate so far. Does not consume state — safe to call per turn. */
  result(): ExpressionMeasurement;
}

/**
 * Accumulates per-frame observations into Section 9.7's three signals.
 *
 * ## The three denominators are deliberately different
 *
 * - **Eye contact** is over *analysed* time. A candidate who leaves the frame is
 *   not making eye contact, so those seconds belong in the denominator. Blink
 *   frames are excluded from both halves instead of counted as looking away — a
 *   closed eye is evidence of nothing, and at a normal blink rate counting them
 *   would shave a few points off everyone.
 * - **Smile frequency** is over *face-detected* time. It is a rate of events, and
 *   seconds where no face was visible could not have produced an observable
 *   event either way; including them would penalise a candidate for the camera
 *   rather than for their delivery.
 * - **Posture flags** are a plain count, over face-detected time by necessity.
 *
 * Each choice is defensible on its own terms and none of them is the default
 * "divide by everything"; the differences are the point.
 */
export function createExpressionAccumulator(): ExpressionAccumulator {
  let analysedMs = 0;
  let faceMs = 0;
  let lookingMs = 0;
  /** Analysed time excluding blinks, which is what `lookingMs` is a share of. */
  let judgeableMs = 0;

  let smiling = false;
  let smileCount = 0;

  let currentIssue: PostureIssue | null = null;
  let issueHeldMs = 0;
  let issueAlreadyFlagged = false;
  let postureFlags = 0;

  return {
    observeFace(observation, dtMs) {
      analysedMs += dtMs;
      faceMs += dtMs;

      if (!observation.gaze.blinking) {
        judgeableMs += dtMs;
        if (isLookingAtCamera(observation)) lookingMs += dtMs;
      }

      // Schmitt trigger on the smile score: rise above SMILE_ON to start,
      // fall below SMILE_OFF to end. One event per genuine smile.
      const smileScore = observation.gaze.smile;
      if (!smiling && smileScore >= SMILE_ON) {
        smiling = true;
        smileCount += 1;
      } else if (smiling && smileScore < SMILE_OFF) {
        smiling = false;
      }

      const issue = classifyPosture(observation);
      if (issue !== null && issue === currentIssue) {
        issueHeldMs += dtMs;
        // One flag per continuous episode, however long it runs. A candidate who
        // slouches once for ten minutes has one posture problem, not three
        // hundred.
        if (!issueAlreadyFlagged && issueHeldMs >= POSTURE_HOLD_MS && postureFlags < MAX_POSTURE_FLAGS) {
          postureFlags += 1;
          issueAlreadyFlagged = true;
        }
      } else {
        currentIssue = issue;
        issueHeldMs = 0;
        issueAlreadyFlagged = false;
      }
    },

    observeNoFace(dtMs) {
      analysedMs += dtMs;
      judgeableMs += dtMs; // out of frame is a judgeable state: not looking
      // A face that has left the frame ends whatever posture episode was running
      // rather than continuing to accrue against an unseen candidate.
      currentIssue = null;
      issueHeldMs = 0;
      issueAlreadyFlagged = false;
      smiling = false;
    },

    result() {
      const analysedSeconds = Number((analysedMs / 1000).toFixed(2));
      const faceDetectedSeconds = Number((faceMs / 1000).toFixed(2));

      const unmeasured: ExpressionMeasurement = {
        eyeContactPercentage: null,
        smileFrequencyScore: null,
        postureFlagCount: null,
        analysedSeconds,
        faceDetectedSeconds,
      };

      if (analysedMs < MIN_ANALYSED_SECONDS * 1000) return unmeasured;
      if (faceMs / analysedMs < MIN_FACE_COVERAGE) return unmeasured;

      const smilesPerMinute = faceMs > 0 ? smileCount / (faceMs / 60_000) : 0;

      return {
        eyeContactPercentage:
          judgeableMs > 0 ? Math.round((lookingMs / judgeableMs) * 1000) / 10 : null,
        smileFrequencyScore:
          Math.round(Math.min(1, smilesPerMinute / SMILES_PER_MINUTE_FOR_FULL_SCORE) * 1000) / 10,
        postureFlagCount: postureFlags,
        analysedSeconds,
        faceDetectedSeconds,
      };
    },
  };
}

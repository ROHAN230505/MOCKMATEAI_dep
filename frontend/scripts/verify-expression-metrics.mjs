/**
 * Numeric verification of the expression maths (Section 9.7, Phase 5B).
 *
 *   npm run verify:expression
 *
 * Same approach as `verify-prosody-dsp.mjs`: Node strips the types off
 * `src/lib/expressionMetrics.ts` on import, so the real module runs against
 * constructed input with no test runner and no new dependency.
 *
 * The head-pose check is the one that matters most. It builds a synthetic face
 * out of four points, rotates it by a known angle with a rotation matrix built
 * here, and requires the module to read that angle back. Without it, the yaw and
 * pitch thresholds behind every eye-contact percentage would rest on an
 * unverified sign convention -- which is exactly why this module derives pose
 * from landmark geometry rather than from MediaPipe's transformation matrix,
 * whose row/column order could only have been assumed.
 */
import {
  classifyPosture,
  createExpressionAccumulator,
  faceCentre,
  gazeFromBlendshapes,
  headPoseFromLandmarks,
  isLookingAtCamera,
} from "../src/lib/expressionMetrics.ts";

let failures = 0;
const check = (name, passed, detail = "") => {
  if (!passed) failures += 1;
  console.log(`${passed ? "  ok  " : " FAIL "} ${name}${detail ? `  ${detail}` : ""}`);
};

const DEG = Math.PI / 180;

/**
 * A frontal synthetic face in MediaPipe's coordinate convention: x right, y
 * down, z decreasing toward the lens. Only the four landmarks the module reads
 * are populated; the array is sparse on purpose, since that is what a partial
 * mesh would look like.
 */
function frontalFace() {
  const face = [];
  face[33] = { x: -0.06, y: 0.0, z: 0.02 }; // subject's right eye outer
  face[263] = { x: 0.06, y: 0.0, z: 0.02 }; // subject's left eye outer
  face[10] = { x: 0.0, y: -0.11, z: 0.03 }; // forehead
  face[152] = { x: 0.0, y: 0.13, z: 0.03 }; // chin
  return face;
}

/** Rotate about y (yaw), x (pitch) then z (roll), and translate to frame centre. */
function rotateFace(face, yawDeg, pitchDeg, rollDeg, centre = { x: 0.5, y: 0.5 }) {
  const [cy, sy] = [Math.cos(yawDeg * DEG), Math.sin(yawDeg * DEG)];
  const [cp, sp] = [Math.cos(pitchDeg * DEG), Math.sin(pitchDeg * DEG)];
  const [cr, sr] = [Math.cos(rollDeg * DEG), Math.sin(rollDeg * DEG)];

  const out = [];
  for (const index of [33, 263, 10, 152]) {
    let { x, y, z } = face[index];
    // Yaw about the y axis. Positive must swing the face toward image-right,
    // i.e. its normal (0,0,-1) toward +x.
    [x, z] = [x * cy - z * sy, x * sy + z * cy];
    // Pitch about the x axis. Positive must tip the face upward (-y).
    [y, z] = [y * cp + z * sp, -y * sp + z * cp];
    // Roll about the z axis. Positive must drop the subject's left eye (+y).
    [x, y] = [x * cr - y * sr, x * sr + y * cr];
    out[index] = { x: x + centre.x, y: y + centre.y, z };
  }
  return out;
}

console.log("\nhead pose reads back known rotations (square frame)");
for (const yaw of [-40, -22, -10, 0, 10, 22, 40]) {
  const pose = headPoseFromLandmarks(rotateFace(frontalFace(), yaw, 0, 0), 1);
  const error = pose === null ? Infinity : Math.abs(pose.yawDeg - yaw);
  check(`yaw ${yaw}deg`, error < 1.5, pose === null ? "-> null" : `-> ${pose.yawDeg.toFixed(1)}deg`);
}
for (const pitch of [-30, -12, 0, 12, 30]) {
  const pose = headPoseFromLandmarks(rotateFace(frontalFace(), 0, pitch, 0), 1);
  const error = pose === null ? Infinity : Math.abs(pose.pitchDeg - pitch);
  check(`pitch ${pitch}deg`, error < 1.5, pose === null ? "-> null" : `-> ${pose.pitchDeg.toFixed(1)}deg`);
}
for (const roll of [-25, -12, 0, 12, 25]) {
  const pose = headPoseFromLandmarks(rotateFace(frontalFace(), 0, 0, roll), 1);
  const error = pose === null ? Infinity : Math.abs(pose.rollDeg - roll);
  check(`roll ${roll}deg`, error < 1.5, pose === null ? "-> null" : `-> ${pose.rollDeg.toFixed(1)}deg`);
}

console.log("\nsigns are the ones the thresholds assume");
const lookingDown = headPoseFromLandmarks(rotateFace(frontalFace(), 0, -20, 0), 1);
check("looking down is negative pitch", lookingDown.pitchDeg < -15, `-> ${lookingDown.pitchDeg.toFixed(1)}deg`);
const turnedRight = headPoseFromLandmarks(rotateFace(frontalFace(), 30, 0, 0), 1);
check("turning toward image-right is positive yaw", turnedRight.yawDeg > 25, `-> ${turnedRight.yawDeg.toFixed(1)}deg`);

console.log("\naspect-ratio correction");
// A 16:9 frame stretches y. Uncorrected, a pure roll would read wrong; the
// module is handed height/width and must undo it.
const wide = rotateFace(frontalFace(), 0, 0, 20);
const stretched = [];
for (const i of [33, 263, 10, 152]) stretched[i] = { ...wide[i], y: (wide[i].y - 0.5) / (9 / 16) + 0.5 };
const corrected = headPoseFromLandmarks(stretched, 9 / 16);
const uncorrected = headPoseFromLandmarks(stretched, 1);
check("16:9 roll is recovered when aspect is supplied", Math.abs(corrected.rollDeg - 20) < 1.5, `-> ${corrected.rollDeg.toFixed(1)}deg`);
check("and is wrong without it, so the correction is doing work", Math.abs(uncorrected.rollDeg - 20) > 5, `-> ${uncorrected.rollDeg.toFixed(1)}deg`);

console.log("\ndegenerate input yields no pose, not a pose of zero");
check("missing landmarks -> null", headPoseFromLandmarks([{ x: 0, y: 0, z: 0 }], 1) === null);
const collapsed = [];
for (const i of [33, 263, 10, 152]) collapsed[i] = { x: 0.5, y: 0.5, z: 0 };
check("collapsed basis -> null", headPoseFromLandmarks(collapsed, 1) === null);

console.log("\ngaze from blendshapes");
const bs = (entries) => Object.entries(entries).map(([categoryName, score]) => ({ categoryName, score }));
const straightAhead = gazeFromBlendshapes(bs({ eyeLookInLeft: 0.05, eyeLookOutRight: 0.04, mouthSmileLeft: 0.02 }));
check("gaze straight ahead is low off-axis", straightAhead.offAxis < 0.1, `-> ${straightAhead.offAxis.toFixed(3)}`);
const glancingAside = gazeFromBlendshapes(bs({ eyeLookOutLeft: 0.8, eyeLookInRight: 0.7 }));
check("glancing aside is high off-axis", glancingAside.offAxis > 0.6, `-> ${glancingAside.offAxis.toFixed(3)}`);
const blinking = gazeFromBlendshapes(bs({ eyeBlinkLeft: 0.9, eyeBlinkRight: 0.88 }));
check("a blink is detected", blinking.blinking === true);
const smiling = gazeFromBlendshapes(bs({ mouthSmileLeft: 0.6, mouthSmileRight: 0.1 }));
check("smile takes the stronger side", Math.abs(smiling.smile - 0.6) < 1e-6, `-> ${smiling.smile}`);
check("absent categories read as zero, not NaN", Number.isFinite(gazeFromBlendshapes([]).offAxis));

console.log("\nframe classification");
const observation = (over = {}) => ({
  pose: { yawDeg: 0, pitchDeg: -5, rollDeg: 0, ...(over.pose ?? {}) },
  gaze: { offAxis: 0.05, down: 0.2, smile: 0, blinking: false, ...(over.gaze ?? {}) },
  centreX: over.centreX ?? 0.5,
  centreY: over.centreY ?? 0.5,
});
check("attentive frame counts as eye contact", isLookingAtCamera(observation()));
check("turned away does not", !isLookingAtCamera(observation({ pose: { yawDeg: 35 } })));
check("looking at the ceiling does not", !isLookingAtCamera(observation({ pose: { pitchDeg: 25 } })));
check("reading off to the side does not", !isLookingAtCamera(observation({ gaze: { offAxis: 0.8 } })));
check(
  "a slight downward tilt still does, since the screen is below the lens",
  isLookingAtCamera(observation({ pose: { pitchDeg: -18 }, gaze: { down: 0.55 } })),
);

check("no posture issue when settled", classifyPosture(observation()) === null);
check("cocked head is tilted", classifyPosture(observation({ pose: { rollDeg: 20 } })) === "tilted");
check("head well down is slouched", classifyPosture(observation({ pose: { pitchDeg: -35 } })) === "slouched");
check("drifted sideways is off_centre", classifyPosture(observation({ centreX: 0.85 })) === "off_centre");
check("sunk low in frame is off_centre", classifyPosture(observation({ centreY: 0.8 })) === "off_centre");

console.log("\nface centre");
const centre = faceCentre([
  { x: 0.4, y: 0.4, z: 0 },
  { x: 0.6, y: 0.6, z: 0 },
]);
check("centre is the landmark mean", Math.abs(centre.x - 0.5) < 1e-9 && Math.abs(centre.y - 0.5) < 1e-9);
check("empty landmark list does not divide by zero", Number.isFinite(faceCentre([]).x));

console.log("\naccumulator: coverage gates withhold rather than guess");
const FRAME_MS = 80; // ~12fps, what the hook actually runs at

const runFrames = (count, build) => {
  const accumulator = createExpressionAccumulator();
  for (let i = 0; i < count; i += 1) {
    const frame = build(i);
    if (frame === null) accumulator.observeNoFace(FRAME_MS);
    else accumulator.observeFace(frame, FRAME_MS);
  }
  return accumulator.result();
};

const tooShort = runFrames(120, () => observation()); // 9.6s
check("under 30s analysed -> all null", tooShort.eyeContactPercentage === null && tooShort.postureFlagCount === null,
  `-> ${tooShort.analysedSeconds}s analysed`);
check("but coverage figures are still reported honestly", tooShort.analysedSeconds > 9 && tooShort.faceDetectedSeconds > 9);

// 90s analysed, a face in only 10% of it: a broken camera, not a candidate.
const barelySeen = runFrames(1125, (i) => (i % 10 === 0 ? observation() : null));
check("a face in 10% of frames -> all null", barelySeen.eyeContactPercentage === null,
  `-> ${barelySeen.faceDetectedSeconds}s of ${barelySeen.analysedSeconds}s`);

// Same duration, face in 60% of it: measurable, and the absences count against.
const mostlySeen = runFrames(1125, (i) => (i % 10 < 6 ? observation() : null));
check("a face in 60% of frames -> measured", mostlySeen.eyeContactPercentage !== null, `-> ${mostlySeen.eyeContactPercentage}%`);
check("time out of frame counts as not looking", mostlySeen.eyeContactPercentage < 65, `-> ${mostlySeen.eyeContactPercentage}%`);

console.log("\naccumulator: eye contact");
const attentive = runFrames(750, () => observation());
check("a fully attentive session scores 100%", attentive.eyeContactPercentage === 100, `-> ${attentive.eyeContactPercentage}%`);

const halfAway = runFrames(750, (i) => observation(i % 2 === 0 ? {} : { pose: { yawDeg: 40 } }));
check("looking away half the time scores ~50%", Math.abs(halfAway.eyeContactPercentage - 50) < 2, `-> ${halfAway.eyeContactPercentage}%`);

// A normal blink rate is ~15/min lasting ~150ms. Counting those as looking away
// would quietly dock every candidate a few points.
const blinkingNormally = runFrames(750, (i) => observation(i % 50 < 2 ? { gaze: { blinking: true } } : {}));
check("blinks do not reduce eye contact", blinkingNormally.eyeContactPercentage === 100, `-> ${blinkingNormally.eyeContactPercentage}%`);

console.log("\naccumulator: smile frequency");
const stoneFaced = runFrames(750, () => observation());
check("never smiling scores 0", stoneFaced.smileFrequencyScore === 0, `-> ${stoneFaced.smileFrequencyScore}`);

// One 1.6s smile every 10s = 6/min, past the saturation anchor of 3/min.
const warm = runFrames(750, (i) => observation({ gaze: { smile: i % 125 < 20 ? 0.7 : 0.0 } }));
check("smiling often saturates the score", warm.smileFrequencyScore === 100, `-> ${warm.smileFrequencyScore}`);

// The score counts events, not duration. Over the same 60 seconds, one brief
// smile and one held for the whole session are both one event -- so the two must
// come out identical, and both far below a candidate who smiled repeatedly.
const oneBriefSmile = runFrames(750, (i) => observation({ gaze: { smile: i < 20 ? 0.7 : 0 } }));
const oneLongGrin = runFrames(750, () => observation({ gaze: { smile: 0.8 } }));
check(
  "one continuous smile counts the same as one brief smile",
  oneLongGrin.smileFrequencyScore === oneBriefSmile.smileFrequencyScore,
  `-> ${oneLongGrin.smileFrequencyScore} vs ${oneBriefSmile.smileFrequencyScore}`,
);
check("and well below smiling repeatedly", oneLongGrin.smileFrequencyScore < warm.smileFrequencyScore,
  `-> ${oneLongGrin.smileFrequencyScore} < ${warm.smileFrequencyScore}`);
check("one smile per minute is a third of the way to the anchor", Math.abs(oneLongGrin.smileFrequencyScore - 33.3) < 0.2,
  `-> ${oneLongGrin.smileFrequencyScore}`);

// A score hovering on the threshold must register once, not once per frame.
// Without hysteresis this pattern would count 375 smiles in a minute.
const flickering = runFrames(750, (i) => observation({ gaze: { smile: i % 2 === 0 ? 0.36 : 0.3 } }));
check(
  "hysteresis absorbs a score sitting on the threshold",
  flickering.smileFrequencyScore === oneBriefSmile.smileFrequencyScore,
  `-> ${flickering.smileFrequencyScore}, i.e. one event not 375`,
);

console.log("\naccumulator: posture flags");
const settled = runFrames(750, () => observation());
check("a settled candidate has no flags", settled.postureFlagCount === 0);

// A 5s slouch, then recovery, three times over.
const slouchesThrice = runFrames(750, (i) => {
  const phase = i % 250;
  return observation(phase < 63 ? { pose: { pitchDeg: -35 } } : {});
});
check("three sustained slouches -> 3 flags", slouchesThrice.postureFlagCount === 3, `-> ${slouchesThrice.postureFlagCount}`);

// A single episode held for the whole session is one problem, not thousands.
const permanentSlouch = runFrames(750, () => observation({ pose: { pitchDeg: -35 } }));
check("one long episode counts once", permanentSlouch.postureFlagCount === 1, `-> ${permanentSlouch.postureFlagCount}`);

// A brief glance down is not a posture problem.
const glances = runFrames(750, (i) => observation(i % 50 < 10 ? { pose: { pitchDeg: -35 } } : {}));
check("brief glances raise no flag", glances.postureFlagCount === 0, `-> ${glances.postureFlagCount}`);

check("flags are capped", runFrames(20000, (i) => observation(i % 60 < 30 ? { pose: { pitchDeg: -35 } } : {})).postureFlagCount <= 20);

console.log(failures === 0 ? "\nall expression metric checks passed\n" : `\n${failures} expression metric check(s) FAILED\n`);
process.exitCode = failures === 0 ? 0 : 1;

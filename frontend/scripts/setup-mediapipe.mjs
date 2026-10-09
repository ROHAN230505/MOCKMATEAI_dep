/**
 * Puts MediaPipe's runtime assets on disk so the app serves them itself.
 *
 *   npm run setup:mediapipe
 *
 * Runs automatically before `dev` and `build`, and is idempotent -- present files
 * are left alone, so the usual case costs a few stat calls.
 *
 * ## Why this script exists
 *
 * MediaPipe's own examples load both the WASM runtime and the model from Google's
 * CDN at page load. That is unacceptable here: a live interview cannot depend on
 * a third-party host being reachable, and a demo that fails because
 * storage.googleapis.com is slow is a demo that failed. Everything is copied or
 * fetched once, up front, and served from our own origin from then on.
 *
 * The WASM comes out of `node_modules` -- it ships inside the pinned
 * `@mediapipe/tasks-vision` package, so it needs no network at all and never
 * drifts from the library version that loads it. Only the `.task` model has to be
 * fetched, and it is verified against a pinned SHA-256 rather than trusted by
 * URL: pinning the library version while letting the model float would leave the
 * half that actually decides the numbers unpinned.
 *
 * A failed fetch is a warning, not an error. The app checks for the model at
 * startup and reports body language as unmeasured when it is missing, which is
 * the truth -- so a build without network still produces a working interview,
 * just without expression signals.
 */
import { createHash } from "node:crypto";
import { copyFileSync, existsSync, mkdirSync, readFileSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(HERE, "..");

const PUBLIC_DIR = join(ROOT, "public", "mediapipe");
const WASM_DIR = join(PUBLIC_DIR, "wasm");
const MODEL_DIR = join(PUBLIC_DIR, "models");

const WASM_SOURCE = join(ROOT, "node_modules", "@mediapipe", "tasks-vision", "wasm");
// `FilesetResolver.forVisionTasks` picks the SIMD build when the browser supports
// it and the nosimd build otherwise, so both pairs are required. The
// `_module_internal` variants belong to a loading mode this app does not use.
const WASM_FILES = [
  "vision_wasm_internal.js",
  "vision_wasm_internal.wasm",
  "vision_wasm_nosimd_internal.js",
  "vision_wasm_nosimd_internal.wasm",
];

// Each entry is pinned by digest, not just by URL. Pinning the library version
// while letting a model float would leave the half that actually decides the
// numbers unpinned.
const MODELS = [
  {
    name: "face_landmarker.task",
    url: "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task",
    sha256: "64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff",
    bytes: 3_758_596,
    // Phase 5B: eye contact, smile frequency, posture.
    purpose: "expression signals",
  },
  {
    name: "gesture_recognizer.task",
    url: "https://storage.googleapis.com/mediapipe-models/gesture_recognizer/gesture_recognizer/float16/1/gesture_recognizer.task",
    sha256: "97952348cf6a6a4915c2ea1496b4b37ebabc50cbbf80571435643c455f2b0482",
    bytes: 8_373_440,
    // Phase 6: one bundle, two capabilities -- Google's trained 7-gesture
    // classifier for interview control, and the 21 hand landmarks that
    // `lib/fingerspelling.ts` classifies into letters.
    purpose: "sign recognition",
  },
];

const sha256 = (buffer) => createHash("sha256").update(buffer).digest("hex");

function copyWasm() {
  if (!existsSync(WASM_SOURCE)) {
    console.warn(`  ! ${WASM_SOURCE} is missing -- run npm install first.`);
    return false;
  }
  mkdirSync(WASM_DIR, { recursive: true });

  let copied = 0;
  for (const name of WASM_FILES) {
    const from = join(WASM_SOURCE, name);
    const to = join(WASM_DIR, name);
    if (!existsSync(from)) {
      console.warn(`  ! ${name} is not in the installed package`);
      return false;
    }
    // Size, not mtime: npm rewrites mtimes on reinstall, and a mismatch in size
    // is the case that actually matters (a half-written or stale copy).
    if (existsSync(to) && statSync(to).size === statSync(from).size) continue;
    copyFileSync(from, to);
    copied += 1;
  }
  console.log(copied === 0 ? "  = wasm runtime already in place" : `  + copied ${copied} wasm file(s)`);
  return true;
}

async function fetchModel(model) {
  mkdirSync(MODEL_DIR, { recursive: true });
  const target = join(MODEL_DIR, model.name);

  if (existsSync(target)) {
    if (sha256(readFileSync(target)) === model.sha256) {
      console.log(`  = ${model.name} already in place and verified`);
      return true;
    }
    console.warn(`  ! ${model.name} on disk does not match the pinned digest -- refetching`);
  }

  console.log(`  . fetching ${model.name} (${(model.bytes / 1e6).toFixed(1)}MB, ${model.purpose}), once`);
  let buffer;
  try {
    const response = await fetch(model.url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    buffer = Buffer.from(await response.arrayBuffer());
  } catch (error) {
    console.warn(`  ! could not fetch ${model.name}: ${error.message}`);
    return false;
  }

  const digest = sha256(buffer);
  if (digest !== model.sha256) {
    // Refused rather than written. An unexpected model is either a supply-chain
    // problem or a silently upgraded artefact, and both would change what a
    // candidate is scored on without anything in the repo recording it.
    console.warn(`  ! ${model.name}: digest mismatch -- expected ${model.sha256}, got ${digest}. Not written.`);
    return false;
  }

  writeFileSync(target, buffer);
  console.log(`  + ${model.name} fetched and verified`);
  return true;
}

console.log("mediapipe assets");
const wasmOk = copyWasm();

const results = [];
for (const model of MODELS) results.push([model, await fetchModel(model)]);
const modelOk = results.every(([, ok]) => ok);

// A manifest the app reads at startup, so "are the assets here?" is one cheap
// request instead of probing for a 12MB wasm binary.
writeFileSync(
  join(PUBLIC_DIR, "manifest.json"),
  JSON.stringify(
    {
      // `ready` stays the overall gate for expression signals, which shipped
      // first and whose absence the app already handles. Per-model readiness is
      // reported alongside so sign recognition can bow out on its own without
      // taking expression analysis down with it.
      ready: Boolean(wasmOk && results.every(([model, ok]) => ok || model.purpose !== "expression signals")),
      wasmPath: "/mediapipe/wasm",
      modelPath: "/mediapipe/models/face_landmarker.task",
      gestureModelPath: "/mediapipe/models/gesture_recognizer.task",
      gestureReady: Boolean(
        wasmOk && results.some(([model, ok]) => ok && model.purpose === "sign recognition"),
      ),
      library: "@mediapipe/tasks-vision",
      models: results.map(([model, ok]) => ({
        name: model.name,
        purpose: model.purpose,
        sha256: model.sha256,
        present: ok,
      })),
    },
    null,
    2,
  ) + "\n",
);

if (!wasmOk || !modelOk) {
  console.warn(
    "\n  Expression signals will report as unmeasured until these assets are present.\n" +
      "  Re-run `npm run setup:mediapipe` once network is available.\n",
  );
} else {
  console.log("  ready\n");
}

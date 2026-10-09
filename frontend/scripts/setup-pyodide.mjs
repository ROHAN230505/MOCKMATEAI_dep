/**
 * Copies Pyodide's runtime out of node_modules so the app serves it itself.
 *
 *   npm run setup:assets   (runs automatically before dev and build)
 *
 * Idempotent: files already present at the right size are left alone.
 *
 * ## Why copy rather than fetch
 *
 * Pyodide's documented quickstart loads the runtime from a CDN. Same objection as
 * MediaPipe: a candidate mid-problem cannot depend on a third-party host being
 * up, and a demo that fails because jsdelivr was slow is a demo that failed.
 *
 * Unlike the MediaPipe model, none of this needs fetching at all — every file
 * ships inside the pinned `pyodide` package, so this step needs no network and
 * the runtime can never drift from the loader that imports it. That also means
 * there is no digest to pin here: the lockfile already pins it.
 *
 * ## What `loadPyodide({ indexURL })` actually needs
 *
 * The loader is imported through the bundler, but it fetches these four at
 * runtime from `indexURL`. Miss one and initialisation fails with a 404 that
 * looks like a WASM error.
 */
import { copyFileSync, existsSync, mkdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const SOURCE = join(ROOT, "node_modules", "pyodide");
const TARGET = join(ROOT, "public", "pyodide");

const RUNTIME_FILES = [
  "pyodide.asm.wasm",
  "pyodide.asm.mjs",
  "python_stdlib.zip",
  "pyodide-lock.json",
];

console.log("pyodide runtime");

if (!existsSync(SOURCE)) {
  console.warn("  ! pyodide is not installed -- run npm install first.");
  writeFileSync(join(ROOT, "public", "pyodide-manifest.json"), JSON.stringify({ ready: false }) + "\n");
  process.exit(0);
}

mkdirSync(TARGET, { recursive: true });

let copied = 0;
let missing = 0;
for (const name of RUNTIME_FILES) {
  const from = join(SOURCE, name);
  const to = join(TARGET, name);
  if (!existsSync(from)) {
    console.warn(`  ! ${name} is not in the installed package`);
    missing += 1;
    continue;
  }
  // Compared by size, not mtime: npm rewrites mtimes on reinstall, and a
  // half-written copy is the case that actually matters.
  if (existsSync(to) && statSync(to).size === statSync(from).size) continue;
  copyFileSync(from, to);
  copied += 1;
}

const ready = missing === 0;
const version = JSON.parse(
  (await import("node:fs")).readFileSync(join(SOURCE, "package.json"), "utf8"),
).version;

writeFileSync(
  join(TARGET, "manifest.json"),
  JSON.stringify({ ready, indexUrl: "/pyodide/", version, files: RUNTIME_FILES }, null, 2) + "\n",
);

if (!ready) {
  console.warn("\n  DSA solutions cannot be run until these files are present.\n");
} else {
  console.log(copied === 0 ? `  = runtime already in place (pyodide ${version})` : `  + copied ${copied} file(s) (pyodide ${version})`);
  console.log("  ready\n");
}

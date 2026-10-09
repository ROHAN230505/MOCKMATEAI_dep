import { useCallback, useRef, useState } from "react";
import type { CaseOutcome, RunSummary, TestCase } from "../lib/dsaGrading";
import { deepEqual, summarise } from "../lib/dsaGrading";

/**
 * Runs a candidate's Python in their own browser (Phase 7).
 *
 * ## Why in the browser
 *
 * Executing untrusted code server-side means sandboxing, resource limits and a
 * container per submission. Running it in the candidate's own tab removes that
 * surface entirely: the only machine at risk is theirs, and Pyodide's WASM
 * sandbox has no filesystem or network to reach anyway.
 *
 * It costs one thing, stated rather than hidden: the hidden test cases must reach
 * the client to be run against, so a determined candidate can read them from
 * devtools. Acceptable for practice; it would not be for an assessment with
 * stakes.
 *
 * ## Self-hosted, pinned
 *
 * Pyodide's quickstart loads from a CDN. This loads from `/pyodide/`, copied out
 * of the pinned npm package by `scripts/setup-pyodide.mjs` -- same reasoning as
 * the MediaPipe assets. Nothing is fetched from a third party at runtime.
 *
 * ## What stops a runaway loop
 *
 * A `while True:` would hang the tab, and Pyodide runs on the main thread here,
 * so no JavaScript timer can interrupt it. Instead the candidate's function runs
 * under a Python-side instruction counter (`sys.settrace`) that raises once it
 * has executed too many lines -- a budget rather than a clock, which makes the
 * cutoff deterministic instead of dependent on how fast the machine is.
 */

const MANIFEST_URL = "/pyodide/manifest.json";

/**
 * Line budget per test case. Generous next to anything in the bank -- the
 * heaviest reference solution is a union-find over a few hundred nodes -- and
 * small enough that an infinite loop stops in well under a second.
 */
const LINE_BUDGET = 2_000_000;

export type RunnerStatus =
  | { state: "idle" }
  | { state: "loading" }
  | { state: "ready" }
  | { state: "running" }
  | { state: "unavailable"; reason: string };

/**
 * Python that installs the budget and calls the candidate's function.
 *
 * Kept in Python rather than driven from JavaScript so the trace hook is
 * installed inside the same interpreter the candidate's code runs in.
 */
const HARNESS = [
  "import json, sys",
  "",
  "class _Budget(Exception):",
  "    pass",
  "",
  "def _mm_run(_fn, _args, _budget):",
  "    _count = [0]",
  "",
  "    def _trace(frame, event, arg):",
  "        if event == 'line':",
  "            _count[0] += 1",
  "            if _count[0] > _budget:",
  "                raise _Budget()",
  "        return _trace",
  "",
  "    sys.settrace(_trace)",
  "    try:",
  "        return _fn(*_args)",
  "    finally:",
  "        sys.settrace(None)",
].join("\n");

interface PyodideLike {
  runPython: (code: string) => unknown;
  globals: { get: (name: string) => unknown; set: (name: string, value: unknown) => void };
  toPy: (value: unknown) => unknown;
}

export function useDsaRunner() {
  const [status, setStatus] = useState<RunnerStatus>({ state: "idle" });
  const pyodideRef = useRef<PyodideLike | null>(null);
  const loadingRef = useRef<Promise<PyodideLike | null> | null>(null);

  /**
   * Loads Pyodide once, on first run rather than on mount.
   *
   * 13MB of WASM is not something to download because someone opened the problem
   * list. It is fetched the first time they actually press Run.
   */
  const ensureLoaded = useCallback(async (): Promise<PyodideLike | null> => {
    if (pyodideRef.current) return pyodideRef.current;
    if (loadingRef.current) return loadingRef.current;

    loadingRef.current = (async () => {
      setStatus({ state: "loading" });
      try {
        const response = await fetch(MANIFEST_URL, { cache: "no-store" });
        if (!response.ok) throw new Error("runtime not installed");
        const manifest = (await response.json()) as { ready: boolean; indexUrl: string };
        if (!manifest.ready) throw new Error("runtime not installed");

        const { loadPyodide } = await import("pyodide");
        const pyodide = (await loadPyodide({
          indexURL: manifest.indexUrl,
          // `packageBaseUrl` is set as well, and deliberately.
          //
          // `indexURL` governs the runtime; `packageBaseUrl` governs where extra
          // Python packages would be fetched from, and it defaults to jsdelivr.
          // Nothing here calls `loadPackage` -- the harness uses only `json` and
          // `sys`, which ship inside the local `python_stdlib.zip` -- so the
          // default is never reached today. Pinning it anyway means the no-CDN
          // guarantee holds for whoever adds a package later: they get a loud
          // 404 from our own origin instead of a silent third-party fetch.
          packageBaseUrl: manifest.indexUrl,
        })) as unknown as PyodideLike;
        pyodide.runPython(HARNESS);
        pyodideRef.current = pyodide;
        setStatus({ state: "ready" });
        return pyodide;
      } catch (error) {
        setStatus({
          state: "unavailable",
          reason:
            error instanceof Error && error.message === "runtime not installed"
              ? "The Python runtime isn't installed. Run `npm run setup:pyodide` in frontend/."
              : "The Python runtime failed to load, so solutions can't be run in this browser.",
        });
        loadingRef.current = null;
        return null;
      }
    })();

    return loadingRef.current;
  }, []);

  const run = useCallback(
    async (
      code: string,
      functionName: string,
      cases: { testCase: TestCase; hidden: boolean }[],
    ): Promise<RunSummary | null> => {
      const pyodide = await ensureLoaded();
      if (!pyodide) return null;

      setStatus({ state: "running" });
      const outcomes: CaseOutcome[] = [];

      const errorForEveryCase = (message: string): RunSummary =>
        summarise(
          cases.map((entry, position) => ({
            kind: "error" as const,
            index: indexWithin(cases, position),
            hidden: entry.hidden,
            message,
          })),
        );

      try {
        // The candidate's code is defined once, not per case.
        try {
          pyodide.runPython(code);
        } catch (error) {
          // A syntax error or a failure at import time is one problem, not one
          // per test case -- reported against every case rather than pretending
          // each was individually run and individually broken.
          return errorForEveryCase(firstLine(String((error as Error)?.message ?? error)));
        }

        const fn = pyodide.globals.get(functionName);
        if (typeof fn !== "function") {
          return errorForEveryCase(`no function named ${functionName}`);
        }

        for (let position = 0; position < cases.length; position += 1) {
          const { testCase, hidden } = cases[position];
          const index = indexWithin(cases, position);
          const startedAt = performance.now();

          pyodide.globals.set("_mm_args", pyodide.toPy(testCase.args));
          pyodide.globals.set("_mm_fn", fn);
          pyodide.globals.set("_mm_budget", LINE_BUDGET);

          try {
            // JSON is the boundary: it turns the Python result into plain
            // JavaScript values, so nothing below has to reason about Pyodide's
            // proxy objects and `deepEqual` compares ordinary arrays and numbers.
            const raw = pyodide.runPython(
              "json.dumps(_mm_run(_mm_fn, list(_mm_args), _mm_budget), default=str)",
            );
            const actual = JSON.parse(String(raw));
            const durationMs = performance.now() - startedAt;

            outcomes.push(
              deepEqual(actual, testCase.expected)
                ? { kind: "passed", index, hidden, durationMs }
                : { kind: "failed", index, hidden, durationMs, actual },
            );
          } catch (error) {
            const message = String((error as Error)?.message ?? error);
            outcomes.push(
              message.includes("_Budget")
                ? { kind: "timeout", index, hidden }
                : { kind: "error", index, hidden, message: firstLine(message) },
            );
          }
        }
      } finally {
        setStatus({ state: "ready" });
      }

      return summarise(outcomes);
    },
    [ensureLoaded],
  );

  return { status, run };
}

/** Sample and hidden cases are numbered separately, so each reads from 1. */
function indexWithin(cases: { hidden: boolean }[], position: number): number {
  const hidden = cases[position].hidden;
  let index = 0;
  for (let i = 0; i < position; i += 1) if (cases[i].hidden === hidden) index += 1;
  return index;
}

/**
 * Python tracebacks arrive as a wall of frames from inside the harness. The
 * candidate needs the exception line, not our plumbing.
 */
function firstLine(message: string): string {
  const lines = message.split("\n").map((line) => line.trim()).filter(Boolean);
  const exception = [...lines]
    .reverse()
    .find((line) => /^[A-Za-z_]+(Error|Exception|Warning)\b/.test(line));
  return (exception ?? lines[lines.length - 1] ?? "an error in your code").slice(0, 200);
}

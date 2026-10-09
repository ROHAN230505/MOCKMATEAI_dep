import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { ShareServerState } from "../../lib/codePanelShare";
import { applyShareAction, nextShareAction } from "../../lib/codePanelShare";

/**
 * Section 4.8B's in-interview scratch panel: a plain code editor and a
 * whiteboard, side by side with the conversation.
 *
 * Only the code tab travels. The server stores `code_panel_snapshot` as text and
 * the interviewer is a language model, so a drawing has nothing to be read as --
 * telling the candidate their sketch was "shared" would be claiming a channel
 * that does not exist. The whiteboard is therefore labelled as their own space,
 * and the share toggle is scoped to the code tab in the wording as well as in
 * the wiring.
 */

/** Section 9.9's debounce: quiet for this long, then the snapshot goes up. */
const IDLE_SEND_MS = 1500;

/** Matches the server's per-snapshot cap so the counter cannot promise more than is stored. */
const MAX_CHARS = 20_000;

type Tab = "code" | "whiteboard";

// The caller hides this panel rather than unmounting it, so a candidate who
// closes it does not lose the code and the sketch it exists to hold.
export interface CodePanelProps {
  /** Sends Section 9.9's `code_panel_update`. Debounced by this component. */
  onShare: (code: string, shared: boolean) => void;
  onClose: () => void;
}

export function CodePanel({ onShare, onClose }: CodePanelProps) {
  const [tab, setTab] = useState<Tab>("code");
  const [code, setCode] = useState("");
  const [shared, setShared] = useState(true);
  const [sentCode, setSentCode] = useState<string | null>(null);

  const shareRef = useRef(onShare);
  shareRef.current = onShare;

  // What to send is decided in `lib/codePanelShare`; this effect only supplies the
  // timing -- immediate for a clear, one idle window for a snapshot.
  const server = useRef<ShareServerState>({ shared: true, sent: null });
  useEffect(() => {
    const action = nextShareAction(server.current, { shared, code });
    if (action.kind === "none") return;
    if (action.kind === "clear") {
      shareRef.current("", false);
      server.current = applyShareAction(server.current, action);
      setSentCode(null);
      return;
    }
    const id = window.setTimeout(() => {
      shareRef.current(action.code, true);
      server.current = applyShareAction(server.current, action);
      setSentCode(action.code);
    }, IDLE_SEND_MS);
    return () => window.clearTimeout(id);
  }, [code, shared]);

  const lineCount = useMemo(() => code.split(/\r?\n/).length, [code]);

  const handleKeyDown = useCallback((event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Tab indents instead of leaving the editor. Shift+Tab still escapes it, so
    // the panel does not become a keyboard trap.
    if (event.key !== "Tab" || event.shiftKey) return;
    event.preventDefault();
    const el = event.currentTarget;
    const { selectionStart: start, selectionEnd: end, value } = el;
    const next = value.slice(0, start) + "  " + value.slice(end);
    setCode(next.slice(0, MAX_CHARS));
    window.requestAnimationFrame(() => {
      el.selectionStart = el.selectionEnd = start + 2;
    });
  }, []);

  return (
    <aside
      aria-label="Code and whiteboard panel"
      className="flex h-full min-h-0 w-full flex-col rounded-card border border-border bg-surface"
    >
      <div className="flex shrink-0 items-center gap-1 border-b border-border px-2 py-2">
        <TabButton active={tab === "code"} onClick={() => setTab("code")}>
          Code
        </TabButton>
        <TabButton active={tab === "whiteboard"} onClick={() => setTab("whiteboard")}>
          Whiteboard
        </TabButton>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close panel"
          title="Close panel"
          className="ml-auto rounded-control p-1.5 text-text-subtle transition-colors hover:bg-surface-raised hover:text-text"
        >
          <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
            <path strokeLinecap="round" d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      </div>

      <div className={tab === "code" ? "flex min-h-0 flex-1 flex-col" : "hidden"}>
        <div className="flex min-h-0 flex-1 overflow-hidden">
          <div
            aria-hidden="true"
            className="tnum shrink-0 overflow-hidden bg-surface-raised px-2 py-3 text-right font-mono text-xs leading-[1.6] text-text-subtle select-none"
          >
            {Array.from({ length: lineCount }, (_, i) => (
              <div key={i}>{i + 1}</div>
            ))}
          </div>
          <label htmlFor="interview-code" className="sr-only">
            Code scratchpad
          </label>
          <textarea
            id="interview-code"
            value={code}
            spellCheck={false}
            autoComplete="off"
            autoCorrect="off"
            autoCapitalize="off"
            onChange={(event) => setCode(event.target.value.slice(0, MAX_CHARS))}
            onKeyDown={handleKeyDown}
            placeholder={"# Sketch your approach here.\n# The interviewer can read this while you talk."}
            className="min-h-0 flex-1 resize-none bg-transparent px-3 py-3 font-mono text-xs leading-[1.6] text-text placeholder:text-text-subtle focus:outline-none"
          />
        </div>
        <ShareBar
          shared={shared}
          onToggle={() => setShared((on) => !on)}
          code={code}
          sentCode={sentCode}
        />
      </div>
      <Whiteboard hidden={tab !== "whiteboard"} />
    </aside>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={`rounded-control px-3 py-1.5 text-xs font-medium transition-colors ${
        active ? "bg-surface-raised text-text" : "text-text-muted hover:text-text"
      }`}
    >
      {children}
    </button>
  );
}

/**
 * The share control, and an honest report of what has actually reached the
 * server. "Shared" alone would read as live mirroring; the panel sends on a
 * pause, so the state in between is named for what it is.
 */
function ShareBar({
  shared,
  onToggle,
  code,
  sentCode,
}: {
  shared: boolean;
  onToggle: () => void;
  code: string;
  /** The snapshot the server is holding, or null when it is holding none. */
  sentCode: string | null;
}) {
  const chars = code.length;
  const pending = shared && code !== (sentCode ?? "");
  return (
    <div className="flex shrink-0 flex-wrap items-center justify-between gap-2 border-t border-border px-3 py-2">
      <label className="flex cursor-pointer items-center gap-2 text-xs text-text-muted">
        <input
          type="checkbox"
          checked={shared}
          onChange={onToggle}
          className="h-3.5 w-3.5 rounded-[0.25rem] border-border accent-accent"
        />
        Share with interviewer
      </label>
      <span className="tnum text-[0.6875rem] text-text-subtle">
        {!shared
          ? "Private — not sent"
          : chars === 0
            ? "Nothing to send yet"
            : pending
              ? "Sending…"
              : "Sent"}
        {chars > 0 && ` · ${chars.toLocaleString()} / ${MAX_CHARS.toLocaleString()}`}
      </span>
    </div>
  );
}

/**
 * Pen colours, named as tokens rather than as hexes.
 *
 * They have to resolve at stroke time, not at module load: the canvas sits on
 * `bg-bg`, which is near-black in the dark theme and near-white in the light
 * one, so a fixed ink is invisible in one of them. (It was: the previous
 * near-white default drew white-on-white for every light-theme user.)
 */
const INK = [
  { name: "Ink", token: "--color-text", fallback: "#e9bcb9" },
  { name: "Amber", token: "--color-accent", fallback: "#ed9e58" },
  { name: "Rose", token: "--color-danger", fallback: "#e58697" },
];

function readInk(token: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const value = getComputedStyle(document.documentElement).getPropertyValue(token).trim();
  return value || fallback;
}

/**
 * A pointer-driven sketch surface. Deliberately local: nothing here is uploaded,
 * and the footer says so rather than letting the share toggle one tab over be
 * read as covering this one too.
 */
function Whiteboard({ hidden }: { hidden: boolean }) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const drawing = useRef(false);
  const [ink, setInk] = useState(INK[0]);
  const [erasing, setErasing] = useState(false);
  const inkRef = useRef(ink);
  inkRef.current = ink;
  const erasingRef = useRef(erasing);
  erasingRef.current = erasing;

  // Canvas pixels do not survive a resize, so the strokes are re-blitted from a
  // snapshot taken before the backing store is replaced.
  useEffect(() => {
    const canvas = canvasRef.current;
    const parent = canvas?.parentElement;
    if (!canvas || !parent) return;
    const resize = () => {
      const dpr = window.devicePixelRatio || 1;
      const { width, height } = parent.getBoundingClientRect();
      if (width === 0 || height === 0) return;
      const previous =
        canvas.width > 0 && canvas.height > 0
          ? (() => {
              const copy = document.createElement("canvas");
              copy.width = canvas.width;
              copy.height = canvas.height;
              copy.getContext("2d")?.drawImage(canvas, 0, 0);
              return copy;
            })()
          : null;
      canvas.width = Math.round(width * dpr);
      canvas.height = Math.round(height * dpr);
      const ctx = canvas.getContext("2d");
      if (!ctx) return;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      if (previous) ctx.drawImage(previous, 0, 0, canvas.width, canvas.height);
    };
    resize();
    const observer = new ResizeObserver(resize);
    observer.observe(parent);
    return () => observer.disconnect();
  }, []);

  const pointAt = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const canvas = event.currentTarget;
    const rect = canvas.getBoundingClientRect();
    return {
      x: ((event.clientX - rect.left) / rect.width) * canvas.width,
      y: ((event.clientY - rect.top) / rect.height) * canvas.height,
    };
  };

  const start = (event: React.PointerEvent<HTMLCanvasElement>) => {
    const ctx = event.currentTarget.getContext("2d");
    if (!ctx) return;
    event.currentTarget.setPointerCapture(event.pointerId);
    drawing.current = true;
    const dpr = window.devicePixelRatio || 1;
    ctx.globalCompositeOperation = erasingRef.current ? "destination-out" : "source-over";
    ctx.strokeStyle = readInk(inkRef.current.token, inkRef.current.fallback);
    ctx.lineWidth = (erasingRef.current ? 18 : 2.5) * dpr;
    const { x, y } = pointAt(event);
    ctx.beginPath();
    ctx.moveTo(x, y);
  };

  const move = (event: React.PointerEvent<HTMLCanvasElement>) => {
    if (!drawing.current) return;
    const ctx = event.currentTarget.getContext("2d");
    if (!ctx) return;
    const { x, y } = pointAt(event);
    ctx.lineTo(x, y);
    ctx.stroke();
  };

  const stop = () => {
    drawing.current = false;
  };

  const clear = () => {
    const canvas = canvasRef.current;
    const ctx = canvas?.getContext("2d");
    if (!canvas || !ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
  };

  return (
    <div className={hidden ? "hidden" : "flex min-h-0 flex-1 flex-col"}>
      <div className="relative min-h-0 flex-1 bg-bg">
        <canvas
          ref={canvasRef}
          onPointerDown={start}
          onPointerMove={move}
          onPointerUp={stop}
          onPointerCancel={stop}
          onPointerLeave={stop}
          aria-label="Whiteboard sketch area"
          className="absolute inset-0 h-full w-full touch-none"
        />
      </div>
      <div className="flex shrink-0 flex-wrap items-center gap-2 border-t border-border px-3 py-2">
        {INK.map((swatch) => (
          <button
            key={ink.token}
            type="button"
            aria-label={swatch.name}
            aria-pressed={!erasing && ink.token === swatch.token}
            title={swatch.name}
            onClick={() => {
              setInk(swatch);
              setErasing(false);
            }}
            className={`h-5 w-5 rounded-full border-2 transition-transform ${
              !erasing && ink.token === swatch.token ? "border-text scale-110" : "border-transparent"
            }`}
            style={{ backgroundColor: `var(${swatch.token})` }}
          />
        ))}
        <button
          type="button"
          aria-pressed={erasing}
          onClick={() => setErasing((on) => !on)}
          className={`rounded-control px-2.5 py-1 text-xs font-medium transition-colors ${
            erasing ? "bg-surface-raised text-text" : "text-text-muted hover:text-text"
          }`}
        >
          Eraser
        </button>
        <button
          type="button"
          onClick={clear}
          className="rounded-control px-2.5 py-1 text-xs font-medium text-text-muted transition-colors hover:text-text"
        >
          Clear
        </button>
        <span className="ml-auto text-[0.6875rem] text-text-subtle">Yours only — not sent</span>
      </div>
    </div>
  );
}

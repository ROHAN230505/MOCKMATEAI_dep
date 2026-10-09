import { AnimatePresence, motion } from "framer-motion";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { useThemeStore } from "../../store/themeStore";
import { sectionsFor, type NavItem } from "./navigation";

/**
 * Command palette — Cmd/Ctrl+K.
 *
 * The one addition here that changes how the product is *used* rather than how
 * it looks. A rail is a menu you read; a palette is a destination you name.
 * Once someone knows where they are going, typing three letters beats moving a
 * pointer across the screen, and it is the interaction that most reliably
 * separates a tool from a website.
 *
 * Matching is a subsequence test, not a substring one, so "mi" finds Mock
 * Interview and "dsh" finds Dashboard. Substring matching is what makes a
 * palette feel broken: people type initials, and initials are rarely
 * contiguous.
 *
 * Escape closes, arrows move, Enter runs. Opening starts empty on purpose — a
 * palette that restores the last query makes the common case begin with a
 * clear.
 */
/** Lets a visible control open the palette without forging a keystroke. */
export const PALETTE_EVENT = "mockmateai:palette";

interface Action {
  id: string;
  label: string;
  description: string;
  group: string;
  hint?: string;
  run: () => void;
}

/** True when every character of `query` appears in `text`, in order. */
function subsequence(text: string, query: string): boolean {
  let index = 0;
  for (const character of query) {
    index = text.indexOf(character, index);
    if (index === -1) return false;
    index += 1;
  }
  return true;
}

export function CommandPalette() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const navigate = useNavigate();
  const role = useAuthStore((state) => state.user?.role);
  const { resolved, setMode } = useThemeStore();

  const actions = useMemo<Action[]>(() => {
    const go = (item: NavItem, group: string): Action => ({
      id: `go:${item.to}`,
      label: item.label,
      description: item.description,
      group,
      hint: item.hint,
      run: () => navigate(item.to, { viewTransition: true }),
    });
    const navActions = sectionsFor(role).flatMap((section) =>
      section.items.map((item) => go(item, section.heading)),
    );
    return [
      ...navActions,
      {
        id: "theme:flip",
        label: resolved === "dark" ? "Switch to light" : "Switch to dark",
        description: "Both themes are designed separately, not inverted",
        group: "Preferences",
        run: () => setMode(resolved === "dark" ? "light" : "dark"),
      },
      {
        id: "theme:system",
        label: "Follow system theme",
        description: "Match whatever the operating system is set to",
        group: "Preferences",
        run: () => setMode("system"),
      },
    ];
  }, [role, navigate, resolved, setMode]);

  const results = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return actions;
    return actions.filter(
      (action) =>
        subsequence(action.label.toLowerCase(), needle) ||
        subsequence(action.description.toLowerCase(), needle),
    );
  }, [actions, query]);

  const close = useCallback(() => {
    setOpen(false);
    setQuery("");
    setCursor(0);
  }, []);

  const run = useCallback(
    (action: Action | undefined) => {
      if (!action) return;
      close();
      action.run();
    },
    [close],
  );

  // The shortcut, plus the `G`-then-key go-to chords. Both are suppressed while
  // the user is typing: a nav shortcut that fires inside a code editor would
  // navigate away mid-answer.
  useEffect(() => {
    let awaitingGo = false;
    let goTimer = 0;

    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      const typing =
        !!target &&
        (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable);

      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k") {
        event.preventDefault();
        setOpen((current) => !current);
        return;
      }
      if (typing || event.metaKey || event.ctrlKey || event.altKey) return;

      if (awaitingGo) {
        awaitingGo = false;
        window.clearTimeout(goTimer);
        const match = sectionsFor(role)
          .flatMap((section) => section.items)
          .find((item) => item.hint === event.key.toLowerCase());
        if (match) {
          event.preventDefault();
          navigate(match.to, { viewTransition: true });
        }
        return;
      }
      if (event.key.toLowerCase() === "g") {
        awaitingGo = true;
        // A chord that waits forever turns the next keypress anywhere into a
        // navigation. One second is long enough to be deliberate.
        goTimer = window.setTimeout(() => {
          awaitingGo = false;
        }, 1000);
      }
    };

    const onRequest = () => setOpen((current) => !current);
    window.addEventListener(PALETTE_EVENT, onRequest);
    window.addEventListener("keydown", onKey);
    return () => {
      window.removeEventListener(PALETTE_EVENT, onRequest);
      window.removeEventListener("keydown", onKey);
      window.clearTimeout(goTimer);
    };
  }, [navigate, role]);

  useEffect(() => {
    if (open) inputRef.current?.focus();
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [query]);

  // Keeps the highlighted row visible when arrowing past the fold.
  useEffect(() => {
    const active = listRef.current?.children[cursor] as HTMLElement | undefined;
    active?.scrollIntoView({ block: "nearest" });
  }, [cursor]);

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          transition={{ duration: 0.12 }}
          className="fixed inset-0 z-[100] flex items-start justify-center bg-black/45 px-4 pt-[12vh]"
          onClick={close}
        >
          <motion.div
            initial={{ opacity: 0, y: -8 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -8 }}
            transition={{ duration: 0.16, ease: [0.16, 1, 0.3, 1] }}
            role="dialog"
            aria-modal="true"
            aria-label="Command palette"
            onClick={(event) => event.stopPropagation()}
            className="w-full max-w-lg overflow-hidden rounded-card border border-border-strong bg-bg-elevated shadow-[var(--shadow-lg)]"
          >
            <div className="flex items-center gap-3 px-4 py-3.5">
              <svg viewBox="0 0 24 24" className="h-4 w-4 shrink-0 text-text-subtle" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                <circle cx="11" cy="11" r="7" />
                <path strokeLinecap="round" d="m20 20-3.5-3.5" />
              </svg>
              <input
                ref={inputRef}
                value={query}
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Escape") close();
                  if (event.key === "ArrowDown") {
                    event.preventDefault();
                    setCursor((c) => Math.min(c + 1, results.length - 1));
                  }
                  if (event.key === "ArrowUp") {
                    event.preventDefault();
                    setCursor((c) => Math.max(c - 1, 0));
                  }
                  if (event.key === "Enter") {
                    event.preventDefault();
                    run(results[cursor]);
                  }
                }}
                placeholder="Go to a page, or change a preference…"
                aria-label="Search commands"
                className="min-w-0 flex-1 bg-transparent text-body text-text placeholder:text-text-subtle focus:outline-none"
              />
              <kbd className="shrink-0 rounded-[0.25rem] border border-border px-1.5 py-0.5 text-micro text-text-subtle">
                esc
              </kbd>
            </div>

            <div className="hairline h-px w-full" />

            {results.length === 0 ? (
              <p className="px-4 py-8 text-center text-small text-text-muted">
                Nothing matches that.
              </p>
            ) : (
              <ul ref={listRef} className="max-h-[19rem] overflow-y-auto py-1.5">
                {results.map((action, index) => (
                  <li key={action.id}>
                    <button
                      type="button"
                      onMouseMove={() => setCursor(index)}
                      onClick={() => run(action)}
                      className={`flex w-full items-center gap-3 px-4 py-2 text-left transition-colors duration-100 ${
                        index === cursor ? "bg-surface-raised" : ""
                      }`}
                    >
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-small font-medium text-text">{action.label}</span>
                        <span className="block truncate text-micro text-text-subtle">{action.description}</span>
                      </span>
                      {action.hint && (
                        <kbd className="shrink-0 rounded-[0.25rem] border border-border px-1.5 py-0.5 font-mono text-micro text-text-subtle">
                          g {action.hint}
                        </kbd>
                      )}
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}

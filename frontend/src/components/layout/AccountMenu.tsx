import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useAuthStore } from "../../store/authStore";
import { useThemeStore } from "../../store/themeStore";
import { logout as logoutApi } from "../../services/authApi";

/**
 * The account control at the foot of the rail.
 *
 * Replaces a block that showed a name, an address and a permanently visible
 * "Log out" row. Two problems with that: logging out is the least frequent
 * thing anyone does here and it had the most prominent position in the rail,
 * and an email address sat on screen all day for anyone walking past — which
 * matters more than usual in a product people demo and screen-share.
 *
 * So the address is behind a deliberate action, and the destructive item is at
 * the bottom of a menu, separated by a rule, where it cannot be hit on the way
 * to something else.
 */
const THEMES = [
  { mode: "light" as const, label: "Light" },
  { mode: "dark" as const, label: "Dark" },
  { mode: "system" as const, label: "System" },
];

export function AccountMenu({ collapsed }: { collapsed: boolean }) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();
  const { user, refreshToken, clearSession } = useAuthStore();
  const { mode, setMode } = useThemeStore();

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  async function handleLogout() {
    if (refreshToken) {
      try {
        await logoutApi(refreshToken);
      } catch {
        // Section 5.6: best-effort — the session is cleared client-side
        // regardless, so a flaky network never traps the user mid-logout.
      }
    }
    clearSession();
    navigate("/login");
  }

  if (!user) return null;

  const initials =
    user.name
      ?.split(" ")
      .filter(Boolean)
      .slice(0, 2)
      .map((part) => part[0]?.toUpperCase())
      .join("") ?? "";

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        title={collapsed ? user.name : undefined}
        className={`flex w-full items-center gap-2.5 rounded-control py-1.5 text-left transition-colors duration-150 hover:bg-surface-raised ${
          collapsed ? "justify-center px-0" : "px-2"
        }`}
      >
        <span
          aria-hidden="true"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-accent-soft text-micro font-semibold text-accent"
        >
          {initials}
        </span>
        {!collapsed && (
          <>
            <span className="min-w-0 flex-1 truncate text-small font-medium text-text">{user.name}</span>
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5 shrink-0 text-text-subtle" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="m8 9 4-4 4 4M8 15l4 4 4-4" />
            </svg>
          </>
        )}
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 6 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: 6 }}
            transition={{ duration: 0.14, ease: [0.16, 1, 0.3, 1] }}
            role="menu"
            className="absolute bottom-full left-0 z-50 mb-2 w-[15rem] overflow-hidden rounded-card border border-border-strong bg-bg-elevated shadow-[var(--shadow-lg)]"
          >
            <div className="px-3 py-2.5">
              <p className="truncate text-small font-medium text-text">{user.name}</p>
              <p className="truncate text-micro text-text-subtle" title={user.email}>
                {user.email}
              </p>
            </div>

            <div className="hairline h-px w-full" />

            <div className="px-3 py-2.5">
              <p className="mb-1.5 text-micro font-medium tracking-[0.1em] text-text-subtle uppercase">
                Appearance
              </p>
              <div className="flex gap-1" role="radiogroup" aria-label="Theme">
                {THEMES.map((option) => (
                  <button
                    key={option.mode}
                    type="button"
                    role="radio"
                    aria-checked={mode === option.mode}
                    onClick={() => setMode(option.mode)}
                    className={`flex-1 rounded-control py-1 text-micro font-medium transition-colors duration-150 ${
                      mode === option.mode
                        ? "bg-accent text-accent-contrast"
                        : "text-text-muted hover:bg-surface-raised hover:text-text"
                    }`}
                  >
                    {option.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="hairline h-px w-full" />

            <button
              type="button"
              role="menuitem"
              onClick={handleLogout}
              className="flex w-full items-center gap-2.5 px-3 py-2.5 text-left text-small text-text-muted transition-colors duration-150 hover:bg-danger/10 hover:text-danger"
            >
              <svg viewBox="0 0 24 24" className="h-[0.9375rem] w-[0.9375rem]" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4M16 17l5-5-5-5M21 12H9" />
              </svg>
              Log out
            </button>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

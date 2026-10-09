import { motion, useReducedMotion } from "framer-motion";
import { useThemeStore } from "../store/themeStore";

/**
 * The theme switch: a physical-feeling track with a travelling knob that
 * carries the sun/moon glyph with it.
 *
 * One knob crossfading two icons (rather than two separate icons fading in
 * place) is what makes the control read as a switch being thrown instead of a
 * button changing state. Under prefers-reduced-motion the travel is instant and
 * only the icon swaps.
 */
export function ThemeToggle({ className = "" }: { className?: string }) {
  const resolved = useThemeStore((s) => s.resolved);
  const toggle = useThemeStore((s) => s.toggle);
  const prefersReducedMotion = useReducedMotion();
  const isDark = resolved === "dark";

  return (
    <button
      type="button"
      onClick={toggle}
      role="switch"
      aria-checked={isDark}
      aria-label={isDark ? "Switch to light theme" : "Switch to dark theme"}
      title={isDark ? "Switch to light theme" : "Switch to dark theme"}
      className={`relative inline-flex h-7 w-[3.25rem] shrink-0 items-center rounded-pill border border-border bg-surface-raised px-0.5 transition-colors duration-150 hover:border-border-strong ${className}`}
    >
      {/* Static glyphs sit under the knob so the track always shows both
          destinations — the knob covers the current one. */}
      <span className="pointer-events-none absolute inset-0 flex items-center justify-between px-1.5 text-text-subtle">
        <SunIcon className="h-3 w-3" />
        <MoonIcon className="h-3 w-3" />
      </span>

      <motion.span
        // Animated on `x` explicitly rather than via `layout`, so the knob's
        // travel is a single spring the icon crossfade can be timed against.
        animate={{ x: isDark ? 24 : 0 }}
        transition={
          prefersReducedMotion
            ? { duration: 0 }
            : { type: "spring", stiffness: 520, damping: 32, mass: 0.7 }
        }
        className="relative z-10 flex h-6 w-6 items-center justify-center rounded-full bg-surface shadow-sm"
        style={{
          backgroundImage: isDark
            ? "linear-gradient(140deg, var(--color-surface-raised), var(--color-surface))"
            : "linear-gradient(140deg, var(--color-bg-elevated), var(--color-surface-raised))",
        }}
      >
        <motion.span
          key={isDark ? "moon" : "sun"}
          initial={prefersReducedMotion ? false : { opacity: 0, rotate: -60, scale: 0.6 }}
          animate={{ opacity: 1, rotate: 0, scale: 1 }}
          transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
          className="text-accent"
        >
          {isDark ? <MoonIcon className="h-3.5 w-3.5" /> : <SunIcon className="h-3.5 w-3.5" />}
        </motion.span>
      </motion.span>
    </button>
  );
}

function SunIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path
        strokeLinecap="round"
        d="M12 2v2m0 16v2M2 12h2m16 0h2M4.9 4.9l1.4 1.4m11.4 11.4 1.4 1.4M19.1 4.9l-1.4 1.4M6.3 17.7l-1.4 1.4"
      />
    </svg>
  );
}

function MoonIcon({ className = "" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M21 12.8A8.5 8.5 0 1 1 11.2 3a6.5 6.5 0 0 0 9.8 9.8Z" />
    </svg>
  );
}

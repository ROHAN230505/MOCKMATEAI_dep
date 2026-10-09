import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

interface SelectCardProps {
  selected: boolean;
  title: string;
  description?: string;
  /** Short trailing label, e.g. a "Recommended" pill. */
  badge?: ReactNode;
  disabled?: boolean;
  onClick: () => void;
}

/**
 * Shared single-select "card" control (Onboarding's experience/mode steps,
 * Interview Setup's type/duration).
 *
 * Selection is carried by three signals at once — accent border, tinted
 * surface, and a filled check — because colour alone isn't sufficient
 * (Section 17). `aria-pressed` gives assistive tech the same state.
 */
export function SelectCard({ selected, title, description, badge, disabled = false, onClick }: SelectCardProps) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-pressed={selected}
      whileHover={disabled ? undefined : { y: prefersReducedMotion ? 0 : -2 }}
      whileTap={disabled ? undefined : { scale: prefersReducedMotion ? 1 : 0.99, y: 0 }}
      transition={{ duration: 0.16, ease: [0.22, 1, 0.36, 1] }}
      className={`relative w-full overflow-hidden rounded-control border px-4 py-3.5 text-left transition-colors duration-200 ${
        disabled
          ? "cursor-not-allowed border-border bg-surface-sunken opacity-55"
          : selected
            ? "border-accent bg-accent-soft shadow-[var(--shadow-glow)]"
            : "border-border bg-surface hover:border-border-strong hover:bg-surface-raised"
      }`}
    >
      <span className="flex items-start justify-between gap-3">
        <span className="min-w-0">
          <span className={`block text-sm font-medium ${selected ? "text-accent" : "text-text"}`}>{title}</span>
          {description && <span className="mt-1 block text-xs leading-relaxed text-text-muted">{description}</span>}
        </span>

        <span className="flex shrink-0 items-center gap-2">
          {badge}
          <span
            aria-hidden="true"
            className={`flex h-[1.15rem] w-[1.15rem] items-center justify-center rounded-full border transition-all duration-200 ${
              selected ? "border-accent bg-accent" : "border-border-strong bg-transparent"
            }`}
          >
            <svg
              viewBox="0 0 16 16"
              className={`h-2.5 w-2.5 text-accent-contrast transition-all duration-200 ${
                selected ? "scale-100 opacity-100" : "scale-50 opacity-0"
              }`}
              fill="none"
              stroke="currentColor"
              strokeWidth="2.5"
            >
              <path strokeLinecap="round" strokeLinejoin="round" d="m3 8.5 3.2 3.2L13 5" />
            </svg>
          </span>
        </span>
      </span>
    </motion.button>
  );
}

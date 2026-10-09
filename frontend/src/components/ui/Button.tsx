import type { HTMLMotionProps } from "framer-motion";
import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { Spinner } from "./Spinner";

type Variant = "primary" | "secondary" | "outline" | "danger" | "ghost";
type Size = "sm" | "md" | "lg";

// Extends framer-motion's own button prop type (not React's plain
// ButtonHTMLAttributes) — motion.button's drag/animation handlers
// otherwise collide with the DOM's native event handler types.
interface ButtonProps extends Omit<HTMLMotionProps<"button">, "children"> {
  variant?: Variant;
  size?: Size;
  loading?: boolean;
  fullWidth?: boolean;
  /** Leading glyph. Kept separate from children so the loading state can hide both at once. */
  icon?: ReactNode;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  // The primary action is the only place in the product that gets a lit accent
  // surface, which is what makes it findable without being loud. It is also the
  // only place a gradient appears (`.grad-action`, index.css) -- scarcity is
  // the whole reason it still reads as emphasis rather than as styling.
  primary: "grad-action text-accent-contrast disabled:opacity-45",
  secondary:
    "bg-surface text-text border border-border hover:bg-surface-raised hover:border-border-strong disabled:opacity-45",
  outline: "bg-transparent text-text border border-border hover:bg-surface-raised disabled:opacity-45",
  danger:
    "bg-transparent text-danger border border-danger/40 hover:bg-danger hover:text-white hover:border-danger disabled:opacity-45",
  ghost: "bg-transparent text-text-muted hover:bg-surface-raised hover:text-text disabled:opacity-45",
};

// Compact by default. `md` is the workhorse at 28px tall — the height a control
// wants to be when a screen has fifteen of them, not two.
const SIZE_CLASSES: Record<Size, string> = {
  sm: "h-7 px-2.5 text-xs gap-1.5",
  md: "h-8 px-3 text-[0.8125rem] gap-1.5",
  lg: "h-10 px-4.5 text-sm gap-2",
};

/**
 * Every interactive control gets a defined hover/press/loading state
 * (Section 5.5): a small lift on hover, a press-in on tap, and a loading spinner
 * that overlays the (opacity-hidden but still laid-out) label so the button never
 * changes width when it starts loading.
 *
 * The press uses a spring rather than a duration. A button that eases back to
 * rest feels animated; one that settles feels like it has mass — and mass is
 * most of what separates a considered control from a styled `<div>`. There is no
 * shine sweep or glare: a single confident lift is the whole interaction.
 */
export function Button({
  variant = "primary",
  size = "md",
  loading = false,
  fullWidth = false,
  disabled,
  icon,
  className = "",
  children,
  ...rest
}: ButtonProps) {
  const prefersReducedMotion = useReducedMotion();
  const inert = disabled || loading;

  return (
    <motion.button
      // No hover lift. At this density a control that moves on hover makes a
      // toolbar of them feel unstable; the colour change is the affordance.
      whileTap={inert ? undefined : { scale: prefersReducedMotion ? 1 : 0.97 }}
      transition={{ type: "spring", stiffness: 500, damping: 30, mass: 0.5 }}
      disabled={inert}
      aria-busy={loading}
      className={`relative inline-flex items-center justify-center rounded-control font-medium whitespace-nowrap transition-colors duration-300 [transition-timing-function:var(--ease-out)] select-none disabled:cursor-not-allowed ${
        fullWidth ? "w-full" : ""
      } ${SIZE_CLASSES[size]} ${VARIANT_CLASSES[variant]} ${className}`}
      {...rest}
    >
      <span className={`relative inline-flex items-center ${SIZE_CLASSES[size].split(" ").pop()} ${loading ? "opacity-0" : "opacity-100"}`}>
        {icon}
        {children}
      </span>
      {loading && (
        <span className="absolute inset-0 flex items-center justify-center">
          <Spinner />
        </span>
      )}
    </motion.button>
  );
}

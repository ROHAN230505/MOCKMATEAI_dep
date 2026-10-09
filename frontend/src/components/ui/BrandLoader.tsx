import { motion, useReducedMotion } from "framer-motion";
import { BrandMark } from "../brand/Brand";

/**
 * The product's loading state, built on the official mark.
 *
 * The mark itself is never rotated, recoloured or distorted — it breathes very
 * slightly and sits inside a soft light. Everything that moves is drawn *around*
 * it: a slow orbital arc and a faint expanding pulse. That's the difference
 * between branded loading and a logo being spun like a spinner.
 *
 * It appears only where the app is genuinely waiting on something — route chunks
 * (`Suspense` in App), and the auth→dashboard handoff while real queries resolve.
 * No artificial delay is ever added to show it.
 */
export function BrandLoader({
  label = "Loading",
  fullScreen = true,
}: {
  label?: string;
  fullScreen?: boolean;
}) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <div
      role="status"
      aria-live="polite"
      aria-label={label}
      className={`flex flex-col items-center justify-center gap-8 ${
        fullScreen ? "min-h-screen bg-bg" : "py-24"
      }`}
    >
      <div className="relative flex h-28 w-28 items-center justify-center">
        {/* Expanding pulse, behind everything. */}
        {!prefersReducedMotion && (
          <motion.span
            aria-hidden="true"
            className="absolute rounded-full border"
            style={{ borderColor: "color-mix(in srgb, var(--color-accent) 26%, transparent)" }}
            initial={{ width: 60, height: 60, opacity: 0.55 }}
            animate={{ width: 112, height: 112, opacity: 0 }}
            transition={{ duration: 2.2, repeat: Infinity, ease: "easeOut" }}
          />
        )}

        {/* One orbital arc. A partial ring reads as motion at a glance where a
            full ring just reads as a circle. */}
        {!prefersReducedMotion && (
          <motion.span
            aria-hidden="true"
            className="absolute inset-0 rounded-full border border-transparent"
            style={{
              borderTopColor: "var(--color-accent)",
              borderRightColor: "color-mix(in srgb, var(--color-accent) 22%, transparent)",
            }}
            animate={{ rotate: 360 }}
            transition={{ duration: 1.9, repeat: Infinity, ease: "linear" }}
          />
        )}

        {/* The mark. Scale only, and barely — the asset is never altered. */}
        <motion.span
          animate={prefersReducedMotion ? undefined : { scale: [1, 1.045, 1] }}
          transition={{ duration: 2.4, repeat: Infinity, ease: "easeInOut" }}
          className="relative"
        >
          <BrandMark size="lg" glow />
        </motion.span>
      </div>

      <p className="marker text-[0.5625rem] text-text-subtle">{label}</p>
    </div>
  );
}

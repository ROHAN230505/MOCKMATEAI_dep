import { AnimatePresence, motion } from "framer-motion";
import type { ReactNode } from "react";

interface BannerProps {
  tone?: "error" | "success" | "info" | "warning";
  /** Optional bold lead-in above the message. */
  title?: ReactNode;
  children: ReactNode;
}

const TONE = {
  error: {
    wrapper: "border-danger/35 bg-danger/8 text-danger",
    icon: "M12 9v4m0 3h.01M10.3 3.9 2.4 17.1A1.8 1.8 0 0 0 4 19.8h16a1.8 1.8 0 0 0 1.6-2.7L13.7 3.9a1.8 1.8 0 0 0-3.4 0Z",
  },
  success: {
    wrapper: "border-success/35 bg-success/8 text-success",
    icon: "M9 12.5l2.5 2.5L16 9m-4 12a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z",
  },
  info: {
    wrapper: "border-accent/35 bg-accent-soft text-accent",
    icon: "M12 11v5m0-8h.01M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z",
  },
  warning: {
    wrapper: "border-warning/35 bg-warning/8 text-warning",
    icon: "M12 9v4m0 3h.01M12 21a9 9 0 1 1 0-18 9 9 0 0 1 0 18Z",
  },
};

/**
 * Inline form/global banner (Section 5.5): slides+fades in from the top;
 * error/destructive banners persist until the caller removes them (e.g.
 * the underlying condition resolves), success ones are expected to be
 * auto-dismissed by the caller after ~3-4s.
 *
 * Each tone carries a glyph as well as a colour, so the meaning survives for
 * anyone who can't distinguish red from green (Section 17).
 */
export function Banner({ tone = "error", title, children }: BannerProps) {
  const style = TONE[tone];

  return (
    <AnimatePresence>
      <motion.div
        role={tone === "error" ? "alert" : "status"}
        initial={{ opacity: 0, y: -8 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -8 }}
        transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
        className={`flex items-start gap-3 rounded-control border px-4 py-3 text-sm ${style.wrapper}`}
      >
        <svg
          aria-hidden="true"
          viewBox="0 0 24 24"
          className="mt-0.5 h-4 w-4 shrink-0"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.8"
        >
          <path strokeLinecap="round" strokeLinejoin="round" d={style.icon} />
        </svg>
        <div className="min-w-0 leading-relaxed">
          {title && <p className="mb-0.5 font-semibold">{title}</p>}
          <div>{children}</div>
        </div>
      </motion.div>
    </AnimatePresence>
  );
}

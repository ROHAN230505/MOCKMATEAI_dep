import { motion, useScroll, useSpring } from "framer-motion";

/**
 * A hairline scroll indicator across the top of long pages.
 *
 * Spring-smoothed rather than bound directly to scroll position: a raw binding
 * tracks every wheel tick exactly and reads as nervous, where a lightly damped
 * one reads as a mechanism.
 */
export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, { stiffness: 140, damping: 26, restDelta: 0.001 });

  return (
    <motion.div
      aria-hidden="true"
      style={{
        scaleX,
        transformOrigin: "left",
        background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))",
      }}
      className="fixed inset-x-0 top-0 z-50 h-[2px]"
    />
  );
}

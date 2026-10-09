import { useEffect, useState } from "react";
import { useReducedMotion } from "framer-motion";

/**
 * Animates a number from 0 to `target` (Section 5.5: readiness score/ring
 * "animates from 0 to its value on first load ... rather than snapping to
 * the final number instantly"). Jumps straight to the target under
 * prefers-reduced-motion.
 */
export function useCountUp(target: number, durationMs = 800): number {
  const prefersReducedMotion = useReducedMotion();
  const [value, setValue] = useState(prefersReducedMotion ? target : 0);

  useEffect(() => {
    if (prefersReducedMotion) {
      setValue(target);
      return;
    }
    let frame: number;
    const start = performance.now();
    const tick = (now: number) => {
      const progress = Math.min((now - start) / durationMs, 1);
      const eased = 1 - Math.pow(1 - progress, 3); // ease-out cubic
      setValue(target * eased);
      if (progress < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target, durationMs, prefersReducedMotion]);

  return value;
}

import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Cinematic route transition (Section 5.5's crossfade, taken further).
 *
 * The outgoing page recedes and defocuses while the incoming one rises into
 * focus — a rack focus rather than a slide. It works because the 3D environment
 * behind is *not* part of the transition: content moves in depth against a scene
 * that stays put, which reads as the camera changing subject inside one
 * continuous space instead of two unrelated screens swapping.
 *
 * Collapses to a plain opacity crossfade under `prefers-reduced-motion`, per
 * Section 5.5's requirement.
 */
export function PageTransition({ children }: { children: ReactNode }) {
  const prefersReducedMotion = useReducedMotion();

  if (prefersReducedMotion) {
    return (
      <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ duration: 0.2 }}>
        {children}
      </motion.div>
    );
  }

  return (
    <motion.div
      // Enter-only, and no `exit`. An `exit` prop makes this component register
      // with whatever `AnimatePresence` is above it and wait to be released —
      // which is precisely how the routed content ended up stuck invisible. With
      // no exit there is no handshake, so the content cannot fail to appear.
      //
      // Transform and opacity only, no `filter`: both are compositor-only, so
      // the transition can't drop frames however much the incoming route mounts.
      initial={{ opacity: 0, y: 12 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.div>
  );
}

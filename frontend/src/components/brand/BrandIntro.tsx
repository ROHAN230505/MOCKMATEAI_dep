import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { BrandMark } from "./Brand";
import { markIntroSeen } from "./introSeen";

/**
 * The opening title sequence: PRACTICE → IMPROVE → ACE → the brand.
 *
 * Design rules it follows, because a brand intro that gets any of these wrong is
 * worse than no intro at all:
 *
 * - **Short.** 3.4s end to end, and it hands off before the landing page has
 *   finished its own entrance, so the whole thing reads as one continuous open.
 * - **Once.** Gated on `sessionStorage`, so it plays on arrival and never again
 *   while the tab lives. A refresh mid-work doesn't re-run a title card.
 * - **Escapable.** Click, any key, or scroll dismisses it immediately. A skip
 *   affordance appears after a beat rather than immediately, so it doesn't
 *   advertise the intro as something to be endured.
 * - **Never blocking.** It renders *over* the app, which mounts and loads
 *   underneath. Nothing waits on the animation, so this adds no real delay — by
 *   the time it lifts, the page behind it is ready.
 * - **Not a loading screen.** No spinner, no progress bar, no percentage. It's a
 *   title card, and it says nothing untrue about work being done.
 *
 * Typographically it's a single stack: each word rises into place, holds, and
 * falls away as the next arrives — one continuous vertical movement rather than
 * three separate fades, which is what makes it read as titling.
 */

const WORDS = ["Practice", "Improve", "Ace"];
const WORD_HOLD_MS = 620;
const BRAND_HOLD_MS = 1080;

export function BrandIntro({ onDone }: { onDone: () => void }) {
  const prefersReducedMotion = useReducedMotion();
  // -1 = not started, 0..2 = word index, 3 = brand reveal
  const [step, setStep] = useState(0);
  const [showSkip, setShowSkip] = useState(false);
  const finished = useRef(false);

  function finish() {
    if (finished.current) return;
    finished.current = true;
    markIntroSeen();
    onDone();
  }

  // Reduced motion gets the brand card only, briefly — the point is still made
  // and nothing animates across the screen.
  useEffect(() => {
    if (prefersReducedMotion) {
      setStep(WORDS.length);
      const timer = window.setTimeout(finish, 700);
      return () => window.clearTimeout(timer);
    }

    const timers = WORDS.map((_, index) =>
      window.setTimeout(() => setStep(index + 1), WORD_HOLD_MS * (index + 1)),
    );
    const skipTimer = window.setTimeout(() => setShowSkip(true), 900);
    const endTimer = window.setTimeout(finish, WORD_HOLD_MS * WORDS.length + BRAND_HOLD_MS);

    return () => {
      timers.forEach(window.clearTimeout);
      window.clearTimeout(skipTimer);
      window.clearTimeout(endTimer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [prefersReducedMotion]);

  // Any deliberate input dismisses it.
  useEffect(() => {
    const dismiss = () => finish();
    window.addEventListener("keydown", dismiss);
    window.addEventListener("wheel", dismiss, { passive: true });
    window.addEventListener("touchstart", dismiss, { passive: true });
    return () => {
      window.removeEventListener("keydown", dismiss);
      window.removeEventListener("wheel", dismiss);
      window.removeEventListener("touchstart", dismiss);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const onBrand = step >= WORDS.length;

  return (
    <motion.div
      onClick={finish}
      role="presentation"
      // The exit is the transition into the landing page: the card lifts and
      // scales past the viewer rather than cross-fading, so the next screen feels
      // like it was behind this one all along.
      initial={{ opacity: 1 }}
      exit={{ opacity: 0, scale: prefersReducedMotion ? 1 : 1.06, filter: "blur(12px)" }}
      transition={{ duration: 0.75, ease: [0.16, 1, 0.3, 1] }}
      className="fixed inset-0 z-[100] flex cursor-pointer flex-col items-center justify-center overflow-hidden bg-bg"
    >
      {/* Atmosphere: one soft key from above, matching the studio lighting used
          everywhere else in the product. */}
      <div aria-hidden="true" className="absolute inset-0" />

      {/* A single slow beam sweep. One moving element in the whole sequence. */}
      {!prefersReducedMotion && (
        <motion.div
          aria-hidden="true"
          className="absolute inset-x-0 top-0 h-px"
          style={{
            background:
              "linear-gradient(90deg, transparent, color-mix(in srgb, var(--color-accent) 70%, transparent), transparent)",
          }}
          initial={{ y: "18vh", opacity: 0 }}
          animate={{ y: "82vh", opacity: [0, 0.9, 0] }}
          transition={{ duration: 3.2, ease: "easeInOut" }}
        />
      )}

      <div className="relative flex h-[9rem] items-center justify-center sm:h-[11rem]">
        <AnimatePresence mode="wait">
          {!onBrand ? (
            <motion.p
              key={WORDS[step]}
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: "0.85em" }}
              animate={{ opacity: 1, y: 0 }}
              exit={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: "-0.85em" }}
              transition={{ duration: 0.55, ease: [0.16, 1, 0.3, 1] }}
              className="display text-[3rem] text-text sm:text-[5rem] lg:text-[6rem]"
            >
              {WORDS[step]}
              <span className="text-accent">.</span>
            </motion.p>
          ) : (
            <motion.div
              key="brand"
              initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 14, scale: 0.96 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              transition={{ duration: 0.95, ease: [0.16, 1, 0.3, 1] }}
              className="flex flex-col items-center gap-6"
            >
              <BrandMark size="hero" glow />
              <div className="flex flex-col items-center">
                <p className="display text-[2.25rem] text-text sm:text-[3.25rem]">
                  MockMate<span className="text-accent">AI</span>
                </p>
                <motion.p
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.45, duration: 0.7 }}
                  className="marker mt-4 text-[0.5625rem] text-text-subtle"
                >
                  Practice · Improve · Ace
                </motion.p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </div>

      <AnimatePresence>
        {showSkip && !onBrand && (
          <motion.span
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.5 }}
            className="absolute bottom-10 text-xs text-text-subtle"
          >
            Press any key to skip
          </motion.span>
        )}
      </AnimatePresence>
    </motion.div>
  );
}

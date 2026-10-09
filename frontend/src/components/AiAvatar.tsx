import { motion, useReducedMotion } from "framer-motion";

export type AvatarState = "speaking" | "listening" | "idle";

/**
 * The AI interviewer, as an abstract neural orb (Section 5.5).
 *
 * Not a face. A synthetic human at this fidelity lands in the uncanny valley and
 * makes an already-nervous candidate more so — an abstract intelligence reads as
 * a system, which is what this is.
 *
 * Motion here is **functional, not decorative**: it is the only signal telling
 * the candidate whose turn it is, which is why it survives `prefers-reduced-motion`
 * in a reduced form rather than being switched off. Each state is distinguishable
 * at a glance and from across a room:
 *
 * - **speaking** — rings pulse outward continuously; the core brightens.
 * - **listening** — a single steady ring, and a slow inhale. Present, not radiating.
 * - **idle** — still, dimmed, no rings.
 *
 * Known Phase 2 limitation: the spec calls for amplitude-reactive motion. The
 * browser's `speechSynthesis` exposes no live amplitude data (only word-boundary
 * events), so "speaking" is a fixed pattern rather than truly audio-driven — a
 * stand-in until a streaming TTS provider with real audio data lands.
 */
export function AiAvatar({ state }: { state: AvatarState }) {
  const prefersReducedMotion = useReducedMotion();
  const isSpeaking = state === "speaking";
  const isListening = state === "listening";

  const coreAnimate =
    prefersReducedMotion || state === "idle"
      ? { scale: 1 }
      : isSpeaking
        ? { scale: [1, 1.06, 0.98, 1.04, 1] }
        : { scale: [1, 1.025, 1] };

  const coreTransition = isSpeaking
    ? { duration: 1.1, repeat: Infinity, ease: "easeInOut" as const }
    : { duration: 2.8, repeat: Infinity, ease: "easeInOut" as const };

  return (
    <div className="relative flex h-52 w-52 items-center justify-center">
      {/* Outward pulses — speaking only, so the language is unambiguous. */}
      {isSpeaking &&
        !prefersReducedMotion &&
        [0, 1, 2].map((index) => (
          <motion.span
            key={index}
            aria-hidden="true"
            className="absolute rounded-full border"
            style={{ borderColor: "color-mix(in srgb, var(--color-accent) 45%, transparent)" }}
            initial={{ width: 112, height: 112, opacity: 0.55 }}
            animate={{ width: 208, height: 208, opacity: 0 }}
            transition={{ duration: 2.4, repeat: Infinity, delay: index * 0.8, ease: "easeOut" }}
          />
        ))}

      {/* A steady dashed ring while listening: present, but not radiating. */}
      {isListening && (
        <motion.span
          aria-hidden="true"
          className="absolute h-44 w-44 rounded-full border border-dashed"
          style={{ borderColor: "color-mix(in srgb, var(--color-accent) 30%, transparent)" }}
          animate={prefersReducedMotion ? undefined : { rotate: 360 }}
          transition={{ duration: 32, repeat: Infinity, ease: "linear" }}
        />
      )}

      {/* Orbiting satellite nodes — the visual tie to the neural field behind. */}
      {!prefersReducedMotion &&
        state !== "idle" &&
        [0, 1, 2].map((index) => (
          <motion.span
            key={`orbit-${index}`}
            aria-hidden="true"
            className="absolute h-36 w-36"
            // Alternating direction via the target angle rather than a
            // `direction` option — counter-rotating orbits keep the three
            // satellites from ever syncing into a single visual ring.
            animate={{ rotate: index % 2 === 0 ? 360 : -360 }}
            transition={{ duration: 14 + index * 6, repeat: Infinity, ease: "linear" }}
            style={{ rotate: index * 120 }}
          >
            <span
              className="absolute top-0 left-1/2 h-1.5 w-1.5 -translate-x-1/2 rounded-full"
              style={{
                background: "var(--color-accent)",
                boxShadow: "0 0 8px color-mix(in srgb, var(--color-accent) 80%, transparent)",
              }}
            />
          </motion.span>
        ))}

      <motion.div
        animate={coreAnimate}
        transition={coreTransition}
        className="relative h-28 w-28 overflow-hidden rounded-full"
        style={{
          background: isSpeaking
            ? "radial-gradient(120% 120% at 32% 24%, var(--grad-b), var(--grad-a) 55%, color-mix(in srgb, var(--grad-a) 55%, #000) 100%)"
            : "radial-gradient(120% 120% at 32% 24%, color-mix(in srgb, var(--grad-b) 62%, transparent), color-mix(in srgb, var(--grad-a) 55%, transparent) 60%, color-mix(in srgb, var(--grad-a) 26%, transparent) 100%)",
          boxShadow: isSpeaking
            ? "0 0 44px -6px color-mix(in srgb, var(--color-accent) 65%, transparent)"
            : "0 0 22px -8px color-mix(in srgb, var(--color-accent) 45%, transparent)",
        }}
      >
        {/* Specular sweep — gives the orb a surface rather than a flat fill. */}
        <span
          aria-hidden="true"
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(150deg, rgba(255,255,255,0.4) 0%, rgba(255,255,255,0.05) 38%, transparent 60%)",
          }}
        />
      </motion.div>

      {/* The visuals above are decorative duplicates of this. */}
      <span className="sr-only" role="status">
        {isSpeaking ? "Interviewer is speaking" : isListening ? "Listening for your answer" : "Interviewer is idle"}
      </span>
    </div>
  );
}

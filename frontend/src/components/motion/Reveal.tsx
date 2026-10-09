import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

/**
 * Scroll-triggered entrance.
 *
 * One component for every reveal in the product, so the distance, duration and
 * easing are identical everywhere — inconsistent reveal timings are what make a
 * long page feel assembled from parts. `once: true` because re-animating on
 * every scroll-by is distracting on a page people scroll up and down.
 *
 * Collapses to a plain opacity fade under `prefers-reduced-motion` (never zero
 * animation: the element still needs to not pop in mid-layout).
 */
export function Reveal({
  children,
  delay = 0,
  y = 26,
  blur = false,
  className = "",
}: {
  children: ReactNode;
  delay?: number;
  y?: number;
  /**
   * A short defocus on entry — reads as depth-of-field pulling into focus.
   *
   * Off by default: animating `filter` forces the element onto its own
   * compositor layer and re-rasterises it every frame of the entrance, which is
   * fine for one headline and expensive for twelve cards revealing at once. Opt
   * in on hero type only.
   */
  blur?: boolean;
  className?: string;
}) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <motion.div
      className={className}
      initial={
        prefersReducedMotion
          ? { opacity: 0 }
          : { opacity: 0, y, filter: blur ? "blur(8px)" : "blur(0px)" }
      }
      whileInView={{ opacity: 1, y: 0, filter: "blur(0px)" }}
      // `amount: 0.01` and no negative root margin. A reveal that starts at
      // `opacity: 0` must be trivially easy to trigger — any condition that can
      // leave the observer unfired leaves the content permanently invisible,
      // which is a far worse failure than a reveal firing slightly early.
      viewport={{ once: true, amount: 0.01 }}
      transition={{
        duration: prefersReducedMotion ? 0.25 : 0.9,
        delay: prefersReducedMotion ? 0 : delay,
        ease: [0.16, 1, 0.3, 1],
      }}
    >
      {children}
    </motion.div>
  );
}

/**
 * Staggered word-by-word reveal for display headings.
 *
 * Words, not characters: per-character staggering on a headline is a portfolio
 * cliché and it wrecks text selection and screen-reader output. Here the whole
 * heading stays one accessible string via `aria-label`, and the visual words are
 * `aria-hidden` spans.
 */
export function CinematicHeading({
  text,
  className = "",
  delay = 0,
  as: Tag = "h1",
  accentFrom,
}: {
  text: string;
  className?: string;
  delay?: number;
  as?: "h1" | "h2" | "h3" | "p";
  /** Zero-based word index from which the accent gradient takes over. */
  accentFrom?: number;
}) {
  const prefersReducedMotion = useReducedMotion();
  const words = text.split(" ");

  return (
    <Tag className={className} aria-label={text}>
      <span aria-hidden="true" className="inline">
        {words.map((word, index) => (
          <motion.span
            key={`${word}-${index}`}
            className={`inline-block whitespace-pre ${
              accentFrom !== undefined && index >= accentFrom ? "text-gradient-accent" : ""
            }`}
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: "0.5em" }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              // Long and heavily decelerated. Display type that snaps into place
              // reads as a web animation; type that glides to a stop reads as
              // titling.
              duration: prefersReducedMotion ? 0.3 : 1.1,
              delay: prefersReducedMotion ? 0 : delay + index * 0.07,
              ease: [0.16, 1, 0.3, 1],
            }}
            style={{ transformOrigin: "bottom center" }}
          >
            {word}
            {index < words.length - 1 ? " " : ""}
          </motion.span>
        ))}
      </span>
    </Tag>
  );
}

import type { ReactNode } from "react";
import { motion, useReducedMotion } from "framer-motion";
import { BrandLockup } from "../brand/Brand";
import { ThemeToggle } from "../ThemeToggle";
import { Nebula } from "../room/Nebula";

/**
 * Shared chrome for signup / login / password reset (Sections 4.2-4.3).
 *
 * Centred, on the galaxy.
 *
 * This replaced a two-column split — form on the left, render on the right.
 * The split had a defensible logic to it, but it put the one thing on the page
 * that *does* anything off to one side, and asymmetry only pays off when there
 * is a second subject worth the weight. On a sign-in screen there is exactly
 * one subject, so the composition now says so: the card sits in the middle of
 * the field, and everything else gets out of its way.
 *
 * The field is decoration and stays `pointer-events-none`, so it can never
 * intercept a click meant for the form.
 *
 * No authentication logic lives here. This renders `children` and nothing else
 * — every form, request and redirect is exactly as it was.
 */
export function AuthLayout({
  children,
  tagline,
}: {
  children: ReactNode;
  /** One line above the form, when the screen benefits from context. */
  tagline?: string;
}) {
  const prefersReducedMotion = useReducedMotion();

  return (
    <div className="void relative flex min-h-screen flex-col">
      <Nebula intensity={1} />
      {/* The core is brightest dead centre, which is exactly where the card
          now sits. This puts the ground back under it so the form never has to
          compete with whichever arm is passing behind it. */}
      <div aria-hidden="true" className="void-scrim pointer-events-none fixed inset-0 -z-10" />

      <header className="relative z-10 flex items-center justify-between px-6 py-6 sm:px-10">
        <BrandLockup to="/" size="sm" />
        <ThemeToggle />
      </header>

      <main className="relative z-10 flex flex-1 items-center justify-center px-6 py-10 sm:px-10">
        <motion.div
          initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 14 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.7, ease: [0.16, 1, 0.3, 1] }}
          className="w-full max-w-[26rem]"
        >
          {/* A real surface, not a translucent pane. Over an additive field,
              glass picks up whatever particle happens to be behind each letter,
              and form labels stop holding still. */}
          <div className="rounded-card border border-border-strong bg-surface/95 p-7 shadow-[var(--shadow-lg)] backdrop-blur-xl sm:p-9">
            {tagline && (
              <p className="mb-5 text-micro font-medium tracking-[0.12em] text-text-subtle uppercase">
                {tagline}
              </p>
            )}
            {children}
          </div>

          <p className="mt-6 text-center text-micro text-text-subtle">
            © {new Date().getFullYear()} MockMateAI · Practice · Improve · Ace
          </p>
        </motion.div>
      </main>
    </div>
  );
}

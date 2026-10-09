import { motion, useReducedMotion, useScroll, useTransform } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { BrandLockup, BrandMark } from "../components/brand/Brand";
import { Nebula } from "../components/room/Nebula";
import { ThemeToggle } from "../components/ThemeToggle";
import { CinematicHeading, Reveal } from "../components/motion/Reveal";
import { useAuthStore } from "../store/authStore";

const CAPABILITIES = [
  {
    id: "interview-simulation",
    marker: "01",
    title: "Interview Simulation",
    lead: "It listens, then it pushes.",
    description:
      "A live, spoken interview that adapts to your answers in real time. Give it a vague answer and it asks the follow-up a real interviewer would — not the next question on a list.",
  },
  {
    id: "sign-language",
    marker: "02",
    title: "Sign-Language Accessibility",
    lead: "The same interview, signed.",
    description:
      "A first-class signed path sharing the same engine, the same rubric and the same feedback pipeline as voice. Not a reduced version of the product — the product.",
  },
  {
    id: "aptitude-dsa",
    marker: "03",
    title: "Aptitude and DSA",
    lead: "The rest of the loop.",
    description:
      "Topic-wise aptitude practice and a full data-structures problem set with an in-browser editor, so everything you're being tested on lives in one place.",
  },
  {
    id: "feedback-reports",
    marker: "04",
    title: "Feedback Reports",
    lead: "Every claim, with a receipt.",
    description:
      "Scores you can trace. Each strength and each improvement cites the question it came from and quotes what you actually said, so you can go back and hear the difference.",
  },
];

const FLOW = [
  { n: "01", title: "Set the target", body: "Choose a role, or paste the job description you're actually preparing for." },
  { n: "02", title: "Sit the interview", body: "Speak your answers out loud. It follows up when something's thin." },
  { n: "03", title: "Read the evidence", body: "Scores, quotes and a plan — ready before you close the tab." },
];

const PRINCIPLES = [
  {
    title: "Honest before kind",
    body: "A score you can't trace is a score you can't act on. Every point in a report cites the question and quotes you.",
  },
  {
    title: "Nothing invented",
    body: "What a session didn't measure stays blank, and says why. No neutral placeholder dressed up as a measurement.",
  },
  {
    title: "A pass isn't a zero",
    body: "Skip a question and it leaves your average entirely. Choosing to move on is not the same as answering badly.",
  },
];

export function Landing() {
  const navigate = useNavigate();
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const prefersReducedMotion = useReducedMotion();
  const [scrolled, setScrolled] = useState(false);
  const heroRef = useRef<HTMLElement>(null);

  const { scrollYProgress } = useScroll({ target: heroRef, offset: ["start start", "end start"] });
  // The copy lifts away and the object is what you're left with. Small numbers
  // on purpose — a hero that flies apart on the first scroll tick feels cheap.
  const copyY = useTransform(scrollYProgress, [0, 1], [0, prefersReducedMotion ? 0 : -60]);
  const copyOpacity = useTransform(scrollYProgress, [0, 0.6], [1, 0]);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12);
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, []);

  function handleStartInterview() {
    navigate(isAuthenticated ? "/interview/setup" : "/signup?redirect=/interview/setup");
  }

  return (
    <div className="void relative min-h-screen">
      <Nebula intensity={1} />
      {/* Lifts the middle of the field back down so the headline sits on a
          predictable ground rather than on whichever arm is passing. */}
      <div aria-hidden="true" className="void-scrim pointer-events-none fixed inset-0 -z-10" />

      <header
        className={`fixed inset-x-0 top-0 z-40 transition-[background-color,border-color,backdrop-filter] duration-700 [transition-timing-function:var(--ease-out)] ${
          scrolled
            ? "border-b border-border bg-bg/72 backdrop-blur-xl"
            : "border-b border-transparent bg-transparent"
        }`}
      >
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 py-4 sm:px-10">
          <BrandLockup to="/" size="sm" />
          <div className="flex items-center gap-3 sm:gap-5">
            <ThemeToggle />
            <Link
              to="/login"
              className="hidden rounded-control px-3 py-2 text-sm font-medium text-text-muted transition-colors duration-300 hover:text-text sm:block"
            >
              Log in
            </Link>
            <Link to="/signup">
              <Button variant="primary" size="sm">
                Start Free
              </Button>
            </Link>
          </div>
        </div>
      </header>

      {/* ---------------------------------------------------------------- HERO */}
      {/*
        Mark, eyebrow, headline — stacked, centred, in that order.

        The mark leads because it's the one element that identifies the product
        before a word is read, and it's sized to roughly the cap height of the
        headline's first line so the two read as one lockup rather than as a logo
        that happens to sit above some type.

        The gap under it is deliberately tight (`mb-5`). A logo floating far above
        a headline looks like two unrelated blocks; close enough to be one visual
        unit is what makes it feel composed. It also rises fractionally slower
        than the copy on scroll, which gives the hero a shallow sense of depth
        without anything moving independently.
      */}
      <section
        ref={heroRef}
        className="relative z-10 flex min-h-[100svh] flex-col items-center justify-center px-6 pt-28 pb-24 text-center sm:px-10"
      >
        <motion.div style={{ y: copyY, opacity: copyOpacity }} className="flex w-full flex-col items-center">
          <motion.div
            initial={prefersReducedMotion ? { opacity: 0 } : { opacity: 0, y: 12, scale: 0.92 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            transition={{ duration: 1.1, ease: [0.16, 1, 0.3, 1] }}
            className="relative mb-5 flex items-center justify-center"
          >
            {/* A soft pool of light under the mark, so it sits *in* the neural
                field rather than on top of it. Sized off the mark itself. */}
            <span
              aria-hidden="true"
              className="absolute inset-0 -z-10 scale-[2.4] rounded-full opacity-45 blur-3xl"
              style={{ background: "radial-gradient(circle, var(--grad-a), transparent 70%)" }}
            />
            <BrandMark size="hero" className="h-[clamp(3.5rem,9vw,6rem)]" />
          </motion.div>

          <Reveal delay={0.05} y={8}>
            <p className="marker mb-6 text-[0.625rem] text-text-subtle">Interview preparation</p>
          </Reveal>

          <CinematicHeading
            text="Practice like it's real."
            className="display max-w-[24ch] text-[2.75rem] text-text sm:text-[4.25rem] lg:text-[5.25rem]"
            delay={0.3}
          />
          <CinematicHeading
            text="Walk in ready."
            className="display mt-1 max-w-[24ch] text-[2.75rem] sm:text-[4.25rem] lg:text-[5.25rem]"
            delay={0.58}
            accentFrom={0}
          />

          <Reveal delay={0.95} y={14} blur>
            <p className="mx-auto mt-8 max-w-lg text-base leading-relaxed text-text-muted sm:text-lg">
              A live, adaptive AI interview — with feedback you can trace back to
              your own words.
            </p>
          </Reveal>

          <Reveal delay={1.1} y={14}>
            <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row">
              <Button variant="primary" size="lg" onClick={handleStartInterview}>
                Start Free Mock Interview
              </Button>
              <a href="#flow">
                <Button variant="ghost" size="lg">
                  How it works
                </Button>
              </a>
            </div>
          </Reveal>
        </motion.div>
      </section>

      {/* ---------------------------------------------------------------- FLOW */}
      <section id="flow" className="relative z-10 scroll-mt-20 px-6 py-20 sm:px-10 lg:py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <p className="marker mb-6 text-[0.6875rem] text-text-subtle">The loop</p>
          </Reveal>
          <Reveal delay={0.08}>
            <h2 className="display max-w-[20ch] text-4xl text-text sm:text-6xl">
              Three steps, then the receipts.
            </h2>
          </Reveal>

          <div className="mt-20 grid gap-16 md:grid-cols-3 md:gap-10">
            {FLOW.map((step, index) => (
              <Reveal key={step.n} delay={index * 0.1}>
                <div className="max-w-sm">
                  <span className="marker text-xs text-accent">{step.n}</span>
                  <h3 className="mt-5 text-xl font-semibold tracking-tight text-text">{step.title}</h3>
                  <p className="mt-3 text-base leading-relaxed text-text-muted">{step.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* -------------------------------------------------------- CAPABILITIES */}
      <section className="relative z-10 px-6 py-12 sm:px-10">
        <div className="mx-auto max-w-6xl">
          {CAPABILITIES.map((item) => (
            <Reveal key={item.id} delay={0.04}>
              <article
                id={item.id}
                className="grid scroll-mt-24 gap-8 border-t border-border py-14 md:grid-cols-12 md:gap-12 lg:py-16"
              >
                <div className="md:col-span-5">
                  <span className="marker text-[0.625rem] text-text-subtle">{item.marker}</span>
                  <h3 className="display mt-4 text-3xl text-text sm:text-4xl">{item.lead}</h3>
                  <p className="mt-5 text-sm font-medium tracking-wide text-accent">{item.title}</p>
                </div>

                <p className="text-base leading-relaxed text-text-muted md:col-span-6 md:col-start-7 lg:text-lg">
                  {item.description}
                </p>
              </article>
            </Reveal>
          ))}
        </div>
      </section>

      {/* ---------------------------------------------------------- PRINCIPLES */}
      <section className="relative z-10 px-6 py-20 sm:px-10 lg:py-24">
        <div className="mx-auto max-w-6xl">
          <Reveal>
            <p className="marker mb-6 text-[0.6875rem] text-text-subtle">How it judges</p>
          </Reveal>
          <Reveal delay={0.08}>
            <h2 className="display max-w-[18ch] text-4xl text-text sm:text-6xl">
              Feedback you can argue with.
            </h2>
          </Reveal>

          <div className="mt-20 grid gap-14 md:grid-cols-3 md:gap-10">
            {PRINCIPLES.map((principle, index) => (
              <Reveal key={principle.title} delay={index * 0.1}>
                <div className="max-w-sm">
                  <h3 className="text-lg font-semibold tracking-tight text-text">{principle.title}</h3>
                  <p className="mt-3 text-base leading-relaxed text-text-muted">{principle.body}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* ----------------------------------------------------------------- CTA */}
      <section className="relative z-10 px-6 pt-14 pb-24 sm:px-10">
        <div className="mx-auto max-w-3xl text-center">
          <Reveal>
            <h2 className="display text-4xl text-text sm:text-6xl">
              Your next interview is the one you already did.
            </h2>
          </Reveal>
          <Reveal delay={0.1}>
            <p className="mx-auto mt-6 max-w-md text-base leading-relaxed text-text-muted sm:text-lg">
              Run a full mock interview in the next ten minutes. Read the feedback tonight.
            </p>
          </Reveal>
          <Reveal delay={0.2}>
            <div className="mt-12 flex justify-center">
              <Button variant="primary" size="lg" onClick={handleStartInterview}>
                Start Free Mock Interview
              </Button>
            </div>
          </Reveal>
          <Reveal delay={0.28} blur={false}>
            <p className="mt-8 text-xs text-text-subtle">No credit card. Works in Chrome and Edge.</p>
          </Reveal>
        </div>
      </section>

      <footer className="relative z-10 border-t border-border px-6 py-10 sm:px-10">
        <div className="mx-auto flex max-w-6xl flex-col items-center gap-8 sm:flex-row sm:justify-between">
          <BrandLockup size="sm" tagline />
          <div className="flex flex-wrap justify-center gap-x-8 gap-y-3 text-sm text-text-muted">
            <a href="#" className="transition-colors duration-300 hover:text-text">
              About
            </a>
            <a href="#" className="transition-colors duration-300 hover:text-text">
              Privacy Policy
            </a>
            <a href="#" className="transition-colors duration-300 hover:text-text">
              Contact
            </a>
            <a href="#" className="transition-colors duration-300 hover:text-text">
              Accessibility Statement
            </a>
          </div>
          <p className="text-sm text-text-subtle">© {new Date().getFullYear()} MockMateAI</p>
        </div>
      </footer>
    </div>
  );
}

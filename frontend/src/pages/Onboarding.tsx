import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Banner } from "../components/ui/Banner";
import { SelectCard } from "../components/ui/SelectCard";
import { Select } from "../components/ui/Input";
import { BrandLockup } from "../components/brand/Brand";
import { ThemeToggle } from "../components/ThemeToggle";
import { Room } from "../components/room/Room";
import { Nebula } from "../components/room/Nebula";
import type { ExperienceLevel, PreferredMode } from "../types/auth";
import { updatePreferences } from "../services/userApi";
import { ApiError } from "../lib/apiClient";
import { useAuthStore } from "../store/authStore";

const ROLE_OPTIONS = [
  "Software Development Engineer (SDE)",
  "Data Analyst",
  "Data Scientist / ML Engineer",
  "Product Manager",
  "Frontend Developer",
  "Backend Developer",
  "DevOps / SRE",
  "QA / Test Engineer",
];

const EXPERIENCE_OPTIONS: { value: ExperienceLevel; label: string }[] = [
  { value: "student_fresher", label: "Student / Fresher" },
  { value: "1-3_years", label: "1–3 years" },
  { value: "3+_years", label: "3+ years" },
];

const MODE_OPTIONS: { value: PreferredMode; label: string; description: string }[] = [
  { value: "voice", label: "Voice", description: "Speak your answers, hear the AI interviewer." },
  { value: "sign", label: "Sign Language", description: "A fully signed interview, same engine and feedback." },
  { value: "both", label: "Both / Decide later", description: "Choose per-interview at setup time." },
];

export function Onboarding() {
  const navigate = useNavigate();
  const setUser = useAuthStore((s) => s.setUser);

  const [step, setStep] = useState(0);
  const [direction, setDirection] = useState(1);
  const [targetRole, setTargetRole] = useState("");
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel | null>(null);
  const [preferredMode, setPreferredMode] = useState<PreferredMode | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const prefersReducedMotion = useReducedMotion();

  function goNext() {
    setDirection(1);
    setStep((s) => s + 1);
  }
  function goBack() {
    setDirection(-1);
    setStep((s) => s - 1);
  }

  async function handleFinish() {
    setError(null);
    setLoading(true);
    try {
      const updated = await updatePreferences({
        targetRole,
        experienceLevel: experienceLevel ?? undefined,
        preferredMode: preferredMode ?? undefined,
      });
      setUser(updated);
      navigate("/dashboard");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setLoading(false);
    }
  }

  const slideDistance = prefersReducedMotion ? 0 : 40;
  const variants = {
    enter: (dir: number) => ({ x: dir * slideDistance, opacity: 0 }),
    center: { x: 0, opacity: 1 },
    exit: (dir: number) => ({ x: -dir * slideDistance, opacity: 0 }),
  };

  return (
    <div className="relative flex min-h-screen items-center justify-center overflow-hidden px-4 py-12">
      {/* No bg-bg here: this element is positioned, so its own background
          paints above a -z-10 canvas and would cover the field. The ground
          already comes from body. */}
      <Room />
      <Nebula />

      <div className="absolute top-4 right-4 z-10 sm:top-6 sm:right-6">
        <ThemeToggle />
      </div>
      <div className="absolute top-5 left-5 z-10 sm:top-7 sm:left-7">
        <BrandLockup size="xs" />
      </div>

      <Card tone="glow" className="relative z-10 w-full max-w-lg overflow-hidden p-7 sm:p-8">
        <div className="mb-6">
          <div className="mb-4 flex items-center justify-between">
            {step > 0 ? (
              <button
                onClick={goBack}
                className="-ml-1 rounded-control px-1 text-sm font-medium text-text-muted transition-colors duration-200 hover:text-text"
              >
                ← Back
              </button>
            ) : (
              <span className="text-sm font-medium text-text-subtle">Let's get you set up</span>
            )}
            <span className="tnum text-xs text-text-subtle">Step {step + 1} of 3</span>
          </div>

          {/* Segmented progress: three explicit stops rather than a continuous
              bar, because the flow has three discrete answers to give. */}
          <div className="flex gap-1.5" role="presentation">
            {[0, 1, 2].map((index) => (
              <span key={index} className="h-1 flex-1 overflow-hidden rounded-pill bg-surface-raised">
                <motion.span
                  className="block h-full rounded-pill bg-accent"
                  initial={false}
                  animate={{ scaleX: index <= step ? 1 : 0 }}
                  style={{ originX: 0 }}
                  transition={{ duration: prefersReducedMotion ? 0 : 0.4, ease: [0.22, 1, 0.36, 1] }}
                />
              </span>
            ))}
          </div>
        </div>

        {error && (
          <div className="mb-4">
            <Banner tone="error">{error}</Banner>
          </div>
        )}

        <AnimatePresence mode="wait" custom={direction}>
          {step === 0 && (
            <motion.div
              key="step-0"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <h1 className="mb-1 text-xl font-semibold tracking-tight text-text">
                What role are you preparing for?
              </h1>
              <p className="mb-5 text-sm leading-relaxed text-text-muted">
                Pick the closest match — you can change this any time.
              </p>
              <Select value={targetRole} onChange={(e) => setTargetRole(e.target.value)}>
                <option value="" disabled>
                  Select a role…
                </option>
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>
                    {role}
                  </option>
                ))}
              </Select>
              <Button variant="primary" fullWidth className="mt-6" disabled={!targetRole} onClick={goNext}>
                Next
              </Button>
            </motion.div>
          )}

          {step === 1 && (
            <motion.div
              key="step-1"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <h1 className="mb-1 text-xl font-semibold tracking-tight text-text">
                What's your experience level?
              </h1>
              <p className="mb-5 text-sm leading-relaxed text-text-muted">
                This helps calibrate question difficulty.
              </p>
              <div className="flex flex-col gap-3">
                {EXPERIENCE_OPTIONS.map((opt) => (
                  <SelectCard
                    key={opt.value}
                    title={opt.label}
                    selected={experienceLevel === opt.value}
                    onClick={() => setExperienceLevel(opt.value)}
                  />
                ))}
              </div>
              <Button variant="primary" fullWidth className="mt-6" disabled={!experienceLevel} onClick={goNext}>
                Next
              </Button>
            </motion.div>
          )}

          {step === 2 && (
            <motion.div
              key="step-2"
              custom={direction}
              variants={variants}
              initial="enter"
              animate="center"
              exit="exit"
              transition={{ duration: 0.25, ease: "easeOut" }}
            >
              <h1 className="mb-1 text-xl font-semibold tracking-tight text-text">
                Would you like to use voice or sign language as your primary interview mode?
              </h1>
              <p className="mb-5 text-sm leading-relaxed text-text-muted">
                Both modes share the same interview engine and feedback.
              </p>
              <div className="flex flex-col gap-3">
                {MODE_OPTIONS.map((opt) => (
                  <SelectCard
                    key={opt.value}
                    title={opt.label}
                    description={opt.description}
                    selected={preferredMode === opt.value}
                    onClick={() => setPreferredMode(opt.value)}
                  />
                ))}
              </div>
              <Button
                variant="primary"
                fullWidth
                className="mt-6"
                disabled={!preferredMode}
                loading={loading}
                onClick={handleFinish}
              >
                Finish Setup
              </Button>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>
    </div>
  );
}

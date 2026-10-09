import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { SelectCard } from "../components/ui/SelectCard";
import { Select, Textarea, Input } from "../components/ui/Input";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { PageHeader } from "../components/ui/PageHeader";
import { JOB_DESCRIPTION_MAX_LENGTH, useInterviewSetupStore } from "../store/interviewSetupStore";
import type { InterviewType } from "../types/interview";

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

const TYPE_OPTIONS: { value: InterviewType; label: string; description: string; recommended?: boolean }[] = [
  { value: "technical", label: "Technical Focus", description: "CS fundamentals and problem-solving questions." },
  { value: "behavioral", label: "Behavioral Focus", description: "Past experience, teamwork, and decision-making." },
  {
    value: "mixed",
    label: "Mixed",
    description: "A blend of both, like most real interviews.",
    recommended: true,
  },
];

const DURATION_OPTIONS = [
  { minutes: 15, description: "A quick warm-up" },
  { minutes: 30, description: "A realistic round" },
  { minutes: 45, description: "A full loop" },
];

/**
 * Section 4.6. The JD/company targeting panel is live as of Phase 3 — the LLM
 * engine (Section 9.3) now actually reads both and tailors questions from
 * question one onward, so the fields do what they claim.
 *
 * Resume upload is still not shown: nothing consumes a resume until the
 * Resume Analyzer (Phase 8), and per Section 1.2 an input that silently does
 * nothing would misrepresent the build.
 */
export function InterviewSetup() {
  const navigate = useNavigate();
  const {
    role,
    type,
    durationMinutes,
    mode,
    jobDescriptionText,
    targetCompanyName,
    setSetup,
  } = useInterviewSetupStore();
  const [error, setError] = useState<string | null>(null);
  const [showTargeting, setShowTargeting] = useState(
    // Expanded on return if the candidate already entered something, so a
    // back-navigation doesn't hide their own input.
    Boolean(jobDescriptionText || targetCompanyName),
  );

  // Section 4.6: "If a JD is entered, the role dropdown becomes
  // optional-but-still-shown (JD text takes priority in the prompt when both
  // are present)."
  const roleRequired = jobDescriptionText.trim().length === 0;

  function handleContinue() {
    if (roleRequired && !role) {
      setError("Select a role, or paste a job description to tailor the interview instead.");
      return;
    }
    if (!durationMinutes) {
      setError("Select a duration to continue.");
      return;
    }
    navigate("/interview/precheck");
  }

  const blocked = (roleRequired && !role) || !durationMinutes;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader
        eyebrow="Mock Interview"
        title="Set up your mock interview"
        description="Voice mode. The AI interviewer adapts to your answers and will follow up when something's vague."
      />

      {error && <Banner tone="error">{error}</Banner>}

      <Card className="flex flex-col gap-5">
        <Select
          label={
            roleRequired ? "Role / Position" : "Role / Position (optional — using your job description)"
          }
          value={role}
          onChange={(e) => setSetup({ role: e.target.value })}
        >
          <option value="" disabled>
            Select a role…
          </option>
          {ROLE_OPTIONS.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </Select>

        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">Interview Type</legend>
          <div className="flex flex-col gap-3">
            {TYPE_OPTIONS.map((opt) => (
              <SelectCard
                key={opt.value}
                title={opt.label}
                description={opt.description}
                badge={opt.recommended ? <Badge tone="accent">Recommended</Badge> : undefined}
                selected={type === opt.value}
                onClick={() => setSetup({ type: opt.value })}
              />
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">Duration</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
            {DURATION_OPTIONS.map((d) => (
              <SelectCard
                key={d.minutes}
                title={`${d.minutes} min`}
                description={d.description}
                selected={durationMinutes === d.minutes}
                onClick={() => setSetup({ durationMinutes: d.minutes })}
              />
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">Mode</legend>
          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <SelectCard
              title="Voice"
              description="Speak your answers out loud."
              selected={mode === "voice"}
              onClick={() => setSetup({ mode: "voice" })}
            />
            <SelectCard
              title="Sign Language"
              description="Questions on screen, answers typed. No microphone needed."
              selected={mode === "sign"}
              onClick={() => setSetup({ mode: "sign" })}
            />
          </div>
        </fieldset>
      </Card>

      {/* Section 4.6's optional custom job-targeting panel. */}
      <Card padded={false} className="overflow-hidden">
        <button
          type="button"
          onClick={() => setShowTargeting((v) => !v)}
          aria-expanded={showTargeting}
          className="flex w-full items-center justify-between gap-4 px-6 py-5 text-left transition-colors duration-200 hover:bg-surface-raised/60"
        >
          <span className="min-w-0">
            <span className="block text-sm font-medium text-text">Tailor this interview to a specific job</span>
            <span className="mt-1 block text-xs text-text-muted">
              Paste a job description and the questions come from it.
            </span>
          </span>
          <span
            aria-hidden="true"
            className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border text-text-muted transition-transform duration-300 ${
              showTargeting ? "rotate-45" : ""
            }`}
          >
            <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2">
              <path strokeLinecap="round" d="M12 5v14M5 12h14" />
            </svg>
          </span>
        </button>

        <AnimatePresence initial={false}>
          {showTargeting && (
            <motion.div
              initial={{ height: 0, opacity: 0 }}
              animate={{ height: "auto", opacity: 1 }}
              exit={{ height: 0, opacity: 0 }}
              transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
              className="overflow-hidden"
            >
              <div className="flex flex-col gap-5 border-t border-border px-6 py-6">
                <Textarea
                  label="Paste a job description"
                  id="job-description"
                  rows={7}
                  value={jobDescriptionText}
                  maxLength={JOB_DESCRIPTION_MAX_LENGTH}
                  onChange={(e) => setSetup({ jobDescriptionText: e.target.value })}
                  placeholder="Paste the job description here and the interviewer will generate role-specific questions from it."
                  /* Section 4.6: "character counter shown". */
                  counter={`${jobDescriptionText.length} / ${JOB_DESCRIPTION_MAX_LENGTH}`}
                />

                <Input
                  label="Company name (optional)"
                  id="company-name"
                  type="text"
                  value={targetCompanyName}
                  maxLength={255}
                  onChange={(e) => setSetup({ targetCompanyName: e.target.value })}
                  placeholder='e.g. "Google", "a fintech startup"'
                  /* Section 4.6 requires this clarification in spirit — so the
                     candidate can't mistake the field for an official
                     integration with the company. */
                  hint="This helps tailor question style, not verified against any company records."
                />
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </Card>

      {/* Floating action bar: on a long form the primary action shouldn't
          require scrolling back to find it, and a floating bar keeps the page
          from being capped with a solid slab. */}
      <div className="sticky bottom-4 z-10">
        <div className="rounded-card border border-border bg-surface p-2">
          <Button variant="primary" size="lg" fullWidth disabled={blocked} onClick={handleContinue}>
            Continue to Setup Check
          </Button>
        </div>
      </div>
    </div>
  );
}

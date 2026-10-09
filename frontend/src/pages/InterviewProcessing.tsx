import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card } from "../components/ui/Card";
import { generateFeedbackReport, getFeedbackStatus } from "../services/feedbackApi";
import { ApiError } from "../lib/apiClient";
import type { EndReason } from "../hooks/useInterviewOrchestrator";

const END_REASON_COPY: Record<NonNullable<EndReason>, string> = {
  completed: "You made it through every question.",
  time_up: "Time's up — here's what you covered.",
  ended_by_candidate: "You ended the interview early.",
};

/**
 * The steps shown while the report generates (Section 4.10).
 *
 * These are honest about what the backend actually does, in the order it does
 * it (see services/feedback/generator.py): read the transcript, score it
 * deterministically, then write the narrative. They advance on a timer rather
 * than on real per-step events, because the backend runs this as one background
 * job — so the copy avoids claiming a step is *finished*, and the last one stays
 * active until the poll returns `ready`.
 */
const STEPS = ["Reading back your transcript", "Scoring your answers", "Writing your feedback"];

const STEP_INTERVAL_MS = 2200;
const POLL_INTERVAL_MS = 1500;
/** After this long, something is wrong — offer a retry instead of spinning forever. */
const STALL_TIMEOUT_MS = 90_000;

/**
 * Backs `/interview/processing/:sessionId` — Section 4.10's post-interview
 * processing screen.
 *
 * Generation is already running server-side by the time this mounts (the
 * interview's end handler starts it), so this page only polls. It does not kick
 * off generation itself except as an explicit retry, which keeps a page refresh
 * from queuing a second provider call for the same report.
 */
export function InterviewProcessing() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const endReason = (location.state as { endReason?: EndReason } | null)?.endReason ?? null;

  const [stepIndex, setStepIndex] = useState(0);
  const [stalled, setStalled] = useState(false);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const mountedAt = useRef(Date.now());

  const { data, error } = useQuery({
    queryKey: ["feedbackStatus", sessionId],
    queryFn: () => getFeedbackStatus(sessionId!),
    enabled: Boolean(sessionId),
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "ready" || status === "failed" ? false : POLL_INTERVAL_MS;
    },
  });

  const retry = useMutation({
    mutationFn: () => generateFeedbackReport(sessionId!),
    onSuccess: () => navigate(`/interview/feedback/${sessionId}`, { replace: true }),
  });

  // Walk the step labels forward while we wait. Stops at the last one rather
  // than looping, so it never looks like progress is restarting.
  useEffect(() => {
    if (data?.status === "ready" || data?.status === "failed") return;
    const timer = window.setInterval(() => {
      setStepIndex((current) => Math.min(current + 1, STEPS.length - 1));
    }, STEP_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [data?.status]);

  useEffect(() => {
    const timer = window.setTimeout(() => setStalled(true), STALL_TIMEOUT_MS);
    return () => window.clearTimeout(timer);
  }, []);

  useEffect(() => {
    if (data?.status === "ready" && sessionId) {
      navigate(`/interview/feedback/${sessionId}`, { replace: true });
    }
  }, [data?.status, sessionId, navigate]);

  // Ticks on its own rather than piggybacking on the poll, so the elapsed
  // counter stays truthful even if polling stalls.
  useEffect(() => {
    if (data?.status === "ready") return;
    const timer = window.setInterval(() => {
      setElapsedSeconds(Math.floor((Date.now() - mountedAt.current) / 1000));
    }, 1000);
    return () => window.clearInterval(timer);
  }, [data?.status]);

  const failureMessage =
    data?.status === "failed"
      ? "Something went wrong while writing your report."
      : error instanceof ApiError && error.status !== 404
        ? error.message
        : null;

  const showRetry = Boolean(failureMessage) || stalled || data?.status === "pending";

  return (
    <div className="relative flex min-h-[78vh] items-center justify-center">
      {/* The report being written is the only thing happening, so this screen
          gets the object close and centred behind it. */}

      <div className="relative z-10 mx-auto flex w-full max-w-xl flex-col gap-6">
        <Card tone="glow" className="flex flex-col items-center gap-6 px-6 py-12 text-center">
          {/* Section 5.5: a real, calm progress indicator — not a fake progress
              bar that pretends to know how long this takes. */}
          <div className="relative flex h-20 w-20 items-center justify-center">
            <motion.span
              aria-hidden="true"
              className="absolute inset-0 rounded-full border-2 border-border"
              style={{ borderTopColor: "var(--color-accent)" }}
              animate={{ rotate: 360 }}
              transition={{ repeat: Infinity, duration: 1.2, ease: "linear" }}
            />
            <motion.span
              aria-hidden="true"
              className="absolute inset-[0.6rem] rounded-full border border-border"
              style={{ borderBottomColor: "var(--color-accent-2)" }}
              animate={{ rotate: -360 }}
              transition={{ repeat: Infinity, duration: 1.9, ease: "linear" }}
            />
            <span
              aria-hidden="true"
              className="h-2.5 w-2.5 rounded-full"
              style={{ background: "linear-gradient(140deg, var(--grad-a), var(--grad-b))" }}
            />
          </div>

          <div>
            <p className="marker mb-3 text-[0.625rem] text-text-subtle">Generating report</p>
            <h1 className="display text-2xl text-text sm:text-3xl">Putting your feedback together</h1>
            {endReason && <p className="mt-3 text-sm text-text-muted">{END_REASON_COPY[endReason]}</p>}
          </div>

          <ul className="flex w-full max-w-xs flex-col gap-3.5 text-left" aria-live="polite">
            {STEPS.map((step, index) => {
              const isActive = index === stepIndex;
              const isDone = index < stepIndex;
              return (
                <li key={step} className="flex items-center gap-3 text-sm">
                  <span
                    className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border text-[0.625rem] font-semibold transition-colors duration-300 ${
                      isDone
                        ? "border-success/45 bg-success/12 text-success"
                        : isActive
                          ? "border-accent bg-accent-soft text-accent"
                          : "border-border text-text-subtle"
                    }`}
                  >
                    {isDone ? (
                      <svg viewBox="0 0 24 24" className="h-3 w-3" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
                        <path strokeLinecap="round" strokeLinejoin="round" d="m5 13 4 4L19 7" />
                      </svg>
                    ) : (
                      index + 1
                    )}
                  </span>
                  <span className={isActive || isDone ? "text-text" : "text-text-subtle"}>{step}</span>
                  {isActive && (
                    <span
                      aria-hidden="true"
                      className="ml-auto h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-accent"
                    />
                  )}
                </li>
              );
            })}
          </ul>

          <p className="max-w-sm text-xs leading-relaxed text-text-subtle">
            This usually takes a few seconds. You can leave this page — your report will be waiting under
            Interview History.
            {elapsedSeconds > 15 ? ` (${elapsedSeconds}s so far)` : ""}
          </p>
        </Card>

        {failureMessage && (
          <Banner tone="error">
            {failureMessage} Your transcript and per-answer scores are safe — only the written summary is
            missing.
          </Banner>
        )}

        {stalled && !failureMessage && (
          <Banner tone="info">
            This is taking longer than expected. You can wait, or ask for the report again.
          </Banner>
        )}

        {showRetry && (
          <div className="flex flex-col gap-3 sm:flex-row">
            <Button variant="primary" onClick={() => retry.mutate()} loading={retry.isPending}>
              Generate my report
            </Button>
            <Button variant="ghost" onClick={() => navigate(`/interview/feedback/${sessionId}`, { replace: true })}>
              Skip to transcript
            </Button>
          </div>
        )}

        {retry.error instanceof ApiError && <Banner tone="error">{retry.error.message}</Banner>}
      </div>
    </div>
  );
}

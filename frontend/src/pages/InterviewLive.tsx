import { AnimatePresence, motion } from "framer-motion";
import { useQuery } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { AiAvatar } from "../components/AiAvatar";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Modal } from "../components/ui/Modal";
import { Spinner } from "../components/ui/Spinner";
import { useInterviewOrchestrator } from "../hooks/useInterviewOrchestrator";
import { useSignRecognition } from "../hooks/useSignRecognition";
import { SignAssist } from "../components/interview/SignAssist";
import { CodePanel } from "../components/interview/CodePanel";
import {
  endInterview as endInterviewRest,
  getInterview,
  submitExpressionSignals,
  submitProsodySignals,
} from "../services/interviewApi";
import type { InterviewMode } from "../types/interview";

function formatTime(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = Math.floor(totalSeconds % 60);
  return `${minutes}:${seconds.toString().padStart(2, "0")}`;
}

/** Icon-first control, so the bar survives narrow viewports without wrapping into two rows. */
function ControlButton({
  label,
  onClick,
  disabled,
  title,
  tone = "neutral",
  icon,
  compact = false,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  title?: string;
  tone?: "neutral" | "danger";
  icon: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title ?? label}
      aria-label={label}
      className={`flex items-center gap-2 rounded-control border px-3.5 py-2.5 text-sm font-medium transition-all duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${
        tone === "danger"
          ? "border-danger/50 text-danger hover:bg-danger hover:text-white"
          : "border-border text-text-muted hover:border-border-strong hover:bg-surface-raised hover:text-text"
      }`}
    >
      {icon}
      <span className={compact ? "hidden sm:inline" : ""}>{label}</span>
    </button>
  );
}

const ICONS = {
  check: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="m5 13 4 4L19 7" />
    </svg>
  ),
  mic: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm7-4a7 7 0 0 1-14 0m7 7v3" />
    </svg>
  ),
  micOff: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Zm7-4a7 7 0 0 1-14 0m7 7v3M4 4l16 16" />
    </svg>
  ),
  pause: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" d="M9 5v14M15 5v14" />
    </svg>
  ),
  play: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M7 4.5v15l12-7.5z" />
    </svg>
  ),
  skip: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M5 5l9 7-9 7zM19 5v14" />
    </svg>
  ),
  end: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 6l12 12M18 6 6 18" />
    </svg>
  ),
  captions: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <rect x="3" y="5" width="18" height="14" rx="2" />
      <path strokeLinecap="round" d="M8 11.5h2.5M8 14.5h4M14 11.5h2M15 14.5h1" />
    </svg>
  ),
  code: (
    <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
      <path strokeLinecap="round" strokeLinejoin="round" d="m9 8-4 4 4 4m6-8 4 4-4 4" />
    </svg>
  ),
};

/**
 * Resolves the session's modality before the room mounts.
 *
 * Read from the server rather than from the setup store, which is deliberately
 * in-memory and does not survive a refresh. The mode decides whether a
 * microphone is requested at all and whether the question is spoken aloud, so
 * guessing it and correcting a moment later would mean a signed interview
 * briefly asking for a mic and reading a question out loud to a candidate who
 * cannot hear it. Worth the one request.
 */
export function InterviewLive() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();

  const { data, isPending, isError } = useQuery({
    queryKey: ["interviewSession", sessionId],
    queryFn: () => getInterview(sessionId!),
    enabled: Boolean(sessionId),
    // The modality of a session cannot change once it has started, so this is
    // fetched once and never revalidated mid-interview.
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  if (!sessionId || isError) {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center gap-4 bg-bg px-6">
        <Banner tone="error">Couldn't load this interview session.</Banner>
        <Button variant="secondary" onClick={() => navigate("/interview/setup", { replace: true })}>
          Back to setup
        </Button>
      </div>
    );
  }

  if (isPending || !data) {
    return (
      <div className="fixed inset-0 flex flex-col items-center justify-center gap-3 bg-bg">
        <Spinner className="text-accent" />
        <p className="text-sm text-text-muted">Preparing your interview…</p>
      </div>
    );
  }

  return <InterviewRoom sessionId={sessionId} mode={data.mode} />;
}

function InterviewRoom({ sessionId, mode }: { sessionId: string; mode: InterviewMode }) {
  const navigate = useNavigate();
  const signMode = mode === "sign";

  const videoRef = useRef<HTMLVideoElement>(null);
  // The same element, also held in state. Section 9.7's expression analyser needs
  // to know *when* the preview exists, and a ref alone never triggers a render —
  // so the orchestrator would be handed null on the only pass that mattered. The
  // callback ref keeps `videoRef` working exactly as before for the srcObject
  // assignment below and adds a reactive copy alongside it.
  const [videoEl, setVideoEl] = useState<HTMLVideoElement | null>(null);
  const attachVideo = useCallback((node: HTMLVideoElement | null) => {
    videoRef.current = node;
    setVideoEl(node);
  }, []);
  const streamRef = useRef<MediaStream | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [showCaptions, setShowCaptions] = useState(true);
  const [showEndConfirm, setShowEndConfirm] = useState(false);
  const [draft, setDraft] = useState("");
  const [showCodePanel, setShowCodePanel] = useState(false);
  const [fingerspelling, setFingerspelling] = useState(false);

  useEffect(() => {
    navigator.mediaDevices
      // No microphone in sign mode: nothing listens, so nothing is captured.
      .getUserMedia({ video: true, audio: !signMode })
      .then((media) => {
        streamRef.current = media;
        setStream(media);
        if (videoRef.current) videoRef.current.srcObject = media;
      })
      .catch(() => {
        // Device access was already confirmed on the precheck screen — a
        // failure here means it was revoked mid-flow; the orchestrator
        // still runs (mic-level/barge-in just stay inert without a stream).
      });
    return () => {
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
  }, [signMode]);

  const wsPath = `/api/v1/interviews/${sessionId}/live`;
  const {
    phase,
    questionText,
    sequenceOrder,
    totalQuestions,
    captionText,
    asrLowConfidence,
    elapsedSeconds,
    totalSeconds,
    isMuted,
    isFollowup,
    endReason,
    errorMessage,
    measureProsody,
    measureExpression,
    expressionStatus,
    usingHttpFallback,
    actions,
  } = useInterviewOrchestrator({ wsPath, sessionId, mode, micStream: stream, videoElement: videoEl });

  useEffect(() => {
    if (phase === "ended") {
      // Section 4.10: the interview hands off to the processing screen, which
      // polls until the report is ready and then forwards to Section 4.11's
      // report. Going straight to the report would race the generation job.
      navigate(`/interview/processing/${sessionId}`, { replace: true, state: { endReason } });
    }
  }, [phase, sessionId, navigate, endReason]);

  // A new question means a new answer. Clearing on `questionText` rather than
  // only after a submit also covers the skip path and a follow-up arriving.
  useEffect(() => {
    setDraft("");
  }, [questionText]);

  function handleSubmitDraft() {
    if (draft.trim().length === 0) return;
    actions.submitComposedAnswer(draft);
    setDraft("");
  }

  // Hand recognition, sign mode only. Gated on `composing` as well as on the
  // mode: a candidate whose hand drifts through an open palm while the
  // interviewer is still thinking has not asked to submit anything.
  const signTurn = signMode && phase === "composing";
  const sign = useSignRecognition(signMode ? videoEl : null, {
    fingerspelling: signTurn && fingerspelling,
    // Never both at once — the trained gestures share handshapes with the
    // letters, so ✌️ would fire a control action every time a V was spelled.
    gestures: signTurn && !fingerspelling,
    onLetter: (letter) => setDraft((current) => current + letter),
    onControl: (action) => {
      if (action === "submit") handleSubmitDraft();
      else actions.skip();
    },
  });

  async function handleEndNow() {
    try {
      await endInterviewRest(sessionId);
      // Only reachable from the error screen, where the WebSocket is already
      // gone — so the final prosody aggregate has to travel over HTTP, and only
      // after `/end` has run (the endpoint refuses a session still in progress).
      //
      // This is a best-effort top-up, not the primary path: `/end` starts report
      // generation as a background task, so a row arriving now may land after
      // scoring has read the table. The in-session updates already sent over the
      // socket are what the report normally scores; this exists so the stored
      // signals are still right for a later regenerate.
      //
      // Both are awaited together rather than in sequence, and neither failure
      // blocks the navigation — a signal that did not record is a missing score,
      // not a reason to trap the candidate on a broken screen.
      await Promise.allSettled([
        // Skipped in sign mode: the endpoint refuses prosody for a signed
        // session, because there was no audio to have measured it from.
        ...(signMode ? [] : [submitProsodySignals(sessionId, measureProsody())]),
        submitExpressionSignals(sessionId, measureExpression()),
      ]);
    } finally {
      navigate(`/interview/processing/${sessionId}`, { replace: true, state: { endReason: "ended_by_candidate" } });
    }
  }

  const isCandidateTurn = phase === "listening" || phase === "composing";
  const avatarState = phase === "ai_speaking" ? "speaking" : isCandidateTurn ? "listening" : "idle";
  const progressPct = totalSeconds > 0 ? Math.min(100, (elapsedSeconds / totalSeconds) * 100) : 0;

  const turnLabel =
    phase === "ai_speaking"
      ? "Interviewer speaking"
      : isCandidateTurn
        ? "Your turn"
        : phase === "evaluating"
          ? "Considering your answer"
          : phase === "paused"
            ? "Paused"
            : phase === "reconnecting"
              ? "Reconnecting"
              : null;

  return (
    <div className="fixed inset-0 flex flex-col overflow-hidden bg-bg">
      {/* Progress rail */}
      <div className="h-[3px] w-full shrink-0 bg-surface-raised">
        <div
          className="h-full transition-[width] duration-500 ease-out"
          style={{
            width: `${progressPct}%`,
            background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))",
          }}
        />
      </div>

      {/* Header rail: state and clock, always visible without stealing focus. */}
      <div className="flex shrink-0 items-center justify-between gap-4 px-5 py-3.5 sm:px-8">
        <div className="flex items-center gap-3">
          {turnLabel && (
            <span className="inline-flex items-center gap-2 rounded-pill border border-border bg-surface/70 px-3 py-1.5 text-xs font-medium text-text-muted backdrop-blur-md">
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 rounded-full ${
                  isCandidateTurn
                    ? "bg-success"
                    : phase === "reconnecting"
                      ? "bg-warning"
                      : phase === "paused"
                        ? "bg-text-subtle"
                        : "bg-accent"
                }`}
              />
              {turnLabel}
            </span>
          )}
          {isMuted && (
            <span className="inline-flex items-center gap-1.5 rounded-pill border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning">
              Muted
            </span>
          )}
          {/* Said here, and not only in the report, because here it is still
              actionable: a candidate who learns their camera was off can turn it
              on, where the same sentence on the report is only an explanation for
              a blank row. The reason is in the tooltip rather than the chip so
              the rail cannot be pushed into wrapping by a long message. */}
          {/* Section 6.6. Said plainly rather than hidden: this network refused
              the live connection, so the session is running on a slower
              transport and a candidate who notices the lag deserves the reason. */}
          {usingHttpFallback && (
            <span
              title="This network blocked the live connection, so the interview is running over standard HTTP. Everything works; replies may take a moment longer."
              className="hidden items-center gap-1.5 rounded-pill border border-warning/40 bg-warning/10 px-3 py-1.5 text-xs font-medium text-warning sm:inline-flex"
            >
              Limited connection
            </span>
          )}
          {expressionStatus.state === "unavailable" && (
            <span
              title={expressionStatus.reason}
              className="hidden items-center gap-1.5 rounded-pill border border-border bg-surface/70 px-3 py-1.5 text-xs font-medium text-text-subtle sm:inline-flex"
            >
              Body language not measured
            </span>
          )}
        </div>
        <span className="tnum text-sm text-text-muted">
          <span className="text-text">{formatTime(elapsedSeconds)}</span> / {formatTime(totalSeconds)}
        </span>
      </div>

      <div className="relative flex min-h-0 flex-1 flex-col gap-4 px-5 py-3 sm:px-8 lg:flex-row">
        <div className="relative flex min-h-0 flex-1 flex-col items-center justify-center gap-8 overflow-y-auto">
          {/* The room the candidate is "in" is the same space as the rest of the
              product. Intensity is held low — this screen is a conversation, and
              the environment must not pull attention off the question. */}

          {phase === "reconnecting" && (
            <div className="absolute top-2 left-1/2 z-10 w-full max-w-sm -translate-x-1/2 px-4">
              <Banner tone="warning">Reconnecting…</Banner>
            </div>
          )}

          {phase === "error" && (
            <div className="relative flex w-full max-w-md flex-col items-center gap-4">
              <Banner tone="error">{errorMessage ?? "Something went wrong."}</Banner>
              <Button variant="danger" onClick={handleEndNow}>
                End Interview Now
              </Button>
            </div>
          )}

          {phase !== "error" && (
            <>
              <div className="relative">
                <AiAvatar state={avatarState} />
              </div>

              {questionText && (
                <div className="relative max-w-2xl text-center">
                  {sequenceOrder !== null && totalQuestions !== null && (
                    <p className="mb-3 text-[0.6875rem] font-semibold tracking-[0.16em] text-text-subtle uppercase">
                      {/* A follow-up isn't "question N of M" — it's a probe on
                          the question just asked, and numbering it as a new
                          question would misrepresent the interview's shape. */}
                      {isFollowup ? "Follow-up" : `Question ${sequenceOrder + 1} of ${totalQuestions}`}
                    </p>
                  )}
                  <motion.p
                    key={questionText}
                    initial={{ opacity: 0, y: 8 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={{ duration: 0.35, ease: [0.22, 1, 0.36, 1] }}
                    className="text-xl leading-snug font-medium text-text sm:text-2xl"
                  >
                    {questionText}
                  </motion.p>
                </div>
              )}

              {/* Section 10.1's EVALUATING state, made visible so the pause
                  between the candidate's answer and the next question reads as
                  the interviewer thinking rather than as the app hanging. */}
              {phase === "evaluating" && (
                <div className="relative flex items-center gap-2.5 rounded-pill border border-border bg-surface/70 px-4 py-2 text-sm text-text-muted backdrop-blur-md">
                  <Spinner className="text-accent" />
                  <span>Considering your answer…</span>
                </div>
              )}

              {phase === "paused" && (
                <p className="relative text-sm text-text-muted">Interview paused. Resume when ready.</p>
              )}

              {/* Section 4.8's answer turn, signed. The candidate composes at their
                  own pace: nothing is captured until they submit, there is no
                  silence watchdog deciding they have finished, and the only clock
                  is the interview's own. */}
              {signMode && phase === "composing" && (
                <div className="relative w-full max-w-2xl">
                  <label htmlFor="signed-answer" className="mb-2 block text-xs font-medium text-text-muted">
                    Your answer
                  </label>
                  <textarea
                    id="signed-answer"
                    value={draft}
                    onChange={(event) => setDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                        event.preventDefault();
                        handleSubmitDraft();
                      }
                    }}
                    rows={5}
                    autoFocus
                    placeholder="Take as long as you need — the only clock is the interview's."
                    className="w-full resize-y rounded-control border border-border bg-surface px-3.5 py-3 text-sm leading-relaxed text-text placeholder:text-text-subtle focus:border-border-strong focus:ring-2 focus:ring-accent/30 focus:outline-none"
                  />
                  <div className="mt-2.5 flex flex-wrap items-center justify-between gap-3">
                    <span className="text-xs text-text-subtle">
                      {draft.trim() ? draft.trim().split(/\s+/).length : 0} words
                      <span className="hidden sm:inline"> · Ctrl+Enter to submit</span>
                    </span>
                    <Button size="sm" onClick={handleSubmitDraft} disabled={draft.trim().length === 0}>
                      Submit answer
                    </Button>
                  </div>

                  <SignAssist
                    status={sign.status}
                    pending={sign.pending}
                    arming={sign.arming}
                    handPresent={sign.handPresent}
                    fingerspelling={fingerspelling}
                    onToggleFingerspelling={() => setFingerspelling((on) => !on)}
                  />
                </div>
              )}

              <AnimatePresence>
                {showCaptions && captionText && (
                  <motion.div
                    initial={{ opacity: 0, y: 10 }}
                    animate={{ opacity: 1, y: 0 }}
                    exit={{ opacity: 0, y: 10 }}
                    transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
                    className="relative max-w-xl rounded-control border border-border bg-surface/85 px-4 py-3 text-center text-sm leading-relaxed text-text-muted backdrop-blur-md"
                  >
                    {captionText}
                    {/* Warn, do not interrupt. The turn still submits on its own
                        -- stopping to confirm every uncertain sentence would
                        make a spoken interview unusable -- but the candidate
                        gets to see that the transcript is shaky while there is
                        still something they can do about it. */}
                    {asrLowConfidence && (
                      <span className="mt-2 block text-xs text-warning">
                        Speech recognition is unsure of this — if the text above is wrong, your
                        language setting in the device check is the usual cause.
                      </span>
                    )}
                  </motion.div>
                )}
              </AnimatePresence>
            </>
          )}
        </div>

        {/* Section 4.8B. Sits beside the conversation on a wide screen and
            below it on a narrow one, so opening the panel never pushes the
            question off-screen. */}
        <div
          className={
            showCodePanel
              ? "h-64 min-h-0 shrink-0 sm:h-72 lg:h-auto lg:w-[38%] lg:min-w-[22rem]"
              : "hidden"
          }
        >
          <CodePanel onShare={actions.shareCodePanel} onClose={() => setShowCodePanel(false)} />
        </div>
      </div>

      {/* Candidate self-view. Sits above the control bar on every breakpoint,
          and shrinks on mobile so it never covers the question. */}
      <video
        ref={attachVideo}
        autoPlay
        muted
        playsInline
        aria-label="Your camera preview"
        className="pointer-events-none fixed right-4 bottom-[7.5rem] z-10 aspect-video w-28 rounded-control border border-border bg-black object-cover shadow-[var(--shadow-lg)] sm:right-8 sm:bottom-[8.5rem] sm:w-44"
      />

      {/* Controls — a floating glass bar rather than a docked toolbar, so the
          interview reads as an open space with a console in it. */}
      <div className="pointer-events-none relative z-20 shrink-0 px-4 pb-4 sm:px-8 sm:pb-6">
        <div className="pointer-events-auto rounded-card border border-border bg-bg-elevated mx-auto flex max-w-4xl flex-wrap items-center justify-center gap-2 px-2 py-2 sm:gap-2">
          {/* No microphone is open in a signed interview, so a mute control
              would be a switch attached to nothing. Same for captions: there is
              no live transcription to caption. */}
          {!signMode && (
            <ControlButton
              label={isMuted ? "Unmute" : "Mute"}
              icon={isMuted ? ICONS.micOff : ICONS.mic}
              onClick={actions.toggleMute}
              disabled={phase === "error"}
              compact
            />
          )}
          <ControlButton
            label={phase === "paused" ? "Resume" : "Pause"}
            icon={phase === "paused" ? ICONS.play : ICONS.pause}
            onClick={phase === "paused" ? actions.resume : actions.pause}
            // Pausing mid-evaluation would leave an in-flight LLM call with
            // nowhere to land, so the control waits for the turn to resolve.
            disabled={phase === "error" || phase === "reconnecting" || phase === "evaluating"}
            compact
          />
          {/* The candidate's own end-of-answer. Listed before Skip because it
              is the common action, and because an interviewer that waits for
              you is the whole point -- the silence timer is now the fallback,
              not the mechanism. Voice only: a typed answer already has its own
              Submit button. */}
          {!signMode && (
            <ControlButton
              label="Done Answering"
              icon={ICONS.check}
              onClick={actions.finishAnswer}
              disabled={!isCandidateTurn}
              title="Submit this answer now instead of waiting for the pause to be detected"
            />
          )}
          <ControlButton
            label="Skip / I Don't Know"
            icon={ICONS.skip}
            onClick={actions.skip}
            disabled={!isCandidateTurn}
            title="Only available while it's your turn to answer"
          />
          <ControlButton
            label={showCodePanel ? "Hide Code" : "Code / Whiteboard"}
            icon={ICONS.code}
            onClick={() => setShowCodePanel((open) => !open)}
            title="Scratch space for code and diagrams"
            compact
          />
          {!signMode && (
            <ControlButton
              label={`Captions ${showCaptions ? "On" : "Off"}`}
              icon={ICONS.captions}
              onClick={() => setShowCaptions((v) => !v)}
              compact
            />
          )}
          <ControlButton
            label="End Interview"
            icon={ICONS.end}
            tone="danger"
            onClick={() => setShowEndConfirm(true)}
          />
        </div>
      </div>

      <Modal
        open={showEndConfirm}
        onClose={() => setShowEndConfirm(false)}
        title="End interview early?"
        description="Are you sure you want to end the interview early? You'll still be able to review what's completed so far."
        footer={
          <>
            <Button variant="ghost" onClick={() => setShowEndConfirm(false)}>
              Cancel
            </Button>
            <Button variant="danger" onClick={actions.endInterview}>
              End Interview
            </Button>
          </>
        }
      />
    </div>
  );
}

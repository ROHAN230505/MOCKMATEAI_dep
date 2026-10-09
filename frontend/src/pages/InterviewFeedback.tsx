import { useState } from "react";
import { motion } from "framer-motion";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate, useParams } from "react-router-dom";
import { BeforeAfter } from "../components/feedback/BeforeAfter";
import { FeedbackItemList } from "../components/feedback/FeedbackItemList";
import { ScoreBreakdown } from "../components/feedback/ScoreBreakdown";
import { ReadinessRing } from "../components/ReadinessRing";
import { Badge } from "../components/ui/Badge";
import { isLowConfidence } from "../hooks/useSpeechRecognition";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { EmptyState, ErrorState, Skeleton } from "../components/ui/States";
import { ApiError } from "../lib/apiClient";
import {
  downloadFeedbackPdf,
  downloadTranscript,
  generateFeedbackReport,
  getFeedbackReport,
} from "../services/feedbackApi";
import { useInterviewSetupStore } from "../store/interviewSetupStore";
import type { TranscriptTurn } from "../types/feedback";
import type { InterviewMode } from "../types/interview";

type Tab = "overview" | "feedback" | "transcript";

const TABS: { id: Tab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "feedback", label: "Strengths & Improvements" },
  { id: "transcript", label: "Question by Question" },
];

function TurnCard({ turn }: { turn: TranscriptTurn }) {
  const hasScores = turn.relevanceScore !== null || turn.completenessScore !== null;
  // Warn, do not hide. The scores below were computed from this text, so if the
  // text is wrong the scores are wrong, and the candidate is the only one who
  // can tell. Saying so is the difference between a low score they can act on
  // and a low score that is simply untrue.
  const misheard = isLowConfidence(turn.asrConfidenceAvg) && !turn.isSkipped && Boolean(turn.answerText);
  return (
    <Card className={turn.isFollowup ? "sm:ml-8 sm:border-l-2 sm:border-l-accent/40" : undefined}>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <span className="text-[0.6875rem] font-semibold tracking-[0.14em] text-text-subtle uppercase">
          {turn.isFollowup ? "Follow-up" : `Question ${turn.number}`}
        </span>
        {/* Section 4.11: the breakdown shows where a follow-up was triggered. */}
        {turn.isFollowup && <Badge tone="accent">Probed deeper</Badge>}
      </div>
      <p className="mb-3.5 text-sm leading-relaxed font-medium text-text">{turn.questionText}</p>

      {turn.isSkipped ? (
        /* Section 4.8: a skip is a neutral badge, never styled like a weak answer. */
        <Badge tone="neutral">Skipped — not counted against you</Badge>
      ) : turn.answerText ? (
        <>
          <p className="text-sm leading-relaxed text-text-muted">{turn.answerText}</p>
          {misheard && (
            <p className="mt-2.5 flex items-start gap-2 text-xs leading-relaxed text-warning">
              <svg viewBox="0 0 24 24" className="mt-0.5 h-3.5 w-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v4m0 3h.01M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
              </svg>
              <span>
                Speech recognition was unsure of this answer, so the transcript above may not be what you
                said — and the scores were computed from that transcript. If it looks wrong, the language
                setting in the device check is the usual cause.
              </span>
            </p>
          )}
        </>
      ) : (
        <p className="text-sm text-text-subtle italic">No answer recorded.</p>
      )}

      {/* Scores appear only where they exist: a skip carries none by design
          (Section 9.3), and showing a "0" there would conflate the two. */}
      {hasScores && !turn.isSkipped && (
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 border-t border-border pt-3.5 text-xs text-text-muted">
          <span>
            Relevance <span className="tnum font-semibold text-text">{turn.relevanceScore}/10</span>
          </span>
          <span>
            Completeness <span className="tnum font-semibold text-text">{turn.completenessScore}/10</span>
          </span>
        </div>
      )}
    </Card>
  );
}

function SignalTile({ label, value, meta }: { label: string; value: string; meta?: string }) {
  return (
    <div className="rounded-control border border-border bg-surface-sunken px-4 py-3.5">
      <dt className="text-xs text-text-muted">{label}</dt>
      <dd className="tnum mt-1 text-lg leading-none font-semibold text-text">{value}</dd>
      {meta && <dd className="mt-1.5 text-xs text-text-subtle">{meta}</dd>}
    </div>
  );
}

/**
 * Backs `/interview/feedback/:sessionId` — Section 4.11's structured feedback
 * report, replacing Phase 2's transcript-only placeholder at the same URL.
 *
 * Two presentation rules carried through from the backend, because a report is
 * only as honest as the screen that renders it:
 *
 * - Unmeasured categories are shown as unmeasured, with a reason. They are not
 *   hidden (which would let a candidate assume they were scored) and not zeroed.
 * - When the narrative was written deterministically rather than by a model,
 *   the report says so.
 */
const CATEGORY_WORDS: Record<string, string> = {
  content: "content",
  communication: "communication",
  confidence: "confidence",
  body_language: "body language",
};

/** What each category would have needed, phrased for a candidate. */
const CATEGORY_NEEDS: Record<string, string> = {
  content: "scored answers",
  communication: "a captured transcript",
  confidence: "voice-tone analysis",
  body_language: "video analysis",
};

/**
 * Categories a modality never had a signal for, keyed by mode.
 *
 * Kept separate from `CATEGORY_NEEDS` because these are not gaps. Listing
 * confidence as "needing voice-tone analysis, which this session didn't record"
 * would tell a signing candidate to go and fix a deliberate design decision.
 */
const INAPPLICABLE_BY_MODE: Partial<Record<InterviewMode, string[]>> = {
  sign: ["confidence"],
};

const MODE_EXPLANATION: Partial<Record<InterviewMode, string>> = {
  sign: "a signed interview has no audio to measure tone from",
};

function joinWords(items: string[]): string {
  if (items.length === 0) return "";
  if (items.length === 1) return items[0];
  return `${items.slice(0, -1).join(", ")} and ${items[items.length - 1]}`;
}

/** The category words are lowercase for mid-sentence use; this one starts one. */
const sentenceCase = (text: string): string => text.charAt(0).toUpperCase() + text.slice(1);

/**
 * Which categories this report is scored on, and what the rest would have needed.
 *
 * Built from the response rather than written out, because which categories are
 * missing genuinely varies now. Before Phase 5 it was always the same two, and
 * the copy said so in fixed words; a candidate whose voice was analysed but whose
 * camera was off would have read that their confidence wasn't measured either,
 * with a real score sitting on screen directly above it.
 */
function CoverageNote({
  measured,
  unmeasured,
  mode,
}: {
  measured: string[];
  unmeasured: string[];
  mode: InterviewMode;
}) {
  const inapplicable = INAPPLICABLE_BY_MODE[mode] ?? [];
  const notApplicable = unmeasured.filter((category) => inapplicable.includes(category));
  const notRecorded = unmeasured.filter((category) => !inapplicable.includes(category));

  const scored = measured.map((category) => CATEGORY_WORDS[category] ?? category);
  const missing = notRecorded.map((category) => CATEGORY_WORDS[category] ?? category);
  const needs = [
    ...new Set(notRecorded.map((category) => CATEGORY_NEEDS[category] ?? "signals this session didn't record")),
  ];
  const byDesign = notApplicable.map((category) => CATEGORY_WORDS[category] ?? category);

  return (
    <>
      {scored.length > 0 && `This report is scored on ${joinWords(scored)}. `}
      {missing.length > 0 &&
        `${sentenceCase(joinWords(missing))} ${missing.length > 1 ? "need" : "needs"} ${joinWords(needs)}, which this session didn't record — so ${missing.length > 1 ? "they're" : "it's"} left blank rather than guessed at. `}
      {byDesign.length > 0 &&
        `${sentenceCase(joinWords(byDesign))} ${byDesign.length > 1 ? "aren't" : "isn't"} scored in this format because ${MODE_EXPLANATION[mode] ?? "this format has no such signal"} — by design, not a gap in your session.`}
    </>
  );
}

export function InterviewFeedback() {
  const { sessionId } = useParams<{ sessionId: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const setSetup = useInterviewSetupStore((s) => s.setSetup);
  const [tab, setTab] = useState<Tab>("overview");
  const [downloadError, setDownloadError] = useState<string | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["feedbackReport", sessionId],
    queryFn: () => getFeedbackReport(sessionId!),
    enabled: Boolean(sessionId),
    retry: false,
  });

  const generate = useMutation({
    mutationFn: () => generateFeedbackReport(sessionId!),
    onSuccess: (report) => queryClient.setQueryData(["feedbackReport", sessionId], report),
  });

  const download = useMutation({
    mutationFn: async (kind: "pdf" | "txt" | "json") => {
      setDownloadError(null);
      if (kind === "pdf") return downloadFeedbackPdf(sessionId!);
      return downloadTranscript(sessionId!, kind);
    },
    onError: (err) =>
      setDownloadError(err instanceof ApiError ? err.message : "Couldn't prepare that download."),
  });

  function handleRetake() {
    if (!data) return;
    setSetup({
      role: data.roleTarget,
      type: data.interviewType,
      durationMinutes: data.durationMinutes,
      mode: data.mode,
    });
    navigate("/interview/setup");
  }

  if (isLoading) {
    return (
      <div className="mx-auto flex max-w-4xl flex-col gap-6">
        <Skeleton className="h-9 w-64" />
        <Card className="flex flex-col items-center gap-6 sm:flex-row">
          <Skeleton className="h-[168px] w-[168px] shrink-0 rounded-full" />
          <div className="flex w-full flex-col gap-3">
            <Skeleton className="h-3.5 w-24" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-5/6" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        </Card>
        <Card>
          <Skeleton className="h-3.5 w-32" />
          <div className="mt-6 flex flex-col gap-5">
            {[0, 1, 2, 3].map((index) => (
              <div key={index} className="flex flex-col gap-2">
                <Skeleton className="h-3 w-28" />
                <Skeleton className="h-2 w-full rounded-pill" />
              </div>
            ))}
          </div>
        </Card>
      </div>
    );
  }

  // No report yet is a normal state, not a failure: an interview abandoned by
  // closing the tab never triggered generation. Offer to generate it.
  if (error instanceof ApiError && error.code === "feedback_not_generated") {
    return (
      <div className="mx-auto flex max-w-xl flex-col gap-6">
        <EmptyState
          icon={
            <svg viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path strokeLinecap="round" strokeLinejoin="round" d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8zM14 3v5h5" />
            </svg>
          }
          title="No report for this interview yet"
          description="Your transcript is saved. Generate the scored report whenever you're ready."
          action={
            <Button variant="primary" onClick={() => generate.mutate()} loading={generate.isPending}>
              Generate my report
            </Button>
          }
        />
        {generate.error instanceof ApiError && <Banner tone="error">{generate.error.message}</Banner>}
      </div>
    );
  }

  if (error || !data) {
    return (
      <ErrorState
        title="Couldn't load this report"
        message={error instanceof ApiError ? error.message : "Couldn't load this feedback report."}
        action={
          <Link to="/interview/history">
            <Button variant="secondary">Back to history</Button>
          </Link>
        }
      />
    );
  }

  const startedAt = data.startedAt ? new Date(data.startedAt).toLocaleString() : null;
  const isDeterministic = data.generatedBy === "deterministic";

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-4">
      <PageHeader
        eyebrow="Feedback report"
        title={data.roleTarget}
        description={
          [data.interviewType, data.targetCompanyName, startedAt].filter(Boolean).join(" · ") || undefined
        }
        actions={
          <>
            <Button
              variant="secondary"
              size="sm"
              onClick={() => download.mutate("pdf")}
              loading={download.isPending && download.variables === "pdf"}
              icon={
                <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 3v12m0 0 4-4m-4 4-4-4M5 19h14" />
                </svg>
              }
            >
              PDF
            </Button>
            <Button variant="outline" size="sm" onClick={() => download.mutate("txt")}>
              Transcript .txt
            </Button>
            <Button variant="ghost" size="sm" onClick={() => download.mutate("json")}>
              .json
            </Button>
          </>
        }
      />

      {downloadError && <Banner tone="error">{downloadError}</Banner>}

      {/* --- Tabs --- */}
      <div role="tablist" aria-label="Feedback sections" className="-mx-4 overflow-x-auto px-4 sm:mx-0 sm:px-0">
        <div className="flex min-w-max gap-2 border-b border-border">
          {TABS.map((entry) => (
            <button
              key={entry.id}
              role="tab"
              type="button"
              aria-selected={tab === entry.id}
              onClick={() => setTab(entry.id)}
              className={`relative rounded-t-control px-5 py-3.5 text-body font-medium whitespace-nowrap transition-colors duration-200 ${
                tab === entry.id
                  ? "text-text"
                  : "text-text-muted hover:bg-surface-raised/60 hover:text-text"
              }`}
            >
              {entry.label}
              {tab === entry.id && (
                <motion.span
                  layoutId="feedback-tab"
                  transition={{ type: "spring", stiffness: 480, damping: 38 }}
                  className="grad-stroke absolute inset-x-3 -bottom-px h-[2px] rounded-pill"
                  aria-hidden="true"
                />
              )}
            </button>
          ))}
        </div>
      </div>

      {tab === "overview" && (
        <div className="flex flex-col gap-6">
          <Card tone="glow" className="relative overflow-hidden p-8 sm:p-10">
            <div className="relative flex flex-col items-center gap-10 sm:flex-row sm:items-start">
              <div className="shrink-0">
                {data.overallReadinessScore === null ? (
                  <div className="flex h-[180px] w-[180px] flex-col items-center justify-center rounded-full border border-dashed border-border text-center">
                    <span className="text-3xl text-text-subtle">—</span>
                    <span className="mt-1.5 px-6 text-xs leading-relaxed text-text-subtle">
                      Not enough answered material to score
                    </span>
                  </div>
                ) : (
                  <ReadinessRing score={data.overallReadinessScore} label={data.readinessLabel} size={190} />
                )}
              </div>
              <div className="flex-1">
                <h2 className="marker mb-3 text-[0.625rem] text-text-subtle">Summary</h2>
                <p className="text-base leading-relaxed text-text">
                  {data.summaryText ?? "No summary was written for this interview."}
                </p>
                <div className="mt-5 flex flex-wrap items-center gap-2">
                  <Badge tone="neutral">
                    {data.answeredCount} of {data.questionCount} answered
                  </Badge>
                  {data.skippedCount > 0 && <Badge tone="neutral">{data.skippedCount} skipped</Badge>}
                </div>
                <p className="mt-3 text-xs leading-relaxed text-text-subtle">
                  Skipped questions are left out of your scores entirely rather than counted as zero.
                </p>
              </div>
            </div>
          </Card>

          <Card>
            <CardHeader
              eyebrow="Readiness"
              title="Score breakdown"
              description="Each category shows the weight actually applied to your overall score."
            />
            <ScoreBreakdown scores={data.categoryScores} mode={data.mode} />
          </Card>

          {data.comparison && (
            <Card>
              <CardHeader eyebrow="Before & after" title="Since your last attempt" />
              <BeforeAfter comparison={data.comparison} />
            </Card>
          )}

          {data.signals && (
            <Card>
              <CardHeader
                eyebrow="Measured"
                title="What we measured in your speech"
                description="Drawn from the transcript itself — not estimated."
              />
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                <SignalTile
                  label="Filler words"
                  value={`${data.signals.fillerCount}`}
                  meta={`${data.signals.fillerRatePer100Words.toFixed(1)} per 100 words`}
                />
                <SignalTile
                  label="Average answer"
                  value={`${Math.round(data.signals.averageAnswerWords)}`}
                  meta="words"
                />
                <SignalTile
                  label="With a number"
                  value={`${data.signals.quantifiedAnswers}/${data.signals.answerCount}`}
                  meta="answers"
                />
                <SignalTile
                  label="Speaking pace"
                  value={
                    data.signals.speakingPaceWpm === null
                      ? "—"
                      : `${Math.round(data.signals.speakingPaceWpm)}`
                  }
                  meta={data.signals.speakingPaceWpm === null ? "not timed" : "words per minute"}
                />
              </dl>
            </Card>
          )}

          {isDeterministic && (
            <Banner tone="info" title="Rule-based analysis">
              No language model was available when this report was written, so the written analysis is
              rule-based. Your scores and the quoted evidence are real measurements of this session, but the
              wording is templated and can't judge whether an answer was technically correct.
            </Banner>
          )}

          <p className="text-xs leading-relaxed text-text-subtle">{data.disclaimer}</p>
        </div>
      )}

      {tab === "feedback" && (
        <div className="flex flex-col gap-6">
          <Card>
            <CardHeader
              eyebrow="Strengths"
              title="What worked"
              description="Each point cites the question and quotes what you actually said."
            />
            <FeedbackItemList
              items={data.strengths}
              tone="success"
              emptyMessage="No specific strengths were identified in this session."
            />
          </Card>
          <Card>
            <CardHeader
              eyebrow="Improvements"
              title="What to work on"
              description="Specific and actionable — take one into your next attempt."
            />
            <FeedbackItemList
              items={data.improvements}
              emptyMessage="No improvement points were identified in this session."
            />
          </Card>
          {data.unmeasuredCategories.length > 0 && (
            <p className="text-xs leading-relaxed text-text-subtle">
              <CoverageNote
                measured={data.measuredCategories}
                unmeasured={data.unmeasuredCategories}
                mode={data.mode}
              />
            </p>
          )}
        </div>
      )}

      {tab === "transcript" && (
        <div className="flex flex-col gap-4">
          {data.turns.length === 0 ? (
            <EmptyState title="No questions were asked in this session." />
          ) : (
            data.turns.map((turn) => <TurnCard key={turn.questionId} turn={turn} />)
          )}
          {/* Corrected. This previously read "runs in your browser and no audio is
              uploaded or stored", which is not true of the Web Speech API — Chrome
              streams microphone audio to Google to transcribe it. The device check
              already told the candidate that; a footer contradicting it turned an
              honest disclosure into a misleading one. */}
          <p className="text-xs leading-relaxed text-text-subtle">
            Your browser handled the speech-to-text — on most browsers, including Chrome, that means your
            audio went to the browser vendor&rsquo;s servers to be transcribed, not to ours. We stored only
            the text, so this transcript is the complete record we hold of this session.
          </p>
        </div>
      )}

      {/* --- Actions --- */}
      <div className="rule-fade" />
      <div className="flex flex-col gap-3 sm:flex-row">
        <Button variant="primary" onClick={handleRetake}>
          Retake This Interview
        </Button>
        <Button variant="ghost" onClick={() => generate.mutate()} loading={generate.isPending}>
          Regenerate report
        </Button>
        <Link to="/dashboard" className="sm:ml-auto">
          <Button variant="ghost">Back to Dashboard</Button>
        </Link>
      </div>
      {generate.error instanceof ApiError && <Banner tone="error">{generate.error.message}</Banner>}
    </div>
  );
}

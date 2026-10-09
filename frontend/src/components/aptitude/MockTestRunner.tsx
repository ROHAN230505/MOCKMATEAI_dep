import { useMutation } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { Badge } from "../ui/Badge";
import { Banner } from "../ui/Banner";
import { Button } from "../ui/Button";
import { Card } from "../ui/Card";
import { Modal } from "../ui/Modal";
import { PageHeader } from "../ui/PageHeader";
import { ApiError } from "../../lib/apiClient";
import { getAttemptTime, submitAptitudeAttempt } from "../../services/practiceApi";
import type { AptitudeResult, PaletteState, TimedAttempt } from "../../types/practice";
import { QuestionPalette } from "./QuestionPalette";

/**
 * A timed mock test (Sections 4.14, 11.1).
 *
 * ## The clock
 *
 * Ticked locally once a second so it reads smoothly, but **re-anchored to the
 * server** every 20 seconds and whenever the tab becomes visible again. Both
 * halves are needed: a purely local timer drifts and is throttled to a crawl in a
 * backgrounded tab (so a candidate could gain minutes by switching away), and a
 * purely polled one stutters. The server's `started_at` is the only thing that
 * decides how much time is left.
 *
 * ## Auto-submit
 *
 * At zero the test submits itself with whatever is filled in. Section 11.1 says
 * mock mode "mimics real test conditions", and in a real test the clock running
 * out ends it — it does not discard the paper. Everything answered still counts.
 */

const TICK_MS = 1000;
const RESYNC_MS = 20_000;

function formatClock(seconds: number): string {
  const safe = Math.max(0, seconds);
  const minutes = Math.floor(safe / 60);
  return `${minutes}:${String(safe % 60).padStart(2, "0")}`;
}

export function MockTestRunner({
  attempt,
  onFinished,
  onAbandon,
}: {
  attempt: TimedAttempt;
  onFinished: (result: AptitudeResult) => void;
  onAbandon: () => void;
}) {
  const [selections, setSelections] = useState<Record<string, number>>({});
  const [flagged, setFlagged] = useState<Set<string>>(new Set());
  const [position, setPosition] = useState(0);
  const [remaining, setRemaining] = useState(attempt.timeRemainingSeconds);
  const [confirming, setConfirming] = useState(false);
  const submittedRef = useRef(false);

  const spent = useRef<Record<string, number>>({});
  const openedAt = useRef(Date.now());

  const submit = useMutation({
    mutationFn: () =>
      submitAptitudeAttempt(
        attempt.attemptId,
        attempt.questions.map((question) => ({
          questionId: question.id,
          selectedOptionIndex: selections[question.id] ?? null,
          timeSpentSeconds: spent.current[question.id] ?? null,
        })),
      ),
    onSuccess: onFinished,
  });

  const finish = useCallback(() => {
    if (submittedRef.current) return;
    submittedRef.current = true;
    const question = attempt.questions[position];
    if (question) {
      spent.current[question.id] =
        (spent.current[question.id] ?? 0) + Math.round((Date.now() - openedAt.current) / 1000);
    }
    submit.mutate();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [attempt.questions, position]);

  // Local tick for a smooth readout.
  useEffect(() => {
    const timer = window.setInterval(() => {
      setRemaining((current) => {
        if (current <= 1) {
          finish();
          return 0;
        }
        return current - 1;
      });
    }, TICK_MS);
    return () => window.clearInterval(timer);
  }, [finish]);

  // Re-anchor to the server, so a throttled or backgrounded tab cannot buy time.
  useEffect(() => {
    let cancelled = false;
    const resync = async () => {
      if (submittedRef.current) return;
      try {
        const { timeRemainingSeconds } = await getAttemptTime(attempt.attemptId);
        if (cancelled || timeRemainingSeconds === null) return;
        setRemaining(timeRemainingSeconds);
        if (timeRemainingSeconds <= 0) finish();
      } catch {
        // A failed poll keeps the local countdown running rather than stalling
        // the test on a flaky network.
      }
    };
    const timer = window.setInterval(resync, RESYNC_MS);
    const onVisible = () => {
      if (document.visibilityState === "visible") resync();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [attempt.attemptId, finish]);

  const question = attempt.questions[position];
  const answeredCount = attempt.questions.filter((q) => selections[q.id] !== undefined).length;
  const unanswered = attempt.questions.length - answeredCount;

  const paletteStates: PaletteState[] = attempt.questions.map((q) =>
    flagged.has(q.id) ? "review" : selections[q.id] !== undefined ? "answered" : "unanswered",
  );

  const goTo = (next: number) => {
    spent.current[question.id] =
      (spent.current[question.id] ?? 0) + Math.round((Date.now() - openedAt.current) / 1000);
    openedAt.current = Date.now();
    setPosition(Math.max(0, Math.min(attempt.questions.length - 1, next)));
  };

  const toggleFlag = () => {
    setFlagged((current) => {
      const next = new Set(current);
      if (next.has(question.id)) next.delete(question.id);
      else next.add(question.id);
      return next;
    });
  };

  // Under two minutes the clock turns urgent. Colour plus a label, never colour
  // alone (Section 17).
  const urgent = remaining <= 120;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow={attempt.testName}
        title={`Question ${position + 1} of ${attempt.questions.length}`}
        description={`${answeredCount} answered. No feedback until you submit — this mimics a real test.`}
      />

      <Card className="flex flex-wrap items-center justify-between gap-3 py-3">
        <span className="flex items-center gap-2 text-sm">
          <span className="text-text-muted">Time left</span>
          <span
            className={`tnum text-lg font-semibold ${urgent ? "text-danger" : "text-text"}`}
            role="timer"
            aria-live={urgent ? "assertive" : "off"}
          >
            {formatClock(remaining)}
          </span>
          {urgent && <Badge tone="danger">Running out</Badge>}
        </span>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => setConfirming(true)}
          loading={submit.isPending}
        >
          Submit test
        </Button>
      </Card>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_16rem]">
        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{question.topic.replace(/_/g, " ")}</Badge>
            <Badge tone="neutral">{question.difficulty}</Badge>
            {flagged.has(question.id) && <Badge tone="warning">Marked for review</Badge>}
          </div>

          <p className="text-base leading-relaxed text-text">{question.questionText}</p>

          <ul className="flex flex-col gap-2">
            {question.options.map((option, index) => {
              const chosen = selections[question.id] === index;
              return (
                <li key={index}>
                  <button
                    type="button"
                    onClick={() => setSelections((c) => ({ ...c, [question.id]: index }))}
                    aria-pressed={chosen}
                    className={`w-full rounded-control border px-4 py-3 text-left text-sm transition-colors duration-150 ${
                      chosen
                        ? "border-accent/50 bg-accent/12 text-text"
                        : "border-border text-text-muted hover:border-border-strong hover:text-text"
                    }`}
                  >
                    <span className="mr-2.5 text-text-subtle">{String.fromCharCode(65 + index)}</span>
                    {option}
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="flex flex-wrap items-center gap-2">
            <Button variant="ghost" size="sm" disabled={position === 0} onClick={() => goTo(position - 1)}>
              Previous
            </Button>
            <Button
              variant="ghost"
              size="sm"
              disabled={position === attempt.questions.length - 1}
              onClick={() => goTo(position + 1)}
            >
              Next
            </Button>
            <Button variant="secondary" size="sm" onClick={toggleFlag}>
              {flagged.has(question.id) ? "Unmark" : "Mark for review"}
            </Button>
            {selections[question.id] !== undefined && (
              <button
                type="button"
                onClick={() =>
                  setSelections((current) => {
                    const next = { ...current };
                    delete next[question.id];
                    return next;
                  })
                }
                className="text-xs text-text-subtle underline decoration-dotted underline-offset-2 hover:text-text-muted"
              >
                Clear answer
              </button>
            )}
          </div>
        </Card>

        <Card className="h-fit">
          <QuestionPalette states={paletteStates} current={position} onJump={goTo} />
        </Card>
      </div>

      {submit.isError && (
        <Banner tone="error">
          {submit.error instanceof ApiError ? submit.error.message : "Couldn't submit the test."}
        </Banner>
      )}

      <Modal
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Submit this test?"
        description={
          unanswered > 0
            ? `${unanswered} question${unanswered === 1 ? " is" : "s are"} still unanswered. Unanswered questions are marked wrong.`
            : "Every question is answered. You won't be able to change anything after this."
        }
        footer={
          <>
            <Button variant="ghost" onClick={() => setConfirming(false)}>
              Keep working
            </Button>
            <Button
              loading={submit.isPending}
              onClick={() => {
                setConfirming(false);
                finish();
              }}
            >
              Submit test
            </Button>
          </>
        }
      />

      <button
        type="button"
        onClick={onAbandon}
        className="self-start text-xs text-text-subtle underline decoration-dotted underline-offset-2 hover:text-text-muted"
      >
        Leave without submitting
      </button>
    </div>
  );
}

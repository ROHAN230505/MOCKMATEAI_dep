import { useMutation, useQuery } from "@tanstack/react-query";
import { useCallback, useMemo, useRef, useState } from "react";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { PracticeTimer } from "../components/practice/PracticeTimer";
import { ErrorState, SkeletonCard } from "../components/ui/States";
import { ApiError } from "../lib/apiClient";
import {
  getAptitudeCatalog,
  getAptitudeHistory,
  getMockTests,
  startAptitudeAttempt,
  startMockTest,
  submitAptitudeAttempt,
} from "../services/practiceApi";
import { MockTestRunner } from "../components/aptitude/MockTestRunner";
import type {
  AptitudeAttempt,
  AptitudeResult,
  AptitudeTopic,
  Difficulty,
  TimedAttempt,
} from "../types/practice";

/**
 * Aptitude practice (Phase 7).
 *
 * Three states in one route rather than three routes: setup, the test itself, and
 * the result. A refresh mid-test would lose the answers either way — they live in
 * component state until submitted — so a URL per stage would promise a
 * resumability that does not exist.
 *
 * The filter controls are driven by the catalog's per-pair counts. That is the
 * whole reason those counts exist: there are eight verbal questions but only
 * three easy ones, so "verbal + easy" cannot fill a five-question test, and the
 * combination is disabled rather than left to fail after the candidate presses
 * start.
 */

const TOPICS: { value: AptitudeTopic; label: string }[] = [
  { value: "quantitative", label: "Quantitative" },
  { value: "logical_reasoning", label: "Logical reasoning" },
  { value: "verbal_ability", label: "Verbal ability" },
  { value: "data_interpretation", label: "Data interpretation" },
];

const DIFFICULTIES: { value: Difficulty; label: string }[] = [
  { value: "easy", label: "Easy" },
  { value: "medium", label: "Medium" },
  { value: "hard", label: "Hard" },
];

const QUESTION_COUNTS = [5, 10, 15, 20];

function toggle<T>(list: T[], value: T): T[] {
  return list.includes(value) ? list.filter((item) => item !== value) : [...list, value];
}

/** A chip that can say why it is unavailable rather than just being dead. */
function FilterChip({
  label,
  selected,
  disabled,
  title,
  count,
  onClick,
}: {
  label: string;
  selected: boolean;
  disabled?: boolean;
  title?: string;
  count?: number;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      title={title}
      aria-pressed={selected}
      className={`rounded-pill border px-3.5 py-2 text-xs font-medium transition-colors duration-200 disabled:cursor-not-allowed disabled:opacity-40 ${
        selected
          ? "border-accent/50 bg-accent/12 text-accent"
          : "border-border text-text-muted hover:border-border-strong hover:text-text"
      }`}
    >
      {label}
      {count !== undefined && <span className="ml-1.5 text-text-subtle">{count}</span>}
    </button>
  );
}

export function Aptitude() {
  const [topics, setTopics] = useState<AptitudeTopic[]>([]);
  const [difficulties, setDifficulties] = useState<Difficulty[]>([]);
  const [questionCount, setQuestionCount] = useState(10);

  const [attempt, setAttempt] = useState<AptitudeAttempt | null>(null);
  // Section 11.1's two modes. Kept as separate state rather than a flag on one
  // attempt because the timed run is a different screen entirely — a countdown,
  // a palette and no feedback until submission.
  const [timed, setTimed] = useState<TimedAttempt | null>(null);
  const [result, setResult] = useState<AptitudeResult | null>(null);
  const [selections, setSelections] = useState<Record<string, number>>({});
  const [position, setPosition] = useState(0);

  // Per-question time, kept in a ref because it changes on every navigation and
  // nothing renders from it until submit.
  const openedAt = useRef<number>(Date.now());
  const spent = useRef<Record<string, number>>({});

  const catalog = useQuery({ queryKey: ["aptitudeCatalog"], queryFn: getAptitudeCatalog });
  const tests = useQuery({ queryKey: ["mockTests"], queryFn: getMockTests });
  const history = useQuery({ queryKey: ["aptitudeHistory"], queryFn: getAptitudeHistory });

  const recordTime = useCallback((questionId: string) => {
    const elapsed = Math.round((Date.now() - openedAt.current) / 1000);
    spent.current[questionId] = (spent.current[questionId] ?? 0) + Math.max(0, elapsed);
    openedAt.current = Date.now();
  }, []);

  const start = useMutation({
    mutationFn: () => startAptitudeAttempt({ topics, difficulties, questionCount }),
    onSuccess: (data) => {
      setAttempt(data);
      setResult(null);
      setSelections({});
      setPosition(0);
      spent.current = {};
      openedAt.current = Date.now();
    },
  });

  const beginTest = useMutation({
    mutationFn: (testId: string) => startMockTest(testId),
    onSuccess: (data) => {
      setTimed(data);
      setResult(null);
      setAttempt(null);
    },
  });

  const submit = useMutation({
    mutationFn: (current: AptitudeAttempt) =>
      submitAptitudeAttempt(
        current.attemptId,
        current.questions.map((question) => ({
          questionId: question.id,
          selectedOptionIndex: selections[question.id] ?? null,
          timeSpentSeconds: spent.current[question.id] ?? null,
        })),
      ),
    onSuccess: (data) => {
      setResult(data);
      setAttempt(null);
      history.refetch();
    },
  });

  /**
   * Which filter combinations can actually produce a test.
   *
   * With no difficulty selected the whole topic counts; with difficulties chosen,
   * only the matching pairs do. Either way the answer is compared against the
   * server's own minimum rather than a copy of it.
   */
  const availability = useMemo(() => {
    const data = catalog.data;
    if (!data) return { total: 0, enough: false, topicAvailable: () => true };

    const countFor = (topic: AptitudeTopic) =>
      difficulties.length === 0
        ? (data.topicCounts[topic] ?? 0)
        : difficulties.reduce((sum, d) => sum + (data.combinationCounts[`${topic}:${d}`] ?? 0), 0);

    const chosen = topics.length > 0 ? topics : TOPICS.map((t) => t.value);
    const total = chosen.reduce((sum, topic) => sum + countFor(topic), 0);

    return {
      total,
      enough: total >= data.minQuestions,
      topicAvailable: (topic: AptitudeTopic) => countFor(topic) > 0,
      countFor,
    };
  }, [catalog.data, topics, difficulties]);

  if (catalog.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader eyebrow="Practice" title="Aptitude" description="Loading the question bank…" />
        <SkeletonCard lines={4} />
      </div>
    );
  }

  if (catalog.isError) {
    return (
      <ErrorState
        message="Couldn't load the aptitude question bank."
        action={<Button onClick={() => catalog.refetch()}>Try again</Button>}
      />
    );
  }

  // ------------------------------------------------------------ TIMED TEST
  if (timed) {
    return (
      <MockTestRunner
        attempt={timed}
        onFinished={(finished) => {
          setTimed(null);
          setResult(finished);
          history.refetch();
        }}
        onAbandon={() => setTimed(null)}
      />
    );
  }

  // ---------------------------------------------------------------- RESULT
  if (result) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader
          eyebrow="Practice"
          title="Aptitude result"
          description={`${result.correctCount} of ${result.totalQuestions} correct.`}
        />

        <Card className="flex flex-wrap items-center justify-between gap-4">
          <div>
            <p className="text-[0.6875rem] font-semibold tracking-[0.16em] text-text-subtle uppercase">
              {result.testName ?? "Score"}
            </p>
            <p className="tnum mt-1 text-4xl font-semibold text-text">{result.score}%</p>
            {result.timeTakenSeconds !== null && result.durationMinutes !== null && (
              <p className="mt-1 text-xs text-text-subtle">
                {Math.floor(result.timeTakenSeconds / 60)}m {result.timeTakenSeconds % 60}s of{" "}
                {result.durationMinutes} minutes
                {result.submittedLate && (
                  <span className="text-warning"> · submitted after time</span>
                )}
              </p>
            )}
          </div>
          <Button onClick={() => setResult(null)}>Practise again</Button>
        </Card>

        <Card>
          <CardHeader eyebrow="By topic" title="Where the marks went" />
          <ul className="mt-4 flex flex-col gap-3">
            {result.topicBreakdown.map((row) => {
              const label = TOPICS.find((t) => t.value === row.topic)?.label ?? row.topic;
              return (
                <li key={row.topic} className="flex items-center justify-between gap-4">
                  <span className={`text-sm ${row.total > 0 ? "text-text" : "text-text-subtle"}`}>
                    {label}
                  </span>
                  {row.percentage === null ? (
                    // Not 0%, which would read as having got them all wrong.
                    <span className="text-xs text-text-subtle">not covered in this test</span>
                  ) : (
                    <span className="tnum text-sm text-text-muted">
                      {row.correct}/{row.total} · {row.percentage}%
                    </span>
                  )}
                </li>
              );
            })}
          </ul>
        </Card>

        <Card>
          <CardHeader eyebrow="Review" title="Every question, with the answer" />
          <ul className="mt-4 flex flex-col gap-5">
            {result.answers.map((answer, index) => (
              <li key={answer.questionId} className="flex flex-col gap-2.5">
                <div className="flex items-start justify-between gap-3">
                  <p className="text-sm leading-relaxed text-text">
                    <span className="text-text-subtle">{index + 1}. </span>
                    {answer.questionText}
                  </p>
                  <Badge tone={answer.isCorrect ? "success" : "danger"}>
                    {answer.isCorrect ? "Correct" : answer.selectedOptionIndex === null ? "Blank" : "Wrong"}
                  </Badge>
                </div>
                <ul className="flex flex-col gap-1.5">
                  {answer.options.map((option, optionIndex) => {
                    const isAnswer = optionIndex === answer.correctOptionIndex;
                    const isChoice = optionIndex === answer.selectedOptionIndex;
                    return (
                      <li
                        key={optionIndex}
                        className={`rounded-control border px-3 py-2 text-xs ${
                          isAnswer
                            ? "border-success/40 bg-success/10 text-success"
                            : isChoice
                              ? "border-danger/40 bg-danger/10 text-danger"
                              : "border-border text-text-muted"
                        }`}
                      >
                        {option}
                        {isAnswer && <span className="ml-2 font-medium">correct answer</span>}
                        {isChoice && !isAnswer && <span className="ml-2 font-medium">your answer</span>}
                      </li>
                    );
                  })}
                </ul>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    );
  }

  // ------------------------------------------------------------------ TEST
  if (attempt) {
    const question = attempt.questions[position];
    const answered = attempt.questions.filter((q) => selections[q.id] !== undefined).length;
    const isLast = position === attempt.questions.length - 1;

    const goTo = (next: number) => {
      recordTime(question.id);
      setPosition(next);
    };

    return (
      <div className="flex flex-col gap-4">
        {/* Practice stays untimed by design: nothing is enforced and nothing
            auto-submits. The clock is a measurement the candidate can choose
            to pace against, which is a different thing from a limit — the
            timed mock test below is where a real deadline lives. */}
        <PageHeader
          eyebrow={`Question ${position + 1} of ${attempt.questions.length}`}
          title="Aptitude practice"
          description={`${answered} answered. Untimed — the clock is yours to pace against, not a limit.`}
          actions={<PracticeTimer resetKey={attempt.attemptId} />}
        />

        <div className="h-[3px] w-full shrink-0 overflow-hidden rounded-pill bg-surface-raised">
          <div
            className="h-full rounded-pill transition-[width] duration-300 ease-out"
            style={{
              width: `${((position + 1) / attempt.questions.length) * 100}%`,
              background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))",
            }}
          />
        </div>

        <Card className="flex flex-col gap-4">
          <div className="flex flex-wrap items-center gap-2">
            <Badge>{TOPICS.find((t) => t.value === question.topic)?.label ?? question.topic}</Badge>
            <Badge tone="neutral">{question.difficulty}</Badge>
          </div>

          <p className="text-base leading-relaxed text-text">{question.questionText}</p>

          <ul className="flex flex-col gap-2">
            {question.options.map((option, index) => {
              const chosen = selections[question.id] === index;
              return (
                <li key={index}>
                  <button
                    type="button"
                    onClick={() =>
                      setSelections((current) => ({ ...current, [question.id]: index }))
                    }
                    aria-pressed={chosen}
                    className={`w-full rounded-control border px-4 py-3 text-left text-sm transition-colors duration-150 ${
                      chosen
                        ? "border-accent/50 bg-accent/12 text-text"
                        : "border-border text-text-muted hover:border-border-strong hover:text-text"
                    }`}
                  >
                    <span className="mr-2.5 text-text-subtle">
                      {String.fromCharCode(65 + index)}
                    </span>
                    {option}
                  </button>
                </li>
              );
            })}
          </ul>

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
              className="self-start text-xs text-text-subtle underline decoration-dotted underline-offset-2 hover:text-text-muted"
            >
              Clear this answer
            </button>
          )}
        </Card>

        {submit.isError && (
          <Banner tone="error">
            {submit.error instanceof ApiError ? submit.error.message : "Couldn't submit your answers."}
          </Banner>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3">
          <Button variant="ghost" disabled={position === 0} onClick={() => goTo(position - 1)}>
            Previous
          </Button>
          {isLast ? (
            <Button
              loading={submit.isPending}
              onClick={() => {
                recordTime(question.id);
                submit.mutate(attempt);
              }}
            >
              {/* Says what will happen: unanswered questions are marked wrong, and
                  the candidate should know that before pressing it. */}
              {answered === attempt.questions.length
                ? "Submit answers"
                : `Submit — ${attempt.questions.length - answered} unanswered`}
            </Button>
          ) : (
            <Button onClick={() => goTo(position + 1)}>Next</Button>
          )}
        </div>
      </div>
    );
  }

  // ----------------------------------------------------------------- SETUP
  const past = history.data ?? [];

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow="Practice"
        title="Aptitude"
        description="Quantitative, reasoning, verbal and data interpretation, drawn from a curated bank."
      />

      <Card className="flex flex-col gap-6">
        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">
            Topics <span className="text-text-subtle">— leave blank for a mix of everything</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {TOPICS.map((topic) => (
              <FilterChip
                key={topic.value}
                label={topic.label}
                count={availability.countFor?.(topic.value)}
                selected={topics.includes(topic.value)}
                disabled={!availability.topicAvailable(topic.value)}
                title={
                  availability.topicAvailable(topic.value)
                    ? undefined
                    : "No questions match this topic at the selected difficulty"
                }
                onClick={() => setTopics((current) => toggle(current, topic.value))}
              />
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">
            Difficulty <span className="text-text-subtle">— leave blank for all</span>
          </legend>
          <div className="flex flex-wrap gap-2">
            {DIFFICULTIES.map((level) => (
              <FilterChip
                key={level.value}
                label={level.label}
                count={catalog.data?.difficultyCounts[level.value]}
                selected={difficulties.includes(level.value)}
                onClick={() => setDifficulties((current) => toggle(current, level.value))}
              />
            ))}
          </div>
        </fieldset>

        <fieldset>
          <legend className="mb-2.5 text-[0.8125rem] font-medium text-text">Questions</legend>
          <div className="flex flex-wrap gap-2">
            {QUESTION_COUNTS.map((count) => (
              <FilterChip
                key={count}
                label={String(count)}
                selected={questionCount === count}
                disabled={count > availability.total}
                title={count > availability.total ? "Not enough questions match these filters" : undefined}
                onClick={() => setQuestionCount(count)}
              />
            ))}
          </div>
        </fieldset>

        {!availability.enough && (
          <Banner tone="warning">
            Only {availability.total} question{availability.total === 1 ? "" : "s"} match these
            filters, and a test needs at least {catalog.data?.minQuestions}. Add a topic or a
            difficulty.
          </Banner>
        )}

        {start.isError && (
          <Banner tone="error">
            {start.error instanceof ApiError ? start.error.message : "Couldn't start the test."}
          </Banner>
        )}

        <Button
          className="self-start"
          loading={start.isPending}
          disabled={!availability.enough}
          onClick={() => start.mutate()}
        >
          Start {Math.min(questionCount, availability.total)} questions
        </Button>
      </Card>

      {(tests.data?.length ?? 0) > 0 && (
        <Card>
          <CardHeader
            eyebrow="Timed"
            title="Full mock tests"
          />
          <p className="mt-2 text-xs leading-relaxed text-text-subtle">
            Timed, with a question palette and no feedback until you submit. Unlike practice above,
            the clock is the server's — reloading won't give you more time.
          </p>
          <ul className="mt-4 flex flex-col gap-2.5">
            {tests.data!.map((test) => (
              <li
                key={test.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border px-3.5 py-3"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="text-sm font-medium text-text">{test.name}</span>
                  <span className="text-xs leading-relaxed text-text-subtle">{test.description}</span>
                  <span className="text-xs text-text-muted">
                    {test.questionCount} questions · {test.durationMinutes} minutes
                  </span>
                </span>
                <Button
                  size="sm"
                  variant="secondary"
                  loading={beginTest.isPending && beginTest.variables === test.id}
                  onClick={() => beginTest.mutate(test.id)}
                >
                  Start test
                </Button>
              </li>
            ))}
          </ul>
          {beginTest.isError && (
            <Banner tone="error">
              {beginTest.error instanceof ApiError
                ? beginTest.error.message
                : "Couldn't start that test."}
            </Banner>
          )}
        </Card>
      )}

      {past.length > 0 && (
        <Card>
          <CardHeader eyebrow="History" title="Your recent attempts" />
          <ul className="mt-4 flex flex-col gap-2.5">
            {past.slice(0, 8).map((item) => (
              <li key={item.attemptId} className="flex items-center justify-between gap-4 text-sm">
                <span className="text-text-muted">
                  {item.submittedAt ? new Date(item.submittedAt).toLocaleString() : "—"}
                </span>
                <span className="tnum text-text">
                  {item.score}% <span className="text-text-subtle">of {item.totalQuestions}</span>
                </span>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useMemo, useState } from "react";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { Button } from "../components/ui/Button";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { PracticeTimer } from "../components/practice/PracticeTimer";
import { GenerateProblem } from "../components/practice/GenerateProblem";
import { ErrorState, SkeletonCard } from "../components/ui/States";
import { useDsaRunner } from "../hooks/useDsaRunner";
import { describeOutcome, type RunSummary, type TestCase } from "../lib/dsaGrading";
import { ApiError } from "../lib/apiClient";
import {
  getDsaHiddenTestCases,
  getDsaProblem,
  getDsaProblems,
  requestDsaHint,
  submitDsaSolution,
} from "../services/practiceApi";
import type { Difficulty, DsaHint } from "../types/practice";

/**
 * DSA practice (Phase 7).
 *
 * Two states in one route: the problem list, and a problem with its editor.
 *
 * ## Run vs Submit
 *
 * **Run** executes the sample cases only — the ones already printed in the
 * problem statement, so there is nothing to give away and a candidate can iterate
 * freely. **Submit** fetches the hidden cases, runs everything, and records the
 * outcome. Keeping them apart means the hidden cases are not downloaded merely
 * because someone opened the problem.
 *
 * ## What the candidate is told
 *
 * That grading runs in their own browser, and therefore that the hidden cases are
 * technically readable from devtools. Said plainly rather than relied upon not
 * being noticed — this is a practice tool and the honest framing costs nothing.
 */

const DIFFICULTY_TONE: Record<Difficulty, "success" | "warning" | "danger"> = {
  easy: "success",
  medium: "warning",
  hard: "danger",
};

const TOPIC_LABELS: Record<string, string> = {
  arrays: "Arrays",
  strings: "Strings",
  linked_lists: "Linked lists",
  trees: "Trees",
  graphs: "Graphs",
  dynamic_programming: "Dynamic programming",
  recursion_backtracking: "Recursion & backtracking",
  sorting_searching: "Sorting & searching",
  greedy: "Greedy",
};

function OutcomeList({ summary, samples }: { summary: RunSummary; samples: TestCase[] }) {
  return (
    <ul className="flex flex-col gap-1.5">
      {summary.outcomes.map((outcome, index) => (
        <li
          key={index}
          className={`rounded-control border px-3 py-2 text-xs leading-relaxed ${
            outcome.kind === "passed"
              ? "border-success/40 bg-success/10 text-success"
              : "border-danger/40 bg-danger/10 text-danger"
          }`}
        >
          {describeOutcome(outcome, outcome.hidden ? undefined : samples[outcome.index])}
        </li>
      ))}
    </ul>
  );
}

export function Dsa() {
  const [openId, setOpenId] = useState<string | null>(null);

  const problems = useQuery({ queryKey: ["dsaProblems"], queryFn: getDsaProblems });

  if (problems.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader eyebrow="Practice" title="DSA" description="Loading problems…" />
        <SkeletonCard lines={5} />
      </div>
    );
  }

  if (problems.isError) {
    return (
      <ErrorState
        message="Couldn't load the problem list."
        action={<Button onClick={() => problems.refetch()}>Try again</Button>}
      />
    );
  }

  if (openId) {
    return <ProblemWorkspace problemId={openId} onBack={() => setOpenId(null)} />;
  }

  const solved = problems.data.filter((p) => p.solved).length;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow="Practice"
        title="DSA"
        description={`${solved} of ${problems.data.length} solved. Solutions run in your browser — nothing is executed on our servers.`}
      />

      {/* Sits above the list because it is the answer to "I have seen all of
          these" -- which is the moment someone looks for it. */}
      <Card>
        <CardHeader
          title="Write me a new one"
          description="A problem that has never existed before, checked before you see it."
        />
        <GenerateProblem onGenerated={(id) => setOpenId(id)} />
      </Card>

      <Card padded={false}>
        <ul className="divide-y divide-border">
          {problems.data.map((problem) => (
            <li key={problem.id}>
              <button
                type="button"
                onClick={() => setOpenId(problem.id)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors duration-150 hover:bg-surface-raised/60"
              >
                <span className="flex min-w-0 flex-col gap-1">
                  <span className="truncate text-sm font-medium text-text">{problem.title}</span>
                  <span className="text-xs text-text-subtle">
                    {TOPIC_LABELS[problem.topic] ?? problem.topic}
                  </span>
                </span>
                <span className="flex shrink-0 items-center gap-2">
                  {problem.solved ? (
                    <Badge tone="success">Solved</Badge>
                  ) : problem.attempted ? (
                    <Badge tone="warning">Attempted</Badge>
                  ) : null}
                  <Badge tone={DIFFICULTY_TONE[problem.difficulty]}>{problem.difficulty}</Badge>
                </span>
              </button>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

function ProblemWorkspace({ problemId, onBack }: { problemId: string; onBack: () => void }) {
  const queryClient = useQueryClient();
  const runner = useDsaRunner();

  const [code, setCode] = useState("");
  const [summary, setSummary] = useState<RunSummary | null>(null);
  const [ranHidden, setRanHidden] = useState(false);
  const [hints, setHints] = useState<DsaHint[]>([]);
  const [error, setError] = useState<string | null>(null);

  const problem = useQuery({
    queryKey: ["dsaProblem", problemId],
    queryFn: () => getDsaProblem(problemId),
  });

  // Seed the editor from the starter template once the problem arrives, without
  // clobbering anything the candidate has since typed.
  useEffect(() => {
    if (problem.data && code === "") setCode(problem.data.starterCode.python ?? "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [problem.data]);

  const samples = useMemo(
    () => (problem.data?.sampleTestCases ?? []) as TestCase[],
    [problem.data],
  );

  const hint = useMutation({
    mutationFn: () => requestDsaHint(problemId, { hintIndex: hints.length, code }),
    onSuccess: (data) => setHints((current) => [...current, data]),
  });

  const submit = useMutation({
    mutationFn: (result: RunSummary) =>
      submitDsaSolution(problemId, {
        code,
        language: "python",
        passedCaseCount: result.passedCount,
        totalCaseCount: result.totalCount,
        runtimeMs: result.runtimeMs,
        hintsUsedCount: hints.length,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dsaProblems"] });
      queryClient.invalidateQueries({ queryKey: ["dsaProblem", problemId] });
      queryClient.invalidateQueries({ queryKey: ["dashboardSummary"] });
    },
  });

  async function handleRun() {
    setError(null);
    setRanHidden(false);
    if (!problem.data) return;
    const result = await runner.run(
      code,
      problem.data.functionName,
      samples.map((testCase) => ({ testCase, hidden: false })),
    );
    setSummary(result);
  }

  async function handleSubmit() {
    setError(null);
    if (!problem.data) return;
    try {
      // Fetched only now, so opening a problem does not download its hidden cases.
      const { hiddenTestCases } = await getDsaHiddenTestCases(problemId);
      const result = await runner.run(code, problem.data.functionName, [
        ...samples.map((testCase) => ({ testCase, hidden: false })),
        ...(hiddenTestCases as TestCase[]).map((testCase) => ({ testCase, hidden: true })),
      ]);
      setRanHidden(true);
      setSummary(result);
      if (result) submit.mutate(result);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "Couldn't run the hidden tests.");
    }
  }

  if (problem.isPending) return <SkeletonCard lines={6} />;
  if (problem.isError || !problem.data) {
    return (
      <ErrorState
        message="Couldn't load this problem."
        action={<Button onClick={onBack}>Back to the list</Button>}
      />
    );
  }

  const busy = runner.status.state === "running" || runner.status.state === "loading";

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <Button variant="ghost" size="sm" onClick={onBack}>
          ← All problems
        </Button>
        <span className="flex items-center gap-2">
          {problem.data.solved && <Badge tone="success">Solved</Badge>}
          <Badge tone={DIFFICULTY_TONE[problem.data.difficulty]}>{problem.data.difficulty}</Badge>
          <Badge>{TOPIC_LABELS[problem.data.topic] ?? problem.data.topic}</Badge>
        </span>
      </div>

      {/* The clock a DSA problem never had. Elapsed by default rather than
          counting down, because unlike the aptitude mock test there is no
          server-owned duration here to count against — see PracticeTimer. */}
      <PageHeader
        eyebrow="Problem"
        title={problem.data.title}
        actions={<PracticeTimer resetKey={problemId} />}
      />

      <div className="grid gap-4 lg:grid-cols-2">
        <div className="flex flex-col gap-4">
          <Card>
            <p className="text-sm leading-relaxed whitespace-pre-line text-text-muted">
              {problem.data.statementText}
            </p>
            {problem.data.constraintsText && (
              <>
                <div className="rule-fade my-4" />
                <p className="text-[0.6875rem] font-semibold tracking-[0.16em] text-text-subtle uppercase">
                  Constraints
                </p>
                <pre className="mt-2 overflow-x-auto text-xs leading-relaxed text-text-muted">
                  {problem.data.constraintsText}
                </pre>
              </>
            )}
          </Card>

          <Card>
            <CardHeader
              eyebrow="Hints"
              title={`${hints.length} of 4 used`}
            />
            <p className="mt-2 text-xs leading-relaxed text-text-subtle">
              Each hint nudges a little further than the last. How many you used is recorded with
              your submission.
            </p>
            {hints.length > 0 && (
              <ul className="mt-3 flex flex-col gap-2">
                {hints.map((item, index) => (
                  <li key={index} className="rounded-control border border-border px-3 py-2.5">
                    <p className="text-sm leading-relaxed text-text-muted">{item.hint}</p>
                    {/* Same disclosure the feedback report makes: a rule-based
                        nudge is never allowed to pass as model reasoning. */}
                    {item.generatedBy === "deterministic" && (
                      <p className="mt-1.5 text-[0.6875rem] text-text-subtle">
                        Rule-based hint — no model was available.
                      </p>
                    )}
                  </li>
                ))}
              </ul>
            )}
            {hint.isError && (
              <Banner tone="error">
                {hint.error instanceof ApiError ? hint.error.message : "Couldn't fetch a hint."}
              </Banner>
            )}
            {hints.length < 4 && (
              <Button
                variant="secondary"
                size="sm"
                className="mt-3 self-start"
                loading={hint.isPending}
                onClick={() => hint.mutate()}
              >
                {hints.length === 0 ? "Get a hint" : "Next hint"}
              </Button>
            )}
          </Card>
        </div>

        <div className="flex flex-col gap-4">
          <Card className="flex flex-col gap-3">
            <label htmlFor="solution" className="text-[0.8125rem] font-medium text-text">
              Your solution <span className="text-text-subtle">— Python</span>
            </label>
            <textarea
              id="solution"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              spellCheck={false}
              rows={16}
              className="w-full resize-y rounded-control border border-border bg-surface px-3.5 py-3 font-mono text-xs leading-relaxed text-text focus:border-border-strong focus:ring-2 focus:ring-accent/30 focus:outline-none"
            />

            <div className="flex flex-wrap items-center gap-2">
              <Button variant="secondary" loading={busy} onClick={handleRun}>
                Run examples
              </Button>
              <Button loading={busy || submit.isPending} onClick={handleSubmit}>
                Submit
              </Button>
              <span className="text-xs text-text-subtle">
                {problem.data.sampleTestCases.length} examples ·{" "}
                {problem.data.hiddenTestCaseCount} hidden
              </span>
            </div>

            {runner.status.state === "loading" && (
              <p className="text-xs text-text-subtle">
                Loading the Python runtime — about 13MB, once per session.
              </p>
            )}
            {runner.status.state === "unavailable" && (
              <Banner tone="error">{runner.status.reason}</Banner>
            )}
            {error && <Banner tone="error">{error}</Banner>}
          </Card>

          {summary && (
            <Card className="flex flex-col gap-3">
              <CardHeader
                eyebrow={ranHidden ? "Submission" : "Examples"}
                title={
                  summary.allPassed
                    ? ranHidden
                      ? "All tests passed"
                      : "All examples passed"
                    : `${summary.passedCount} of ${summary.totalCount} passed`
                }
              />
              <OutcomeList summary={summary} samples={samples} />
              {!ranHidden && summary.allPassed && (
                <p className="text-xs text-text-subtle">
                  The examples pass. Submit to run the {problem.data.hiddenTestCaseCount} hidden
                  tests as well.
                </p>
              )}
              {summary.runtimeMs > 0 && (
                <p className="tnum text-xs text-text-subtle">
                  {summary.runtimeMs}ms across {summary.totalCount} case
                  {summary.totalCount === 1 ? "" : "s"}
                </p>
              )}
            </Card>
          )}

          <p className="text-xs leading-relaxed text-text-subtle">
            Your code runs inside your own browser and is never executed on our servers. That does
            mean the hidden test cases are downloaded to your machine to be run against, so they
            are not truly secret — this is practice, not an exam.
          </p>
        </div>
      </div>
    </div>
  );
}

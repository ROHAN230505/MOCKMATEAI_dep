import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import { Button } from "../components/ui/Button";
import { Glyph } from "../components/ui/Glyph";
import { ErrorState, Skeleton } from "../components/ui/States";
import { KpiTile } from "../components/dashboard/KpiTile";
import { TrendChart } from "../components/charts/TrendChart";
import { RadarChart } from "../components/charts/RadarChart";
import { QuestionBars } from "../components/charts/QuestionBars";
import { useCountUp } from "../hooks/useCountUp";
import { useReportSeries } from "../hooks/useReportSeries";
import { getDashboardSummary } from "../services/dashboardApi";
import { getInterviewHistory } from "../services/interviewApi";
import { useAuthStore } from "../store/authStore";

/**
 * The interview analytics dashboard.
 *
 * ## Where the data comes from
 *
 * Three endpoints that already existed — `GET /dashboard/summary`,
 * `GET /interviews/history`, and `GET /feedback/:id` once per recent session (see
 * `useReportSeries`). No new API, no aggregate endpoint, no backend change.
 *
 * That's enough for genuine analytics: score across sessions, the category radar,
 * per-question relevance and completeness, speech signals, and the before/after
 * delta the report already computes. Everything plotted is measured.
 *
 * ## Layout
 *
 * A 12-column grid in four bands, ordered by decision value:
 *
 * 1. **KPIs** — four figures, with a sparkline where a real series exists.
 * 2. **Performance** — the trend chart (8 cols) beside the readiness dial (4).
 * 3. **Last interview** — radar, per-question bars, delivery signals.
 * 4. **Coaching + activity** — strengths, improvements, summary, session list.
 *
 * Every band collapses to a single column below `lg`, and the charts are all
 * `viewBox`-scaled SVG, so they reflow rather than overflow.
 */

function Panel({
  title,
  subtitle,
  action,
  children,
  className = "",
  bodyClass = "p-4",
}: {
  title?: string;
  subtitle?: ReactNode;
  action?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
}) {
  return (
    <section className={`panel flex min-w-0 flex-col rounded-card ${className}`}>
      {title && (
        <header className="flex min-h-9 shrink-0 items-center justify-between gap-3 border-b border-border px-4 py-2">
          <div className="min-w-0">
            <h2 className="marker text-text-subtle">{title}</h2>
            {subtitle && <p className="mt-0.5 truncate text-[0.6875rem] text-text-subtle">{subtitle}</p>}
          </div>
          {action}
        </header>
      )}
      <div className={`min-w-0 flex-1 ${bodyClass}`}>{children}</div>
    </section>
  );
}

/** The readiness dial. Compact — the trend chart beside it carries the story. */
function ReadinessDial({ score, label }: { score: number; label: string }) {
  const animated = useCountUp(score);
  const R = 62;
  const C = 2 * Math.PI * R;

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative h-[160px] w-[160px]">
        <svg viewBox="0 0 160 160" className="h-full w-full -rotate-90">
          <defs>
            <linearGradient id="dial-arc" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor="var(--grad-a)" />
              <stop offset="100%" stopColor="var(--grad-b)" />
            </linearGradient>
          </defs>
          <circle cx="80" cy="80" r={R} fill="none" stroke="var(--color-surface-raised)" strokeWidth="9" />
          <circle
            cx="80"
            cy="80"
            r={R}
            fill="none"
            stroke="url(#dial-arc)"
            strokeWidth="9"
            strokeLinecap="round"
            strokeDasharray={C}
            strokeDashoffset={C * (1 - Math.max(0, Math.min(100, animated)) / 100)}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="stat text-[2.5rem] leading-none text-text">{Math.round(animated)}</span>
          <span className="mt-1 text-[0.625rem] text-text-subtle">out of 100</span>
        </div>
      </div>
      <span className="mt-2 rounded-pill border border-accent/30 bg-accent-soft px-2.5 py-0.5 text-[0.6875rem] font-medium text-accent">
        {label}
      </span>
    </div>
  );
}

/** One delivery signal. Every value here is measured from the transcript. */
function SignalRow({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3 border-b border-border py-2 last:border-0">
      <span className="min-w-0 truncate text-[0.75rem] text-text-muted">{label}</span>
      <span className="flex shrink-0 items-baseline gap-1.5">
        <span className="stat text-[0.8125rem] text-text">{value}</span>
        {note && <span className="text-[0.625rem] text-text-subtle">{note}</span>}
      </span>
    </div>
  );
}

export function Dashboard() {
  const user = useAuthStore((s) => s.user);

  const summary = useQuery({ queryKey: ["dashboard-summary"], queryFn: getDashboardSummary });
  const history = useQuery({ queryKey: ["interview-history"], queryFn: getInterviewHistory });
  const { series, latest } = useReportSeries(history.data, 6);

  const firstName = user?.name?.split(" ")[0];
  const report = latest?.report ?? null;

  if (summary.isLoading) {
    return (
      <div className="mx-auto flex max-w-[1500px] flex-col gap-5">
        <Skeleton className="h-10 w-72" />
        <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
          {[0, 1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-28 w-full" />
          ))}
        </div>
        <div className="grid gap-5 lg:grid-cols-12">
          <Skeleton className="h-72 w-full lg:col-span-8" />
          <Skeleton className="h-72 w-full lg:col-span-4" />
        </div>
      </div>
    );
  }

  if (summary.isError || !summary.data) {
    return <ErrorState message="Couldn't load your dashboard. Please refresh the page." />;
  }

  const data = summary.data;

  // --- Series derived from real reports ------------------------------------
  const trend = series.map((entry) => ({
    label: entry.session.roleTarget,
    date: entry.session.startedAt,
    value: entry.report?.overallReadinessScore ?? null,
  }));
  const scoreSpark = trend.map((t) => t.value).filter((v): v is number => v !== null);

  // The report's own before/after block is the only genuine delta available.
  const overallDelta =
    report?.comparison?.deltas.find((d) => d.category === "overall")?.delta ?? null;

  const radarData = (report?.categoryScores ?? []).map((c) => ({
    label: c.label,
    value: c.measured ? c.score : null,
  }));

  const questionData = (report?.turns ?? []).map((turn) => ({
    number: turn.number,
    questionText: turn.questionText,
    isFollowup: turn.isFollowup,
    isSkipped: turn.isSkipped,
    relevance: turn.relevanceScore,
    completeness: turn.completenessScore,
  }));

  const signals = report?.signals ?? null;

  return (
    <div className="mx-auto flex max-w-[1500px] flex-col gap-5">
      {/* =========================================================== HEADER === */}
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="marker text-text-subtle">Overview</p>
          <h1 className="mt-1.5 text-[1.25rem] font-semibold tracking-tight text-text">
            Welcome back{firstName ? `, ${firstName}` : ""}
          </h1>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/interview/history">
            <Button variant="secondary" size="sm">
              History
            </Button>
          </Link>
          <Link to="/interview/setup">
            <Button variant="primary" size="sm">
              Start AI Interview
            </Button>
          </Link>
        </div>
      </header>

      {/* ========================================================= BAND 1 KPI === */}
      <div className="grid gap-5 sm:grid-cols-2 xl:grid-cols-4">
        <KpiTile
          index={0}
          label="Readiness"
          value={data.readinessIndex}
          note={data.readinessLabel}
          href="/interview/history"
          icon={
            <Glyph className="h-4 w-4">
              <path d="M12 2v4m0 12v4M2 12h4m12 0h4" />
              <circle cx="12" cy="12" r="5" />
            </Glyph>
          }
        />
        <KpiTile
          index={1}
          label="Avg. interview score"
          value={data.mockInterviewsAvgScore}
          note={`${data.mockInterviewsCount} completed`}
          delta={overallDelta}
          spark={scoreSpark}
          href="/interview/history"
          icon={
            <Glyph className="h-4 w-4">
              <path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 0 0-6 0v6a3 3 0 0 0 3 3Z" />
              <path d="M19 11a7 7 0 0 1-14 0M12 18v3" />
            </Glyph>
          }
        />
        <KpiTile
          index={2}
          label="DSA solved"
          value={data.dsaProblemsSolved}
          suffix={`/ ${data.dsaProblemsTotal}`}
          note="Problems"
          href="/dsa"
          icon={
            <Glyph className="h-4 w-4">
              <path d="m8 16-4-4 4-4m8 0 4 4-4 4M14 4l-4 16" />
            </Glyph>
          }
        />
        <KpiTile
          index={3}
          label="Resume ATS"
          value={data.resumeLastAtsScore}
          note="Not analyzed"
          href="/resume"
          icon={
            <Glyph className="h-4 w-4">
              <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
              <path d="M14 3v5h5M9 13h6" />
            </Glyph>
          }
        />
      </div>

      {/* =================================================== BAND 2 PERFORMANCE === */}
      <div className="grid gap-5 lg:grid-cols-12">
        <Panel
          title="Performance over time"
          subtitle="Overall score from each completed interview"
          className="lg:col-span-8"
          action={
            <Link to="/interview/history" className="text-[0.6875rem] text-text-muted hover:text-text">
              All sessions
            </Link>
          }
        >
          <TrendChart data={trend} />
        </Panel>

        <Panel title="Readiness index" className="lg:col-span-4" bodyClass="flex items-center justify-center p-4">
          <ReadinessDial score={data.readinessIndex} label={data.readinessLabel} />
        </Panel>
      </div>

      {/* ================================================ BAND 3 LAST INTERVIEW === */}
      {report ? (
        <div className="grid gap-5 lg:grid-cols-12">
          <Panel
            title="Skill breakdown"
            subtitle={report.roleTarget}
            className="lg:col-span-4"
            bodyClass="p-4"
          >
            <RadarChart data={radarData} />
          </Panel>

          <Panel
            title="Question by question"
            subtitle={`${report.answeredCount} answered · ${report.skippedCount} skipped`}
            className="lg:col-span-5"
            action={
              <Link
                to={`/interview/feedback/${report.sessionId}`}
                className="text-[0.6875rem] text-text-muted hover:text-text"
              >
                Open report
              </Link>
            }
          >
            <QuestionBars data={questionData} />
          </Panel>

          <Panel title="Delivery signals" className="lg:col-span-3">
            {signals ? (
              <div className="flex flex-col">
                <SignalRow
                  label="Filler words"
                  value={`${signals.fillerCount}`}
                  note={`${signals.fillerRatePer100Words.toFixed(1)}/100w`}
                />
                <SignalRow label="Avg. answer" value={`${Math.round(signals.averageAnswerWords)}`} note="words" />
                <SignalRow
                  label="With a number"
                  value={`${signals.quantifiedAnswers}/${signals.answerCount}`}
                  note="answers"
                />
                <SignalRow
                  label="Under-developed"
                  value={`${signals.underElaboratedAnswers}`}
                  note="answers"
                />
                <SignalRow
                  label="Speaking pace"
                  value={signals.speakingPaceWpm === null ? "—" : `${Math.round(signals.speakingPaceWpm)}`}
                  note={signals.speakingPaceWpm === null ? "not timed" : "wpm"}
                />
              </div>
            ) : (
              <p className="text-text-subtle">No speech signals for that session.</p>
            )}
          </Panel>
        </div>
      ) : (
        <Panel title="Last interview">
          <div className="flex flex-col items-start gap-2.5 py-6">
            <p className="text-text-muted">
              {history.data && history.data.length > 0
                ? "None of your sessions have a generated report yet."
                : "Run your first interview and this fills with your scored breakdown."}
            </p>
            <Link to="/interview/setup">
              <Button variant="primary" size="sm">
                Start AI Interview
              </Button>
            </Link>
          </div>
        </Panel>
      )}

      {/* ============================================ BAND 4 COACHING + ACTIVITY === */}
      <div className="grid gap-5 lg:grid-cols-12">
        <Panel
          title="Recent interviews"
          className="lg:col-span-5"
          bodyClass="p-2"
          action={
            <Link to="/interview/history" className="text-[0.6875rem] text-text-muted hover:text-text">
              View all
            </Link>
          }
        >
          {history.isLoading && (
            <div className="flex flex-col gap-1.5 p-2">
              {[0, 1, 2].map((i) => (
                <Skeleton key={i} className="h-9 w-full" />
              ))}
            </div>
          )}

          {history.data?.length === 0 && (
            <div className="flex flex-col items-start gap-2.5 p-4">
              <p className="text-text-muted">No interviews yet.</p>
              <Link to="/interview/setup">
                <Button variant="secondary" size="sm">
                  Run your first
                </Button>
              </Link>
            </div>
          )}

          {history.data && history.data.length > 0 && (
            <ul>
              {history.data.slice(0, 6).map((session) => {
                const entry = series.find((s) => s.session.id === session.id);
                const score = entry?.report?.overallReadinessScore ?? null;
                return (
                  <li key={session.id}>
                    <Link to={`/interview/feedback/${session.id}`} className="row py-2.5">
                      <span
                        aria-hidden="true"
                        className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                          session.status === "completed"
                            ? "bg-success"
                            : session.status === "in_progress"
                              ? "bg-accent"
                              : "bg-text-subtle"
                        }`}
                      />
                      <span className="min-w-0 flex-1 truncate font-medium text-text">
                        {session.roleTarget}
                      </span>
                      <span className="tnum shrink-0 text-text-subtle">
                        {session.startedAt ? new Date(session.startedAt).toLocaleDateString() : "—"}
                      </span>
                      <span className={`stat w-8 shrink-0 text-right ${score !== null ? "text-text" : "text-text-subtle"}`}>
                        {score !== null ? Math.round(score) : "—"}
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </Panel>

        {report && (
          <>
            <Panel title="Strengths" className="lg:col-span-4">
              {report.strengths.length > 0 ? (
                <ul className="flex flex-col gap-3">
                  {report.strengths.slice(0, 3).map((item, i) => (
                    <li key={i} className="flex gap-2.5 text-text-muted">
                      <span className="mt-[0.4rem] h-1 w-1 shrink-0 rounded-full bg-success" />
                      <span className="leading-relaxed">{item.text}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-text-subtle">None identified in your last session.</p>
              )}
            </Panel>

            <Panel title="Areas to improve" className="lg:col-span-3">
              {report.improvements.length > 0 ? (
                <ul className="flex flex-col gap-3">
                  {report.improvements.slice(0, 3).map((item, i) => (
                    <li key={i} className="flex gap-2.5 text-text-muted">
                      <span className="mt-[0.4rem] h-1 w-1 shrink-0 rounded-full bg-accent" />
                      <span className="leading-relaxed">{item.text}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="text-text-subtle">None identified in your last session.</p>
              )}
            </Panel>
          </>
        )}
      </div>

      {/* Coach summary — full width, since it's prose and reads badly in a column. */}
      {report?.summaryText && (
        <Panel
          title="AI coach summary"
          subtitle={report.generatedBy === "deterministic" ? "Rule-based analysis" : undefined}
          action={
            <Link
              to={`/interview/feedback/${report.sessionId}`}
              className="text-[0.6875rem] text-text-muted hover:text-text"
            >
              Read full report
            </Link>
          }
        >
          <motion.blockquote
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            transition={{ duration: 0.5 }}
            className="border-l-2 border-accent/40 pl-4 leading-relaxed text-text-muted"
          >
            <span className="line-clamp-3 block">{report.summaryText}</span>
          </motion.blockquote>
        </Panel>
      )}

      {data.weeklyFocus.length > 0 && (
        <Panel title="This week's focus">
          {/* Ordered by what would actually move the Readiness Index, and each
              carries the measurement it came from — a chip that just said
              "practise aptitude" with no number behind it would be the generic
              advice this product exists not to give. */}
          <ul className="flex flex-col gap-2.5">
            {data.weeklyFocus.map((focus) => (
              <li
                key={focus.id}
                className="flex flex-wrap items-center justify-between gap-3 rounded-control border border-border px-3 py-2.5"
              >
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-[0.8125rem] font-medium text-text">{focus.label}</span>
                  <span className="text-xs leading-relaxed text-text-subtle">
                    {focus.reason}{" "}
                    <span className="text-text-muted">
                      Worth about +{focus.projectedGain} on your index.
                    </span>
                  </span>
                </span>
                <Link
                  to={focus.route}
                  className="shrink-0 rounded-pill border border-border px-3 py-1.5 text-xs font-medium text-text-muted transition-colors duration-200 hover:border-border-strong hover:text-text"
                >
                  {focus.cta}
                </Link>
              </li>
            ))}
          </ul>
        </Panel>
      )}
    </div>
  );
}

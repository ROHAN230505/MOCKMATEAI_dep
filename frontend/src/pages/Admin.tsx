import { useQuery } from "@tanstack/react-query";
import { Badge } from "../components/ui/Badge";
import { Banner } from "../components/ui/Banner";
import { Card, CardHeader } from "../components/ui/Card";
import { PageHeader } from "../components/ui/PageHeader";
import { ErrorState, SkeletonCard } from "../components/ui/States";
import { ApiError } from "../lib/apiClient";
import { getAdminAnalytics } from "../services/settingsApi";

/**
 * Admin / TnP aggregate dashboard (Section 16).
 *
 * Cohort-level only. There is no individual drill-down here and no way to reach
 * one: Section 16 permits it solely for candidates who have explicitly opted into
 * sharing, and no opt-in exists in this build, so it is not implemented rather
 * than merely hidden.
 *
 * The screen also shows what it *cannot* measure, which is unusual for a
 * dashboard and deliberate. A blank space invites the assumption that a number
 * is coming; a stated reason closes the question.
 */

const TOPIC_LABELS: Record<string, string> = {
  quantitative: "Quantitative",
  logical_reasoning: "Logical reasoning",
  verbal_ability: "Verbal ability",
  data_interpretation: "Data interpretation",
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

function Bar({ value }: { value: number }) {
  return (
    <div className="h-1.5 w-full overflow-hidden rounded-pill bg-surface-raised">
      <div
        className="h-full rounded-pill transition-[width] duration-500 ease-out"
        style={{
          width: `${Math.max(2, Math.min(100, value))}%`,
          background: "linear-gradient(90deg, var(--grad-a), var(--grad-b))",
        }}
      />
    </div>
  );
}

function StatList({ rows }: { rows: { label: string; value: string }[] }) {
  return (
    <ul className="mt-4 flex flex-col gap-2.5">
      {rows.map((row) => (
        <li key={row.label} className="flex items-center justify-between gap-4 text-sm">
          <span className="text-text-muted">{row.label}</span>
          <span className="tnum text-text">{row.value}</span>
        </li>
      ))}
    </ul>
  );
}

export function Admin() {
  const analytics = useQuery({
    queryKey: ["adminAnalytics"],
    queryFn: getAdminAnalytics,
    retry: false,
  });

  if (analytics.isPending) {
    return (
      <div className="flex flex-col gap-4">
        <PageHeader eyebrow="Admin" title="Batch analytics" description="Loading..." />
        <SkeletonCard lines={5} />
      </div>
    );
  }

  if (analytics.isError) {
    const forbidden = analytics.error instanceof ApiError && analytics.error.status === 403;
    return (
      <ErrorState
        title={forbidden ? "Admin access required" : "Something went wrong"}
        message={
          forbidden
            ? "This dashboard is limited to admin accounts. The check runs on the server, so there is nothing to unlock here."
            : "Couldn't load batch analytics."
        }
      />
    );
  }

  const data = analytics.data;

  return (
    <div className="flex flex-col gap-4">
      <PageHeader
        eyebrow="Admin"
        title="Batch analytics"
        description={`Aggregate across ${data.cohortSize} account${data.cohortSize === 1 ? "" : "s"}. No individual candidate data appears here.`}
      />

      {data.suppressed ? (
        <Banner tone="warning" title="Not enough accounts to report on">
          {data.suppressionReason}
        </Banner>
      ) : (
        <>
          <Card>
            <CardHeader eyebrow="Engagement" title="Which modules the batch actually uses" />
            <ul className="mt-4 flex flex-col gap-3.5">
              {data.engagement.map((row) => (
                <li key={row.module} className="flex flex-col gap-1.5">
                  <div className="flex items-baseline justify-between gap-3">
                    <span className="text-sm text-text">{row.module}</span>
                    <span className="tnum text-xs text-text-muted">
                      {row.users} of {data.cohortSize} - {row.percentage}%
                    </span>
                  </div>
                  <Bar value={row.percentage} />
                </li>
              ))}
            </ul>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader eyebrow="Scores" title="Average by category" />
              <ul className="mt-4 flex flex-col gap-3.5">
                {data.categoryAverages.map((row) => (
                  <li key={row.category} className="flex flex-col gap-1.5">
                    <div className="flex items-baseline justify-between gap-3">
                      <span
                        className={`text-sm ${row.average === null ? "text-text-subtle" : "text-text"}`}
                      >
                        {row.category}
                      </span>
                      <span className="tnum text-xs text-text-muted">
                        {row.average === null ? "not measured" : row.average}
                      </span>
                    </div>
                    {row.average === null ? (
                      <div className="h-1.5 w-full rounded-pill border border-dashed border-border" />
                    ) : (
                      <Bar value={row.average} />
                    )}
                  </li>
                ))}
              </ul>
            </Card>

            <Card>
              {/* The curriculum signal Section 16 actually asks for. */}
              <CardHeader eyebrow="Weak areas" title="Most common weakest category" />
              {data.weakestCategoryCounts.length === 0 ? (
                <p className="mt-4 text-sm text-text-subtle">No reports generated yet.</p>
              ) : (
                <ul className="mt-4 flex flex-col gap-3.5">
                  {data.weakestCategoryCounts.map((row) => (
                    <li key={row.category} className="flex flex-col gap-1.5">
                      <div className="flex items-baseline justify-between gap-3">
                        <span className="text-sm text-text">{row.category}</span>
                        <span className="tnum text-xs text-text-muted">
                          {row.count} report{row.count === 1 ? "" : "s"} - {row.percentage}%
                        </span>
                      </div>
                      <Bar value={row.percentage} />
                    </li>
                  ))}
                </ul>
              )}
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            <Card>
              <CardHeader eyebrow="Aptitude" title="Accuracy by topic" />
              {data.aptitudeTopicAccuracy.length === 0 ? (
                <p className="mt-4 text-sm text-text-subtle">No attempts yet.</p>
              ) : (
                <StatList
                  rows={data.aptitudeTopicAccuracy.map((row) => ({
                    label: TOPIC_LABELS[row.topic] ?? row.topic,
                    value:
                      row.accuracy === null
                        ? `- (${row.answered} answered)`
                        : `${row.accuracy}% of ${row.answered}`,
                  }))}
                />
              )}
            </Card>

            <Card>
              <CardHeader eyebrow="DSA" title="Problems cleared by anyone" />
              <StatList
                rows={data.dsaTopicCompletion.map((row) => ({
                  label: TOPIC_LABELS[row.topic] ?? row.topic,
                  value: `${row.solvedByAnyone}/${row.problems}`,
                }))}
              />
            </Card>
          </div>
        </>
      )}

      <Card>
        <CardHeader eyebrow="Not measured" title="What this dashboard deliberately can't tell you" />
        <ul className="mt-4 flex flex-col gap-3">
          {data.notMeasured.map((row) => (
            <li key={row.metric} className="flex flex-col gap-1">
              <span className="flex items-center gap-2 text-sm text-text">
                {row.metric}
                <Badge>Absent</Badge>
              </span>
              <span className="text-xs leading-relaxed text-text-subtle">{row.reason}</span>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}

import { useQueries } from "@tanstack/react-query";
import { getFeedbackReport } from "../services/feedbackApi";
import type { FeedbackReport } from "../types/feedback";
import type { InterviewHistoryItem } from "../types/interview";

/**
 * Loads the reports for the most recent completed sessions, so the dashboard can
 * plot score over time from real data.
 *
 * Notes on why it's shaped this way:
 *
 * - **Existing endpoint only.** This calls `GET /feedback/:id` — the same call
 *   the report page makes — once per session. No new API, no aggregate endpoint,
 *   no backend change.
 * - **Shared cache keys.** The query key matches the one the report page and the
 *   "last report" panel already use, so opening a report afterwards is served
 *   from cache rather than refetched.
 * - **Bounded.** Capped at `limit` sessions. A user with fifty interviews should
 *   not fire fifty requests to draw a six-point line.
 * - **404 is data, not failure.** A session whose report was never generated
 *   returns 404; `retry: false` stops that from being retried, and the caller
 *   renders it as a gap in the series rather than as an error or a zero.
 */
export function useReportSeries(history: InterviewHistoryItem[] | undefined, limit = 6) {
  // Oldest → newest, so the chart reads left to right in time order. The history
  // endpoint returns newest first.
  const sessions = (history ?? [])
    .filter((session) => session.status === "completed")
    .slice(0, limit)
    .reverse();

  const results = useQueries({
    queries: sessions.map((session) => ({
      queryKey: ["feedbackReport", session.id],
      queryFn: () => getFeedbackReport(session.id),
      retry: false,
      staleTime: 5 * 60 * 1000,
    })),
  });

  const series = sessions.map((session, index) => {
    const result = results[index];
    return {
      session,
      report: (result?.data as FeedbackReport | undefined) ?? null,
      isLoading: result?.isLoading ?? false,
    };
  });

  return {
    series,
    isLoading: results.some((r) => r.isLoading),
    /** The newest session that actually has a report — the "latest" everywhere else. */
    latest: [...series].reverse().find((entry) => entry.report !== null) ?? null,
  };
}

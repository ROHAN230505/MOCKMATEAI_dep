import { apiRequest } from "../lib/apiClient";

export interface DashboardSummary {
  readinessIndex: number;
  readinessLabel: string;
  mockInterviewsCount: number;
  mockInterviewsAvgScore: number | null;
  aptitudeAvgScore: number | null;
  dsaProblemsSolved: number;
  dsaProblemsTotal: number;
  resumeLastAtsScore: number | null;
  weeklyFocus: WeeklyFocusItem[];
}

export function getDashboardSummary() {
  return apiRequest<DashboardSummary>("/dashboard/summary");
}

/**
 * One "This Week's Focus" chip (Section 4.5).
 *
 * Was a bare string, which left nowhere to put the route the spec requires each
 * chip's Start button to carry.
 */
export interface WeeklyFocusItem {
  id: string;
  label: string;
  /** The measurement behind the suggestion — shown to the candidate, not just logged. */
  reason: string;
  route: string;
  cta: string;
  /** Points this would add to the Readiness Index. Drives the ordering. */
  projectedGain: number;
}

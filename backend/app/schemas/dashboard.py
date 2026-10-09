from app.schemas.common import CamelModel


class DashboardSummary(CamelModel):
    """
    Backs `GET /dashboard/summary` (Section 7.9) for the dashboard shell
    (Section 4.5). Phase 1 has no interview/aptitude/DSA/resume data yet,
    so every module summary is computed honestly as "zero attempts so far"
    rather than a placeholder fake number — Phase 8 wires this up to real
    `readiness_snapshots` aggregation (Section 10.2).
    """

    readiness_index: float
    readiness_label: str
    mock_interviews_count: int
    mock_interviews_avg_score: float | None
    aptitude_avg_score: float | None
    dsa_problems_solved: int
    dsa_problems_total: int
    resume_last_ats_score: int | None
    weekly_focus: list["WeeklyFocusItem"]


class WeeklyFocusItem(CamelModel):
    """
    One "This Week's Focus" chip (Section 4.5).

    Was a bare string, which could not satisfy the spec's requirement that each
    chip carry a Start button "routing to the relevant module" — there was
    nowhere to put the route. `reason` is the measurement behind the suggestion,
    shown rather than logged, and `projectedGain` is what acting on it would add
    to the Readiness Index.
    """

    id: str
    label: str
    reason: str
    route: str
    cta: str
    projected_gain: float

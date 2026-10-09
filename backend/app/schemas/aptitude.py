"""
Aptitude module schemas (Section 8's aptitude tables, Phase 7).

The shape that matters here is what `AptitudeQuestionOut` deliberately omits:
`correct_option_index`. A practice test whose questions arrive with the answer
attached is not a test, and "the frontend won't look" is not a control. The
answer stays server-side and only appears in the result payload after the
attempt has been submitted.
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import AptitudeTopic, Difficulty
from app.schemas.common import CamelModel


class StartAttemptRequest(CamelModel):
    """
    Practice mode only, and that is a schema decision worth recording.

    `aptitude_attempts.test_id` is nullable, which Section 8 documents as
    "null = practice mode". A non-null value would point at a curated test, but
    Section 8 defines no `aptitude_tests` table for one to live in — so there is
    nowhere to reference and every attempt this endpoint creates is practice.
    """

    topics: list[AptitudeTopic] = Field(default_factory=list)
    difficulties: list[Difficulty] = Field(default_factory=list)
    question_count: int = Field(default=10, ge=5, le=30)


class AptitudeQuestionOut(CamelModel):
    id: UUID
    topic: AptitudeTopic
    difficulty: Difficulty
    question_text: str
    options: list[str]


class AttemptOut(CamelModel):
    attempt_id: UUID
    total_questions: int
    questions: list[AptitudeQuestionOut]


class SubmittedAnswer(CamelModel):
    question_id: UUID
    # None means the candidate left it blank, which is scored as incorrect but
    # recorded distinctly from a wrong pick — a blank and a guess are different
    # behaviours and the answer row keeps them apart.
    selected_option_index: int | None = Field(default=None, ge=0, le=9)
    time_spent_seconds: int | None = Field(default=None, ge=0, le=36_000)


class SubmitAttemptRequest(CamelModel):
    answers: list[SubmittedAnswer] = Field(default_factory=list)


class AnswerReviewOut(CamelModel):
    """Post-submission review. This is the only place the correct answer appears."""

    question_id: UUID
    question_text: str
    topic: AptitudeTopic
    difficulty: Difficulty
    options: list[str]
    selected_option_index: int | None
    correct_option_index: int
    is_correct: bool
    time_spent_seconds: int | None


class TopicBreakdownOut(CamelModel):
    topic: AptitudeTopic
    correct: int
    total: int
    # None when the attempt included no questions from this topic, rather than
    # 0% — which would read as having got them all wrong.
    percentage: float | None


class AttemptResultOut(CamelModel):
    attempt_id: UUID
    # Present only for a timed mock test. All derived from stored timestamps and
    # the test definition rather than persisted, so no column exists that could
    # disagree with `started_at`/`submitted_at`.
    test_name: str | None = None
    duration_minutes: int | None = None
    time_taken_seconds: int | None = None
    #: True when the submission landed after the time limit.
    submitted_late: bool = False
    # Stored as a percentage 0-100. `aptitude_attempts.score` is an integer
    # column that the dashboard averages directly into a 0-100 readiness index,
    # so a raw correct-count would make that average meaningless across attempts
    # of different lengths. `total_questions` keeps the denominator.
    score: int
    correct_count: int
    total_questions: int
    topic_breakdown: list[TopicBreakdownOut]
    answers: list[AnswerReviewOut]


class AttemptHistoryItem(CamelModel):
    attempt_id: UUID
    score: int | None
    total_questions: int | None
    started_at: datetime | None = None
    submitted_at: datetime | None = None


class MockTestOut(CamelModel):
    """A curated timed test (Section 4.13). Defined in code — see `content/aptitude_tests.py`."""

    id: UUID
    name: str
    description: str
    question_count: int
    duration_minutes: int
    topics: list[AptitudeTopic]


class TimedAttemptOut(AttemptOut):
    """
    A started mock test.

    Carries the deadline the *server* computed, not a duration the client is
    trusted to count down from: `timeRemainingSeconds` is derived from
    `started_at`, so a reload or a nudged clock gets the same answer.
    """

    test_id: UUID
    test_name: str
    duration_minutes: int
    time_remaining_seconds: int

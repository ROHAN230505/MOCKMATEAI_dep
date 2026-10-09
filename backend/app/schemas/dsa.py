"""
DSA module schemas (Section 8's dsa tables, Phase 7).

Two omissions are load-bearing:

- **`DSAProblemOut` carries only the sample test cases.** The hidden ones stay
  server-side here, even though the browser-based runner needs them at submit
  time. See `SubmitSolutionRequest` for how that tension is resolved and what it
  costs.
- **No reference solution anywhere.** The banks keep one per problem so the test
  cases can be verified by execution, but it is stripped in `build_rows()`, is
  not a column, and `tests/test_content_banks.py` walks the row for callables.
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.models.enums import DSATopic, Difficulty, SubmissionStatus
from app.schemas.common import CamelModel


class TestCaseOut(CamelModel):
    args: list
    expected: object


class DSAProblemListItem(CamelModel):
    id: UUID
    title: str
    topic: DSATopic
    difficulty: Difficulty
    # Whether *this* candidate has a passing submission, so the list can show
    # progress without a second request.
    solved: bool
    attempted: bool


class DSAProblemOut(CamelModel):
    id: UUID
    title: str
    topic: DSATopic
    difficulty: Difficulty
    statement_text: str
    constraints_text: str | None
    starter_code: dict
    function_name: str
    sample_test_cases: list[TestCaseOut]
    hidden_test_case_count: int
    solved: bool


class RunTestsRequest(CamelModel):
    """
    Hidden test cases, fetched for a run.

    This is the honest cost of grading in the browser. Execution happens in the
    candidate's own tab (the chosen design — no server-side code execution), so
    the hidden cases have to travel to the client to be run against, which means
    a candidate willing to open devtools can read them. For a practice tool that
    is an acceptable trade and the UI says so plainly; it would not be acceptable
    for an assessment with stakes, which would need server-side execution.
    """

    language: str = Field(default="python", pattern="^python$")


class HiddenTestCasesOut(CamelModel):
    hidden_test_cases: list[TestCaseOut]


class SubmitSolutionRequest(CamelModel):
    code: str = Field(min_length=1, max_length=50_000)
    language: str = Field(default="python", pattern="^python$")
    # Reported by the in-browser runner. Clamped, and never used to decide
    # whether the submission passed — the server derives `status` from the
    # per-case outcomes it is given, and stores runtime only as reported.
    passed_case_count: int = Field(ge=0, le=1000)
    total_case_count: int = Field(ge=0, le=1000)
    runtime_ms: int | None = Field(default=None, ge=0, le=600_000)
    hints_used_count: int = Field(default=0, ge=0, le=20)


class HintRequest(CamelModel):
    """
    A body rather than query parameters, for two reasons.

    The candidate's code does not belong in a URL: it would land in browser
    history, access logs and any proxy in between, and it can be longer than a
    query string safely carries. That is the same argument this module already
    makes for the hidden-test-cases route.

    And a mistyped query parameter silently falls back to its default, which is
    exactly what happened while writing these endpoints — `hintIndex=4` was
    ignored because FastAPI matched the Python name `hint_index`, so a request
    asking for the fifth hint quietly got the first. A `CamelModel` body is
    validated against the same camelCase contract as every other request here.
    """

    hint_index: int = Field(default=0, ge=0, le=20)
    code: str = Field(default="", max_length=8000)


class DSASubmissionOut(CamelModel):
    id: UUID
    problem_id: UUID
    language: str
    status: SubmissionStatus
    runtime_ms: int | None
    hints_used_count: int
    submitted_at: datetime


class HintOut(CamelModel):
    hint: str
    # "anthropic" / "openai" / "deterministic" — the same disclosure the feedback
    # report makes, so a rule-based hint is never mistaken for model reasoning.
    generated_by: str
    hints_used_count: int


class GenerateProblemRequest(CamelModel):
    """What to write a fresh problem about.

    Both required: a generated problem with no stated topic or difficulty is a
    lottery, and the whole value of generating one is that it targets what the
    candidate wants to practise."""

    topic: DSATopic
    difficulty: Difficulty

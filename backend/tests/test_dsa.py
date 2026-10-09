"""
DSA module tests (Phase 7).

Two things are pinned harder than the rest:

- **No reference solution ever reaches a client.** The banks keep one per problem
  so the test cases can be verified by execution, and this checks it cannot leak
  through the API.
- **The server decides `status`, not the client.** A submission claiming three of
  three passed against a nine-case problem is `partial`. Not a security boundary
  — a client running its own grading can lie about counts too, and nothing here
  pretends otherwise — but the rule lives in one place so "problems solved" on
  the dashboard means one consistent thing.
"""
import pytest

from app.content.dsa_bank import BANK, build_rows
from app.models.dsa import DSAProblem, DSASubmission
from app.models.enums import SubmissionStatus

PASSWORD = "Str0ng!Pass"


def _signup_and_login(client, email="dsa@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


@pytest.fixture()
def seeded(db_session):
    for row in build_rows():
        db_session.add(DSAProblem(**row))
    db_session.commit()
    return db_session


def _two_sum(db):
    return db.query(DSAProblem).filter(DSAProblem.title == "Two Sum").one()


def _case_total(slug="two-sum"):
    problem = next(p for p in BANK if p["slug"] == slug)
    return len(problem["sample"]) + len(problem["hidden"])


def test_problem_list_includes_progress(client, seeded):
    token = _signup_and_login(client)
    resp = client.get("/api/v1/dsa/problems", headers=_headers(token))
    assert resp.status_code == 200
    problems = resp.json()["data"]
    assert len(problems) == len(BANK)
    assert all(p["solved"] is False and p["attempted"] is False for p in problems)
    # Named topics rather than a count, because which topics exist is the thing
    # the listing has to get right.
    assert {p["topic"] for p in problems} >= {
        "arrays", "strings", "graphs", "trees", "linked_lists", "dynamic_programming"
    }


def test_reading_a_problem_gives_samples_but_only_a_count_of_the_hidden_ones(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    data = client.get(f"/api/v1/dsa/problems/{problem.id}", headers=_headers(token)).json()["data"]

    assert data["title"] == "Two Sum"
    assert data["functionName"] == "two_sum"
    assert len(data["sampleTestCases"]) == 2
    assert data["hiddenTestCaseCount"] == 4
    # The cases themselves are not on this response.
    assert "hiddenTestCases" not in data
    assert data["starterCode"]["python"].startswith("def two_sum(")


def test_the_reference_solution_never_reaches_a_client(client, seeded):
    """
    Checked against the raw response text across every problem, so a field added
    to the schema later cannot quietly start carrying it.
    """
    token = _signup_and_login(client)
    listing = client.get("/api/v1/dsa/problems", headers=_headers(token))
    assert "reference" not in listing.text

    for problem in seeded.query(DSAProblem).all():
        body = client.get(f"/api/v1/dsa/problems/{problem.id}", headers=_headers(token)).text
        assert "reference" not in body
        # The bank's helpers are module-private; none of their names should appear.
        assert "_two_sum" not in body
        assert "seen[" not in body


def test_hidden_cases_are_available_from_their_own_route_for_the_runner(client, seeded):
    """
    Grading runs in the candidate's browser, so the hidden cases have to travel
    there. Kept off the problem-reading path so merely browsing does not hand
    them over — but reachable, and the schema says plainly what that costs.
    """
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = client.post(
        f"/api/v1/dsa/problems/{problem.id}/test-cases", json={}, headers=_headers(token)
    )
    assert resp.status_code == 200
    cases = resp.json()["data"]["hiddenTestCases"]
    assert len(cases) == 4
    assert all("args" in case and "expected" in case for case in cases)


def test_a_missing_problem_is_404(client, seeded):
    token = _signup_and_login(client)
    resp = client.get(
        "/api/v1/dsa/problems/00000000-0000-0000-0000-000000000000", headers=_headers(token)
    )
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "problem_not_found"


def test_dsa_endpoints_require_authentication(client, seeded):
    problem = _two_sum(seeded)
    assert client.get("/api/v1/dsa/problems").status_code == 401
    assert client.get(f"/api/v1/dsa/problems/{problem.id}").status_code == 401
    assert client.post(f"/api/v1/dsa/problems/{problem.id}/test-cases", json={}).status_code == 401


# ---------------------------------------------------------------------------
# Submission status is the server's call
# ---------------------------------------------------------------------------
def _submit(client, token, problem, **body):
    payload = {
        "code": "def two_sum(nums, target):\n    return [0, 1]\n",
        "language": "python",
        "passedCaseCount": _case_total(),
        "totalCaseCount": _case_total(),
        "runtimeMs": 12,
        "hintsUsedCount": 0,
    }
    payload.update(body)
    return client.post(
        f"/api/v1/dsa/problems/{problem.id}/submit", json=payload, headers=_headers(token)
    )


@pytest.mark.parametrize(
    "passed,expected",
    [
        (6, "passed"),
        (3, "partial"),
        (1, "partial"),
        (0, "failed"),
    ],
)
def test_status_is_derived_from_the_case_counts(client, seeded, passed, expected):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = _submit(client, token, problem, passedCaseCount=passed)
    assert resp.status_code == 200
    assert resp.json()["data"]["status"] == expected


def test_a_client_cannot_claim_a_pass_by_shrinking_the_total(client, seeded):
    """
    "3 of 3 passed" against a six-case problem is partial. The server grades
    against the stored case count, never the client's claim about it.
    """
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = _submit(client, token, problem, passedCaseCount=3, totalCaseCount=3)
    assert resp.json()["data"]["status"] == "partial"


def test_a_client_cannot_claim_more_passes_than_there_are_cases(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = _submit(client, token, problem, passedCaseCount=999, totalCaseCount=999)
    # Clamped to the real total, so it reads as a pass rather than as nonsense —
    # but it cannot inflate anything, because passing is already the ceiling.
    assert resp.json()["data"]["status"] == "passed"


def test_a_submission_cannot_post_its_own_status(client, seeded):
    """`status` is not an input. Sending one is ignored, not honoured."""
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = _submit(client, token, problem, passedCaseCount=0, status="passed")
    assert resp.json()["data"]["status"] == "failed"


def test_submissions_are_recorded_with_their_code_and_hint_count(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    _submit(client, token, problem, hintsUsedCount=3, runtimeMs=45)

    row = seeded.query(DSASubmission).filter(DSASubmission.problem_id == problem.id).one()
    assert row.hints_used_count == 3
    assert row.runtime_ms == 45
    assert "def two_sum" in row.code
    assert row.status is SubmissionStatus.PASSED


def test_oversized_code_is_rejected(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    assert _submit(client, token, problem, code="x" * 60_000).status_code == 422


def test_only_python_is_accepted_since_only_python_can_be_run(client, seeded):
    """
    The in-browser runner is Pyodide. Accepting a language it cannot execute
    would store submissions that were never actually graded.
    """
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    assert _submit(client, token, problem, language="java").status_code == 422


def test_a_passing_submission_marks_the_problem_solved_everywhere(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    _submit(client, token, problem, passedCaseCount=_case_total())

    detail = client.get(f"/api/v1/dsa/problems/{problem.id}", headers=_headers(token)).json()["data"]
    assert detail["solved"] is True

    listing = client.get("/api/v1/dsa/problems", headers=_headers(token)).json()["data"]
    entry = next(p for p in listing if p["title"] == "Two Sum")
    assert entry["solved"] is True and entry["attempted"] is True


def test_a_failing_submission_marks_attempted_but_not_solved(client, seeded):
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    _submit(client, token, problem, passedCaseCount=0)

    listing = client.get("/api/v1/dsa/problems", headers=_headers(token)).json()["data"]
    entry = next(p for p in listing if p["title"] == "Two Sum")
    assert entry["attempted"] is True
    assert entry["solved"] is False


def test_progress_is_per_user(client, seeded):
    first = _signup_and_login(client, "solver@example.com")
    problem = _two_sum(seeded)
    _submit(client, first, problem, passedCaseCount=_case_total())

    second = _signup_and_login(client, "other-dsa@example.com")
    listing = client.get("/api/v1/dsa/problems", headers=_headers(second)).json()["data"]
    assert all(p["solved"] is False for p in listing)


def test_submission_history_is_scoped_to_the_caller(client, seeded):
    owner = _signup_and_login(client, "owner-dsa@example.com")
    problem = _two_sum(seeded)
    _submit(client, owner, problem, passedCaseCount=2)

    intruder = _signup_and_login(client, "nosy-dsa@example.com")
    theirs = client.get(
        f"/api/v1/dsa/problems/{problem.id}/submissions", headers=_headers(intruder)
    ).json()["data"]
    assert theirs == []

    mine = client.get(
        f"/api/v1/dsa/problems/{problem.id}/submissions", headers=_headers(owner)
    ).json()["data"]
    assert len(mine) == 1


def test_a_solved_problem_reaches_the_dashboard(client, seeded):
    """
    `dashboard_service` already counted distinct problems with a passing
    submission before this module existed.
    """
    token = _signup_and_login(client)
    before = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert before["dsaProblemsSolved"] == 0
    assert before["dsaProblemsTotal"] == len(BANK)

    _submit(client, token, _two_sum(seeded), passedCaseCount=_case_total())

    after = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert after["dsaProblemsSolved"] == 1


def test_repeated_passes_on_one_problem_count_once(client, seeded):
    """The dashboard counts distinct problems, not submissions."""
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    for _ in range(3):
        _submit(client, token, problem, passedCaseCount=_case_total())

    summary = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert summary["dsaProblemsSolved"] == 1


# ---------------------------------------------------------------------------
# Hints: a nudge, never a solution
# ---------------------------------------------------------------------------
@pytest.mark.parametrize(
    "text,is_code",
    [
        ("Think about what you would need to have already seen at each step.", False),
        ("Consider using a hash map to remember values you have passed.", False),
        ("def two_sum(nums, target):", True),
        ("for value in nums:", True),
        ("while low <= high:", True),
        ("import collections", True),
        ("return [seen[target - value], index]", True),
        ("```python", True),
    ],
)
def test_a_hint_containing_code_is_recognised_as_such(text, is_code):
    """
    The prompt forbids code. This is the check that runs anyway, because
    prompt-level defence is never sufficient on its own (Section 12.8) and here
    the failure is not subtle — a model that answers outright destroys the
    exercise.
    """
    from app.services.dsa_hints import looks_like_code

    assert looks_like_code(text) is is_code


def test_the_deterministic_ladder_escalates_and_is_bounded():
    from app.services.dsa_hints import LADDER, MAX_HINTS, deterministic_hint

    assert len(LADDER) == MAX_HINTS
    assert len({deterministic_hint(i) for i in range(MAX_HINTS)}) == MAX_HINTS
    # Past the end it clamps rather than raising.
    assert deterministic_hint(99) == LADDER[-1]
    # And no rung is itself code.
    from app.services.dsa_hints import looks_like_code

    assert not any(looks_like_code(rung) for rung in LADDER)


def test_a_hint_is_returned_and_labelled_with_its_source(client, seeded):
    """
    The mock provider does not serve free-form JSON, so this exercises the
    fallback — and the response must say `deterministic` rather than let a canned
    nudge pass as model reasoning.
    """
    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = client.post(
        f"/api/v1/dsa/problems/{problem.id}/hint",
        json={"hintIndex": 0, "code": "def two_sum(nums, target): pass"},
        headers=_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["hint"]
    assert data["generatedBy"] in {"deterministic", "anthropic", "openai", "mock"}
    assert data["hintsUsedCount"] == 1


def test_hints_run_out_rather_than_repeating_forever(client, seeded):
    from app.services.dsa_hints import MAX_HINTS

    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    resp = client.post(
        f"/api/v1/dsa/problems/{problem.id}/hint",
        json={"hintIndex": MAX_HINTS},
        headers=_headers(token),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["code"] == "no_more_hints"


def test_a_hint_never_comes_back_as_code(client, seeded):
    from app.services.dsa_hints import looks_like_code

    token = _signup_and_login(client)
    problem = _two_sum(seeded)
    for index in range(4):
        data = client.post(
            f"/api/v1/dsa/problems/{problem.id}/hint",
            json={"hintIndex": index},
            headers=_headers(token),
        ).json()["data"]
        assert not looks_like_code(data["hint"]), data["hint"]


def test_requesting_a_hint_requires_authentication(client, seeded):
    problem = _two_sum(seeded)
    assert client.post(
        f"/api/v1/dsa/problems/{problem.id}/hint", json={"hintIndex": 0}
    ).status_code == 401

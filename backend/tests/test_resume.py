"""
Resume analyzer tests (Phase 8).

The load-bearing claims here are about what the score is *not*. It is not a
prediction of any real ATS — those are proprietary and disagree with each other —
so what it must be instead is explainable: every component visible, nothing
scored that was not measured, and no keyword advice that tells a candidate to add
a word they already used.
"""
import pytest

from app.models.resume import ResumeAnalysis
from app.services.resume import analyzer
from app.services.resume.service import NOT_STORED

PASSWORD = "Str0ng!Pass"

STRONG_RESUME = """Jane Doe
jane.doe@example.com | +1 555 123 4567 | linkedin.com/in/janedoe

EXPERIENCE
Senior Backend Engineer, Acme (2021-2024)
- Cut p95 checkout latency from 2100ms to 180ms by batching 40 sequential queries into one.
- Led a team of 4 engineers migrating 120 services onto a new deployment pipeline.
- Reduced infrastructure spend by 32% across two quarters.
- Introduced contract tests that cut integration failures from 15 a week to under 2.

Backend Engineer, Globex (2019-2021)
- Built an event pipeline processing 2 million records a day.
- Automated a release process that had taken 3 hours down to 12 minutes.

EDUCATION
BSc Computer Science, University of Somewhere, 2019

SKILLS
Python, PostgreSQL, Redis, Docker, Kubernetes, FastAPI, React, Terraform
""" + ("Additional relevant detail about delivery and collaboration. " * 20)

WEAK_RESUME = """John Smith

I am responsible for various tasks at my company. Worked on several projects.
Helped with the team. Involved in meetings and other duties included admin.
""" + ("More narrative prose without structure or numbers. " * 12)


def _signup_and_login(client, email="resume@example.com"):
    client.post("/api/v1/auth/signup", json={"name": "Ada", "email": email, "password": PASSWORD})
    return client.post(
        "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
    ).json()["data"]["accessToken"]


def _headers(token):
    return {"Authorization": "Bearer " + token}


# ---------------------------------------------------------------------------
# The analyser itself
# ---------------------------------------------------------------------------
def test_a_well_formed_resume_outscores_a_weak_one():
    strong = analyzer.analyse(STRONG_RESUME)
    weak = analyzer.analyse(WEAK_RESUME)
    assert strong.ats_score > weak.ats_score
    assert strong.ats_score >= 80
    assert weak.ats_score <= 55


def test_every_component_is_returned_so_the_score_is_explainable():
    """
    The number is only defensible if a candidate can see what produced it. A bare
    score would be exactly the kind of unexplained figure this codebase refuses
    everywhere else.
    """
    result = analyzer.analyse(STRONG_RESUME)
    names = {component.name for component in result.components}
    assert names == {"parseability", "sections", "contact", "impact"}
    for component in result.components:
        assert 0 <= component.score <= 100
        assert component.detail.strip()
        assert 0 < component.weight <= 1


def test_keyword_matching_is_unmeasured_without_a_job_description():
    """
    Not scored as zero. A candidate who pasted no job description has not failed
    keyword matching, they have not been assessed on it — the same rule Section
    10.2 applies to the interview categories.
    """
    result = analyzer.analyse(STRONG_RESUME)
    assert "keywords" in result.unmeasured
    assert all(component.name != "keywords" for component in result.components)
    # NULL, not [] — an empty list would read as "we looked and found no gaps".
    assert result.keyword_gaps is None
    assert result.matched_keywords is None


def test_supplying_a_job_description_adds_the_keyword_component():
    result = analyzer.analyse(
        STRONG_RESUME,
        "Senior Python engineer. Kubernetes and Terraform required. Kafka experience a plus.",
    )
    assert "keywords" not in result.unmeasured
    keyword = next(c for c in result.components if c.name == "keywords")
    assert keyword.score > 0
    assert result.keyword_gaps is not None
    assert "kafka" in result.keyword_gaps
    assert "kubernetes" in result.matched_keywords


def test_dropping_a_component_renormalises_rather_than_capping_the_score():
    """
    Without renormalisation, a resume with no job description could never exceed
    75 — the sum of the other weights — and the two scores would not mean the
    same thing.
    """
    perfect = analyzer.analyse(STRONG_RESUME)
    total_weight = sum(component.weight for component in perfect.components)
    assert total_weight < 1.0  # keywords' 0.25 is absent
    assert perfect.ats_score > 75


def test_an_unreadable_document_scores_nothing_rather_than_zero():
    """
    A scanned resume extracts as almost nothing. That is a failure to measure,
    and it is reported as one, with advice that names the actual cause.
    """
    result = analyzer.analyse("   ")
    assert result.ats_score is None
    assert result.word_count == 0
    assert any("scanned" in suggestion or "image" in suggestion for suggestion in result.suggestions)


def test_keyword_advice_does_not_tell_you_to_add_a_word_you_already_used():
    """
    Substring matching, deliberately in the loose direction. "engineering" in the
    resume satisfies "engineer" in the advert. Erring the other way would send
    candidates to pad their resume with synonyms they already have, which makes
    resumes worse rather than better.
    """
    resume = "I did backend engineering with containerised deployments and automated testing."
    result = analyzer.analyse(resume, "Backend engineer. Container experience. Automation required.")
    assert "engineer" not in (result.keyword_gaps or [])
    assert "container" not in (result.keyword_gaps or [])


def test_sentence_punctuation_is_not_reported_as_a_missing_keyword():
    """
    A real bug found while building this. The tokeniser keeps trailing dots so
    "node.js" survives, which meant a sentence-ending "experience." never matched
    the stop list and came back as a keyword the candidate should add.
    """
    gaps = analyzer.analyse("Python developer.", "Five years of experience. Django required.").keyword_gaps
    assert gaps is not None
    assert not any(word.endswith(".") for word in gaps), gaps
    assert "experience" not in gaps


def test_real_skill_names_survive_tokenisation():
    """The other half of that fix: stripping "+" turned "c++" into "c"."""
    assert analyzer._tokens("C++ and C# and Node.js and asp.net.") == [
        "c++", "and", "c#", "and", "node.js", "and", "asp.net",
    ]
    assert "c++" in analyzer.extract_keywords("Senior C++ engineer. C++ required.")


def test_keywords_are_ordered_by_how_often_the_advert_asks_for_them():
    keywords = analyzer.extract_keywords(
        "Terraform is essential. Terraform, Terraform. We also use Rust occasionally."
    )
    assert keywords[0] == "terraform"


@pytest.mark.parametrize(
    "resume,expected_low",
    [
        # No contact details anywhere near the top.
        ("EXPERIENCE\n- Did things with numbers like 40% and 12ms\nEDUCATION\nBSc", "contact"),
        # Contact details but no recognisable section headings.
        ("a@b.com +1 555 111 2222\nI have done many things over 10 years.", "sections"),
    ],
)
def test_each_component_can_be_the_one_that_fails(resume, expected_low):
    result = analyzer.analyse(resume)
    component = next(c for c in result.components if c.name == expected_low)
    assert component.score < 60, f"{expected_low} scored {component.score}"


def test_suggestions_are_triggered_by_what_was_measured():
    """
    Not a fixed list of resume advice. A resume with good contact details is never
    told to add contact details.
    """
    strong = analyzer.analyse(STRONG_RESUME)
    assert not any("email, phone" in s for s in strong.suggestions)

    weak = analyzer.analyse(WEAK_RESUME)
    joined = " ".join(weak.suggestions)
    assert "Experience, Education, Skills" in joined
    assert "results" in joined


def test_a_clean_resume_still_gets_a_useful_line():
    result = analyzer.analyse(STRONG_RESUME)
    assert result.suggestions, "an empty suggestion list would look like a broken screen"


# ---------------------------------------------------------------------------
# The API, and what it stores
# ---------------------------------------------------------------------------
def test_analysing_a_resume_returns_the_full_explanation(client, db_session):
    token = _signup_and_login(client)
    resp = client.post(
        "/api/v1/resume/analyses",
        json={"resumeText": STRONG_RESUME, "fileName": "jane-doe-cv.pdf"},
        headers=_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()["data"]
    assert data["atsScore"] >= 80
    assert len(data["components"]) == 4
    assert data["unmeasured"] == ["keywords"]
    assert data["keywordGaps"] is None
    assert data["hadJobDescription"] is False
    assert data["suggestions"]


def test_the_resume_text_is_never_stored(client, db_session):
    """
    Only what was derived from it. The document itself stays on the candidate's
    machine, and nothing recognisable from it reaches the database.
    """
    token = _signup_and_login(client)
    client.post(
        "/api/v1/resume/analyses",
        json={"resumeText": STRONG_RESUME, "fileName": "jane-doe-cv.pdf"},
        headers=_headers(token),
    )

    row = db_session.query(ResumeAnalysis).one()
    serialised = repr(
        [row.file_storage_url, row.job_description_text, row.keyword_gaps, row.suggestions]
    )
    assert "Jane Doe" not in serialised
    assert "jane.doe@example.com" not in serialised
    assert "555 123 4567" not in serialised
    assert "Acme" not in serialised
    # The filename is not stored either: it routinely contains the candidate's name.
    assert "jane-doe-cv" not in serialised


def test_the_storage_column_says_plainly_that_nothing_was_stored(client, db_session):
    """
    `file_storage_url` is NOT NULL and this build stores no file. A path shaped
    like a URL to a file that does not exist would be the exact failure this
    codebase rules out everywhere else.
    """
    token = _signup_and_login(client)
    client.post("/api/v1/resume/analyses", json={"resumeText": STRONG_RESUME}, headers=_headers(token))

    row = db_session.query(ResumeAnalysis).one()
    assert row.file_storage_url == NOT_STORED
    assert not row.file_storage_url.startswith("http")
    assert not row.file_storage_url.startswith("/")
    assert "not-stored" in row.file_storage_url


def test_the_job_description_is_stored_because_gaps_are_meaningless_without_it(client, db_session):
    token = _signup_and_login(client)
    client.post(
        "/api/v1/resume/analyses",
        json={"resumeText": STRONG_RESUME, "jobDescriptionText": "Kafka and Terraform required."},
        headers=_headers(token),
    )
    row = db_session.query(ResumeAnalysis).one()
    assert "Kafka" in (row.job_description_text or "")


def test_a_past_analysis_reads_back_identically(client, db_session):
    """History and a fresh run must agree, or the score changes when you revisit it."""
    token = _signup_and_login(client)
    fresh = client.post(
        "/api/v1/resume/analyses",
        json={"resumeText": STRONG_RESUME, "jobDescriptionText": "Kubernetes and Kafka."},
        headers=_headers(token),
    ).json()["data"]

    again = client.get(f"/api/v1/resume/analyses/{fresh['id']}", headers=_headers(token)).json()["data"]
    assert again == fresh


def test_history_lists_past_analyses(client, db_session):
    token = _signup_and_login(client)
    client.post("/api/v1/resume/analyses", json={"resumeText": STRONG_RESUME}, headers=_headers(token))
    client.post(
        "/api/v1/resume/analyses",
        json={"resumeText": WEAK_RESUME, "jobDescriptionText": "Python."},
        headers=_headers(token),
    )
    history = client.get("/api/v1/resume/analyses", headers=_headers(token)).json()["data"]
    assert len(history) == 2
    assert {item["hadJobDescription"] for item in history} == {True, False}


def test_another_user_cannot_read_someone_elses_analysis(client, db_session):
    owner = _signup_and_login(client, "owner-cv@example.com")
    created = client.post(
        "/api/v1/resume/analyses", json={"resumeText": STRONG_RESUME}, headers=_headers(owner)
    ).json()["data"]

    intruder = _signup_and_login(client, "nosy-cv@example.com")
    assert client.get(
        f"/api/v1/resume/analyses/{created['id']}", headers=_headers(intruder)
    ).status_code == 404
    assert client.get("/api/v1/resume/analyses", headers=_headers(intruder)).json()["data"] == []


def test_resume_endpoints_require_authentication(client):
    assert client.post("/api/v1/resume/analyses", json={"resumeText": "x"}).status_code == 401
    assert client.get("/api/v1/resume/analyses").status_code == 401


@pytest.mark.parametrize(
    "payload",
    [
        {"resumeText": ""},
        {"resumeText": "x" * 60_001},
        {"resumeText": "ok", "jobDescriptionText": "y" * 20_001},
    ],
)
def test_oversized_or_empty_input_is_rejected(client, payload):
    token = _signup_and_login(client)
    assert client.post("/api/v1/resume/analyses", json=payload, headers=_headers(token)).status_code == 422


def test_an_analysis_reaches_the_dashboard(client, db_session):
    """
    `dashboard_service` already read the latest `ats_score` before this module
    existed — the same handoff Phases 5 and 7 had.
    """
    token = _signup_and_login(client)
    before = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert before["resumeLastAtsScore"] is None

    client.post("/api/v1/resume/analyses", json={"resumeText": STRONG_RESUME}, headers=_headers(token))

    after = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert after["resumeLastAtsScore"] is not None
    assert after["resumeLastAtsScore"] >= 80


def test_the_dashboard_uses_the_most_recent_analysis(client, db_session):
    token = _signup_and_login(client)
    client.post("/api/v1/resume/analyses", json={"resumeText": STRONG_RESUME}, headers=_headers(token))
    client.post("/api/v1/resume/analyses", json={"resumeText": WEAK_RESUME}, headers=_headers(token))

    summary = client.get("/api/v1/dashboard/summary", headers=_headers(token)).json()["data"]
    assert summary["resumeLastAtsScore"] <= 55

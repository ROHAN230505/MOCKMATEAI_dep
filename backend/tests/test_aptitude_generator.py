"""
Generated aptitude questions, and the verification that stands between a model
and a candidate's score.

The structural checks are pure and tested directly. The verification round trip
is tested against a stub gateway rather than a live provider, per Section 15 --
and because the cases that matter here (the model contradicting its own answer
key, the provider being down) are ones you cannot ask a real provider to
produce on demand.
"""
import pytest

from app.models.enums import AptitudeTopic, Difficulty
from app.services import aptitude_generator as gen
from app.services.ai.errors import LLMServiceError


def _question(**over):
    base = {
        "question_text": "A train travels 120 km in 2 hours. What is its average speed?",
        "options": ["40 km/h", "50 km/h", "60 km/h", "70 km/h"],
        "correct_option_index": 2,
        "why": "120 km / 2 h = 60 km/h.",
    }
    base.update(over)
    return base


# --- structural rejection -------------------------------------------------
def test_a_well_formed_question_passes():
    assert gen.structural_problem(_question()) is None


@pytest.mark.parametrize(
    "over,expected",
    [
        ({"options": ["a", "b", "c"]}, "exactly"),
        ({"options": ["a", "b", "c", "d", "e"]}, "exactly"),
        ({"correct_option_index": 4}, "out of range"),
        ({"correct_option_index": -1}, "out of range"),
        ({"question_text": ""}, "missing"),
        ({"why": ""}, "working"),
        ({"options": ["a", "b", "c", ""]}, "empty"),
    ],
)
def test_malformed_questions_are_rejected(over, expected):
    problem = gen.structural_problem(_question(**over))
    assert problem is not None and expected in problem


def test_duplicate_options_are_rejected_case_insensitively():
    """
    "12 KM" and "12 km" are the same answer offered twice, which makes the
    question unanswerable rather than merely easy.
    """
    assert gen.structural_problem(_question(options=["12 km", "12 KM", "13 km", "14 km"])) is not None


def test_all_of_the_above_is_rejected():
    """Not a distractor: it changes the question into a different one."""
    assert gen.structural_problem(
        _question(options=["40 km/h", "50 km/h", "60 km/h", "All of the above"])
    ) is not None


def test_an_index_out_of_range_is_caught_before_any_provider_call():
    """The check that makes a question unanswerable rather than just wrong."""
    assert "out of range" in gen.structural_problem(_question(correct_option_index=9))


# --- verification ---------------------------------------------------------
#
# The point of the whole module. A generated question is a measurement the
# candidate is scored against, so a wrong answer key marks a correct answer
# wrong and nobody ever finds out.


class _StubResponse:
    def __init__(self, payload, provider="stub"):
        self.payload = payload
        self.provider = provider


class _StubGateway:
    """Returns a queued payload per call, so a generate-then-verify sequence
    can be scripted exactly."""

    def __init__(self, payloads):
        self._payloads = list(payloads)
        self.calls = 0

    async def complete_json(self, request):
        self.calls += 1
        item = self._payloads.pop(0) if self._payloads else {}
        if isinstance(item, Exception):
            raise item
        return _StubResponse(item)


@pytest.fixture()
def stub(monkeypatch):
    def install(payloads):
        gateway = _StubGateway(payloads)
        monkeypatch.setattr(gen, "get_gateway", lambda: gateway)
        return gateway

    return install


@pytest.mark.anyio
async def test_a_question_whose_key_the_solver_disputes_is_discarded(stub):
    """
    The case this exists for: the generator marks index 2, an independent
    solve says index 1. One of them is wrong and there is no way to tell
    which, so the question does not reach a candidate.
    """
    stub([
        {"questions": [_question(correct_option_index=2)]},
        {"answer_index": 1, "working": "I make it 50."},
    ])
    out = await gen.generate_verified(
        topics=[AptitudeTopic.QUANTITATIVE], difficulties=[Difficulty.EASY], count=1
    )
    assert out == []


@pytest.mark.anyio
async def test_a_question_the_solver_agrees_with_survives(stub):
    stub([
        {"questions": [_question(correct_option_index=2)]},
        {"answer_index": 2, "working": "120/2 = 60."},
    ])
    out = await gen.generate_verified(
        topics=[AptitudeTopic.QUANTITATIVE], difficulties=[Difficulty.EASY], count=1
    )
    assert len(out) == 1
    assert out[0].correct_option_index == 2


@pytest.mark.anyio
async def test_a_solver_reporting_no_correct_option_discards_the_question(stub):
    """-1 is the solver saying the question is broken, not answering it."""
    stub([
        {"questions": [_question()]},
        {"answer_index": -1, "working": "None of these is right."},
    ])
    assert await gen.generate_verified(topics=[], difficulties=[], count=1) == []


@pytest.mark.anyio
async def test_a_provider_outage_yields_nothing_rather_than_raising(stub):
    """The caller tops up from the bank; a failed generation is not an error."""
    stub([LLMServiceError("provider down", provider="stub")])
    assert await gen.generate_verified(topics=[], difficulties=[], count=5) == []


@pytest.mark.anyio
async def test_a_failed_verification_call_discards_rather_than_trusts(stub):
    """Unverified is treated as unusable, never as 'probably fine'."""
    stub([
        {"questions": [_question()]},
        LLMServiceError("rate limited", provider="stub"),
    ])
    assert await gen.generate_verified(topics=[], difficulties=[], count=1) == []


@pytest.mark.anyio
async def test_malformed_questions_never_reach_verification(stub):
    """A round trip saved, and the reason structural checks run first."""
    gateway = stub([{"questions": [_question(options=["a", "b"])]}])
    assert await gen.generate_verified(topics=[], difficulties=[], count=1) == []
    assert gateway.calls == 1, "a malformed question should not be verified"


@pytest.mark.anyio
async def test_it_returns_no_more_than_asked_for(stub):
    """It over-generates to absorb rejections; the surplus must not leak out."""
    stub([
        {"questions": [_question(question_text=f"Q{i}?") for i in range(6)]},
        *[{"answer_index": 2, "working": "ok"} for _ in range(6)],
    ])
    out = await gen.generate_verified(topics=[], difficulties=[], count=2)
    assert len(out) == 2


@pytest.fixture()
def seeded(db_session):
    """The curated bank, inserted directly. These cases are about falling back
    to it, so an empty bank would make them pass for the wrong reason."""
    from app.content.aptitude_bank import build_rows
    from app.models.aptitude import AptitudeQuestion

    for row in build_rows():
        db_session.add(
            AptitudeQuestion(
                topic=row["topic"],
                difficulty=row["difficulty"],
                question_text=row["question_text"],
                options=row["options"],
                correct_option_index=row["correct_option_index"],
                company_pattern_tag=row["company_pattern_tag"],
            )
        )
    db_session.commit()
    return db_session

# --- the deadline ---------------------------------------------------------
@pytest.mark.anyio
async def test_generation_past_the_deadline_falls_back_to_the_bank(seeded, db_session, monkeypatch):
    """
    Bounded waiting is the difference between a feature and a hang. Generation
    measured 9-17s on a free tier; a candidate staring at a spinner assumes the
    page is broken, and there is no honest progress to show them because
    revealing questions one at a time would reveal which failed verification.
    """
    import asyncio

    from app.services import aptitude_service

    async def never_finishes(**_kwargs):
        await asyncio.sleep(60)

    monkeypatch.setattr(aptitude_service.aptitude_generator, "generate_verified", never_finishes)
    monkeypatch.setattr(aptitude_service, "GENERATION_DEADLINE_SECONDS", 0.05)

    questions = await aptitude_service.build_question_set(
        db_session, topics=[], difficulties=[], count=5
    )

    assert len(questions) == 5
    assert all(q.is_generated is False for q in questions), "the bank should have served all five"


@pytest.mark.anyio
async def test_a_generator_crash_still_yields_a_full_test(seeded, db_session, monkeypatch):
    """A test must never fail to start because the clever path broke."""
    from app.services import aptitude_service

    async def explodes(**_kwargs):
        raise RuntimeError("generator is broken")

    monkeypatch.setattr(aptitude_service.aptitude_generator, "generate_verified", explodes)

    questions = await aptitude_service.build_question_set(
        db_session, topics=[], difficulties=[], count=4
    )
    assert len(questions) == 4


@pytest.mark.anyio
async def test_a_partial_generation_is_topped_up_from_the_bank(seeded, db_session, monkeypatch):
    """
    Verification rejecting some questions is the system working, not a
    shortfall -- the candidate still gets a full-length test.
    """
    from app.models.enums import AptitudeTopic, Difficulty as D
    from app.services import aptitude_service

    async def two_only(**_kwargs):
        return [
            gen.GeneratedQuestion(
                topic=AptitudeTopic.QUANTITATIVE,
                difficulty=D.EASY,
                question_text=f"Generated {i}?",
                options=["a", "b", "c", "d"],
                correct_option_index=i % 4,
                why="because",
            )
            for i in range(2)
        ]

    monkeypatch.setattr(aptitude_service.aptitude_generator, "generate_verified", two_only)

    questions = await aptitude_service.build_question_set(
        db_session, topics=[], difficulties=[], count=6
    )
    assert len(questions) == 6
    assert sum(1 for q in questions if q.is_generated) == 2


@pytest.mark.anyio
async def test_generated_questions_never_pollute_the_curated_pool(seeded, db_session, monkeypatch):
    """
    They are written for one attempt. Sampled again later they would become a
    permanent part of a bank whose whole guarantee is execution-verified keys.
    """
    from app.models.enums import AptitudeTopic, Difficulty as D
    from app.services import aptitude_service

    aptitude_service.persist_generated(
        db_session,
        [
            gen.GeneratedQuestion(
                topic=AptitudeTopic.QUANTITATIVE,
                difficulty=D.EASY,
                question_text="A generated question that must never be resampled",
                options=["a", "b", "c", "d"],
                correct_option_index=0,
                why="because",
            )
        ],
    )
    db_session.commit()

    pool = aptitude_service.select_questions(db_session, topics=[], difficulties=[], count=100)
    assert all(not q.is_generated for q in pool)

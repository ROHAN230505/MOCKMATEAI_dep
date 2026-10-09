"""
Generated DSA problems, and the recomputation that stands between a model and
a candidate's grade.

The stakes differ from aptitude. A wrong MCQ key marks one answer wrong; a
wrong hidden test case fails a CORRECT submission and shows the candidate a
diff between their right answer and a wrong one, with no way to tell which is
which.
"""
import pytest

from app.models.enums import Difficulty, DSATopic
from app.services import dsa_generator as gen
from app.services.ai.errors import LLMServiceError


def _payload(**over):
    base = {
        "title": "Sum of Two Largest Distinct Elements",
        "statement_text": "Return the sum of the two largest distinct values.",
        "constraints_text": "0 <= len(arr) <= 10000",
        "function_name": "sum_two_largest_distinct",
        "starter_code": "def sum_two_largest_distinct(arr):\n    pass\n",
        "sample": [
            {"args": [[1, 5, 3, 9, 7]], "expected": 16},
            {"args": [[4, 4, 4]], "expected": 4},
        ],
        "hidden": [
            {"args": [[]], "expected": 0},
            {"args": [[10]], "expected": 10},
            {"args": [[5, -3]], "expected": 2},
        ],
    }
    base.update(over)
    return base


# --- structural rejection -------------------------------------------------
def test_a_well_formed_problem_passes():
    assert gen.structural_problem(_payload()) is None


def test_a_function_name_the_starter_code_does_not_define_is_rejected():
    """The runner finds the entry point by name; a mismatch is unrunnable."""
    assert gen.structural_problem(_payload(function_name="other_name")) is not None


@pytest.mark.parametrize("name", ["class", "2fast", "has space", ""])
def test_an_unusable_identifier_is_rejected(name):
    assert gen.structural_problem(_payload(function_name=name)) is not None


def test_too_few_cases_are_rejected():
    assert gen.structural_problem(_payload(sample=[{"args": [[1]], "expected": 1}])) is not None
    assert gen.structural_problem(_payload(hidden=[{"args": [[1]], "expected": 1}])) is not None


def test_args_that_are_not_a_list_are_rejected():
    """`args` is applied positionally; anything else cannot be called."""
    bad = _payload(hidden=[{"args": {"n": 1}, "expected": 1}, *_payload()["hidden"][1:]])
    assert gen.structural_problem(bad) is not None


def test_a_missing_expected_value_is_rejected():
    bad = _payload(hidden=[{"args": [[1]]}, *_payload()["hidden"][1:]])
    assert "expected" in (gen.structural_problem(bad) or "")


def test_cases_that_all_expect_the_same_value_are_rejected():
    """A function returning that constant would pass, so it grades nothing."""
    same = [{"args": [[i]], "expected": 7} for i in range(5)]
    problem = gen.structural_problem(_payload(sample=same[:2], hidden=same[2:]))
    assert problem is not None and "constant" in problem


# --- recomputation --------------------------------------------------------
class _StubResponse:
    def __init__(self, payload):
        self.payload = payload
        self.provider = "stub"


class _StubGateway:
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


def _agreeing(payload):
    cases = payload["sample"] + payload["hidden"]
    return {"results": [{"index": i, "expected": c["expected"]} for i, c in enumerate(cases)]}


@pytest.mark.anyio
async def test_a_problem_whose_outputs_recompute_identically_survives(stub):
    payload = _payload()
    stub([payload, _agreeing(payload)])
    out = await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY)
    assert out is not None
    assert out.function_name == "sum_two_largest_distinct"
    assert len(out.hidden) == 3


@pytest.mark.anyio
async def test_one_disagreeing_case_discards_the_whole_problem(stub):
    """
    Not "drop that case" -- drop the problem. A statement the two calls read
    differently is ambiguous, and the remaining cases are no more trustworthy
    than the one that disagreed.
    """
    payload = _payload()
    verdict = _agreeing(payload)
    verdict["results"][3]["expected"] = 999
    stub([payload, verdict])
    assert await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY) is None


@pytest.mark.anyio
async def test_a_short_verification_response_discards_the_problem(stub):
    """Fewer results than cases means some were never checked."""
    payload = _payload()
    verdict = _agreeing(payload)
    verdict["results"] = verdict["results"][:2]
    stub([payload, verdict])
    assert await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY) is None


@pytest.mark.anyio
async def test_agreement_is_exact_not_approximate(stub):
    """The grader compares exactly, so 16 and 16.0 are not the same answer."""
    payload = _payload()
    verdict = _agreeing(payload)
    verdict["results"][0]["expected"] = 16.0000001
    stub([payload, verdict])
    assert await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY) is None


@pytest.mark.anyio
async def test_a_malformed_problem_never_reaches_verification(stub):
    gateway = stub([_payload(function_name="nope")])
    assert await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY) is None
    assert gateway.calls == 1


@pytest.mark.anyio
async def test_a_provider_outage_returns_none_rather_than_raising(stub):
    stub([LLMServiceError("down", provider="stub")])
    assert await gen.generate_verified(topic=DSATopic.ARRAYS, difficulty=Difficulty.EASY) is None

"""
Freshly generated DSA problems, with their expected outputs independently
recomputed before anyone is graded against them.

## The failure this has to prevent

A candidate's submission is graded by running their code against hidden test
cases and comparing outputs. If a hidden case's `expected` value is wrong, a
*correct* solution fails, and the candidate is shown a diff between their right
answer and a wrong one with no way to tell which is which. That is worse than
no problem at all, and it is the reason `dsa_bank.py` verifies its test cases by
executing a reference solution (`tests/test_content_banks.py`) rather than by
anyone having read them and agreed.

## Why generated problems cannot be verified the same way

The curated bank's references are Python functions in our own source, so the
test suite can call them. A generated reference is a *string*, and running it
would mean executing model-written code on the server -- which `dsa_service.py`
rules out by design ("no server-side code execution"; candidate code runs in
the browser under Pyodide). Nor can the browser verify it, because that would
require shipping the reference solution to the client, and
`tests/test_dsa_api.py` pins that it never does.

## So: independent recomputation

The generator writes the problem and its expected outputs. A second, separate
call is then given the statement and the ARGUMENTS ONLY -- no expected values,
no reference solution -- and asked to work out what each call should return.
The problem ships only if every recomputed value matches.

This is weaker than execution and is not presented as equivalent. It catches
the arithmetic slips and off-by-ones that make up most bad test cases, because
the two calls fail independently; it will not catch a misconception the model
holds consistently across both. Hence generated problems stay flagged, stay out
of the curated pool, and the bank remains the default.
"""
from __future__ import annotations

import json
import keyword
import logging
from dataclasses import dataclass, field

from app.models.enums import Difficulty, DSATopic
from app.services.ai.contracts import LLMRequest
from app.services.ai.errors import LLMProviderError
from app.services.ai.gateway import get_gateway

logger = logging.getLogger("mockmateai.dsa.generator")

MIN_SAMPLE_CASES = 2
MIN_HIDDEN_CASES = 3
MAX_CASES = 12
MAX_STATEMENT_CHARS = 2000


@dataclass(frozen=True)
class GeneratedProblem:
    title: str
    topic: DSATopic
    difficulty: Difficulty
    statement_text: str
    constraints_text: str
    function_name: str
    starter_code: str
    sample: list[dict] = field(default_factory=list)
    hidden: list[dict] = field(default_factory=list)


_CASE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["args", "expected"],
    "properties": {
        "args": {"type": "array"},
        "expected": {},
    },
}

GENERATE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": [
        "title", "statement_text", "constraints_text", "function_name",
        "starter_code", "sample", "hidden",
    ],
    "properties": {
        "title": {"type": "string"},
        "statement_text": {"type": "string"},
        "constraints_text": {"type": "string"},
        "function_name": {"type": "string"},
        "starter_code": {"type": "string"},
        "sample": {"type": "array", "items": _CASE_SCHEMA},
        "hidden": {"type": "array", "items": _CASE_SCHEMA},
    },
}

RECOMPUTE_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["results"],
    "properties": {
        "results": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
    },
}

GENERATE_SYSTEM = (
    "You write coding-interview problems in the style of a curated practice set. "
    "Each problem is solved by a single Python function.\n\n"
    "RULES:\n"
    "- The problem must be solvable by one self-contained function with no I/O, "
    "no imports beyond the standard library, and no external state.\n"
    "- `function_name` must be a valid Python identifier, and `starter_code` must "
    "define exactly that function with a `pass` body and a short comment saying "
    "what to return.\n"
    "- Every test case is `{\"args\": [...], \"expected\": ...}` where `args` is the "
    "positional argument list. `expected` must be the exact value the function "
    "returns -- JSON types only, and the same type every time.\n"
    "- Work out every expected value carefully. A wrong one fails a correct "
    "solution, which is worse than no problem at all.\n"
    "- Sample cases are shown to the candidate and must be small enough to trace "
    "by hand. Hidden cases should include the edge cases: empty input, a single "
    "element, duplicates, negatives, and the boundary named in the constraints.\n"
    "- State the return value unambiguously, including ordering and tie-breaking. "
    "A problem whose answer depends on an unstated convention cannot be graded."
)

RECOMPUTE_SYSTEM = (
    "You are given a programming problem statement and a list of argument sets. "
    "You are NOT given the expected outputs and no answer key exists in what you "
    "were given.\n\n"
    "For each argument set, work out exactly what the described function must "
    "return, and return them in the same order as `results`, each as "
    "{\"index\": <position>, \"expected\": <value>}. Use JSON types only. If the "
    "statement is ambiguous for a given input, return null for that entry."
)


def _json_safe(value) -> bool:
    """Whether a value survives a JSON round trip unchanged.

    `test_cases` is a JSON column and the browser runner compares parsed JSON,
    so anything that does not round-trip cleanly cannot be graded against."""
    try:
        return json.loads(json.dumps(value)) == value
    except (TypeError, ValueError):
        return False


def structural_problem(payload: dict) -> str | None:
    """
    Why this payload cannot be used as a problem, or None if it is well formed.

    Runs before any verification call. Several of these are not cosmetic: a
    `function_name` the starter code does not define means the runner cannot
    find an entry point, and a case whose args are not a list cannot be applied
    as positional arguments at all.
    """
    title = str(payload.get("title", "")).strip()
    statement = str(payload.get("statement_text", "")).strip()
    fn = str(payload.get("function_name", "")).strip()
    starter = str(payload.get("starter_code", "")).strip()
    sample = payload.get("sample")
    hidden = payload.get("hidden")

    if not title or len(title) > 120:
        return "title missing or too long"
    if not statement or len(statement) > MAX_STATEMENT_CHARS:
        return "statement missing or too long"
    if not fn.isidentifier() or keyword.iskeyword(fn):
        return f"function_name {fn!r} is not a usable Python identifier"
    if f"def {fn}" not in starter:
        return "starter_code does not define the named function"
    if not isinstance(sample, list) or not isinstance(hidden, list):
        return "sample and hidden must both be lists"
    if len(sample) < MIN_SAMPLE_CASES:
        return f"needs at least {MIN_SAMPLE_CASES} sample cases"
    if len(hidden) < MIN_HIDDEN_CASES:
        return f"needs at least {MIN_HIDDEN_CASES} hidden cases"
    if len(sample) + len(hidden) > MAX_CASES:
        return "too many test cases"

    for kind, cases in (("sample", sample), ("hidden", hidden)):
        for index, case in enumerate(cases):
            if not isinstance(case, dict):
                return f"{kind}[{index}] is not an object"
            if not isinstance(case.get("args"), list):
                return f"{kind}[{index}].args must be a list of positional arguments"
            if "expected" not in case:
                return f"{kind}[{index}] has no expected value"
            if not _json_safe(case["args"]) or not _json_safe(case["expected"]):
                return f"{kind}[{index}] does not survive a JSON round trip"

    # A problem whose cases all expect the same answer grades nothing: a
    # function returning that constant would pass.
    expected_values = [json.dumps(c["expected"], sort_keys=True) for c in list(sample) + list(hidden)]
    if len(set(expected_values)) == 1:
        return "every case expects the same value, so a constant would pass"
    return None


async def _recompute_matches(payload: dict) -> bool:
    """
    Independently work out every expected value, and require exact agreement.

    The statement and the argument lists go out; the expected values do not.
    That is what makes this a second opinion rather than a request to confirm
    the first one.

    Agreement is exact rather than approximate, deliberately. The grader
    compares outputs exactly, so a test case the verifier only *nearly* agrees
    with is one that will fail a correct submission.
    """
    cases = list(payload["sample"]) + list(payload["hidden"])
    listing = "\n".join(f"{i}: {json.dumps(c['args'])}" for i, c in enumerate(cases))
    request = LLMRequest(
        system_prompt=RECOMPUTE_SYSTEM,
        conversation=[
            {
                "role": "user",
                "content": (
                    f"{payload['statement_text']}\n\n"
                    f"Constraints:\n{payload.get('constraints_text') or 'none stated'}\n\n"
                    f"Function: {payload['function_name']}(...)\n\n"
                    f"Argument sets:\n{listing}"
                ),
            }
        ],
        max_output_tokens=3000,
        json_schema=RECOMPUTE_SCHEMA,
        schema_name="dsa_recompute",
    )
    try:
        response = await get_gateway().complete_json(request)
    except LLMProviderError as exc:
        logger.info("DSA verification call failed, problem discarded: %s", exc)
        return False

    results = (response.payload or {}).get("results")
    if not isinstance(results, list) or len(results) != len(cases):
        logger.info(
            "DSA verification returned %s results for %s cases; discarding.",
            len(results) if isinstance(results, list) else "no",
            len(cases),
        )
        return False

    by_index: dict[int, object] = {}
    for entry in results:
        if isinstance(entry, dict) and isinstance(entry.get("index"), int):
            by_index[entry["index"]] = entry.get("expected")

    for index, case in enumerate(cases):
        if index not in by_index:
            return False
        if by_index[index] != case["expected"]:
            logger.info(
                "Discarded a generated problem on case %s: author said %s, verifier said %s.",
                index,
                json.dumps(case["expected"])[:60],
                json.dumps(by_index[index])[:60],
            )
            return False
    return True


async def generate_verified(
    *,
    topic: DSATopic,
    difficulty: Difficulty,
) -> GeneratedProblem | None:
    """
    One fresh problem, or None if it could not be produced and verified.

    None is an ordinary outcome, not an error: the caller serves the curated
    bank, which is the behaviour this feature was added on top of.
    """
    request = LLMRequest(
        system_prompt=GENERATE_SYSTEM,
        conversation=[
            {
                "role": "user",
                "content": (
                    f"Write one {difficulty.value} problem on the topic: {topic.value}.\n"
                    "Give 2-3 sample cases and 3-5 hidden cases covering the edges."
                ),
            }
        ],
        max_output_tokens=4000,
        json_schema=GENERATE_SCHEMA,
        schema_name="dsa_problem",
    )

    try:
        response = await get_gateway().complete_json(request)
    except LLMProviderError as exc:
        logger.warning("DSA generation unavailable: %s", exc)
        return None

    payload = response.payload or {}
    problem = structural_problem(payload)
    if problem:
        logger.info("Discarded a malformed generated problem (%s).", problem)
        return None

    if not await _recompute_matches(payload):
        return None

    return GeneratedProblem(
        title=str(payload["title"]).strip(),
        topic=topic,
        difficulty=difficulty,
        statement_text=str(payload["statement_text"]).strip(),
        constraints_text=str(payload.get("constraints_text", "")).strip(),
        function_name=str(payload["function_name"]).strip(),
        starter_code=str(payload["starter_code"]).strip(),
        sample=list(payload["sample"]),
        hidden=list(payload["hidden"]),
    )

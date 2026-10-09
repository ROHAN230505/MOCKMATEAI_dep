"""
Content bank integrity (Phase 7).

The reason this file exists: a wrong expected value in a hidden test case fails a
*correct* candidate solution, and the candidate has no way to see why. So every
expected value is verified by running the reference implementation against it
rather than by anyone having read it and agreed. The references live in
`app/content/dsa_bank.py` for exactly this purpose and never reach a client.

The aptitude checks are structural — nothing can execute a multiple-choice
question — plus the guard against the failure that actually bit during authoring:
by hand, the correct option landed at index 1 or 2 in 30 of 32 questions, so
always picking B scored 59% on a test meant to measure aptitude.
"""
import re
from collections import Counter

import pytest

from app.content.aptitude_bank import BANK as APTITUDE_BANK, build_rows as aptitude_rows
from app.content.dsa_bank import BANK as DSA_BANK, build_rows as dsa_rows
from app.models.enums import AptitudeTopic, Difficulty


# ---------------------------------------------------------------------------
# DSA: every expected value is executed, not asserted
# ---------------------------------------------------------------------------
def _all_cases():
    for problem in DSA_BANK:
        for kind in ("sample", "hidden"):
            for index, case in enumerate(problem[kind]):
                yield problem["slug"], kind, index, problem["reference"], case


@pytest.mark.parametrize(
    "slug,kind,index,reference,case",
    list(_all_cases()),
    ids=[f"{slug}-{kind}{index}" for slug, kind, index, _, _ in _all_cases()],
)
def test_every_dsa_test_case_matches_its_reference_solution(slug, kind, index, reference, case):
    actual = reference(*case["args"])
    assert actual == case["expected"], (
        f"{slug} {kind}[{index}]: reference returned {actual!r}, "
        f"but the stored expected value is {case['expected']!r}"
    )


def test_every_dsa_problem_has_sample_and_hidden_cases():
    """
    Samples are shown to the candidate and hidden ones are not, so a problem
    missing either is either unsolvable-by-inspection or trivially gameable.
    """
    for problem in DSA_BANK:
        assert len(problem["sample"]) >= 2, problem["slug"]
        assert len(problem["hidden"]) >= 3, problem["slug"]


def test_dsa_starter_code_defines_the_function_the_runner_will_call():
    for problem in DSA_BANK:
        name = problem["function_name"]
        assert f"def {name}(" in problem["starter_code"], problem["slug"]
        assert reference_arity(problem) == len(problem["sample"][0]["args"]), problem["slug"]


def reference_arity(problem) -> int:
    signature = re.search(r"def \w+\(([^)]*)\)", problem["starter_code"])
    assert signature is not None
    params = [p for p in signature.group(1).split(",") if p.strip()]
    return len(params)


def _walk(value):
    """Every value nested anywhere inside a row."""
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from _walk(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            yield from _walk(item)


def test_dsa_rows_never_carry_the_reference_solution():
    """
    The one thing that must not reach a client. Pinned here and at the API.

    Checked by walking for callables rather than by grepping the repr: the first
    version of this test searched for the substring "function" and failed on the
    legitimate 'functionName' key, which is the runner's entry point and belongs
    in the row. A string search would also have missed a callable stored under
    any name that does not contain the word.
    """
    for row in dsa_rows():
        assert "reference" not in row
        for value in _walk(row):
            assert not callable(value), f"a callable reached the row: {value!r}"


def test_dsa_slugs_and_titles_are_unique():
    slugs = [p["slug"] for p in DSA_BANK]
    titles = [p["title"] for p in DSA_BANK]
    assert len(set(slugs)) == len(slugs)
    assert len(set(titles)) == len(titles)


# ---------------------------------------------------------------------------
# Aptitude: structural integrity and non-guessability
# ---------------------------------------------------------------------------
def test_every_aptitude_question_is_well_formed():
    for topic, difficulty, question, options, correct_index, why, _tag in APTITUDE_BANK:
        assert isinstance(topic, AptitudeTopic)
        assert isinstance(difficulty, Difficulty)
        assert question.strip()
        assert len(options) == 4, question
        assert len(set(options)) == 4, f"duplicate options: {question}"
        assert 0 <= correct_index < len(options), question
        # The working is what makes a marked answer auditable, so it is required.
        assert why and len(why) > 20, question


def test_shuffling_preserves_the_correct_answer():
    rows = aptitude_rows()
    assert len(rows) == len(APTITUDE_BANK)
    for row, entry in zip(rows, APTITUDE_BANK):
        expected_text = entry[3][entry[4]]
        assert row["options"][row["correct_option_index"]] == expected_text
        assert sorted(row["options"]) == sorted(entry[3])


def test_shuffling_is_reproducible():
    """
    `selected_option_index` is persisted as an index. If the order could drift
    between runs, every historical answer would quietly start pointing at a
    different option.
    """
    first = [(r["question_text"], r["options"], r["correct_option_index"]) for r in aptitude_rows()]
    second = [(r["question_text"], r["options"], r["correct_option_index"]) for r in aptitude_rows()]
    assert first == second


def test_no_single_option_position_is_worth_guessing():
    rows = aptitude_rows()
    counts = Counter(row["correct_option_index"] for row in rows)
    share = max(counts.values()) / len(rows)
    assert share <= 0.4, f"always picking one position would score {share:.0%}: {dict(counts)}"


def test_every_topic_and_difficulty_is_represented():
    topics = Counter(entry[0] for entry in APTITUDE_BANK)
    assert set(topics) == set(AptitudeTopic), "a topic with no questions cannot be practised"
    for topic, count in topics.items():
        assert count >= 4, f"{topic} has only {count} questions"
    difficulties = Counter(entry[1] for entry in APTITUDE_BANK)
    assert set(difficulties) == set(Difficulty)


def test_aptitude_questions_are_unique():
    questions = [entry[2] for entry in APTITUDE_BANK]
    assert len(set(questions)) == len(questions)

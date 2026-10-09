"""
Curated full-length aptitude tests (Sections 4.13, 11.1).

## Why these live in code and not a table

Section 8 defines no `aptitude_tests` table. `aptitude_attempts.test_id` is a
nullable GUID with no foreign key, documented only as "null = practice mode" --
so a test id is free to reference a definition that lives here. The UUIDs below
are fixed literals rather than generated, so an attempt row keeps pointing at the
same test across restarts, redeploys and machines.

## Why none of these are named after a company

Section 4.13 offers "company-pattern sets" as an example, and
`aptitude_questions.company_pattern_tag` exists to support them. Every seeded
question has that tag as NULL, because nobody here has data on how any real
employer actually builds its test.

Labelling a set "Google pattern" on that basis would be inventing a claim about a
third party -- the same thing Section 4.6 already guards against when it insists
the company-name field is "not verified against any company records". So these
tests are described by what they actually contain: a topic mix, a length and a
time limit. If real pattern data is ever sourced, a set can be added here with
`company_pattern_tag` set and the mechanism needs no change.
"""
import uuid

from app.models.enums import AptitudeTopic, Difficulty

# Fixed ids. Regenerating these would orphan every historical attempt.
MIXED_FULL = uuid.UUID("1a5f2c40-0000-4000-8000-000000000001")
QUANT_FOCUS = uuid.UUID("1a5f2c40-0000-4000-8000-000000000002")
REASONING_VERBAL = uuid.UUID("1a5f2c40-0000-4000-8000-000000000003")

TESTS: list[dict] = [
    {
        "id": MIXED_FULL,
        "name": "Full-length mixed test",
        "description": (
            "Every topic, weighted the way a campus placement round usually is. "
            "The closest thing here to sitting a real test."
        ),
        "topics": list(AptitudeTopic),
        "difficulties": list(Difficulty),
        "question_count": 20,
        "duration_minutes": 25,
    },
    {
        "id": QUANT_FOCUS,
        "name": "Quantitative under time",
        "description": (
            "Quantitative and data interpretation only, at a pace that forces you to move on. "
            "Built for the round most candidates lose time in."
        ),
        "topics": [AptitudeTopic.QUANTITATIVE, AptitudeTopic.DATA_INTERPRETATION],
        "difficulties": list(Difficulty),
        "question_count": 12,
        "duration_minutes": 15,
    },
    {
        "id": REASONING_VERBAL,
        "name": "Reasoning and verbal",
        "description": (
            "Logical reasoning and verbal ability, the two that reward reading carefully "
            "rather than calculating quickly."
        ),
        "topics": [AptitudeTopic.LOGICAL_REASONING, AptitudeTopic.VERBAL_ABILITY],
        "difficulties": list(Difficulty),
        "question_count": 12,
        "duration_minutes": 15,
    },
]

BY_ID = {test["id"]: test for test in TESTS}


def get_test(test_id: uuid.UUID) -> dict | None:
    return BY_ID.get(test_id)

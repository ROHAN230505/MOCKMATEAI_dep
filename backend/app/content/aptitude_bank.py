"""
Curated aptitude question bank (Section 8's `aptitude_questions`, Phase 7).

Static and hand-written, following the precedent `question_bank.py` set in
Phase 2: content a candidate is scored against should be reviewable, and a
generated question is a question nobody has checked. Every entry below carries
its working in a `why` field so a reviewer can verify the marked answer without
re-deriving it, and `tests/test_content_banks.py` re-checks the structural
invariants (option count, index in range, no duplicate options) on every test run.

`options` is stored as a JSON list and `correct_option_index` indexes into it.
The index is deliberately not always the same position — an earlier draft had the
answer first in every entry, which would have made the whole bank passable by
someone who noticed.
"""
import random

from app.models.enums import AptitudeTopic, Difficulty

# Each entry: (topic, difficulty, question, options, correct_index, why, company_tag)
BANK: list[tuple[AptitudeTopic, Difficulty, str, list[str], int, str, str | None]] = [
    # ---------------------------------------------------------------- QUANTITATIVE
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.EASY,
        "A shirt is sold for \u20b91,200 after a 20% discount. What was its original price?",
        ["\u20b91,440", "\u20b91,500", "\u20b91,380", "\u20b91,560"], 1,
        "1200 is 80% of the original, so original = 1200 / 0.8 = 1500.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.EASY,
        "An article costing \u20b9450 is sold for \u20b9540. What is the profit percentage?",
        ["16.7%", "18%", "20%", "22.5%"], 2,
        "Profit = 540 - 450 = 90. 90 / 450 = 0.20 = 20%.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.EASY,
        "Find the simple interest on \u20b98,000 at 6% per annum for 3 years.",
        ["\u20b91,200", "\u20b91,440", "\u20b91,520", "\u20b91,680"], 1,
        "SI = P x R x T / 100 = 8000 x 6 x 3 / 100 = 1440.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.MEDIUM,
        "Two numbers are in the ratio 3:5 and differ by 24. What is the larger number?",
        ["36", "48", "60", "72"], 2,
        "The difference is 5 - 3 = 2 parts = 24, so one part = 12 and the larger is 5 x 12 = 60.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.MEDIUM,
        "The average of 5 numbers is 27. If one number, 35, is removed, what is the average of the remaining 4?",
        ["23", "25", "26", "28"], 1,
        "Total = 5 x 27 = 135. Remove 35 to get 100, and 100 / 4 = 25.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.MEDIUM,
        "A can finish a job in 12 days and B in 18 days. Working together, how many days will they take?",
        ["6.5 days", "7.2 days", "7.5 days", "8 days"], 1,
        "Combined rate = 1/12 + 1/18 = 3/36 + 2/36 = 5/36 per day, so 36/5 = 7.2 days.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.HARD,
        "A train 240 m long, travelling at 54 km/h, crosses a platform in 30 seconds. "
        "How long is the platform?",
        ["180 m", "195 m", "210 m", "240 m"], 2,
        "54 km/h = 15 m/s. In 30 s it covers 450 m, which is train + platform, so 450 - 240 = 210 m.",
        None,
    ),
    (
        AptitudeTopic.QUANTITATIVE, Difficulty.HARD,
        "A sum doubles in 8 years under simple interest. In how many years will it triple "
        "at the same rate?",
        ["12 years", "16 years", "20 years", "24 years"], 1,
        "Doubling means the interest earned equals the principal in 8 years. Tripling needs "
        "interest of twice the principal, which takes 16 years at the same annual rate.",
        None,
    ),

    # ------------------------------------------------------------ LOGICAL REASONING
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.EASY,
        "What comes next in the series: 3, 6, 11, 18, 27, ?",
        ["36", "38", "40", "42"], 1,
        "The gaps are 3, 5, 7, 9 - each two more than the last. The next gap is 11, so 27 + 11 = 38.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.EASY,
        "Which number does not belong: 121, 144, 169, 200, 225?",
        ["144", "169", "200", "225"], 2,
        "All are perfect squares (11, 12, 13, 15 squared) except 200.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.EASY,
        "What comes next in the series: 2, 6, 12, 20, 30, ?",
        ["36", "40", "42", "44"], 2,
        "Each term is n x (n+1): 1x2, 2x3, 3x4, 4x5, 5x6, so the next is 6x7 = 42.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.MEDIUM,
        "If you face north, turn 90\u00b0 clockwise, then 180\u00b0, then 90\u00b0 anticlockwise, "
        "which direction are you facing?",
        ["North", "East", "West", "South"], 3,
        "North -> 90 clockwise = East -> 180 = West -> 90 anticlockwise = South.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.MEDIUM,
        "What comes next in the letter series: B, D, G, K, P, ?",
        ["S", "T", "U", "V"], 3,
        "Positions are 2, 4, 7, 11, 16 with gaps 2, 3, 4, 5. The next gap is 6, giving position 22 = V.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.MEDIUM,
        "A is B's sister. C is B's mother. D is C's father. How is A related to D?",
        ["Daughter", "Granddaughter", "Niece", "Cannot be determined"], 1,
        "C is A's mother (A and B are siblings), and D is C's father, so D is A's grandfather "
        "and A is his granddaughter.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.HARD,
        "All roses are flowers. Some flowers fade quickly. Which conclusion follows?",
        [
            "Some roses fade quickly",
            "No rose fades quickly",
            "All flowers are roses",
            "Neither conclusion follows",
        ], 3,
        "The flowers that fade quickly need not include any rose, so nothing can be concluded "
        "about roses fading. This is the classic undistributed-middle trap.",
        None,
    ),
    (
        AptitudeTopic.LOGICAL_REASONING, Difficulty.HARD,
        "In a code, CAT is written as 3-1-20. How would DOG be written?",
        ["4-15-7", "4-14-7", "5-15-8", "4-15-6"], 0,
        "Each letter maps to its position in the alphabet: D=4, O=15, G=7.",
        None,
    ),
    # -------------------------------------------------------------- VERBAL ABILITY
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.EASY,
        "Choose the word closest in meaning to CANDID.",
        ["Cautious", "Frank", "Hostile", "Indirect"], 1,
        "Candid means open and straightforward in speech, i.e. frank.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.EASY,
        "Choose the word most opposite in meaning to PRUDENT.",
        ["Careful", "Thrifty", "Reckless", "Sensible"], 2,
        "Prudent means showing care for the future; its opposite is reckless. "
        "Careful, thrifty and sensible are all near-synonyms.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.EASY,
        "Complete the sentence: Neither of the two candidates ___ qualified for the role.",
        ["are", "is", "were", "have been"], 1,
        "\"Neither\" is singular, so it takes a singular verb: neither ... is.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.MEDIUM,
        "Choose the word closest in meaning to UBIQUITOUS.",
        ["Rare", "Omnipresent", "Ancient", "Unclear"], 1,
        "Ubiquitous means present everywhere, i.e. omnipresent.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.MEDIUM,
        "Identify the error: \"One of my friend is coming to the meeting tomorrow.\"",
        [
            "\"One of\" should be \"One from\"",
            "\"friend\" should be \"friends\"",
            "\"is\" should be \"are\"",
            "There is no error",
        ], 1,
        "\"One of\" must be followed by a plural noun: one of my friends. The singular verb "
        "\"is\" is correct because the subject is \"one\".",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.MEDIUM,
        "What does the idiom \"to bite the bullet\" mean?",
        [
            "To speak without thinking",
            "To endure something painful with courage",
            "To take an unnecessary risk",
            "To refuse to compromise",
        ], 1,
        "The idiom means to force yourself to face an unpleasant but unavoidable situation.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.HARD,
        "Complete the analogy: EPHEMERAL is to PERMANENT as TRANSIENT is to ___.",
        ["Fleeting", "Enduring", "Fragile", "Sudden"], 1,
        "Ephemeral and permanent are opposites. Transient means short-lived, so its opposite "
        "is enduring. Fleeting and fragile are near-synonyms of transient, not opposites.",
        None,
    ),
    (
        AptitudeTopic.VERBAL_ABILITY, Difficulty.HARD,
        "Complete the sentence: The evidence against him was so ___ that the jury acquitted him "
        "within an hour.",
        ["damning", "flimsy", "extensive", "compelling"], 1,
        "An acquittal means the case failed, so the evidence must have been weak. Damning, "
        "extensive and compelling would all point the other way.",
        None,
    ),

    # ---------------------------------------------------------- DATA INTERPRETATION
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.EASY,
        "A company’s annual sales in ₹ lakh were: 2019: 40, 2020: 50, 2021: 45, 2022: 60. "
        "What was the percentage increase from 2019 to 2022?",
        ["33.3%", "40%", "50%", "60%"], 2,
        "Increase = 60 - 40 = 20 on a base of 40, so 20/40 = 50%.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.EASY,
        "Using the same sales figures (2019: 40, 2020: 50, 2021: 45, 2022: 60 in ₹ lakh), "
        "in which year did sales fall compared with the previous year?",
        ["2020", "2021", "2022", "None of the years"], 1,
        "Only 2021 fell, from 50 down to 45.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.EASY,
        "A monthly budget of ₹48,000 is split Rent 35%, Food 25%, Transport 15%, Savings 25%. "
        "How much goes to Transport?",
        ["₹6,400", "₹7,200", "₹8,400", "₹12,000"], 1,
        "15% of 48,000 = 7,200.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.MEDIUM,
        "Using the same sales figures (2019: 40, 2020: 50, 2021: 45, 2022: 60 in ₹ lakh), "
        "what were the average annual sales over the four years?",
        ["₹47.50 lakh", "₹48.75 lakh", "₹50.00 lakh", "₹51.25 lakh"], 1,
        "Total = 40 + 50 + 45 + 60 = 195, and 195 / 4 = 48.75.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.MEDIUM,
        "Using the same budget (₹48,000; Rent 35%, Transport 15%), by how much does Rent "
        "exceed Transport?",
        ["₹7,200", "₹8,400", "₹9,600", "₹10,800"], 2,
        "The gap is 35% - 15% = 20% of 48,000 = 9,600.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.MEDIUM,
        "In a test of 100 students the score distribution was: below 50: 12, 50-59: 18, "
        "60-69: 30, 70-79: 25, 80 and above: 15. What percentage scored 60 or above?",
        ["55%", "62%", "70%", "72%"], 2,
        "30 + 25 + 15 = 70 out of 100, so 70%.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.HARD,
        "In a survey of 400 people, 200 prefer tea, 160 prefer coffee and 60 prefer neither. "
        "How many prefer both?",
        ["0", "20", "40", "60"], 1,
        "400 - 60 = 340 prefer at least one. By inclusion-exclusion, 200 + 160 - both = 340, "
        "so both = 20.",
        None,
    ),
    (
        AptitudeTopic.DATA_INTERPRETATION, Difficulty.HARD,
        "Sales grew from ₹40 lakh in 2019 to ₹60 lakh in 2022. What was the approximate "
        "compound annual growth rate over those three years?",
        ["12.6%", "14.5%", "16.7%", "18.9%"], 1,
        "CAGR = (60/40)^(1/3) - 1 = 1.5^(1/3) - 1 = 1.1447 - 1, about 14.5%. "
        "16.7% is the trap: it is the simple average of a 50% total rise over three years.",
        None,
    ),
]


def build_rows() -> list[dict]:
    """
    The bank with each question's options shuffled deterministically.

    The list above orders options however reads best for a reviewer: ascending
    for numeric answers, most-plausible-first for verbal ones. That ordering is a
    tell. Authored by hand, the correct answer landed at index 1 or 2 in 30 of
    32 questions and never at 0 or 3 among the numeric ones, because a
    hand-written numeric distractor set naturally brackets the answer. A
    candidate who always picked B would have scored 59% on a test meant to
    measure aptitude, which makes the score measure the wrong thing.

    Shuffling per question, seeded from the question text, removes position as a
    signal while staying reproducible: `random.Random` seeded with a string
    hashes it with SHA-512 rather than using `hash()`, so the arrangement is
    identical across runs, machines and Python invocations. That matters because
    `aptitude_attempt_answers.selected_option_index` is stored as an index — if
    the order could drift, every historical answer would silently start pointing
    at a different option.
    """
    rows: list[dict] = []
    for topic, difficulty, question, options, correct_index, why, tag in BANK:
        order = list(range(len(options)))
        random.Random(f"aptitude-options:{question}").shuffle(order)
        rows.append(
            {
                "topic": topic,
                "difficulty": difficulty,
                "question_text": question,
                # shuffled[j] is options[order[j]], so the answer now sits at the
                # position holding its original index.
                "options": [options[i] for i in order],
                "correct_option_index": order.index(correct_index),
                "company_pattern_tag": tag,
                # Not a database column — carried so the verification script can
                # print the working beside the question it belongs to.
                "why": why,
            }
        )
    return rows

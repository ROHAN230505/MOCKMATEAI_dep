"""
Static, curated question bank for Phase 2's "fixed, pre-planned question
list" (MASTER_PROMPT.md Section 18, Phase 2). Deliberately NOT LLM-backed —
Phase 2's whole point is proving the real-time turn-taking pipeline before
Phase 3 adds the LLM Question/Follow-up Engine (Section 9.3) on top, so the
questions below are role-agnostic and never vary based on the candidate's
target role, resume, job description, or company (those fields are still
captured and persisted at session start per Section 4.6, ready for Phase 3
to actually use — see app/services/interview_service.py).

Selection is a random sample within the relevant pool(s), seeded per call
so two sessions rarely look identical, with the opener always first for
realism (most real interviews start with a rapport question regardless of
focus area).
"""
import random

from app.models.enums import InterviewType

OPENER = "Tell me a little about yourself and what's brought you to this interview."

BEHAVIORAL_QUESTIONS = [
    "Tell me about a time you disagreed with a teammate or manager. How did you handle it?",
    "Describe a project that didn't go the way you planned. What did you learn?",
    "Tell me about a time you had to learn something new very quickly to get a task done.",
    "Describe a situation where you had to work with a tight deadline. How did you prioritize?",
    "Tell me about a time you received critical feedback. How did you respond to it?",
    "Describe a time you took initiative on something outside your usual responsibilities.",
    "Tell me about a time you had to persuade someone to see things your way.",
    "Describe the most challenging problem you've had to solve in a team setting.",
    "Tell me about a time you made a mistake at work or school. What happened next?",
    "Describe a situation where you had to balance multiple priorities at once.",
    "Tell me about a time you helped a struggling teammate.",
    "What's an accomplishment you're genuinely proud of, and why?",
]

TECHNICAL_QUESTIONS = [
    "Walk me through the difference between a stack and a queue, and give an example of when you'd use each.",
    "What is time complexity, and why does it matter when choosing between two approaches to a problem?",
    "Explain what a hash map is and how it achieves fast lookups.",
    "What's the difference between a process and a thread?",
    "How would you find whether a linked list has a cycle in it? Explain your approach.",
    "What is recursion, and what's a risk you need to watch for when using it?",
    "Explain the difference between SQL and NoSQL databases, and when you'd reach for each.",
    "What does it mean for an API to be RESTful?",
    "How does binary search work, and what has to be true about the input for it to work at all?",
    "What's the difference between synchronous and asynchronous code execution?",
    "Explain what Big-O notation is describing, in your own words.",
    "What's a race condition, and how might you avoid one?",
]

QUESTIONS_PER_DURATION: dict[int, int] = {15: 3, 30: 6, 45: 9}


def question_count_for_duration(duration_minutes: int) -> int:
    return QUESTIONS_PER_DURATION.get(duration_minutes, max(2, duration_minutes // 5))


def select_planned_questions(interview_type: InterviewType, duration_minutes: int) -> list[str]:
    """Returns an ordered list of question texts, opener first, then a random sample of the rest."""
    total = question_count_for_duration(duration_minutes)

    if interview_type == InterviewType.TECHNICAL:
        pool = TECHNICAL_QUESTIONS
    elif interview_type == InterviewType.BEHAVIORAL:
        pool = BEHAVIORAL_QUESTIONS
    else:
        pool = BEHAVIORAL_QUESTIONS + TECHNICAL_QUESTIONS

    remaining_needed = max(total - 1, 0)
    sampled = random.sample(pool, k=min(remaining_needed, len(pool)))
    return [OPENER, *sampled]

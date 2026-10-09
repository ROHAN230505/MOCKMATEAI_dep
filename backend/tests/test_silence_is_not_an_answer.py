"""
Silence is never scored, and a segue is never a question.

Both come from one real session, whose report showed:

  Question 2  "Can you explain what time complexity is..."
              No answer recorded.        Relevance 10/10  Completeness 10/10
  Question 5  "Sure, let's move on."
              No answer recorded.        Relevance 2/10   Completeness 0/10

Every turn in that session had `transcript_text = None`. The scores describe
nothing, and two of the questions were the model's own transition phrases
stored as though they were questions a candidate had failed to answer.
"""
from app.services.interview_service import _is_transition_only
from app.services.llm_engine import EngineContext, build_conversation, build_system_prompt


# --- a segue is not a question -------------------------------------------
def test_bare_transitions_are_recognised():
    for text in (
        "Sure, let's move on.",
        "No problem, let's move on.",
        "Let's move on",
        "Okay, next question.",
    ):
        assert _is_transition_only(text), text


def test_a_transition_followed_by_a_real_question_is_left_alone():
    """The exact shape that IS correct, and must not be repaired away."""
    assert not _is_transition_only(
        "No problem, let's move on. Explain the difference between SQL and NoSQL "
        "databases, and when you'd reach for each."
    )


def test_a_plain_question_is_never_treated_as_a_transition():
    for text in (
        "What does it mean for an API to be RESTful?",
        "Thanks. What does it mean for an API to be RESTful?",
        "Tell me about a time you led a migration.",
    ):
        assert not _is_transition_only(text), text


def test_a_question_mark_settles_it():
    """A question mark is proof there is a question, whatever precedes it."""
    assert not _is_transition_only("Let's move on. Ready?")


# --- silence is stated as silence ----------------------------------------
def _ctx(answer):
    return EngineContext(
        session_id="s",
        role_target="Backend Engineer",
        interview_type="technical",
        duration_minutes=15,
        current_question_text="What is a REST API?",
        current_answer_text=answer,
    )


def test_an_empty_transcript_is_named_rather_than_sent_as_a_blank_answer():
    """
    An empty <candidate_answer> fence reads as an answer that happened to be
    blank, and the model scores it. Naming the situation is what stops that.
    """
    content = build_conversation(_ctx("   "))[-2]["content"]
    assert "NO SPEECH WAS CAPTURED" in content
    assert "<candidate_answer>" not in content
    assert "Do NOT score this" in content


def test_a_real_answer_is_still_fenced_as_untrusted_data():
    """The prompt-injection boundary must survive the change."""
    content = build_conversation(_ctx("It uses HTTP verbs on resources."))[-2]["content"]
    assert "<candidate_answer>" in content
    assert "NO SPEECH" not in content


def test_the_interviewer_is_told_to_reflect_the_answer_back():
    """What the candidate asked for: hear your own answer summarised, so you
    can tell how it landed and correct it if it landed wrong."""
    prompt = build_system_prompt(_ctx("anything"))
    assert "REFLECT BEFORE YOU MOVE ON" in prompt
    assert "one short" in prompt


def test_reflection_is_explicitly_skipped_when_there_is_nothing_to_reflect():
    """Summarising silence would be inventing an answer."""
    prompt = build_system_prompt(_ctx(None))
    assert "cannot summarise silence" in prompt

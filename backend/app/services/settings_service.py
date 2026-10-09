"""
Settings and the privacy data inventory (Sections 4.17-4.19).

The inventory is built by counting real rows, not by listing categories the
schema happens to define. A candidate asking "what do you hold on me?" deserves
a number that came from a query.
"""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.aptitude import AptitudeAttempt
from app.models.dsa import DSASubmission
from app.models.feedback import FeedbackReport
from app.models.interview import InterviewAnswer, InterviewQuestion, InterviewSession
from app.models.resume import ResumeAnalysis
from app.models.user import User


def _count(db: Session, statement) -> int:
    return db.execute(statement).scalar_one() or 0


def build_inventory(db: Session, user: User) -> dict:
    sessions = _count(
        db, select(func.count()).select_from(InterviewSession).where(InterviewSession.user_id == user.id)
    )
    answers = _count(
        db,
        select(func.count())
        .select_from(InterviewAnswer)
        .join(InterviewQuestion, InterviewQuestion.id == InterviewAnswer.question_id)
        .join(InterviewSession, InterviewSession.id == InterviewQuestion.session_id)
        .where(InterviewSession.user_id == user.id),
    )
    reports = _count(
        db,
        select(func.count())
        .select_from(FeedbackReport)
        .join(InterviewSession, InterviewSession.id == FeedbackReport.session_id)
        .where(InterviewSession.user_id == user.id),
    )
    attempts = _count(
        db, select(func.count()).select_from(AptitudeAttempt).where(AptitudeAttempt.user_id == user.id)
    )
    submissions = _count(
        db, select(func.count()).select_from(DSASubmission).where(DSASubmission.user_id == user.id)
    )
    resumes = _count(
        db, select(func.count()).select_from(ResumeAnalysis).where(ResumeAnalysis.user_id == user.id)
    )

    categories = [
        {"key": "sessions", "label": "Interview sessions", "count": sessions,
         "detail": "Role, type, duration and timings for each interview you started."},
        {"key": "answers", "label": "Answer transcripts", "count": answers,
         "detail": "The text of what you said, produced in your browser and sent as text."},
        {"key": "reports", "label": "Feedback reports", "count": reports,
         "detail": "Scores, strengths and improvement notes, with the quotes they cite."},
        {"key": "aptitude", "label": "Aptitude attempts", "count": attempts,
         "detail": "Which questions you were asked, what you picked, and how long you took."},
        {"key": "dsa", "label": "DSA submissions", "count": submissions,
         "detail": "The code you submitted, its result, and how many hints you used."},
        {"key": "resume", "label": "Resume analyses", "count": resumes,
         "detail": "Scores and keyword gaps only. The resume text itself is never kept."},
    ]

    # Stated as its own list rather than omitted. "We don't store your video" is
    # information a candidate wants on this screen, and an absent row says nothing.
    never_stored = [
        {"key": "audio", "label": "Audio recordings", "count": 0,
         "detail": "Speech recognition runs in your browser. No audio is ever uploaded."},
        {"key": "video", "label": "Video recordings", "count": 0,
         "detail": "Expression analysis runs in your browser on frames that are discarded immediately."},
        {"key": "resume_file", "label": "Resume files", "count": 0,
         "detail": "Your PDF is read in your browser and never leaves it — not the file, not its name."},
        {"key": "code_execution", "label": "Executed code", "count": 0,
         "detail": "DSA solutions run inside your own browser, never on our servers."},
    ]

    return {"categories": categories, "never_stored": never_stored}

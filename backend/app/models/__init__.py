"""
Import every model module so `Base.metadata` is fully populated as soon as
`app.models` is imported once — required both by Alembic's `--autogenerate`
and by `Base.metadata.create_all()` in tests.
"""
from app.models.aptitude import AptitudeAttempt, AptitudeAttemptAnswer, AptitudeQuestion  # noqa: F401
from app.models.dsa import DSAProblem, DSASubmission  # noqa: F401
from app.models.feedback import FeedbackDetail, FeedbackReport  # noqa: F401
from app.models.interview import AnswerEvaluation, InterviewAnswer, InterviewQuestion, InterviewSession  # noqa: F401
from app.models.readiness import ReadinessSnapshot  # noqa: F401
from app.models.recording import Recording  # noqa: F401
from app.models.resume import ResumeAnalysis  # noqa: F401
from app.models.scoring import ScoringWeights  # noqa: F401
from app.models.signals import ExpressionSignal, ProsodySignal  # noqa: F401
from app.models.user import RefreshToken, User  # noqa: F401

__all__ = [
    "User",
    "RefreshToken",
    "InterviewSession",
    "InterviewQuestion",
    "InterviewAnswer",
    "AnswerEvaluation",
    "FeedbackReport",
    "FeedbackDetail",
    "ProsodySignal",
    "ExpressionSignal",
    "Recording",
    "AptitudeQuestion",
    "AptitudeAttempt",
    "AptitudeAttemptAnswer",
    "DSAProblem",
    "DSASubmission",
    "ResumeAnalysis",
    "ReadinessSnapshot",
    "ScoringWeights",
]

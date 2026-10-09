"""
Resume analysis persistence (Phase 8).

## `file_storage_url` and the file we do not have

Section 8 declares `file_storage_url` as `NOT NULL`, which assumes the resume
file is stored somewhere. This build does not store it: extraction happens in the
browser and only text is submitted, for the reason set out in `schemas/resume.py`.

That leaves a required column with nothing true to put in it, and the honest
answer is a sentinel that says so rather than a string shaped like a URL to a
file that does not exist. A fabricated path would be exactly the failure this
codebase rules out everywhere else — a value that looks like a thing the system
has when it does not.

If file retention is ever wanted, it is a product decision, not a code change:
it needs a storage backend, a retention window (`recording_retention_days`
already exists in config and would be the obvious model), and a deletion path.
Until then this column records the truth.
"""
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.responses import ApiError
from app.core.timeutils import utcnow
from app.models.resume import ResumeAnalysis
from app.models.user import User
from app.schemas.resume import AnalyseResumeRequest
from app.services.resume import analyzer

logger = logging.getLogger("mockmateai.resume")

# Not a URL, and deliberately not shaped like one.
NOT_STORED = "not-stored:client-side-extraction"


def analyse_and_store(db: Session, user: User, body: AnalyseResumeRequest) -> tuple[ResumeAnalysis, analyzer.Analysis]:
    result = analyzer.analyse(body.resume_text, body.job_description_text)

    row = ResumeAnalysis(
        user_id=user.id,
        file_storage_url=NOT_STORED,
        # The job description is stored: it is the candidate's own paste of a
        # public advert, it contains no personal data, and without it a past
        # analysis cannot explain which role its keyword gaps were measured
        # against. The resume text itself is *not* stored — only what was
        # derived from it.
        job_description_text=(body.job_description_text or None),
        ats_score=result.ats_score,
        keyword_gaps=({"gaps": result.keyword_gaps, "matched": result.matched_keywords}
                      if result.keyword_gaps is not None else None),
        suggestions={
            "items": result.suggestions,
            "components": [
                {
                    "name": component.name,
                    "label": component.label,
                    "score": round(component.score, 1),
                    "weight": component.weight,
                    "detail": component.detail,
                }
                for component in result.components
            ],
            "measured": result.measured,
            "unmeasured": result.unmeasured,
            "wordCount": result.word_count,
        },
        analyzed_at=utcnow(),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    logger.info(
        "Resume analysed [user_id=%s score=%s had_jd=%s words=%s]",
        user.id,
        result.ats_score,
        bool(body.job_description_text),
        result.word_count,
    )
    return row, result


def get_for_user(db: Session, user: User, analysis_id: UUID) -> ResumeAnalysis:
    row = db.scalars(select(ResumeAnalysis).where(ResumeAnalysis.id == analysis_id)).first()
    if row is None or row.user_id != user.id:
        raise ApiError(status_code=404, code="analysis_not_found", message="Resume analysis not found.")
    return row


def list_for_user(db: Session, user: User, *, limit: int = 20) -> list[ResumeAnalysis]:
    return list(
        db.scalars(
            select(ResumeAnalysis)
            .where(ResumeAnalysis.user_id == user.id)
            .order_by(ResumeAnalysis.analyzed_at.desc())
            .limit(limit)
        )
    )


def to_payload(row: ResumeAnalysis) -> dict:
    """Rebuild the response from what was stored, so history and a fresh run agree."""
    stored = row.suggestions or {}
    keywords = row.keyword_gaps or {}
    return {
        "id": row.id,
        "ats_score": row.ats_score,
        "components": stored.get("components", []),
        "measured": stored.get("measured", []),
        "unmeasured": stored.get("unmeasured", []),
        "keyword_gaps": keywords.get("gaps"),
        "matched_keywords": keywords.get("matched"),
        "suggestions": stored.get("items", []),
        "word_count": stored.get("wordCount", 0),
        "had_job_description": bool(row.job_description_text),
        "analyzed_at": row.analyzed_at,
    }

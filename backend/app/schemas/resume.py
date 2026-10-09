"""
Resume analysis schemas (Section 8's `resume_analyses`, Phase 8).

The request carries **extracted text, not a file**. Text extraction happens in
the browser, and the reason is worth stating plainly: a resume is the most
PII-dense document a candidate owns — legal name, address, phone number, email,
and their entire employment history. Every other media pipeline in this product
already keeps the raw artifact on the candidate's machine (audio in Phase 2,
video in Phase 5B, their code in Phase 7), and a resume is the last thing that
should break that pattern.
"""
from datetime import datetime
from uuid import UUID

from pydantic import Field

from app.schemas.common import CamelModel

# A resume longer than this is not a resume. Bounded so a paste cannot be used to
# push arbitrary volumes of text through the analyser.
MAX_RESUME_CHARS = 60_000
MAX_JD_CHARS = 20_000


class AnalyseResumeRequest(CamelModel):
    resume_text: str = Field(min_length=1, max_length=MAX_RESUME_CHARS)
    # Optional. Without it, keyword coverage is reported as unmeasured rather
    # than scored as zero — see `services/resume/analyzer.py`.
    job_description_text: str | None = Field(default=None, max_length=MAX_JD_CHARS)
    # Carried only so the UI can show which document a past analysis came from.
    # Never stored: it routinely contains the candidate's own name.
    file_name: str | None = Field(default=None, max_length=255)


class ComponentOut(CamelModel):
    name: str
    label: str
    score: float
    # The weight actually applied after renormalising over measured components.
    weight: float
    detail: str


class ResumeAnalysisOut(CamelModel):
    id: UUID
    ats_score: int | None
    components: list[ComponentOut]
    measured: list[str]
    unmeasured: list[str]
    # NULL rather than [] when no job description was supplied: an empty list
    # would read as "we looked for gaps and found none".
    keyword_gaps: list[str] | None
    matched_keywords: list[str] | None
    suggestions: list[str]
    word_count: int
    had_job_description: bool
    analyzed_at: datetime | None


class ResumeHistoryItem(CamelModel):
    id: UUID
    ats_score: int | None
    had_job_description: bool
    analyzed_at: datetime | None

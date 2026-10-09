"""
Deterministic resume analysis (Phase 8).

## What "ATS score" means here, and what it does not

Applicant tracking systems are proprietary and they do not agree with each other.
Nobody outside Workday can compute a Workday score, and a product claiming to
would be inventing a number. So this is **not** a prediction of what any real ATS
will do with a resume.

What it is: a measurement of the things every ATS demonstrably depends on, each
one checkable by the candidate against their own document. Text that extracts
cleanly, the sections a parser looks for, contact details it can find, and — when
a job description is supplied — how much of that description's vocabulary the
resume actually uses. The score is the weighted average of those, and the
components are returned alongside it so a candidate can see what moved it rather
than being handed a number to trust.

## Unmeasured components are excluded, not zeroed

Keyword coverage needs a job description. Without one it is not measured, and the
weights renormalise over what was — the same rule Section 10.2 applies to the
interview categories, for the same reason: a candidate who did not paste a job
description has not scored zero on keyword matching, they have not been assessed
on it. `keyword_gaps` stays NULL in that case rather than becoming an empty list,
which would read as "no gaps found".
"""
import re
from dataclasses import dataclass, field

# Section headings an ATS parser looks for. Matched loosely because resumes
# spell them a dozen ways, but anchored to a line start so "my experience with
# Python" in a summary paragraph does not count as an Experience section.
SECTION_PATTERNS: dict[str, tuple[str, ...]] = {
    "experience": (r"^\s*(work\s+)?experience\b", r"^\s*employment\b", r"^\s*professional\s+experience\b"),
    "education": (r"^\s*education\b", r"^\s*academics?\b", r"^\s*qualifications?\b"),
    "skills": (r"^\s*(technical\s+)?skills\b", r"^\s*technologies\b", r"^\s*competenc(y|ies)\b"),
    "projects": (r"^\s*projects?\b", r"^\s*portfolio\b"),
}

EMAIL_PATTERN = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
# Deliberately loose: international formats vary wildly and a false negative here
# would tell a candidate to add a phone number they already have.
PHONE_PATTERN = re.compile(r"(\+?\d[\d\s().-]{7,}\d)")
URL_PATTERN = re.compile(r"(https?://|www\.|linkedin\.com|github\.com)", re.IGNORECASE)

BULLET_PATTERN = re.compile(r"^\s*[-*\u2022\u25cf\u25aa\u2023\u00b7]\s+", re.MULTILINE)
DIGIT_PATTERN = re.compile(r"\d")

# Strong openers an ATS-friendly bullet tends to start with. Not scored as a
# vocabulary test — only used to notice bullets that open with a filler phrase.
WEAK_OPENERS = (
    "responsible for",
    "worked on",
    "helped with",
    "involved in",
    "duties included",
    "tasked with",
    "assisted with",
)

# Words too common to count as job-description keywords. Kept short on purpose:
# an aggressive stop list would quietly drop real requirements like "test" or
# "design".
STOP_WORDS = frozenset(
    """a an and are as at be by for from has have in into is it its of on or that the to with will
    you your we our us they their this these those be being been do does did not no if then than
    such can could should would may might must about across after before during over under between
    within without more most less least other another any all both each few many some very own same
    so just also using use used than who whom which what when where why how per via etc ability able
    role roles work working works job jobs position positions candidate candidates team teams year
    years experience experienced strong good great excellent required requirements requirement
    responsibilities responsibility preferred plus nice must-have looking seeking hiring join joining
    ideal ideally successful opportunity opportunities company companies well like including include
    includes help helping make makes making new""".split()
)

# A resume much shorter than this is not a resume; much longer and an ATS is
# likely reading a document a human never will.
MIN_REASONABLE_WORDS = 150
MAX_REASONABLE_WORDS = 1200


@dataclass
class Component:
    """One scored dimension, 0-100, with the weight it carries."""

    name: str
    label: str
    score: float
    weight: float
    detail: str


@dataclass
class Analysis:
    ats_score: int | None
    components: list[Component] = field(default_factory=list)
    measured: list[str] = field(default_factory=list)
    unmeasured: list[str] = field(default_factory=list)
    keyword_gaps: list[str] | None = None
    matched_keywords: list[str] | None = None
    suggestions: list[str] = field(default_factory=list)
    word_count: int = 0


def _tokens(text: str) -> list[str]:
    """
    Lowercase word tokens, keeping the punctuation that makes up real skill names.

    Internal dots and pluses are kept because "node.js", "asp.net" and "c++" are
    single terms a job description means literally.

    Only a trailing *dot* is stripped, and only because a sentence-ending
    "experience." otherwise never matched the stop list and was reported back to
    candidates as a missing keyword to add. Trailing "+" and "#" are left alone:
    no sentence ends in either, and stripping them turned "c++" into "c".
    """
    return [
        token.rstrip(".")
        for token in re.findall(r"[a-z0-9][a-z0-9+#.]*", text.lower())
        if token.rstrip(".")
    ]


def extract_keywords(job_description: str, *, limit: int = 40) -> list[str]:
    """
    The terms a job description actually asks for, most frequent first.

    Frequency-ordered rather than first-seen: a requirement mentioned four times
    matters more than one listed once in a nice-to-have line, and a candidate
    working through a gap list should see the important ones first.
    """
    counts: dict[str, int] = {}
    for token in _tokens(job_description):
        if len(token) < 3 or token in STOP_WORDS or token.isdigit():
            continue
        counts[token] = counts.get(token, 0) + 1

    ordered = sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))
    return [word for word, _ in ordered[:limit]]


def _parseability(text: str) -> Component:
    """
    Whether the document extracted into something a parser can read at all.

    The most common real ATS failure is not vocabulary, it is a resume laid out
    in columns or as an image, which arrives as jumbled text or as nothing.
    """
    words = _tokens(text)
    word_count = len(words)

    if word_count == 0:
        return Component("parseability", "Text extraction", 0.0, 0.25,
                         "No text could be read from this file at all.")

    # Very long "words" are the signature of a table or column layout collapsing
    # into a run of glued-together text.
    glued = sum(1 for word in words if len(word) > 30)
    glued_ratio = glued / word_count

    score = 100.0
    detail = "Text extracted cleanly."

    if word_count < MIN_REASONABLE_WORDS:
        score -= 45
        detail = f"Only {word_count} words were readable, which usually means a scanned or image-based resume."
    elif word_count > MAX_REASONABLE_WORDS:
        score -= 15
        detail = f"{word_count} words is long for a resume; an ATS will read it but a person may not."

    if glued_ratio > 0.02:
        score -= 30
        detail = "Some text ran together, which usually means a multi-column or table layout."

    return Component("parseability", "Text extraction", max(0.0, score), 0.25, detail)


def _sections(text: str) -> Component:
    found = []
    for name, patterns in SECTION_PATTERNS.items():
        if any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns):
            found.append(name)

    # Experience and education are what a parser fills its structured fields
    # from; skills and projects help but their absence is not disqualifying.
    core = {"experience", "education"} & set(found)
    score = len(core) / 2 * 70 + len({"skills", "projects"} & set(found)) / 2 * 30

    missing = [name for name in SECTION_PATTERNS if name not in found]
    detail = (
        "All the standard sections are present."
        if not missing
        else "No clear heading for: " + ", ".join(sorted(missing)) + "."
    )
    return Component("sections", "Standard sections", score, 0.2, detail)


def _contactability(text: str) -> Component:
    head = text[:1500]  # contact details belong at the top; an ATS looks there
    has_email = bool(EMAIL_PATTERN.search(head))
    has_phone = bool(PHONE_PATTERN.search(head))
    has_link = bool(URL_PATTERN.search(head))

    score = (60 if has_email else 0) + (25 if has_phone else 0) + (15 if has_link else 0)
    missing = [
        label
        for label, present in (("an email address", has_email), ("a phone number", has_phone),
                               ("a LinkedIn or GitHub link", has_link))
        if not present
    ]
    detail = (
        "Email, phone and a profile link are all near the top."
        if not missing
        else "Near the top of the page, couldn't find " + ", ".join(missing) + "."
    )
    return Component("contact", "Contact details", float(score), 0.15, detail)


def _impact(text: str) -> Component:
    """Bullets, numbers, and openers that describe duties rather than results."""
    bullets = BULLET_PATTERN.findall(text)
    bullet_count = len(bullets)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    quantified = sum(1 for line in lines if DIGIT_PATTERN.search(line))
    lowered = text.lower()
    weak = sum(lowered.count(phrase) for phrase in WEAK_OPENERS)

    score = 40.0
    notes = []

    if bullet_count >= 8:
        score += 30
    elif bullet_count >= 3:
        score += 18
    else:
        notes.append("very few bullet points")

    quantified_ratio = quantified / len(lines) if lines else 0
    if quantified_ratio >= 0.25:
        score += 30
    elif quantified_ratio >= 0.1:
        score += 15
    else:
        notes.append("almost no numbers or measurable results")

    if weak > 0:
        score -= min(20, weak * 5)
        notes.append(f"{weak} bullet{'s' if weak != 1 else ''} opening with a phrase like \"responsible for\"")

    detail = "Bullets are specific and quantified." if not notes else "Found " + "; ".join(notes) + "."
    return Component("impact", "Impact and specificity", max(0.0, min(100.0, score)), 0.15, detail)


def _keyword_coverage(text: str, job_description: str) -> tuple[Component, list[str], list[str]]:
    """
    How much of the job description's vocabulary the resume actually uses.

    Substring matching on the token stream rather than exact token equality, so
    "engineering" in the resume satisfies "engineer" in the description. The
    looser direction is the right one to err in: telling a candidate to add a
    word they have already used in another form would send them to pad their
    resume with a synonym, which is exactly the behaviour that makes resumes
    worse.
    """
    keywords = extract_keywords(job_description)
    if not keywords:
        return (
            Component("keywords", "Job description match", 0.0, 0.25,
                      "The job description had no distinctive terms to match against."),
            [],
            [],
        )

    haystack = " ".join(_tokens(text))
    matched = [word for word in keywords if word in haystack]
    gaps = [word for word in keywords if word not in haystack]

    coverage = len(matched) / len(keywords) * 100
    detail = f"Your resume uses {len(matched)} of the {len(keywords)} distinctive terms in this job description."
    return Component("keywords", "Job description match", coverage, 0.25, detail), matched, gaps


def build_suggestions(analysis_components: list[Component], gaps: list[str] | None) -> list[str]:
    """
    Concrete next steps, derived from the components that actually scored badly.

    Deliberately not a fixed list of resume advice: every line here is triggered
    by something measured in *this* document, so a candidate is never told to fix
    something that is already fine.
    """
    by_name = {component.name: component for component in analysis_components}
    suggestions: list[str] = []

    parseability = by_name.get("parseability")
    if parseability and parseability.score < 70:
        suggestions.append(
            "Export the resume as a single-column PDF from a word processor rather than a design tool. "
            "Multi-column and image-based layouts are the most common reason an ATS reads a resume as empty."
        )

    sections = by_name.get("sections")
    if sections and sections.score < 100:
        suggestions.append(
            "Use plain section headings — Experience, Education, Skills, Projects. Parsers fill their "
            "structured fields by looking for exactly those words."
        )

    contact = by_name.get("contact")
    if contact and contact.score < 100:
        suggestions.append(
            "Put your email, phone number and a LinkedIn or GitHub link in the first few lines, as text "
            "rather than inside a header image or a text box."
        )

    impact = by_name.get("impact")
    if impact and impact.score < 70:
        suggestions.append(
            "Rewrite duty-style bullets as results: what you did, and what changed because of it. "
            "A number — a percentage, a duration, a count — makes the difference concrete."
        )

    if gaps:
        shown = ", ".join(gaps[:8])
        suggestions.append(
            f"The job description asks about terms your resume never uses: {shown}. "
            "Add the ones you genuinely have experience with, in the bullet where you actually did the work."
        )

    if not suggestions:
        suggestions.append(
            "Nothing structural is holding this resume back. Tailor the wording per application and keep "
            "the most relevant experience in the top third of the first page."
        )

    return suggestions


def analyse(resume_text: str, job_description: str | None = None) -> Analysis:
    """
    Score a resume, over the components that could be measured.

    Returns `ats_score = None` only when nothing could be measured at all, which
    in practice means an empty extraction. Anything else produces a score plus
    the components behind it, so the number is always explainable.
    """
    text = (resume_text or "").strip()
    word_count = len(_tokens(text))

    components = [_parseability(text), _sections(text), _contactability(text), _impact(text)]

    matched: list[str] | None = None
    gaps: list[str] | None = None
    unmeasured: list[str] = []

    if job_description and job_description.strip():
        keyword_component, matched, gaps = _keyword_coverage(text, job_description)
        components.append(keyword_component)
    else:
        # Not scored as zero. A candidate who pasted no job description has not
        # failed keyword matching, they have not been assessed on it -- and
        # `keyword_gaps` stays NULL rather than becoming an empty list, which
        # would read as "we looked and found no gaps".
        unmeasured.append("keywords")

    total_weight = sum(component.weight for component in components)
    if total_weight <= 0 or word_count == 0:
        return Analysis(
            ats_score=None,
            components=components,
            measured=[],
            unmeasured=[component.name for component in components] + unmeasured,
            keyword_gaps=gaps,
            matched_keywords=matched,
            suggestions=[
                "No text could be read from this file. If it is a scanned image or a photo of a "
                "printed page, export a text-based PDF instead — an ATS cannot read either."
            ],
            word_count=0,
        )

    # Renormalised over the measured components, so dropping keyword matching
    # rescales the rest rather than capping the achievable score at 75.
    weighted = sum(component.score * component.weight for component in components) / total_weight

    return Analysis(
        ats_score=round(weighted),
        components=components,
        measured=[component.name for component in components],
        unmeasured=unmeasured,
        keyword_gaps=gaps,
        matched_keywords=matched,
        suggestions=build_suggestions(components, gaps),
        word_count=word_count,
    )

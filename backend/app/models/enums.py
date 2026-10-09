"""
All enumerated types referenced by the Section 8 database schema.

Defined once here and imported by every model module so the same Python
enum backs both the SQLAlchemy column type and any Pydantic schema that
needs to expose the same set of values.
"""
import enum


class AuthProvider(str, enum.Enum):
    PASSWORD = "password"
    GOOGLE = "google"
    BOTH = "both"


class UserRole(str, enum.Enum):
    CANDIDATE = "candidate"
    ADMIN = "admin"


class PreferredMode(str, enum.Enum):
    VOICE = "voice"
    SIGN = "sign"
    BOTH = "both"


class ExperienceLevel(str, enum.Enum):
    STUDENT_FRESHER = "student_fresher"
    ONE_TO_THREE_YEARS = "1-3_years"
    THREE_PLUS_YEARS = "3+_years"


class InterviewType(str, enum.Enum):
    TECHNICAL = "technical"
    BEHAVIORAL = "behavioral"
    MIXED = "mixed"


class InterviewMode(str, enum.Enum):
    VOICE = "voice"
    SIGN = "sign"


class SessionStatus(str, enum.Enum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class TransportMode(str, enum.Enum):
    WEBRTC_FULL = "webrtc_full"
    WEBRTC_NO_WS = "webrtc_no_ws"
    TURN_RELAY = "turn_relay"
    AUDIO_ONLY_HTTP = "audio_only_http"
    # Phase 2 addition (not in the original Section 6.6 ladder): ASR/TTS run
    # client-side via the browser's Web Speech API (see MASTER_PROMPT.md
    # Phase 2 notes), so no WebRTC media transport to the backend exists
    # yet at all — the WebSocket carries only text/control events. Real
    # values from the fallback ladder above start applying once a cloud
    # ASR/TTS provider is wired in and audio actually streams to the
    # backend (Phase 3+).
    BROWSER_NATIVE_SPEECH = "browser_native_speech"


class LLMProvider(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


class TTSProvider(str, enum.Enum):
    PROVIDER_PRIMARY = "provider_primary"
    PROVIDER_FALLBACK = "provider_fallback"
    # Phase 2: the browser's own speechSynthesis, not one of our configured
    # backend TTS providers (see TransportMode.BROWSER_NATIVE_SPEECH).
    BROWSER_NATIVE = "browser_native"


class QuestionType(str, enum.Enum):
    PLANNED = "planned"
    FOLLOWUP = "followup"


class FeedbackCategory(str, enum.Enum):
    CONTENT = "content"
    COMMUNICATION = "communication"
    CONFIDENCE = "confidence"
    BODY_LANGUAGE = "body_language"


class FeedbackItemType(str, enum.Enum):
    STRENGTH = "strength"
    IMPROVEMENT = "improvement"


class FeedbackGenerationStatus(str, enum.Enum):
    """
    Lifecycle of one feedback report (Phase 4).

    Not in Section 8's column list, but Section 4.10's post-interview
    "processing" screen has to poll something real, and Section 21.2 requires a
    defined degraded-mode outcome rather than a spinner that never resolves. A
    row stuck in PROCESSING because the worker died is distinguishable from one
    that legitimately hasn't started, and FAILED carries a reason.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class AptitudeTopic(str, enum.Enum):
    QUANTITATIVE = "quantitative"
    LOGICAL_REASONING = "logical_reasoning"
    VERBAL_ABILITY = "verbal_ability"
    DATA_INTERPRETATION = "data_interpretation"


class Difficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class DSATopic(str, enum.Enum):
    ARRAYS = "arrays"
    STRINGS = "strings"
    LINKED_LISTS = "linked_lists"
    TREES = "trees"
    GRAPHS = "graphs"
    DYNAMIC_PROGRAMMING = "dynamic_programming"
    RECURSION_BACKTRACKING = "recursion_backtracking"
    SORTING_SEARCHING = "sorting_searching"
    GREEDY = "greedy"


class SubmissionStatus(str, enum.Enum):
    PASSED = "passed"
    FAILED = "failed"
    PARTIAL = "partial"

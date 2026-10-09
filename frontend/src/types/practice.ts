/** Aptitude and DSA module types (Phase 7). */

export type AptitudeTopic =
  | "quantitative"
  | "logical_reasoning"
  | "verbal_ability"
  | "data_interpretation";

export type Difficulty = "easy" | "medium" | "hard";
export type SubmissionStatus = "passed" | "failed" | "partial";

export interface AptitudeCatalog {
  topicCounts: Record<string, number>;
  difficultyCounts: Record<string, number>;
  /** Keyed "topic:difficulty" — lets the UI grey out a filter that cannot fill a test. */
  combinationCounts: Record<string, number>;
  minQuestions: number;
}

/** Note the absence of the answer. It is not sent until the attempt is submitted. */
export interface AptitudeQuestion {
  id: string;
  topic: AptitudeTopic;
  difficulty: Difficulty;
  questionText: string;
  options: string[];
}

export interface AptitudeAttempt {
  attemptId: string;
  totalQuestions: number;
  questions: AptitudeQuestion[];
}

export interface AptitudeAnswerReview {
  questionId: string;
  questionText: string;
  topic: AptitudeTopic;
  difficulty: Difficulty;
  options: string[];
  selectedOptionIndex: number | null;
  correctOptionIndex: number;
  isCorrect: boolean;
  timeSpentSeconds: number | null;
}

export interface AptitudeTopicBreakdown {
  topic: AptitudeTopic;
  correct: number;
  total: number;
  /** Null when the attempt asked nothing from this topic — not 0%. */
  percentage: number | null;
}

export interface AptitudeResult {
  attemptId: string;
  // Present only for a timed mock test. Derived server-side from `started_at`
  // and `submitted_at` rather than stored, so nothing can be set wrong.
  testName: string | null;
  durationMinutes: number | null;
  timeTakenSeconds: number | null;
  submittedLate: boolean;
  /** A percentage, 0-100. See the service docstring for why not a raw count. */
  score: number;
  correctCount: number;
  totalQuestions: number;
  topicBreakdown: AptitudeTopicBreakdown[];
  answers: AptitudeAnswerReview[];
}

export interface AptitudeHistoryItem {
  attemptId: string;
  score: number | null;
  totalQuestions: number | null;
  startedAt: string | null;
  submittedAt: string | null;
}

export interface DsaProblemListItem {
  id: string;
  title: string;
  topic: string;
  difficulty: Difficulty;
  solved: boolean;
  attempted: boolean;
}

export interface DsaTestCase {
  args: unknown[];
  expected: unknown;
}

export interface DsaProblem {
  id: string;
  title: string;
  topic: string;
  difficulty: Difficulty;
  statementText: string;
  constraintsText: string | null;
  starterCode: Record<string, string>;
  functionName: string;
  sampleTestCases: DsaTestCase[];
  /** The count only. The cases come from their own route, for the runner. */
  hiddenTestCaseCount: number;
  solved: boolean;
}

export interface DsaSubmission {
  id: string;
  problemId: string;
  language: string;
  status: SubmissionStatus;
  runtimeMs: number | null;
  hintsUsedCount: number;
  submittedAt: string;
}

export interface DsaHint {
  hint: string;
  /** "deterministic" means a rule-based nudge, not model reasoning. */
  generatedBy: string;
  hintsUsedCount: number;
}

// --- Resume analysis (Phase 8) ---------------------------------------------

export interface ResumeComponent {
  name: string;
  label: string;
  score: number;
  /** The weight actually applied after renormalising over measured components. */
  weight: number;
  detail: string;
}

export interface ResumeAnalysis {
  id: string;
  /** Null when nothing could be read from the document at all. */
  atsScore: number | null;
  components: ResumeComponent[];
  measured: string[];
  unmeasured: string[];
  /** Null — not [] — when no job description was given. */
  keywordGaps: string[] | null;
  matchedKeywords: string[] | null;
  suggestions: string[];
  wordCount: number;
  hadJobDescription: boolean;
  analyzedAt: string | null;
}

export interface ResumeHistoryItem {
  id: string;
  atsScore: number | null;
  hadJobDescription: boolean;
  analyzedAt: string | null;
}

// --- Timed mock tests (Sections 4.13, 4.14) ---------------------------------

export interface MockTest {
  id: string;
  name: string;
  description: string;
  questionCount: number;
  durationMinutes: number;
  topics: AptitudeTopic[];
}

export interface TimedAttempt extends AptitudeAttempt {
  testId: string;
  testName: string;
  durationMinutes: number;
  /** Counted down from the server's `started_at`, not handed over as a duration. */
  timeRemainingSeconds: number;
}

/** The three states a palette cell can be in (Section 4.14). */
export type PaletteState = "answered" | "unanswered" | "review";

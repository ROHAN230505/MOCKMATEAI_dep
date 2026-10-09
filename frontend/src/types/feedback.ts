// Mirrors backend/app/schemas/feedback.py.

import type { InterviewMode, InterviewType } from "./interview";

export type FeedbackCategory = "content" | "communication" | "confidence" | "body_language";
export type FeedbackItemType = "strength" | "improvement";
export type FeedbackGenerationStatus = "pending" | "processing" | "ready" | "failed";

export interface CategoryScore {
  category: FeedbackCategory;
  score: number | null;
  /** Weight actually applied after renormalizing over measured categories (Section 10.2). */
  weight: number | null;
  /**
   * False means nothing measured this category in this session — NOT that the
   * candidate scored zero. The UI must render these two cases differently.
   */
  measured: boolean;
  label: string;
}

export interface FeedbackItem {
  category: FeedbackCategory;
  type: FeedbackItemType;
  text: string;
  /** e.g. `Q3: "we cut p95 latency to 180ms"` — the quote that justifies the claim. */
  evidenceReference: string | null;
}

export interface TranscriptTurn {
  number: number;
  questionId: string;
  questionText: string;
  isFollowup: boolean;
  answerText: string | null;
  isSkipped: boolean;
  relevanceScore: number | null;
  completenessScore: number | null;
  /** null = the browser reported no confidence, which is not the same as low. */
  asrConfidenceAvg: number | null;
}

export interface TranscriptSignals {
  answerCount: number;
  totalWords: number;
  fillerCount: number;
  fillerRatePer100Words: number;
  averageAnswerWords: number;
  quantifiedAnswers: number;
  underElaboratedAnswers: number;
  wellDevelopedAnswers: number;
  speakingPaceWpm: number | null;
}

export type DeltaDirection = "improved" | "declined" | "unchanged" | "not_comparable";

export interface CategoryDelta {
  /** "overall" plus the four `CategoryScore.category` values. */
  category: string;
  previous: number | null;
  current: number | null;
  delta: number | null;
  direction: DeltaDirection;
}

export interface FeedbackComparison {
  previousSessionId: string;
  previousRoleTarget: string;
  previousCompletedAt: string | null;
  sameRole: boolean;
  headline: string;
  deltas: CategoryDelta[];
}

export interface FeedbackReport {
  sessionId: string;
  status: FeedbackGenerationStatus;
  generatedAt: string | null;
  /** "anthropic" / "openai" / "deterministic" — surfaced so rule-based prose is labeled. */
  generatedBy: string | null;

  roleTarget: string;
  interviewType: InterviewType;
  durationMinutes: number;
  mode: InterviewMode;
  startedAt: string | null;
  endedAt: string | null;
  targetCompanyName: string | null;

  overallReadinessScore: number | null;
  readinessLabel: string;
  categoryScores: CategoryScore[];
  measuredCategories: string[];
  unmeasuredCategories: string[];

  summaryText: string | null;
  strengths: FeedbackItem[];
  improvements: FeedbackItem[];

  answeredCount: number;
  skippedCount: number;
  questionCount: number;
  turns: TranscriptTurn[];
  signals: TranscriptSignals | null;

  comparison: FeedbackComparison | null;
  disclaimer: string;
}

export interface FeedbackStatus {
  sessionId: string;
  status: FeedbackGenerationStatus;
  generatedAt: string | null;
  error: string | null;
}

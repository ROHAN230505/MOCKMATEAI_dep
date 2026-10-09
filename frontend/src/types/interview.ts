// Mirrors backend/app/schemas/interview.py.

export type InterviewType = "technical" | "behavioral" | "mixed";
export type InterviewMode = "voice" | "sign";
export type SessionStatus = "in_progress" | "completed" | "abandoned";
export type TransportMode =
  | "webrtc_full"
  | "webrtc_no_ws"
  | "turn_relay"
  | "audio_only_http"
  | "browser_native_speech";

export interface StartInterviewResponse {
  sessionId: string;
  wsUrl: string;
  transportMode: TransportMode;
}

export interface InterviewAnswer {
  transcriptText: string | null;
  isSkipped: boolean;
  asrConfidenceAvg: number | null;
}

export interface AnswerEvaluation {
  relevanceScore: number | null;
  completenessScore: number | null;
  followupTriggered: boolean;
  followupReasonText: string | null;
}

export interface InterviewQuestion {
  id: string;
  sequenceOrder: number;
  questionText: string;
  questionType: "planned" | "followup";
  interruptedAtCharOffset: number | null;
  parentQuestionId: string | null;
  answer: InterviewAnswer | null;
  evaluation: AnswerEvaluation | null;
}

export interface InterviewSessionDetail {
  id: string;
  roleTarget: string;
  interviewType: InterviewType;
  durationMinutes: number;
  mode: InterviewMode;
  status: SessionStatus;
  startedAt: string | null;
  endedAt: string | null;
  transportMode: TransportMode | null;
  questions: InterviewQuestion[];
}

export interface InterviewHistoryItem {
  id: string;
  roleTarget: string;
  interviewType: InterviewType;
  durationMinutes: number;
  mode: InterviewMode;
  status: SessionStatus;
  startedAt: string | null;
  endedAt: string | null;
}

/**
 * Section 9.7's voice prosody signals.
 *
 * Only the two audio-derived measures are sent: speaking pace and filler-word
 * count are computed server-side from the transcript, so they come back on the
 * response but are never submitted.
 */
export interface ProsodySignalsBody {
  pitchVarianceScore: number | null;
  avgPauseDurationMs: number | null;
  voicedSeconds: number;
}

export interface ProsodySignals {
  sessionId: string;
  avgPaceWpm: number | null;
  fillerWordCount: number | null;
  pitchVarianceScore: number | null;
  avgPauseDurationMs: number | null;
}

/**
 * Section 9.7's expression signals.
 *
 * The coverage fields are submitted with the scores because they are what makes
 * the scores believable: the backend re-checks them and stores NULL when they do
 * not support a measurement, rather than taking the three scores on faith.
 */
export interface ExpressionSignalsBody {
  eyeContactPercentage: number | null;
  smileFrequencyScore: number | null;
  postureFlagCount: number | null;
  analysedSeconds: number;
  faceDetectedSeconds: number;
}

export interface ExpressionSignals {
  sessionId: string;
  eyeContactPercentage: number | null;
  smileFrequencyScore: number | null;
  postureFlagCount: number | null;
}

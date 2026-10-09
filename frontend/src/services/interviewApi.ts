import { apiRequest } from "../lib/apiClient";
import type {
  InterviewHistoryItem,
  InterviewMode,
  InterviewSessionDetail,
  ExpressionSignals,
  ExpressionSignalsBody,
  InterviewType,
  ProsodySignals,
  ProsodySignalsBody,
  StartInterviewResponse,
} from "../types/interview";

export function startInterview(input: {
  role: string;
  type: InterviewType;
  durationMinutes: number;
  mode: InterviewMode;
  consentGiven: boolean;
  // Section 4.6's optional custom job targeting. Omit rather than sending
  // empty strings so the backend's "is a JD present?" check stays truthy-based.
  jobDescriptionText?: string;
  targetCompanyName?: string;
}) {
  return apiRequest<StartInterviewResponse>("/interviews/start", { method: "POST", body: input });
}

export function endInterview(sessionId: string) {
  return apiRequest<InterviewSessionDetail>(`/interviews/${sessionId}/end`, { method: "POST" });
}

export function getInterview(sessionId: string) {
  return apiRequest<InterviewSessionDetail>(`/interviews/${sessionId}`);
}

export function getInterviewHistory() {
  return apiRequest<InterviewHistoryItem[]>("/interviews/history");
}

/**
 * Section 9.7's prosody signals, recorded after the fact.
 *
 * The live interview sends its running aggregate over the WebSocket instead —
 * see the `prosody_update` branch in `app/routers/interviews.py` for why it
 * cannot wait for the end. This is the fallback for when there is no socket to
 * send on: the REST end path taken by the error screen's "End Interview Now".
 */
export function submitProsodySignals(sessionId: string, body: ProsodySignalsBody) {
  return apiRequest<ProsodySignals>(`/interviews/${sessionId}/signals/prosody`, {
    method: "POST",
    body,
  });
}

/**
 * Section 9.7's expression signals, recorded after the fact.
 *
 * Same two-channel arrangement as prosody: the live interview streams its running
 * aggregate over the WebSocket, and this covers the REST end path where no socket
 * remains. Carries three scores and two coverage figures — never a frame, never a
 * landmark.
 */
export function submitExpressionSignals(sessionId: string, body: ExpressionSignalsBody) {
  return apiRequest<ExpressionSignals>(`/interviews/${sessionId}/signals/expression`, {
    method: "POST",
    body,
  });
}

/**
 * Section 6.6's HTTP fallback for the live turn loop.
 *
 * Carries exactly the events the WebSocket carries and gets back exactly the
 * events it would have pushed, so the interview is the same interview — see
 * `backend/app/services/live_channel.py` for why the ladder above this rung
 * does not apply to a build whose speech never leaves the browser.
 */
export function postLiveEvents(sessionId: string, events: Record<string, unknown>[]) {
  return apiRequest<{ events: Record<string, unknown>[]; ended: boolean }>(
    `/interviews/${sessionId}/events`,
    { method: "POST", body: { events } },
  );
}

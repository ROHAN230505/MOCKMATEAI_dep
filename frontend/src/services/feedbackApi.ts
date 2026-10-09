import { apiDownload, apiRequest, saveBlob } from "../lib/apiClient";
import type { FeedbackReport, FeedbackStatus } from "../types/feedback";

export function getFeedbackReport(sessionId: string) {
  return apiRequest<FeedbackReport>(`/feedback/${sessionId}`);
}

/** The lightweight shape the Section 4.10 processing screen polls. */
export function getFeedbackStatus(sessionId: string) {
  return apiRequest<FeedbackStatus>(`/feedback/${sessionId}/status`);
}

/**
 * Generate or regenerate the report, awaiting the result.
 *
 * The automatic path runs server-side when the interview ends; this is the
 * explicit retry, used when generation failed or was never started (an
 * interview abandoned by closing the tab).
 */
export function generateFeedbackReport(sessionId: string) {
  return apiRequest<FeedbackReport>(`/feedback/${sessionId}/generate`, { method: "POST" });
}

export async function downloadFeedbackPdf(sessionId: string) {
  const { blob, filename } = await apiDownload(`/feedback/${sessionId}/pdf`);
  saveBlob(blob, filename ?? `mockmateai-feedback-${sessionId}.pdf`);
}

export async function downloadTranscript(sessionId: string, format: "txt" | "json") {
  const { blob, filename } = await apiDownload(`/recordings/${sessionId}/transcript?format=${format}`);
  saveBlob(blob, filename ?? `mockmateai-transcript-${sessionId}.${format}`);
}

import { apiRequest } from "../lib/apiClient";
import type {
  AptitudeCatalog,
  AptitudeAttempt,
  AptitudeHistoryItem,
  AptitudeResult,
  AptitudeTopic,
  Difficulty,
  DsaHint,
  DsaProblem,
  DsaProblemListItem,
  DsaSubmission,
  DsaTestCase,
  MockTest,
  ResumeAnalysis,
  ResumeHistoryItem,
  TimedAttempt,
} from "../types/practice";

// --- Aptitude ---------------------------------------------------------------

export function getAptitudeCatalog() {
  return apiRequest<AptitudeCatalog>("/aptitude/catalog");
}

export function startAptitudeAttempt(input: {
  topics: AptitudeTopic[];
  difficulties: Difficulty[];
  questionCount: number;
}) {
  return apiRequest<AptitudeAttempt>("/aptitude/attempts", { method: "POST", body: input });
}

export function submitAptitudeAttempt(
  attemptId: string,
  answers: { questionId: string; selectedOptionIndex: number | null; timeSpentSeconds: number | null }[],
) {
  return apiRequest<AptitudeResult>(`/aptitude/attempts/${attemptId}/submit`, {
    method: "POST",
    body: { answers },
  });
}

export function getAptitudeResult(attemptId: string) {
  return apiRequest<AptitudeResult>(`/aptitude/attempts/${attemptId}`);
}

export function getAptitudeHistory() {
  return apiRequest<AptitudeHistoryItem[]>("/aptitude/attempts");
}

// --- DSA --------------------------------------------------------------------

export function getDsaProblems() {
  return apiRequest<DsaProblemListItem[]>("/dsa/problems");
}

/**
 * Write a brand-new problem on demand.
 *
 * Several seconds: the server generates it and then independently recomputes
 * every expected output before returning it, and only ships a problem where
 * the two agree. A 503 means it failed that check and was discarded rather
 * than handed over unverified -- a wrong hidden test fails a CORRECT
 * solution, which is the one failure a candidate cannot diagnose.
 */
export function generateDsaProblem(input: { topic: string; difficulty: Difficulty }) {
  return apiRequest<DsaProblem>("/dsa/problems/generate", { method: "POST", body: input });
}

export function getDsaProblem(problemId: string) {
  return apiRequest<DsaProblem>(`/dsa/problems/${problemId}`);
}

/**
 * The hidden cases, for the in-browser runner.
 *
 * A POST because it starts a graded run rather than being a cacheable read. And
 * yes — these reach the client, which is the acknowledged cost of grading in the
 * browser rather than on a server. The UI says so.
 */
export function getDsaHiddenTestCases(problemId: string) {
  return apiRequest<{ hiddenTestCases: DsaTestCase[] }>(`/dsa/problems/${problemId}/test-cases`, {
    method: "POST",
    body: {},
  });
}

export function submitDsaSolution(
  problemId: string,
  input: {
    code: string;
    language: string;
    passedCaseCount: number;
    totalCaseCount: number;
    runtimeMs: number | null;
    hintsUsedCount: number;
  },
) {
  return apiRequest<DsaSubmission>(`/dsa/problems/${problemId}/submit`, {
    method: "POST",
    body: input,
  });
}

export function getDsaSubmissions(problemId: string) {
  return apiRequest<DsaSubmission[]>(`/dsa/problems/${problemId}/submissions`);
}

export function requestDsaHint(problemId: string, input: { hintIndex: number; code: string }) {
  return apiRequest<DsaHint>(`/dsa/problems/${problemId}/hint`, { method: "POST", body: input });
}

// --- Resume -----------------------------------------------------------------

/**
 * Submits extracted **text**, never the file.
 *
 * The document is parsed in the browser and discarded there — see
 * `lib/resumeExtract.ts` for why a resume in particular is kept off the server.
 */
export function analyseResume(input: {
  resumeText: string;
  jobDescriptionText?: string;
  fileName?: string;
}) {
  return apiRequest<ResumeAnalysis>("/resume/analyses", { method: "POST", body: input });
}

export function getResumeHistory() {
  return apiRequest<ResumeHistoryItem[]>("/resume/analyses");
}

export function getResumeAnalysis(analysisId: string) {
  return apiRequest<ResumeAnalysis>(`/resume/analyses/${analysisId}`);
}

export function getMockTests() {
  return apiRequest<MockTest[]>("/aptitude/tests");
}

export function startMockTest(testId: string) {
  return apiRequest<TimedAttempt>(`/aptitude/tests/${testId}/start`, { method: "POST", body: {} });
}

/**
 * The server's view of the clock.
 *
 * Polled rather than trusted to a local interval: a backgrounded tab throttles
 * timers, and a reload would otherwise restart a full-length countdown.
 */
export function getAttemptTime(attemptId: string) {
  return apiRequest<{ timeRemainingSeconds: number | null; submitted: boolean }>(
    `/aptitude/attempts/${attemptId}/time`,
  );
}

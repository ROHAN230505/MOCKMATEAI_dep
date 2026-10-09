import { useCallback, useEffect, useRef, useState } from "react";
import { buildWsUrl } from "../lib/apiClient";
import { postLiveEvents } from "../services/interviewApi";
import type { InterviewMode } from "../types/interview";
import { useAuthStore } from "../store/authStore";
import { useExpressionAnalyser } from "./useExpressionAnalyser";
import { useMicLevel } from "./useMicLevel";
import { useProsodyAnalyser } from "./useProsodyAnalyser";
import { useSpeechRecognition } from "./useSpeechRecognition";
import { useSpeechSynthesis } from "./useSpeechSynthesis";

/**
 * Client-side interview state machine (Section 5.2/10.1), adapted for
 * Phase 2's reality: ASR/TTS run in the browser, so this machine — not the
 * server — owns AI_SPEAKING vs LISTENING. The server is still authoritative
 * over question sequencing, timing, and persistence (see
 * app/routers/interviews.py's WebSocket handler); this hook is the
 * frontend half of that same protocol.
 */
// `evaluating` is Section 10.1's EVALUATING state. As of Phase 3 the server
// owns it (deciding what to say next is an LLM call it makes) and announces
// it via `turn_state_changed`, so the candidate sees a "thinking" cue instead
// of unexplained silence between their answer and the next question.
export type OrchestratorPhase =
  | "connecting"
  | "ai_speaking"
  | "listening"
  // Phase 6: the signed equivalent of `listening`. A separate state rather than
  // a reuse, because the two mean different things to the UI — `listening` says
  // a microphone is open, `composing` says a text field has focus and nothing
  // is being captured until the candidate submits.
  | "composing"
  | "evaluating"
  | "paused"
  | "reconnecting"
  | "ended"
  | "error";
export type EndReason = "completed" | "time_up" | "ended_by_candidate" | null;

// Section 4.8A: "~200-300ms debounce to avoid false triggers from a stray
// cough". Threshold is a plain RMS cutoff — good enough to prove the
// barge-in *mechanism* end-to-end; a real VAD model can replace this
// scalar check later without touching the state machine around it.
const BARGE_IN_LEVEL_THRESHOLD = 0.15;
const BARGE_IN_DEBOUNCE_MS = 250;

// Section 5.6: "attempt ... reconnection for up to 30 seconds before
// offering 'End Interview Now'".
const RECONNECT_INTERVAL_MS = 3000;
const RECONNECT_MAX_ATTEMPTS = 10;
// Two refused upgrades is enough to call it: a proxy that blocks WebSockets
// blocks them every time, and the candidate should not spend Section 5.6’s full
// thirty seconds discovering that.
const WS_ATTEMPTS_BEFORE_FALLBACK = 2;

interface OrchestratorOptions {
  wsPath: string; // StartInterviewResponse.wsUrl
  /** Needed by the Section 6.6 HTTP fallback, which addresses the session directly. */
  sessionId: string;
  /**
   * How the candidate answers. `sign` runs the same protocol and the same
   * engine with the speech layer removed entirely: no TTS, no recogniser, no
   * microphone, no prosody. Everything else — question sequencing, follow-ups,
   * the timer, pause/skip/end, expression signals — is identical.
   */
  mode?: InterviewMode;
  micStream: MediaStream | null;
  /**
   * The candidate's own camera preview, for Section 9.7's expression signals.
   * Optional: with no element (or no camera) expression stays unmeasured and the
   * interview is otherwise unaffected.
   */
  videoElement?: HTMLVideoElement | null;
}

export function useInterviewOrchestrator({
  wsPath,
  sessionId,
  mode = "voice",
  micStream,
  videoElement = null,
}: OrchestratorOptions) {
  const signMode = mode === "sign";
  const [phase, setPhase] = useState<OrchestratorPhase>("connecting");
  const [questionText, setQuestionText] = useState<string | null>(null);
  const [sequenceOrder, setSequenceOrder] = useState<number | null>(null);
  const [totalQuestions, setTotalQuestions] = useState<number | null>(null);
  const [captionText, setCaptionText] = useState("");
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [totalSeconds, setTotalSeconds] = useState(0);
  const [isMuted, setIsMuted] = useState(false);
  const [endReason, setEndReason] = useState<EndReason>(null);
  const [usingHttpFallback, setUsingHttpFallback] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  // Phase 3: whether the current question is an adaptive follow-up rather
  // than a planned topic, so the UI can say so (Section 4.11 treats
  // follow-ups as a distinct outcome type worth surfacing).
  const [isFollowup, setIsFollowup] = useState(false);
  const [plannedRemaining, setPlannedRemaining] = useState<number | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const currentQuestionIdRef = useRef<string | null>(null);
  const phaseRef = useRef<OrchestratorPhase>("connecting");
  const prePauseSubPhaseRef = useRef<"ai_speaking" | "listening" | "composing">("listening");
  const reconnectAttemptsRef = useRef(0);
  const reconnectTimeoutRef = useRef<number | undefined>(undefined);
  const intentionalCloseRef = useRef(false);

  const setPhaseBoth = useCallback((next: OrchestratorPhase) => {
    phaseRef.current = next;
    setPhase(next);
  }, []);

  // Section 9.7's prosody measurement. Kept on its own AnalyserNode rather
  // than folded into `useMicLevel` below: that hook is a shared primitive the
  // precheck screen uses too, and it is torn down whenever the candidate mutes,
  // which would discard the session aggregate every time. This one is handed
  // `isMuted` as a *pause* instead, so accumulated measurements survive a mute.
  // Null in sign mode: there is no audio track on the stream to analyse, and
  // prosody is not a term of a signed session's score. The backend refuses a
  // prosody row for a signed session, so submitting one would be rejected anyway.
  const { measure, startAnswer, takeAnswerTiming } = useProsodyAnalyser(
    signMode ? null : micStream,
    isMuted,
  );

  // Section 9.7's expression signals. Paused whenever the interview is not
  // actually running: a candidate reading a reconnection banner is not failing to
  // make eye contact, and counting those seconds against them would turn a
  // network problem into a body-language score.
  const expressionPaused = phase === "paused" || phase === "reconnecting" || phase === "error";
  const { measure: measureExpression, status: expressionStatus } = useExpressionAnalyser(
    videoElement,
    expressionPaused,
    // In sign mode a second vision model runs on this same thread, so the
    // expression analyser takes a smaller share of each frame rather than both
    // of them assuming they have it to themselves.
    signMode,
  );

  // --- Section 6.6's HTTP fallback ---------------------------------------
  //
  // Reached only when the socket never opens at all. A socket that opened and
  // then dropped is a transient network problem and the reconnect ladder above
  // is the right answer; a socket that will not open on this network is not
  // going to start working, and retrying it for the full thirty seconds only
  // delays the interview the candidate came to do.
  // Set once `handleMessage` exists, below. Both transports deliver events
  // through it, so the fallback cannot diverge in how it reads them.
  const handleMessageRef = useRef<(raw: string) => void>(() => {});
  const transportRef = useRef<"ws" | "http">("ws");
  const everOpenedRef = useRef(false);
  const httpQueueRef = useRef<Record<string, unknown>[]>([]);
  const httpFlushRef = useRef<number | undefined>(undefined);
  const httpInFlightRef = useRef(false);

  const flushHttp = useCallback(async () => {
    // One request at a time, in order. The turn loop is sequential on the
    // server, and overlapping requests would let a later event's effects land
    // before an earlier one's.
    if (httpInFlightRef.current || httpQueueRef.current.length === 0) return;
    const batch = httpQueueRef.current;
    httpQueueRef.current = [];
    httpInFlightRef.current = true;
    try {
      const result = await postLiveEvents(sessionId, batch);
      for (const event of result.events) handleMessageRef.current(JSON.stringify(event));
      if (result.ended) intentionalCloseRef.current = true;
    } catch {
      setPhaseBoth("error");
      setErrorMessage("Lost connection to the interview session. You can end the interview now.");
    } finally {
      httpInFlightRef.current = false;
      if (httpQueueRef.current.length > 0) void flushHttp();
    }
  }, [sessionId, setPhaseBoth]);

  const enqueueHttp = useCallback(
    (message: Record<string, unknown>) => {
      httpQueueRef.current.push(message);
      // Coalesced across a tick so a turn's signals and its answer travel
      // together: one round trip per turn is what makes this usable on the kind
      // of network that forced the fallback.
      window.clearTimeout(httpFlushRef.current);
      httpFlushRef.current = window.setTimeout(() => void flushHttp(), 40);
    },
    [flushHttp],
  );

  const switchToHttp = useCallback(() => {
    if (transportRef.current === "http") return;
    transportRef.current = "http";
    setUsingHttpFallback(true);
    window.clearTimeout(reconnectTimeoutRef.current);
    wsRef.current?.close();
    wsRef.current = null;
    // The opening question is delivered on connect over a socket. Asked for
    // explicitly here — and only when none has arrived, so a mid-session
    // switchover cannot make the engine generate a second opening question.
    if (!currentQuestionIdRef.current) enqueueHttp({ type: "client_ready" });
  }, [enqueueHttp]);

  const send = useCallback(
    (message: Record<string, unknown>) => {
      if (transportRef.current === "http") {
        enqueueHttp(message);
        return;
      }
      if (wsRef.current?.readyState === WebSocket.OPEN) {
        wsRef.current.send(JSON.stringify(message));
      }
    },
    [enqueueHttp],
  );

  const synthesis = useSpeechSynthesis({
    onSpeechEnd: (wasInterrupted, charOffset) => {
      if (wasInterrupted && currentQuestionIdRef.current) {
        send({ type: "barge_in", questionId: currentQuestionIdRef.current, charOffset });
      }
      if (phaseRef.current === "ai_speaking") {
        setPhaseBoth("listening");
        // The answer's timing window opens here, when the interviewer stops
        // talking -- including on a barge-in, which reaches this same callback.
        startAnswer();
        recognitionControls.current.start();
      }
    },
  });

  // Both signal families go up together. Kept as one function so a future send
  // site cannot accidentally submit prosody and forget expression.
  const sendSignals = useCallback(() => {
    if (!signMode) send({ type: "prosody_update", prosody: measure() });
    send({ type: "expression_update", expression: measureExpression() });
  }, [send, signMode, measure, measureExpression]);

  const recognition = useSpeechRecognition({
    onInterimTranscript: setCaptionText,
    onTurnComplete: (transcript, confidence) => {
      if (!currentQuestionIdRef.current) return;
      const timing = takeAnswerTiming();
      // Signals go first, deliberately. The server may end the session inside
      // its own `submit_answer` handler (time ran out, or that was the last
      // question) and schedules report generation there, so an update sent
      // afterwards would arrive too late to be scored.
      sendSignals();
      send({
        type: "submit_answer",
        questionId: currentQuestionIdRef.current,
        transcriptText: transcript.length > 0 ? transcript : null,
        isSkipped: false,
        asrConfidenceAvg: confidence,
        // Real offsets now, bracketing the speech itself rather than the
        // listening window -- which is what makes Section 9.7's speaking pace a
        // measurement instead of a NULL. Null when the candidate said nothing
        // audible, because there is then genuinely nothing to time.
        answerStartedAt: timing?.startedAt ?? null,
        answerEndedAt: timing?.endedAt ?? null,
      });
      setCaptionText("");
    },
    onError: setErrorMessage,
  });
  // Lets the synthesis callback above call the latest recognition.start()
  // without listing `recognition` (a new object each render) as a dependency.
  const recognitionControls = useRef(recognition);
  recognitionControls.current = recognition;

  // --- Barge-in: watch mic level while the AI is "speaking" ---
  // Barge-in only exists to interrupt speech. Nothing speaks in sign mode.
  const micLevel = useMicLevel(signMode || isMuted ? null : micStream);
  const aboveThresholdSinceRef = useRef<number | null>(null);

  useEffect(() => {
    if (phase !== "ai_speaking") {
      aboveThresholdSinceRef.current = null;
      return;
    }
    if (micLevel >= BARGE_IN_LEVEL_THRESHOLD) {
      if (aboveThresholdSinceRef.current === null) {
        aboveThresholdSinceRef.current = Date.now();
      } else if (Date.now() - aboveThresholdSinceRef.current >= BARGE_IN_DEBOUNCE_MS) {
        synthesis.cancel(); // -> onSpeechEnd(true, offset) above: sends barge_in, starts listening
        aboveThresholdSinceRef.current = null;
      }
    } else {
      aboveThresholdSinceRef.current = null;
    }
  }, [micLevel, phase, synthesis]);

  // --- WebSocket lifecycle ---
  const connectRef = useRef<() => void>(() => {});

  const handleMessage = useCallback(
    (raw: string) => {
      const message = JSON.parse(raw);
      switch (message.type) {
        case "question_asked":
          currentQuestionIdRef.current = message.questionId;
          setQuestionText(message.questionText);
          setSequenceOrder(message.sequenceOrder);
          setTotalQuestions(message.totalQuestions);
          setIsFollowup(Boolean(message.isFollowup));
          setPlannedRemaining(
            typeof message.plannedRemaining === "number" ? message.plannedRemaining : null,
          );
          setCaptionText("");
          if (signMode) {
            // No speech to wait through, so there is no AI_SPEAKING state to
            // pass through: the question appears and it is the candidate's turn.
            setPhaseBoth("composing");
          } else {
            setPhaseBoth("ai_speaking");
            synthesis.speak(message.questionText);
          }
          break;
        case "turn_state_changed":
          // Only EVALUATING is adopted from the server. AI_SPEAKING and
          // LISTENING are driven locally by the actual speech APIs, which
          // know the true state — taking the server's word for those would
          // fight the local state machine and could unmute the mic while TTS
          // is still audible.
          if (message.state === "EVALUATING" && phaseRef.current !== "ended") {
            setPhaseBoth("evaluating");
          }
          break;
        case "followup_triggered":
          // The question_asked that follows carries isFollowup, which is what
          // the UI renders; this event exists for logging/telemetry parity
          // with Section 7.3's event list.
          break;
        case "timer_sync":
          setElapsedSeconds(message.elapsedSeconds);
          setTotalSeconds(message.totalSeconds);
          break;
        case "session_ended":
          intentionalCloseRef.current = true;
          setEndReason(message.reason);
          setPhaseBoth("ended");
          recognition.cancel();
          synthesis.cancel();
          break;
        case "error":
          setErrorMessage(message.message);
          break;
        default:
          break; // session_paused/session_resumed are acks; UI already reflects the optimistic local state
      }
    },
    [setPhaseBoth, synthesis, recognition, signMode],
  );

  const attemptReconnect = useCallback(() => {
    if (reconnectAttemptsRef.current >= RECONNECT_MAX_ATTEMPTS) {
      setPhaseBoth("error");
      setErrorMessage("Lost connection to the interview session. You can end the interview now.");
      return;
    }
    if (!everOpenedRef.current && reconnectAttemptsRef.current >= WS_ATTEMPTS_BEFORE_FALLBACK) {
      switchToHttp();
      return;
    }
    reconnectAttemptsRef.current += 1;
    setPhaseBoth("reconnecting");
    reconnectTimeoutRef.current = window.setTimeout(() => connectRef.current(), RECONNECT_INTERVAL_MS);
  }, [setPhaseBoth, switchToHttp]);

  const connect = useCallback(() => {
    // Read fresh from the store rather than a closed-over value — a
    // reconnect attempt minutes into a long interview must use whatever
    // access token is current, not the one captured at mount time. (A
    // reconnect landing exactly after the 15-minute access-token expiry
    // with no other request having triggered a refresh yet is a known
    // Phase 2 gap — see README.)
    const accessToken = useAuthStore.getState().accessToken;
    if (!accessToken) {
      setPhaseBoth("error");
      setErrorMessage("Your session has expired. Please log in again.");
      return;
    }

    const ws = new WebSocket(buildWsUrl(wsPath, accessToken));
    wsRef.current = ws;

    ws.onopen = () => {
      everOpenedRef.current = true;
      reconnectAttemptsRef.current = 0;
    };
    ws.onmessage = (event) => handleMessage(event.data);
    ws.onclose = () => {
      if (intentionalCloseRef.current || phaseRef.current === "ended") return;
      attemptReconnect();
    };
  }, [wsPath, handleMessage, attemptReconnect, setPhaseBoth]);

  handleMessageRef.current = handleMessage;

  connectRef.current = connect;

  useEffect(() => {
    connect();
    return () => {
      intentionalCloseRef.current = true;
      window.clearTimeout(reconnectTimeoutRef.current);
      wsRef.current?.close();
      recognition.cancel();
      synthesis.cancel();
    };
    // Deliberately mount-only: `connect` is re-invoked via `connectRef`
    // for reconnects, not by re-running this effect.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- Actions exposed to the Live Interview screen ---
  const toggleMute = useCallback(() => {
    setIsMuted((prev) => {
      const next = !prev;
      if (phaseRef.current === "listening") {
        if (next) recognition.pauseListening();
        else recognition.resumeListening();
      }
      return next;
    });
  }, [recognition]);

  // Section 9.9. The panel calls this on a debounce rather than per keystroke,
  // and calls it once more with `shared: false` when the toggle goes off so the
  // server clears what it was holding instead of keeping a stale copy.
  const shareCodePanel = useCallback(
    (code: string, shared: boolean) => {
      send({ type: "code_panel_update", code, shared });
    },
    [send],
  );

  const pause = useCallback(() => {
    prePauseSubPhaseRef.current =
      phaseRef.current === "ai_speaking"
        ? "ai_speaking"
        : phaseRef.current === "composing"
          ? "composing"
          : "listening";
    if (phaseRef.current === "ai_speaking") synthesis.pause();
    if (phaseRef.current === "listening") recognition.pauseListening();
    setPhaseBoth("paused");
    send({ type: "pause_requested" });
  }, [synthesis, recognition, send, setPhaseBoth]);

  const resume = useCallback(() => {
    send({ type: "resume_requested" });
    if (prePauseSubPhaseRef.current === "composing") {
      // Nothing to restart — the draft was never captured anywhere but the
      // candidate's own text field, which kept its contents across the pause.
      setPhaseBoth("composing");
    } else if (prePauseSubPhaseRef.current === "listening") {
      setPhaseBoth("listening");
      recognition.resumeListening();
    } else {
      setPhaseBoth("ai_speaking");
      synthesis.resume();
    }
  }, [send, recognition, synthesis, setPhaseBoth]);

  /**
   * Submit a typed answer (sign mode).
   *
   * The signed counterpart of the recogniser's `onTurnComplete`, and it sends the
   * identical `submit_answer` frame — the server cannot tell the two apart, which
   * is what makes the engine, the follow-up logic and the rubric genuinely shared
   * rather than parallel implementations.
   */
  const submitComposedAnswer = useCallback(
    (text: string) => {
      if (!currentQuestionIdRef.current) return;
      const trimmed = text.trim();
      sendSignals();
      send({
        type: "submit_answer",
        questionId: currentQuestionIdRef.current,
        transcriptText: trimmed.length > 0 ? trimmed : null,
        isSkipped: false,
        // Null, not 1.0. A typed answer is not a perfectly recognised one, it is
        // an unrecognised one — no recogniser ran, so there is no confidence to
        // report, and claiming certainty would be inventing a measurement.
        asrConfidenceAvg: null,
        // No speech, so no speaking span. Costs nothing: pace is not a term of a
        // signed session's score (see `applicable_components` in
        // `transcript_signals.py`).
        answerStartedAt: null,
        answerEndedAt: null,
      });
      setCaptionText("");
    },
    [send, sendSignals],
  );

  /**
   * "I've finished answering."
   *
   * Ends the turn on the candidate's word rather than on a silence timer, and
   * exists because the timer is a guess about a human being. Even at a generous
   * 2.6s it can only ever be a guess: some people pause four seconds mid-answer
   * and some stop dead at the end of a sentence, and no single number serves
   * both. This makes the guess a fallback rather than the mechanism.
   *
   * It goes through the recogniser rather than sending the answer directly, so
   * whatever was captured -- including a final result still in flight -- is
   * submitted by the same path as an automatic finish. One code path, one set
   * of behaviours.
   */
  const finishAnswer = useCallback(() => {
    if (!currentQuestionIdRef.current) return;
    if (phaseRef.current !== "listening") return;
    recognition.finishAnswer();
  }, [recognition]);

  const skip = useCallback(() => {
    if (!currentQuestionIdRef.current) return;
    if (phaseRef.current === "listening") recognition.cancel();
    if (phaseRef.current === "ai_speaking") synthesis.cancel();
    // Discarded, not sent: a skip has no answer, so it has no speaking span.
    takeAnswerTiming();
    sendSignals();
    send({
      type: "submit_answer",
      questionId: currentQuestionIdRef.current,
      transcriptText: null,
      isSkipped: true,
      asrConfidenceAvg: null,
      answerStartedAt: null,
      answerEndedAt: null,
    });
    setCaptionText("");
  }, [send, recognition, synthesis, sendSignals, takeAnswerTiming]);

  const endInterview = useCallback(() => {
    intentionalCloseRef.current = true;
    recognition.cancel();
    synthesis.cancel();
    // The last chance to record signals over this socket: `end_requested` ends
    // the session, closes the connection and starts report generation.
    sendSignals();
    send({ type: "end_requested" });
  }, [send, recognition, synthesis, sendSignals]);

  return {
    phase,
    questionText,
    sequenceOrder,
    totalQuestions,
    captionText,
    elapsedSeconds,
    totalSeconds,
    isMuted,
    isAiSpeaking: synthesis.isSpeaking,
    asrLowConfidence: recognition.lowConfidence,
    isFollowup,
    plannedRemaining,
    endReason,
    errorMessage,
    // Exposed for the REST end path only (the "End Interview Now" button on the
    // error screen), where the socket is already gone and the final aggregates
    // have to go over HTTP instead.
    measureProsody: measure,
    measureExpression,
    // Whether video analysis is running, and if not, why. The report is the place
    // that says body language was unmeasured; this is here so the live screen can
    // tell the candidate while they can still do something about it.
    expressionStatus,
    usingHttpFallback,
    signMode,
    actions: { toggleMute, pause, resume, skip, finishAnswer, endInterview, submitComposedAnswer, shareCodePanel },
  };
}

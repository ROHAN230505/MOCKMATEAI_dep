import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Card } from "../components/ui/Card";
import { Button } from "../components/ui/Button";
import { Checkbox } from "../components/ui/Checkbox";
import { Banner } from "../components/ui/Banner";
import { PageHeader } from "../components/ui/PageHeader";
import { useMicLevel } from "../hooks/useMicLevel";
import { isSpeechRecognitionSupported } from "../hooks/useSpeechRecognition";
import { isSpeechSynthesisSupported } from "../hooks/useSpeechSynthesis";
import { SpeechLanguagePicker } from "../components/interview/SpeechLanguagePicker";
import { useInterviewSetupStore } from "../store/interviewSetupStore";
import { startInterview } from "../services/interviewApi";
import { ApiError } from "../lib/apiClient";

/**
 * A device status row. The state is carried by an icon *and* a colour, so it
 * survives for anyone who can't distinguish red from green (Section 17).
 */
function StatusRow({ ok, label, detail }: { ok: boolean; label: string; detail: string }) {
  return (
    <div className="flex items-center gap-3">
      <span
        aria-hidden="true"
        className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full border ${
          ok ? "border-success/40 bg-success/12 text-success" : "border-danger/40 bg-danger/12 text-danger"
        }`}
      >
        <svg viewBox="0 0 24 24" className="h-3.5 w-3.5" fill="none" stroke="currentColor" strokeWidth="2.4">
          {ok ? (
            <path strokeLinecap="round" strokeLinejoin="round" d="m5 13 4 4L19 7" />
          ) : (
            <path strokeLinecap="round" d="M6 6l12 12M18 6 6 18" />
          )}
        </svg>
      </span>
      <span className="text-sm text-text">
        {label} <span className="text-text-muted">{detail}</span>
      </span>
    </div>
  );
}

/** Segmented mic meter — reads as a level, not as a progress bar toward a goal. */
function MicMeter({ level }: { level: number }) {
  const segments = 24;
  const active = Math.round(Math.max(0, Math.min(1, level)) * segments);

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium text-text-muted">Microphone level</span>
        <span className="text-xs text-text-subtle">Say something to test it</span>
      </div>
      <div className="flex h-6 items-end gap-[3px]" role="meter" aria-valuemin={0} aria-valuemax={100} aria-valuenow={Math.round(level * 100)} aria-label="Microphone level">
        {Array.from({ length: segments }).map((_, index) => {
          const on = index < active;
          // Bars rise toward the middle of the meter so a quiet room reads as
          // a flat floor rather than a broken control.
          const height = 35 + Math.sin((index / segments) * Math.PI) * 65;
          return (
            <span
              key={index}
              aria-hidden="true"
              className={`flex-1 rounded-[2px] transition-colors duration-75 ${
                on ? (index > segments * 0.85 ? "bg-warning" : "bg-accent") : "bg-surface-raised"
              }`}
              style={{ height: `${height}%` }}
            />
          );
        })}
      </div>
    </div>
  );
}

export function InterviewPrecheck() {
  const navigate = useNavigate();
  const setup = useInterviewSetupStore();
  const videoRef = useRef<HTMLVideoElement>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameraOk, setCameraOk] = useState(false);
  const [micOk, setMicOk] = useState(false);
  const [deviceError, setDeviceError] = useState<string | null>(null);
  const [consentGiven, setConsentGiven] = useState(false);
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);

  // A signed interview never speaks or listens, so it needs neither the Web
  // Speech API nor a microphone. Asking for a mic we will not use is not a
  // harmless default -- it is a permission prompt with nothing behind it, and a
  // "Microphone: not detected" row that blocks a candidate from starting an
  // interview their microphone plays no part in.
  const signMode = setup.mode === "sign";
  const speechSupported = signMode || (isSpeechRecognitionSupported() && isSpeechSynthesisSupported());
  const micLevel = useMicLevel(signMode ? null : stream);

  async function runDeviceCheck() {
    setDeviceError(null);
    try {
      const media = await navigator.mediaDevices.getUserMedia({
        video: true,
        audio: !signMode,
      });
      streamRef.current = media;
      setStream(media);
      setCameraOk(media.getVideoTracks().length > 0);
      setMicOk(media.getAudioTracks().length > 0);
      if (videoRef.current) videoRef.current.srcObject = media;
    } catch {
      setCameraOk(false);
      setMicOk(false);
      setDeviceError(
        signMode
          ? "Couldn't access your camera. Check your browser permissions and try again."
          : "Couldn't access your camera/microphone. Check your browser permissions and try again.",
      );
    }
  }

  useEffect(() => {
    runDeviceCheck();
    return () => {
      // Reads the ref, not the `stream` state closed over at mount time —
      // getUserMedia resolves asynchronously, so the state value here
      // would otherwise still be the initial `null`.
      streamRef.current?.getTracks().forEach((track) => track.stop());
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleBegin() {
    setStartError(null);
    setStarting(true);
    try {
      const result = await startInterview({
        role: setup.role,
        type: setup.type,
        durationMinutes: setup.durationMinutes,
        mode: setup.mode,
        consentGiven,
        // Section 4.6 — sent once at session start and never re-uploaded
        // mid-interview. Omitted entirely when blank so the backend's
        // "is a JD present?" branch stays a simple truthiness check.
        jobDescriptionText: setup.jobDescriptionText.trim() || undefined,
        targetCompanyName: setup.targetCompanyName.trim() || undefined,
      });
      stream?.getTracks().forEach((track) => track.stop());
      navigate(`/interview/live/${result.sessionId}`);
    } catch (err) {
      setStartError(err instanceof ApiError ? err.message : "Couldn't start the interview. Please try again.");
      setStarting(false);
    }
  }

  const canBegin = cameraOk && (signMode || micOk) && consentGiven && speechSupported && !starting;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-4">
      <PageHeader
        eyebrow="Step 2 of 2"
        title={signMode ? "Camera check" : "Camera & microphone check"}
        description={
          signMode
            ? "Make sure you can be seen clearly before we begin."
            : "Make sure you can be seen and heard before we begin."
        }
      />

      <Card className="flex flex-col gap-4">
        <div className="relative overflow-hidden rounded-control border border-border bg-black">
          <video ref={videoRef} autoPlay muted playsInline className="aspect-video w-full object-cover" />
          {!cameraOk && (
            <div className="absolute inset-0 flex flex-col items-center justify-center gap-2 bg-surface-sunken text-center">
              <svg
                viewBox="0 0 24 24"
                className="h-7 w-7 text-text-subtle"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.6"
                aria-hidden="true"
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5V7a1 1 0 0 0-1-1H4a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h10a1 1 0 0 0 1-1v-3.5l6 4.5v-12z" />
                <path strokeLinecap="round" d="M3 3l18 18" />
              </svg>
              <p className="text-sm text-text-muted">Waiting for camera access…</p>
            </div>
          )}
          {/* Live badge, so it's obvious this is a preview and not a recording. */}
          {cameraOk && (
            <span className="absolute top-3 left-3 inline-flex items-center gap-1.5 rounded-pill bg-black/55 px-2.5 py-1 text-xs font-medium text-white backdrop-blur-sm">
              <span aria-hidden="true" className="h-1.5 w-1.5 rounded-full bg-danger" />
              Preview
            </span>
          )}
        </div>

        {!signMode && <MicMeter level={micLevel} />}

        {!signMode && (
          <>
            <div className="rule-fade" />
            <SpeechLanguagePicker />
          </>
        )}

        {deviceError && (
          <div className="flex flex-col gap-3">
            <Banner tone="error">{deviceError}</Banner>
            <Button variant="secondary" size="sm" onClick={runDeviceCheck} className="self-start">
              Test Again
            </Button>
          </div>
        )}

        <div className="rule-fade" />

        <div className="grid gap-3 sm:grid-cols-2">
          <StatusRow ok={cameraOk} label="Camera" detail={cameraOk ? "detected" : "not detected"} />
          {!signMode && (
            <StatusRow ok={micOk} label="Microphone" detail={micOk ? "detected" : "not detected"} />
          )}
        </div>

        {signMode && (
          <Banner tone="info" title="How a signed interview works">
            Each question appears on screen — nothing is spoken aloud, so no audio is captured. You type
            your answer and submit it when you're ready, and there's no timer on any single answer. Your
            camera stays on for the body-language part of your feedback.
          </Banner>
        )}

        {!speechSupported && !signMode && (
          <Banner tone="error" title="Unsupported browser">
            Your browser doesn't support the speech features this interview needs. Please switch to Chrome or
            Edge.
          </Banner>
        )}
      </Card>

      <Card className="flex flex-col gap-5">
        <details className="group">
          <summary className="flex cursor-pointer list-none items-center justify-between gap-3 text-sm font-medium text-text">
            What we record and why
            <span
              aria-hidden="true"
              className="text-text-subtle transition-transform duration-300 group-open:rotate-180"
            >
              <svg viewBox="0 0 24 24" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
                <path strokeLinecap="round" strokeLinejoin="round" d="m6 9 6 6 6-6" />
              </svg>
            </span>
          </summary>
          <div className="mt-3 space-y-2.5 border-l-2 border-border pl-4 text-sm leading-relaxed text-text-muted">
            <p>
              While you're in the live interview, your browser converts your speech to text locally using its
              built-in speech recognition — for most browsers (including Chrome), this sends your audio to that
              browser vendor's own servers to do the transcription, not ours.
            </p>
            <p>
              We store the resulting text transcript of your answers. We do not record or store audio or video
              in this version of MockMateAI.
            </p>
            <p>
              Only you can see your own transcripts. You can delete your account and all associated data at any
              time from Settings.
            </p>
          </div>
        </details>

        <Checkbox
          label="I consent to my speech being processed for this session as described above."
          checked={consentGiven}
          onChange={(e) => setConsentGiven(e.target.checked)}
        />
      </Card>

      {startError && <Banner tone="error">{startError}</Banner>}

      <div className="sticky bottom-4 z-10">
        <div className="rounded-card border border-border bg-surface p-2">
          <Button variant="primary" size="lg" fullWidth loading={starting} disabled={!canBegin} onClick={handleBegin}>
            Begin Interview
          </Button>
          {!canBegin && !starting && (
            <p className="mt-2.5 text-center text-xs text-text-subtle">
              {!speechSupported
                ? "Switch to Chrome or Edge to continue."
                : !cameraOk || !micOk
                  ? "Grant camera and microphone access to continue."
                  : "Give consent above to continue."}
            </p>
          )}
        </div>
      </div>
    </div>
  );
}

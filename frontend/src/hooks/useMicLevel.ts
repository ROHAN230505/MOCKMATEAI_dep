import { useEffect, useRef, useState } from "react";

/**
 * Real-time mic amplitude (0-1ish RMS) from a live MediaStream, via the Web
 * Audio API's AnalyserNode. Drives both the precheck mic-level bar (Section
 * 4.7) and, thresholded by the caller, barge-in voice-activity detection
 * during AI_SPEAKING (Section 4.8A) — same primitive, two consumers.
 */
export function useMicLevel(stream: MediaStream | null): number {
  const [level, setLevel] = useState(0);
  const frameRef = useRef<number>(0);

  useEffect(() => {
    if (!stream) {
      setLevel(0);
      return;
    }

    const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    const audioContext = new AudioCtx();
    const source = audioContext.createMediaStreamSource(stream);
    const analyser = audioContext.createAnalyser();
    analyser.fftSize = 512;
    source.connect(analyser);

    const buffer = new Uint8Array(analyser.frequencyBinCount);

    const tick = () => {
      analyser.getByteTimeDomainData(buffer);
      let sumSquares = 0;
      for (let i = 0; i < buffer.length; i++) {
        const normalized = (buffer[i] - 128) / 128;
        sumSquares += normalized * normalized;
      }
      const rms = Math.sqrt(sumSquares / buffer.length);
      setLevel(Math.min(1, rms * 4)); // scaled up — raw RMS from quiet mics reads very low
      frameRef.current = requestAnimationFrame(tick);
    };
    frameRef.current = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(frameRef.current);
      source.disconnect();
      analyser.disconnect();
      audioContext.close().catch(() => {});
    };
  }, [stream]);

  return level;
}

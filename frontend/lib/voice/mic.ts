"use client";

// The microphone side of the voice agent: open the mic, keep a live loudness for the orb, and record one question
// until the person stops talking. The recording goes to ElevenLabs Scribe, which works in every browser.

// Config
const SPEAKING_LEVEL = 0.04; // loudness that counts as speech; low, because noise suppression makes quiet voices quieter
const SILENCE_AFTER_SPEECH_MS = 1100; // this much quiet after speaking ends the question; past a breath, so the last word is not cut off
const WAIT_FOR_SPEECH_MS = 7000; // give up if nothing is said
const LONGEST_QUESTION_MS = 20000;

export type Level = { current: number };
export type Mic = { stream: MediaStream; stop: () => void };

export const canRecord = () => typeof window !== "undefined" && typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

/** Opens the mic and keeps `level` at its loudness (0 to 1). Null when the mic is blocked. */
export async function openMic(level: Level): Promise<Mic | null> {
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
    const context = new AudioContext();
    const analyser = context.createAnalyser();
    analyser.fftSize = 512;
    context.createMediaStreamSource(stream).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (const v of samples) sum += ((v - 128) / 128) ** 2;
      level.current = Math.min(1, Math.sqrt(sum / samples.length) * 4);
      frame = requestAnimationFrame(tick);
    };
    tick();
    const stop = () => {
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((track) => track.stop());
      void context.close();
      level.current = 0;
    };
    return { stream, stop };
  } catch {
    return null;
  }
}

export type Recording = { stop: () => void; done: Promise<Blob | null> };

/** Records until the person stops talking, or with `untilStopped` (a held key) until stop(). Resolves null when nothing was said. */
export function recordQuestion(mic: Mic, level: Level, untilStopped = false): Recording {
  const chunks: Blob[] = [];
  const recorder = new MediaRecorder(mic.stream);
  recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  const startedAt = performance.now();
  let spoke = false;
  let loudAt = startedAt;
  const watch = setInterval(() => {
    const now = performance.now();
    if (level.current > SPEAKING_LEVEL) {
      spoke = true;
      loudAt = now;
    }
    const finished = !untilStopped && (spoke ? now - loudAt > SILENCE_AFTER_SPEECH_MS : now - startedAt > WAIT_FOR_SPEECH_MS);
    if (finished || now - startedAt > LONGEST_QUESTION_MS) stop();
  }, 100);
  const done = new Promise<Blob | null>((resolve) => {
    recorder.onstop = () => {
      clearInterval(watch);
      mic.stop();
      resolve(spoke ? new Blob(chunks, { type: recorder.mimeType || "audio/webm" }) : null);
    };
  });
  function stop() {
    if (recorder.state === "recording") recorder.stop();
  }
  recorder.start();
  return { stop, done };
}

/** Sends the recording to ElevenLabs through our server route and returns the words. */
export async function transcribe(audio: Blob, signal?: AbortSignal): Promise<string> {
  const res = await fetch("/api/voice/listen", { method: "POST", headers: { "Content-Type": audio.type }, body: audio, signal });
  const data = (await res.json()) as { text?: string; error?: string };
  if (!res.ok) throw new Error(data.error ?? "Voice failed.");
  return (data.text ?? "").trim();
}

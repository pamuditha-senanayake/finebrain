"use client";

// pcm.ts: the raw speech ElevenLabs sends (16-bit mono PCM at 24 kHz), how it becomes playable audio, and its loudness.
// Used by: lib/voice/speaker.ts. Uses: app/api/voice/speak (through fetch).
import type { Level } from "./mic";

// Config
const SAMPLE_RATE = 24000; // matches SPEAK_FORMAT in elevenlabs.ts

/** Little-endian 16-bit samples to an audio buffer. */
export function toBuffer(ctx: AudioContext, bytes: Uint8Array): AudioBuffer {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const buffer = ctx.createBuffer(1, bytes.byteLength / 2, SAMPLE_RATE);
  const samples = buffer.getChannelData(0);
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 32768;
  return buffer;
}

/** Glues the downloaded pieces into one run of bytes. */
export function joined(parts: Uint8Array[]): Uint8Array {
  const all = new Uint8Array(parts.reduce((sum, part) => sum + part.byteLength, 0));
  let at = 0;
  for (const part of parts) {
    all.set(part, at);
    at += part.byteLength;
  }
  return all;
}

/** Fetches the spoken text as one stream of PCM. Throws when ElevenLabs cannot speak. */
export async function fetchSpeech(text: string, signal?: AbortSignal): Promise<ReadableStreamDefaultReader<Uint8Array>> {
  const res = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal });
  if (!res.ok || !res.body) throw new Error("speak failed");
  return res.body.getReader();
}

/** Keeps `level` at the reply's real loudness, so the orb moves with the voice. */
export function meter(ctx: AudioContext, level: Level): { input: AnalyserNode; stop: () => void } {
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.connect(ctx.destination);
  const samples = new Uint8Array(analyser.fftSize);
  let frame = 0;
  const tick = () => {
    analyser.getByteTimeDomainData(samples);
    let sum = 0;
    for (const v of samples) sum += ((v - 128) / 128) ** 2;
    level.current = Math.min(1, Math.sqrt(sum / samples.length) * 5);
    frame = requestAnimationFrame(tick);
  };
  tick();
  return { input: analyser, stop: () => (cancelAnimationFrame(frame), (level.current = 0)) };
}

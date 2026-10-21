"use client";

// The speaking side of the voice agent. Browsers only allow sound that starts right after a tap, but the answer
// arrives seconds later. So one audio context is unlocked on the tap, and every reply plays through it.
import type { Level } from "./mic";

let context: AudioContext | null = null;

/** Call inside a tap or click, before any await. Safe to call many times. */
export function unlockAudio() {
  if (typeof window === "undefined") return;
  context ??= new AudioContext();
  void context.resume();
  const blank = context.createBufferSource(); // a silent sample finishes the unlock on Safari
  blank.buffer = context.createBuffer(1, 1, 22050);
  blank.connect(context.destination);
  blank.start(0);
}

export type Playback = { stop: () => void; done: Promise<void> };

/** Speaks `text` with the ElevenLabs voice; `level` follows the real loudness so the orb moves with it. */
export async function speak(text: string, level: Level, signal?: AbortSignal): Promise<Playback> {
  const res = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text }), signal });
  if (!res.ok) throw new Error("speak failed");
  unlockAudio();
  const ctx = context!;
  const buffer = await ctx.decodeAudioData(await res.arrayBuffer());
  // The turn may have been cancelled while the audio downloaded; a stale reply must stay silent.
  signal?.throwIfAborted();
  const source = ctx.createBufferSource();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  source.buffer = buffer;
  source.connect(analyser);
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
  const done = new Promise<void>((resolve) => {
    source.onended = () => {
      cancelAnimationFrame(frame);
      level.current = 0;
      resolve();
    };
  });
  source.start();
  tick();
  return { stop: () => source.stop(), done };
}

/** The first two sentences: what is shown and spoken first. The rest waits behind "More". */
export function shortOf(answer: string): { short: string; rest: string } {
  const parts = answer.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [answer];
  const short = parts.slice(0, 2).join("").trim();
  return { short, rest: answer.slice(short.length).trim() };
}

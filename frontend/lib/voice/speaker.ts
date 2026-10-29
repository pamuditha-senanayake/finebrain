"use client";

// The speaking side of the voice agent. Sound is only allowed right after a tap, so one audio context is unlocked on
// the tap and every reply plays through it, as raw PCM, while it downloads.
import type { Level } from "./mic";
import { fetchSpeech, joined, meter, toBuffer } from "./pcm";

// Config
const BYTES_PER_SECOND = 48000; // 24 kHz 16-bit mono, as pcm.ts plays it
const SPOKEN_CHARS_PER_SECOND = 16; // a little faster than the voice really speaks, so the length guess errs towards waiting
const FIRST_PIECE_BYTES = 14400; // start with 0.3 s in hand: sooner sound, still enough to cover the next chunk
const MIN_CHUNK_BYTES = 9600; // about 0.2 s of speech per queued piece after that
// Said the moment a spoken question is understood, so the wait feels shorter. Never the same one twice in a row.
const CUES = ["Let me check.", "One moment.", "Looking into it.", "Sure, one second.", "Let me look.", "On it.", "Checking now."];

let context: AudioContext | null = null;
let cues: AudioBuffer[] = [];
let cuesAsked = false;
let cuePlaying: AudioBufferSourceNode | null = null;
let lastCue = -1;

/** Call inside a tap or click, before any await. Safe to call many times. */
export function unlockAudio() {
  if (typeof window === "undefined") return;
  context ??= new AudioContext();
  void context.resume();
  const blank = context.createBufferSource(); // a silent sample finishes the unlock on Safari
  blank.buffer = context.createBuffer(1, 1, 22050);
  blank.connect(context.destination);
  blank.start(0);
  if (!cuesAsked) void prepareCues();
}

export type Playback = { stop: () => void; done: Promise<void> };

/** Speaks `text` with the ElevenLabs voice, starting with the first chunk. Throws only if nothing could be played. */
export async function speak(text: string, level: Level, signal?: AbortSignal): Promise<Playback> {
  stopCue();
  const reader = await fetchSpeech(text, signal);
  unlockAudio();
  const ctx = context!;
  const sound = meter(ctx, level);
  const queued: AudioBufferSourceNode[] = [];
  let startAt = 0;
  let stopped = false;
  let carry: Uint8Array[] = [];
  let firstByteAt: number | undefined;

  // Step 1: each piece plays right after the one before; a late piece starts as soon as it lands
  function queue(bytes: Uint8Array) {
    const even = bytes.subarray(0, bytes.byteLength - (bytes.byteLength % 2));
    carry = even.byteLength < bytes.byteLength ? [bytes.subarray(even.byteLength)] : [];
    const source = ctx.createBufferSource();
    source.buffer = toBuffer(ctx, even);
    source.connect(sound.input);
    startAt = Math.max(startAt, ctx.currentTime + 0.03);
    source.start(startAt);
    startAt += source.buffer.duration;
    queued.push(source);
  }

  // Step 2: read until a piece is big enough, so errors before any sound still throw to the caller
  async function readPiece(enough: (size: number) => boolean = (size) => size >= MIN_CHUNK_BYTES): Promise<boolean> {
    const parts = [...carry];
    let size = parts.reduce((sum, part) => sum + part.byteLength, 0);
    while (!enough(size)) {
      const { done, value } = await reader.read();
      if (done) break;
      firstByteAt ??= performance.now();
      parts.push(value);
      size += value.byteLength;
    }
    if (size < 2) return false;
    queue(joined(parts));
    return true;
  }

  // Step 3: start once the rest, at its arrival speed, lands before the voice needs it (ElevenLabs is sometimes slower than speech)
  const expectedBytes = (text.length / SPOKEN_CHARS_PER_SECOND) * BYTES_PER_SECOND;
  const readyToStart = (size: number) => {
    if (size < FIRST_PIECE_BYTES || firstByteAt === undefined) return false;
    const rate = size / Math.max((performance.now() - firstByteAt) / 1000, 0.05);
    return (expectedBytes - size) / rate <= expectedBytes / BYTES_PER_SECOND;
  };
  if (!(await readPiece(readyToStart))) throw (sound.stop(), new Error("no speech"));

  const stop = () => {
    stopped = true;
    void reader.cancel().catch(() => {});
    for (const source of queued) source.stop();
    sound.stop();
  };
  // A turn cancelled while the reply still downloads silences it; once downloaded, the caller's stop does.
  signal?.addEventListener("abort", stop);

  // Step 4: the rest streams in behind the first piece; done resolves when the last piece has played
  const done = (async () => {
    try {
      while (!stopped && (await readPiece()));
      signal?.removeEventListener("abort", stop);
      if (!stopped) await new Promise<void>((resolve) => ((queued[queued.length - 1].onended = () => resolve())));
    } catch {
      // A cancelled turn or a dropped stream ends the reply where it is.
    }
    sound.stop();
  })();

  return { stop, done };
}

// --- The cue

/** Fetches the cue phrases once, in the background. A failure is quiet; the next tap tries again. */
async function prepareCues() {
  cuesAsked = true;
  try {
    const ctx = context!;
    cues = await Promise.all(CUES.map(async (cue) => {
      const reader = await fetchSpeech(cue);
      const parts: Uint8Array[] = [];
      for (let read = await reader.read(); !read.done; read = await reader.read()) parts.push(read.value);
      const all = joined(parts);
      return toBuffer(ctx, all.subarray(0, all.byteLength - (all.byteLength % 2)));
    }));
  } catch {
    cuesAsked = false;
  }
}

/** Says a short cue like "Let me check", picked at random but never the last one. Silent when the cues are not ready yet. */
export function playCue() {
  if (!context || cues.length === 0) return;
  stopCue();
  const pick = cues.length < 2 ? 0 : (lastCue + 1 + Math.floor(Math.random() * (cues.length - 1))) % cues.length;
  lastCue = pick;
  const source = context.createBufferSource();
  source.buffer = cues[pick];
  source.connect(context.destination);
  source.start();
  cuePlaying = source;
}

function stopCue() {
  cuePlaying?.stop();
  cuePlaying = null;
}

/** The first two sentences: what is shown and spoken first. The rest waits behind "More". */
export function shortOf(answer: string): { short: string; rest: string } {
  const parts = answer.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [answer];
  const short = parts.slice(0, 2).join("").trim();
  return { short, rest: answer.slice(short.length).trim() };
}

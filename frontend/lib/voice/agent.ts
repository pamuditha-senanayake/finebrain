"use client";

// agent.ts: Lisena's voice, one for the whole app. It lives outside React, so going to another page never cuts a reply
// off or drops the chat; the orb on every page and the Lisena page are two views of the same agent.
// Used by: components/shell/ask-orb.tsx, ask-bubble.tsx, voice-settings.tsx, features/l1/ask-voice.tsx.
// Uses: mic.ts, speaker.ts, turn.ts, intake-chat.ts, lib/api/conversation.ts, lib/page-snapshot.ts.
// One file on purpose: the turn, the recording and the playback must be shared by every step, so splitting would mean passing them around.
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { AskAnswer } from "@/contracts";
import type { VoiceState } from "@/features/l1/voice-orb";
import { askNow, fixHeard } from "@/lib/api/conversation";
import { snapshotPage } from "@/lib/page-snapshot";
import { forgetIntake, intakeReply, intakeStart, takesOver, type ChatAnswer } from "./intake-chat";
import { canRecord, openMic, recordQuestion, transcribe, type Recording } from "./mic";
import { playCue, shortOf, speak, unlockAudio } from "./speaker";
import { endTurn, failureNote, isOffline, OFFLINE, startTurn, stepSignal, type Turn, type TurnKeeper } from "./turn";

// Config
const KEEP = 20; // exchanges kept on screen; the full history is on the Lisena page
const ASK_PAGE = "/l1/ask"; // asks about the whole system; every other page asks about what is on screen
const SMALL_TALK = /^(hi|hello|hey|thanks|thank you|cheers|bye|goodbye|good (morning|afternoon|evening|night)|how are you)\b/i; // no cue before these
const SMALL_TALK_WORDS = 6;
const MIC_BLOCKED = "The microphone is blocked, sir. Allow it in the browser, or type instead.";
const FIX_TIME_LIMIT_MS = 3000; // fixing misheard words must stay quick; past this the words go on as heard

export type Exchange = { id: number; q: string; a: ChatAnswer | null };
type Settings = { handsFree: boolean; editFirst: boolean; speakOut: boolean };
type Live = { voice: VoiceState; heard: string; note: string; draft: string; items: Exchange[] };

/** How the person likes to talk, kept across visits. */
export const useVoiceSettings = create<Settings & { change: (s: Partial<Settings>) => void }>()(
  persist((set) => ({ handsFree: false, editFirst: false, speakOut: true, change: (s) => set(s) }), { name: "cb.voice.v1", storage: createJSONStorage(() => localStorage) }),
);

/** What is happening right now: listening, the words heard, the chat. Not kept across reloads. */
export const useVoice = create<Live>()(() => ({ voice: "idle", heard: "", note: "", draft: "", items: [] }));

export const level = { current: 0 }; // live loudness for the orb, read every frame
const turn: TurnKeeper = { current: null };
let recording: Recording | null = null;
let stopSoon = false; // the key was let go before the mic opened
let playback: { stop: () => void } | null = null;
let seq = 0;
let route: ((q: string) => string | null) | null = null;
let pageNames: string[] = []; // the pages this person may open, so a misheard page name can be fixed

const patch = (p: Partial<Live>) => useVoice.setState(p);
const settings = () => useVoiceSettings.getState();

/** The shell tells the agent how to open a page and which pages there are, so "go to the library" works from any spoken question. */
export function setRoute(fn: (q: string) => string | null, pages: string[]) {
  route = fn;
  pageNames = pages;
}

export const setDraft = (draft: string) => patch({ draft });

// --- Talking

/** The orb's tap: stop speaking, stop listening, or start listening. */
export function tap() {
  const { voice } = useVoice.getState();
  if (voice === "listening") return stopListening();
  if (voice === "speaking" || voice === "thinking") return stopAll();
  void listen();
}

/** Ends a held-key question, or a question the person wants to finish early. */
export function stopListening() {
  if (recording) recording.stop();
  else stopSoon = true;
}

/** Stops everything, which also ends hands-free until the next tap. */
export function stopAll() {
  endTurn(turn);
  recording?.stop();
  stopSpeaking();
  patch({ voice: "idle" });
}

/** Records one question, turns it into words, then asks it (or, with "edit first", puts it in the box). */
export async function listen(hold = false) {
  unlockAudio();
  stopSpeaking();
  if (isOffline()) return patch({ note: OFFLINE, voice: "idle" });
  if (!canRecord()) return patch({ note: "Voice is not available in this browser, sir. Please type." });
  const now = startTurn(turn);
  patch({ voice: "listening", note: "", heard: "" });
  // Step 1: record until a pause, or until the key is let go
  const audio = await record(now, hold);
  if (!now.isCurrent() || audio === "blocked") return;
  if (!audio) return patch({ voice: "idle", note: settings().handsFree ? "Hands-free paused. Tap to talk again." : "I did not hear anything, sir. Tap and speak again." });
  // Step 2: the words
  patch({ voice: "thinking" });
  let words = "";
  try {
    words = await transcribe(audio, stepSignal(now));
  } catch (e) {
    if (now.isCurrent()) patch({ voice: "idle", note: failureNote(e, "I could not make that out, sir. Try again, or type.") });
    return;
  }
  if (!now.isCurrent()) return;
  if (!words) return patch({ voice: "idle", note: "I could not make that out, sir. Try again, or type." });
  patch({ heard: words });
  words = await fixHeard(words, pageNames, recentQuestions(), AbortSignal.any([now.signal, AbortSignal.timeout(FIX_TIME_LIMIT_MS)]));
  if (!now.isCurrent()) return;
  // Step 3: edit first puts the words in the box; otherwise ask at once, with a short cue unless it is small talk
  if (settings().editFirst) return patch({ voice: "idle", draft: [useVoice.getState().draft.trim(), words].filter(Boolean).join(" ") });
  if (!isSmallTalk(words)) playCue();
  void send(words, { speak: true, listenAfter: true });
}

async function record(now: Turn, hold: boolean): Promise<Blob | null | "blocked"> {
  stopSoon = false;
  const mic = await openMic(level);
  if (!mic) return patch({ note: MIC_BLOCKED, voice: "idle" }), "blocked";
  if (!now.isCurrent()) return mic.stop(), null;
  const take = recordQuestion(mic, level, hold);
  recording = take;
  if (stopSoon) take.stop();
  const audio = await take.done;
  if (recording === take) recording = null;
  return audio;
}

/** The last two questions, so "show me his runs" can be heard against what was just asked. */
const recentQuestions = () => useVoice.getState().items.slice(-2).map((x) => x.q);

const isSmallTalk = (words: string) => words.split(/\s+/).length <= SMALL_TALK_WORDS && SMALL_TALK.test(words.trim());

// --- Asking

/** Asks one question. `speak` reads the answer aloud (if spoken replies are on); `listenAfter` keeps hands-free going. */
export async function send(question: string, { speak: spoken = false, listenAfter = false } = {}) {
  const q = question.trim();
  if (!q) return;
  unlockAudio();
  stopSpeaking();
  const now = startTurn(turn);
  const id = ++seq;
  patch({ note: "", heard: q });
  // Step 1: adding a document is a talk of its own (intake-chat.ts); every reply goes there until it is filed or stopped
  if (takesOver(q)) return intakeTurn(id, q, () => intakeReply(q), now, spoken, listenAfter);
  // Step 2: "go to the library" opens it; no model call
  const opened = route?.(q);
  if (opened) return addExchange({ id, q, a: { question: q, answer: `Opening ${opened}.`, citations: [], withheld: 0 } }), patch({ voice: "idle" });
  if (isOffline()) return patch({ note: OFFLINE, voice: "idle" });
  // Step 3: ask, with what is on screen
  addExchange({ id, q, a: null });
  patch({ voice: "thinking" });
  let answer: AskAnswer;
  try {
    answer = await askNow({ question: q, page: pageNow(), signal: stepSignal(now) });
  } catch (e) {
    patch({ items: useVoice.getState().items.filter((x) => x.id !== id) });
    if (now.isCurrent()) patch({ voice: "idle", note: failureNote(e, "The brain could not answer, sir. Please try again.") });
    return;
  }
  // A newer question took over while this one waited; its answer is dropped, not shown or spoken
  if (!now.isCurrent()) return patch({ items: useVoice.getState().items.filter((x) => x.id !== id) });
  patch({ items: useVoice.getState().items.map((x) => (x.id === id ? { ...x, a: answer } : x)) });
  // Step 4: speak it, then listen again when hands-free is on
  if (spoken && settings().speakOut) await say(shortOf(answer.answer).short, now);
  if (!now.isCurrent()) return;
  patch({ voice: "idle" });
  if (listenAfter && settings().handsFree && !settings().editFirst) void listen();
}

/** Attaching a file in the chat starts adding it; Lisena reads it and asks her first question. */
export function attach(file: File) {
  unlockAudio();
  stopSpeaking();
  return intakeTurn(++seq, `Attached ${file.name}`, () => intakeStart(file), startTurn(turn), true, false);
}

/** One intake exchange: show it thinking, put Lisena's words in, speak them, and keep listening when hands-free is on. */
async function intakeTurn(id: number, q: string, reply: () => Promise<ChatAnswer>, now: Turn, spoken: boolean, listenAfter: boolean) {
  addExchange({ id, q, a: null });
  patch({ voice: "thinking", note: "" });
  let a: ChatAnswer;
  try {
    a = await reply();
  } catch (e) {
    patch({ items: useVoice.getState().items.filter((x) => x.id !== id) });
    const reason = e instanceof Error ? e.message : "";
    const why = reason === "too_large" ? "That file is over 10 MB, sir." : reason.startsWith("unsupported_type") ? "I can read text, Markdown, CSV, PDF and Word files, sir." : reason === "intake_paused" ? "Adding documents is paused in Workflow Studio, sir." : reason === "not_found" ? "That upload has ended, sir. Attach the file again." : "";
    if (reason === "not_found") forgetIntake();
    if (now.isCurrent()) patch({ voice: "idle", note: why || failureNote(e, "I could not do that, sir. Please try again.") });
    return;
  }
  if (!now.isCurrent()) return;
  patch({ items: useVoice.getState().items.map((x) => (x.id === id ? { ...x, a } : x)) });
  if (spoken && settings().speakOut) await say(a.answer, now);
  if (!now.isCurrent()) return;
  patch({ voice: "idle" });
  if (listenAfter && settings().handsFree && !settings().editFirst && a.intake?.kind !== "attach" && a.intake?.kind !== "filed") void listen();
}

function addExchange(x: Exchange) {
  patch({ items: [...useVoice.getState().items.slice(1 - KEEP), x] });
}

function pageNow() {
  return location.pathname.startsWith(ASK_PAGE) ? { path: ASK_PAGE, scope: "system" as const } : { ...snapshotPage(), scope: "page" as const };
}

/** Starts a fresh chat on screen; the history keeps the old one. */
export function clearChat() {
  stopAll();
  forgetIntake();
  patch({ items: [], heard: "", note: "", draft: "" });
}

// --- Speaking

export function stopSpeaking() {
  playback?.stop();
  playback = null;
  level.current = 0;
}

/** Speaks with the ElevenLabs voice and resolves when done; falls back to the browser's own voice. */
export async function say(words: string, now?: Turn) {
  stopSpeaking();
  patch({ voice: "speaking" });
  try {
    const p = await speak(words, level, now && stepSignal(now));
    playback = p;
    await p.done;
    if (playback === p) playback = null;
  } catch {
    // A cancelled turn stays silent; otherwise the browser's own voice still works without a connection
    if (!now || now.isCurrent()) await browserSay(words);
  }
  useVoice.setState((s) => (s.voice === "speaking" ? { voice: "idle" } : {}));
}

/** The browser's voice has no loudness to read, so the orb pulses on a rhythm. */
function browserSay(words: string): Promise<void> {
  if (!("speechSynthesis" in window)) return Promise.resolve();
  return new Promise((resolve) => {
    const u = new SpeechSynthesisUtterance(words);
    u.lang = "en-US";
    let frame = 0;
    const pulse = (t: number) => ((level.current = 0.25 + 0.5 * Math.abs(Math.sin(t / 95)) * Math.abs(Math.sin(t / 260))), (frame = requestAnimationFrame(pulse)));
    const done = () => (cancelAnimationFrame(frame), (level.current = 0), resolve());
    u.onstart = () => (frame = requestAnimationFrame(pulse));
    u.onend = done;
    u.onerror = done;
    playback = { stop: () => (window.speechSynthesis.cancel(), done()) };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  });
}

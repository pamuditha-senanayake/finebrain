"use client";

import { Keyboard, Mic, Plus, Send, Square, Volume2, VolumeX, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { ConnectorPicker } from "@/features/connect/connector-picker";
import { Interview } from "@/features/setup/interview";
import { useAsk, useConversation } from "@/lib/api/conversation";
import { findPage } from "@/lib/ask-go";
import { useCurrentUser } from "@/lib/auth";
import { canRecord, openMic, recordQuestion, transcribe, type Mic as OpenMic } from "@/lib/voice/mic";
import { playCue, shortOf, speak, unlockAudio } from "@/lib/voice/speaker";
import { endTurn, failureNote, isOffline, OFFLINE, startTurn, stepSignal, type Turn as VoiceTurn } from "@/lib/voice/turn";
import { cn } from "@/lib/utils";
import { AskChat, type Turn } from "./ask-chat";
import { AskHistory } from "./ask-history";
import { AskUpload } from "./ask-upload";
import { GLIDE, useOrbSize, VoiceOrb, type OrbStage, type VoiceState } from "./voice-orb";
import { t } from "@/lib/i18n";

// The browser speech APIs are not in TypeScript's DOM types yet, so describe the parts used here.
type Recognition = {
  lang: string;
  interimResults: boolean;
  continuous: boolean;
  onresult: ((e: { results: ArrayLike<ArrayLike<{ transcript: string }> & { isFinal: boolean }> }) => void) | null;
  onerror: ((e: { error: string }) => void) | null;
  onend: (() => void) | null;
  start: () => void;
  stop: () => void;
  abort: () => void;
};
type RecognitionCtor = new () => Recognition;
const recognitionCtor = (): RecognitionCtor | null => {
  if (typeof window === "undefined") return null;
  const w = window as unknown as { SpeechRecognition?: RecognitionCtor; webkitSpeechRecognition?: RecognitionCtor };
  return w.SpeechRecognition ?? w.webkitSpeechRecognition ?? null;
};
const noop = () => () => {};
/** Voice works by recording and sending the audio to ElevenLabs, or with the browser's own recognition when it cannot record. */
const useVoiceSupported = () => useSyncExternalStore(noop, () => !!recognitionCtor() || canRecord(), () => true);

const LABEL: Record<VoiceState, string> = { idle: "Tap to talk", listening: "Listening", thinking: "Thinking", speaking: "Speaking" };
/** How the chat and the orb move between looks: the same 700ms ease as the orb's size. */
const MOVE = "flex-grow 700ms cubic-bezier(0.22, 1, 0.36, 1), opacity 500ms ease";
const SUGGESTIONS = ["What is our refund window?", "When does the domain renew?", "What are support hours?"];

/** Typing "/" in the box offers these. They do things instead of asking a question. */
const COMMANDS = [
  { cmd: "/setup", label: "Set up the brain" },
  { cmd: "/connect", label: "Add a connector" },
  { cmd: "/claude", label: "Use in Claude" },
] as const;
type Command = (typeof COMMANDS)[number]["cmd"];


/** Full page Ask the Brain with a voice agent: talk or type, hear the answer, see its sources on demand. */
export function AskVoice() {
  const ask = useAsk();
  const conversation = useConversation();
  const supported = useVoiceSupported();
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [heard, setHeard] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [speakOut, setSpeakOut] = useState(true);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [filed, setFiled] = useState("");
  const onFiled = (message: string, ok: boolean) => (ok ? (setFiled(message), setNote("")) : (setNote(message), setFiled("")));
  const [setup, setSetup] = useState(false);
  const [picker, setPicker] = useState(false);
  const router = useRouter();
  const { user } = useCurrentUser();
  const level = useRef(0);
  const rec = useRef<Recognition | null>(null);
  const recording = useRef<{ stop: () => void } | null>(null);
  const mic = useRef<OpenMic | null>(null);
  const player = useRef<{ stop: () => void } | null>(null);
  // The running question; a new one cancels it, so a late answer is never spoken.
  const turn = useRef<AbortController | null>(null);

  // Stop listening and speaking when leaving the page.
  useEffect(
    () => () => {
      endTurn(turn);
      rec.current?.abort();
      recording.current?.stop();
      mic.current?.stop();
      player.current?.stop();
    },
    [],
  );

  const MIC_BLOCKED = "The microphone is blocked. Allow it in the browser, or type instead.";

  function beginListening() {
    stopSpeaking();
    setNote("");
    setHeard("");
    setVoice("listening");
  }

  /** Called on the tap: unlocks sound for the reply, then listens. ElevenLabs first, because it works in every browser. */
  function listen() {
    unlockAudio();
    if (isOffline()) return setNote(OFFLINE);
    if (canRecord()) void listenRecorded();
    else if (recognitionCtor()) listenInBrowser();
    else setTyping(true);
  }

  /** Records one question until a short silence (or a second tap), then ElevenLabs turns it into words. */
  async function listenRecorded() {
    const now = startTurn(turn);
    beginListening();
    const opened = await openMic(level);
    if (!opened) {
      setNote(MIC_BLOCKED);
      setVoice("idle");
      return;
    }
    mic.current = opened;
    const take = recordQuestion(opened, level);
    recording.current = take;
    const audio = await take.done;
    recording.current = null;
    mic.current = null;
    if (!audio) {
      setNote("I did not hear anything, sir. Tap and speak again.");
      setVoice("idle");
      return;
    }
    setVoice("thinking");
    playCue();
    try {
      const words = await transcribe(audio, stepSignal(now));
      if (!now.isCurrent()) return;
      if (!words) throw new Error("No words recognised.");
      void answer(words);
    } catch (e) {
      if (!now.isCurrent()) return;
      setNote(failureNote(e, "I could not make that out, sir. Tap to try again, or type instead."));
      setVoice("idle");
    }
  }

  /** The browser's own recognition, only for browsers that cannot record. */
  function listenInBrowser() {
    endTurn(turn);
    const r = new (recognitionCtor()!)();
    r.lang = "en-US";
    r.interimResults = true;
    r.continuous = false;
    let final = "";
    r.onresult = (e) => {
      let interim = "";
      for (let i = 0; i < e.results.length; i++) {
        const res = e.results[i];
        if (res.isFinal) final += res[0].transcript;
        else interim += res[0].transcript;
      }
      setHeard((final + interim).trim());
    };
    r.onerror = (e) => setNote(e.error === "not-allowed" ? MIC_BLOCKED : e.error === "no-speech" ? "I did not hear anything, sir. Tap and speak again." : "Voice is not working in this browser. Please type instead.");
    r.onend = () => {
      rec.current = null;
      const q = final.trim();
      if (q) void answer(q);
      else setVoice("idle");
    };
    rec.current = r;
    beginListening();
    r.start();
  }

  async function answer(q: string) {
    unlockAudio();
    // "Go to the library" goes there at once; no model call.
    const page = findPage(q, user);
    if (page) return void router.push(page.href);
    const now = startTurn(turn);
    setHeard(q);
    // A new question clears any old "could not hear" note; a failed answer sets its own below.
    setNote("");
    setVoice("thinking");
    try {
      // A short pause keeps "thinking" visible, so the reply does not feel like it skipped a step.
      const [a] = await Promise.all([ask.mutateAsync({ question: q, page: { path: "/l1/ask", scope: "system" }, signal: stepSignal(now) }), new Promise((r) => setTimeout(r, 700))]);
      // A newer question took over while this one waited; its answer is dropped, not shown or spoken.
      if (!now.isCurrent()) return;
      setTurns((t) => [...t, { q, a }]);
      if (speakOut) void say(shortOf(a.answer).short, now);
      else setVoice("idle");
    } catch (e) {
      if (!now.isCurrent()) return;
      setNote(failureNote(e, "The brain could not answer. Try again."));
      setVoice("idle");
    }
  }

  function stopSpeaking() {
    player.current?.stop();
    player.current = null;
    level.current = 0;
  }

  /** Speaks with the ElevenLabs voice; the orb follows the real loudness. Falls back to the browser's voice. */
  async function say(words: string, now?: VoiceTurn) {
    stopSpeaking();
    try {
      setVoice("speaking");
      const playback = await speak(words, level, now && stepSignal(now));
      player.current = playback;
      await playback.done;
      if (player.current === playback) player.current = null;
      setVoice((v) => (v === "speaking" ? "idle" : v));
    } catch {
      // A cancelled turn stays silent; otherwise the browser's own voice still works without a connection.
      if (now && !now.isCurrent()) return;
      browserSay(words);
    }
  }

  /** The browser's own voice, used when ElevenLabs is unreachable. It has no loudness to read, so the orb pulses on a rhythm. */
  function browserSay(words: string) {
    if (!("speechSynthesis" in window)) {
      setVoice("idle");
      return;
    }
    const u = new SpeechSynthesisUtterance(words);
    u.lang = "en-US";
    let raf = 0;
    const pulse = (now: number) => {
      level.current = 0.25 + 0.5 * Math.abs(Math.sin(now / 95)) * Math.abs(Math.sin(now / 260));
      raf = requestAnimationFrame(pulse);
    };
    const done = () => {
      cancelAnimationFrame(raf);
      level.current = 0;
      setVoice((v) => (v === "speaking" ? "idle" : v));
    };
    u.onstart = () => {
      raf = requestAnimationFrame(pulse);
    };
    u.onend = done;
    u.onerror = done;
    player.current = { stop: () => { window.speechSynthesis.cancel(); done(); } };
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
    setVoice("speaking");
  }

  function tapOrb() {
    if (voice === "listening") {
      rec.current?.stop();
      recording.current?.stop();
    } else listen();
  }

  function run(cmd: Command) {
    setText("");
    setNote("");
    if (cmd === "/setup") {
      setTyping(false);
      setHeard("");
      setSetup(true);
    } else if (cmd === "/connect") setPicker(true);
    else router.push("/l1/claude");
  }

  function submitText() {
    const q = text.trim();
    if (!q || voice === "thinking") return;
    if (q.startsWith("/")) {
      const hit = COMMANDS.find((c) => c.cmd.startsWith(q.split(" ")[0].toLowerCase()));
      if (hit) run(hit.cmd);
      else setNote("Try /setup, /connect or /claude.");
      return;
    }
    setText("");
    void answer(q);
  }

  const last = turns[turns.length - 1];
  // The whole chat shows, scrolled to the newest: what was saved before this page opened, then this visit's turns.
  const saved: Turn[] = conversation.saved.map((t) => ({ q: t.question, a: { question: t.question, answer: t.answer, citations: [], withheld: 0 } }));
  const before = [...saved, ...turns.slice(0, -1)];
  // Three looks: home (orb, greeting, quick questions, bar), big (only the orb, listening or thinking),
  // and chat (messages fill the page, a small orb at the bottom; tap it to talk again).
  const stage: OrbStage = voice === "listening" || voice === "thinking" ? "big" : before.length > 0 || turns.length > 0 ? "small" : "rest";
  const orb = useOrbSize(stage);
  const chat = [...before, ...(last ? [last] : [])];
  const slash = typing && text.startsWith("/") ? COMMANDS.filter((c) => c.cmd.startsWith(text.trim().split(" ")[0].toLowerCase())) : [];

  // The setup interview takes over the page; the orb stays small above it and speaks each question.
  if (setup) {
    return (
      <div className="-mx-3 -my-4 flex min-h-[calc(100dvh-3rem)] flex-col sm:-mx-6 sm:-my-5">
        <h1 className="sr-only">Ask the Brain, setup</h1>
        <div className="flex justify-center pt-6">
          <button type="button" onClick={() => { stopSpeaking(); setVoice("idle"); }} className="rounded-full outline-none" aria-label="Stop speaking">
            <VoiceOrb state={voice} level={level} size={120} />
          </button>
        </div>
        <div className="flex-1 px-6 pb-10 pt-2">
          <Interview variant="ask" onQuestion={(q) => { if (speakOut) void say(q); }} onExit={() => { stopSpeaking(); setVoice("idle"); setSetup(false); }} />
        </div>
      </div>
    );
  }

  return (
    <div className="-mx-3 -my-4 flex h-[calc(100dvh-3rem)] flex-col overflow-hidden sm:-mx-6 sm:-my-5">
      <h1 className="sr-only">Ask the Brain</h1>

      <div className="flex items-center gap-2 px-6 pt-5 short:pt-3">
        <AskHistory currentId={conversation.id} onOpen={(id) => { endTurn(turn); stopSpeaking(); setVoice("idle"); conversation.open(id); setTurns([]); setHeard(""); }} />
        {(before.length > 0 || turns.length > 0) && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => { conversation.startOver(); setTurns([]); setHeard(""); }}>
            <Plus /> New
          </Button>
        )}
        <Button variant="ghost" size="icon-sm" className="ml-auto text-muted-foreground" onClick={() => { setSpeakOut(!speakOut); stopSpeaking(); if (voice === "speaking") setVoice("idle"); }} aria-label={speakOut ? "Turn spoken replies off" : "Turn spoken replies on"} aria-pressed={speakOut}>
          {speakOut ? <Volume2 /> : <VolumeX />}
        </Button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <AskChat turns={chat} className={cn("min-h-0 basis-0", stage !== "small" && "pointer-events-none")} style={{ flexGrow: stage === "small" ? 1 : 0, opacity: stage === "small" ? 1 : 0, transition: MOVE }} />
        <div className="basis-0" style={{ flexGrow: stage === "small" ? 0 : 1, transition: MOVE }} />
        <div className="flex shrink-0 flex-col items-center px-6 pb-4 text-center">
          <div className="relative">
            <button type="button" onClick={tapOrb} disabled={voice === "thinking"} className="rounded-full outline-none focus-visible:ring-4 focus-visible:ring-ring/40" aria-label={voice === "listening" ? "Stop listening" : "Talk to the Brain"}>
              <VoiceOrb state={voice} level={level} size={orb.size} drawSize={orb.drawSize} />
            </button>
            {/* In the chat look, a small keyboard just right of the orb's edge opens a text field, for asking without voice. */}
            {stage === "small" && !typing && (
              <Button variant="ghost" size="icon-sm" className="absolute top-1/2 -translate-y-1/2 rounded-full text-muted-foreground animate-in fade-in" style={{ left: `calc(50% + ${orb.size * 0.5}px)` }} onClick={() => setTyping(true)} aria-label="Type instead">
                <Keyboard />
              </Button>
            )}
          </div>
          {stage === "small" && typing && (
            <form style={{ marginTop: -orb.size * 0.1 }} className="flex w-full max-w-md items-center gap-1 rounded-full border bg-surface p-1.5 pl-5 animate-in fade-in slide-in-from-bottom-1" onSubmit={(e) => { e.preventDefault(); submitText(); }}>
              <input value={text} onChange={(e) => setText(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") setTyping(false); }} placeholder="Ask anything" aria-label="Question" autoFocus className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
              <Button type="submit" size="icon-sm" className="rounded-full" disabled={!text.trim() || voice === "thinking"} aria-label="Ask"><Send /></Button>
              <Button type="button" size="icon-sm" variant="ghost" className="rounded-full text-muted-foreground" onClick={() => setTyping(false)} aria-label="Close typing"><X /></Button>
            </form>
          )}
          {stage !== "small" && (
            <p style={{ marginTop: -orb.size * 0.1, transition: GLIDE }} className={cn("text-sm font-medium uppercase tracking-[0.18em]", voice === "idle" ? "text-muted-foreground" : "text-primary")} role="status">
              {supported || voice !== "idle" ? LABEL[voice] : "Type to ask"}
            </p>
          )}
          {stage === "big" && heard && <p className={cn("mt-6 max-w-2xl text-xl font-medium leading-snug", voice === "listening" && "text-muted-foreground")}>{heard}</p>}
          {stage === "rest" && (
            <div className="mt-6 short:mt-4">
              <p className="mx-auto max-w-md text-[15px] leading-relaxed text-muted-foreground">{t("ask.greeting")}</p>
              <p className="mt-2 text-xl font-semibold tracking-tight">{t("ask.greetingAsk")}</p>
              <div className="mt-5 flex flex-wrap justify-center gap-1.5 short:mt-3">
                {SUGGESTIONS.map((s) => (
                  <button key={s} type="button" onClick={() => void answer(s)} className="rounded-full border bg-surface px-3 py-1 text-xs transition-colors hover:bg-accent">
                    {s}
                  </button>
                ))}
                <button type="button" onClick={() => run("/setup")} className="rounded-full border border-dashed px-3 py-1 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                  /setup
                </button>
              </div>
            </div>
          )}
          {note && <p className="mt-4 text-sm text-warn-fg">{note}</p>}
          {filed && <p className="mt-4 text-sm text-muted-foreground" role="status">{filed}</p>}
        </div>
        <div className="basis-0" style={{ flexGrow: stage === "small" ? 0 : 1, transition: MOVE }} />
      </div>

      <ConnectorPicker open={picker} onOpenChange={setPicker} />
      {stage === "rest" && (
      <div className="relative mx-auto flex w-full max-w-2xl items-center justify-center gap-4 px-6 pb-8 pt-2 short:pb-4">
        {slash.length > 0 && (
          <ul className="absolute inset-x-6 bottom-full mb-2 overflow-hidden rounded-2xl border bg-popover p-1.5 shadow-lg" role="listbox" aria-label="Commands">
            {slash.map((c, i) => (
              <li key={c.cmd}>
                <button type="button" role="option" aria-selected={i === 0} onClick={() => run(c.cmd)} className={cn("flex w-full items-center gap-4 rounded-xl px-4 py-3 text-left hover:bg-accent", i === 0 && "bg-accent/60")}>
                  <span className="w-20 font-mono text-sm">{c.cmd}</span>
                  <span className="text-[15px] text-muted-foreground">{c.label}</span>
                </button>
              </li>
            ))}
          </ul>
        )}
        {typing ? (
          <form className="flex w-full items-center gap-2 rounded-full border bg-surface p-1.5 pl-5" onSubmit={(e) => { e.preventDefault(); submitText(); }}>
            <AskUpload onDone={onFiled} />
            <input value={text} onChange={(e) => setText(e.target.value)} placeholder="Ask anything, or type /" aria-label="Question" autoFocus className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
            <Button type="submit" size="icon" className="rounded-full" disabled={!text.trim() || voice === "thinking"} aria-label="Ask"><Send /></Button>
            {supported && <Button type="button" size="icon" variant="ghost" className="rounded-full" onClick={() => setTyping(false)} aria-label="Use voice"><Mic /></Button>}
          </form>
        ) : (
          <>
            <Button variant="ghost" size="icon" className="rounded-full text-muted-foreground" onClick={() => setTyping(true)} aria-label="Type instead"><Keyboard /></Button>
            <Button size="icon" className={cn("size-16 rounded-full shadow-lg shadow-primary/25", voice === "listening" && "animate-pulse")} onClick={tapOrb} disabled={voice === "thinking"} aria-label={voice === "listening" ? "Stop listening" : voice === "speaking" ? "Stop speaking" : "Talk"}>
              {voice === "listening" || voice === "speaking" ? <Square className="size-5" /> : <Mic className="size-6" />}
            </Button>
            <AskUpload onDone={onFiled} />
          </>
        )}
      </div>
      )}
    </div>
  );
}

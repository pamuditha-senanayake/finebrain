"use client";

import { History, Keyboard, Mic, Plus, Send, Square, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { ShowMe } from "@/components/shell/show-me";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { AskAnswer } from "@/contracts";
import { Button } from "@/components/ui/button";
import { ConnectorPicker } from "@/features/connect/connector-picker";
import { Interview } from "@/features/setup/interview";
import { useAsk, useConversation } from "@/lib/api/conversation";
import { findPage } from "@/lib/ask-go";
import { useCurrentUser } from "@/lib/auth";
import { canRecord, openMic, recordQuestion, transcribe, type Mic as OpenMic } from "@/lib/voice/mic";
import { shortOf, speak, unlockAudio } from "@/lib/voice/speaker";
import { date } from "@/lib/format";
import { lookedInLabel } from "@/lib/looked-in";
import { cn } from "@/lib/utils";
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
const SUGGESTIONS = ["What is our refund window?", "When does the domain renew?", "What are support hours?"];

/** Typing "/" in the box offers these. They do things instead of asking a question. */
const COMMANDS = [
  { cmd: "/setup", label: "Set up the brain" },
  { cmd: "/connect", label: "Add a connector" },
  { cmd: "/claude", label: "Use in Claude" },
] as const;
type Command = (typeof COMMANDS)[number]["cmd"];

type Turn = { q: string; a: AskAnswer };

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
  const [sources, setSources] = useState(false);
  const [more, setMore] = useState(false);
  const [earlier, setEarlier] = useState(false);
  const [setup, setSetup] = useState(false);
  const [picker, setPicker] = useState(false);
  const router = useRouter();
  const { user } = useCurrentUser();
  const level = useRef(0);
  const rec = useRef<Recognition | null>(null);
  const recording = useRef<{ stop: () => void } | null>(null);
  const mic = useRef<OpenMic | null>(null);
  const player = useRef<{ stop: () => void } | null>(null);

  // Stop listening and speaking when leaving the page.
  useEffect(
    () => () => {
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
    setSources(false);
    setVoice("listening");
  }

  /** Called on the tap: unlocks sound for the reply, then listens. ElevenLabs first, because it works in every browser. */
  function listen() {
    unlockAudio();
    if (canRecord()) void listenRecorded();
    else if (recognitionCtor()) listenInBrowser();
    else setTyping(true);
  }

  /** Records one question until a short silence (or a second tap), then ElevenLabs turns it into words. */
  async function listenRecorded() {
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
    try {
      const words = await transcribe(audio);
      if (!words) throw new Error("No words recognised.");
      void answer(words);
    } catch {
      setNote("I could not make that out, sir. Tap to try again, or type instead.");
      setVoice("idle");
    }
  }

  /** The browser's own recognition, only for browsers that cannot record. */
  function listenInBrowser() {
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
    setHeard(q);
    setSources(false);
    setMore(false);
    setVoice("thinking");
    try {
      // A short pause keeps "thinking" visible, so the reply does not feel like it skipped a step.
      const [a] = await Promise.all([ask.mutateAsync({ question: q, page: { path: "/l1/ask", scope: "system" } }), new Promise((r) => setTimeout(r, 700))]);
      setTurns((t) => [...t, { q, a }]);
      if (speakOut) void say(shortOf(a.answer).short);
      else setVoice("idle");
    } catch {
      setNote("The brain could not answer. Try again.");
      setVoice("idle");
    }
  }

  function stopSpeaking() {
    player.current?.stop();
    player.current = null;
    level.current = 0;
  }

  /** Speaks with the ElevenLabs voice; the orb follows the real loudness. Falls back to the browser's voice. */
  async function say(words: string) {
    stopSpeaking();
    try {
      setVoice("speaking");
      const playback = await speak(words, level);
      player.current = playback;
      await playback.done;
      if (player.current === playback) player.current = null;
      setVoice((v) => (v === "speaking" ? "idle" : v));
    } catch {
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
  const showLast = last && voice !== "listening" && voice !== "thinking" && heard === last.q;
  // Earlier turns: what was saved before this page opened, then this visit's turns except the last.
  const saved: Turn[] = conversation.saved.map((t) => ({ q: t.question, a: { question: t.question, answer: t.answer, citations: [], withheld: 0 } }));
  const before = [...saved, ...turns.slice(0, -1)];
  // The orb fills the screen while it listens and thinks, then shrinks to the top so the answer gets the room.
  const stage: OrbStage = voice === "listening" || voice === "thinking" ? "big" : heard || turns.length > 0 ? "small" : "rest";
  const orb = useOrbSize(stage);
  // The greeting and quick questions only show before the first tap.
  const welcome = !heard && turns.length === 0 && voice === "idle";
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
        {before.length > 0 && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setEarlier(!earlier)} aria-expanded={earlier}>
            <History /> Earlier ({before.length})
          </Button>
        )}
        {(before.length > 0 || turns.length > 0) && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => { conversation.startOver(); setTurns([]); setHeard(""); setEarlier(false); }}>
            <Plus /> New
          </Button>
        )}
        <Button variant="ghost" size="icon-sm" className="ml-auto text-muted-foreground" onClick={() => { setSpeakOut(!speakOut); stopSpeaking(); if (voice === "speaking") setVoice("idle"); }} aria-label={speakOut ? "Turn spoken replies off" : "Turn spoken replies on"} aria-pressed={speakOut}>
          {speakOut ? <Volume2 /> : <VolumeX />}
        </Button>
      </div>

      {earlier && (
        <ol className="scrollbar-thin mx-auto flex max-h-[45%] w-full max-w-2xl shrink-0 flex-col gap-3 overflow-y-auto px-6 pt-4" aria-label="Earlier chat">
          {before.map((t, i) => (
            <li key={i} className="flex flex-col gap-2">
              <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary/10 px-4 py-2 text-[15px]">{t.q}</p>
              <p className="max-w-[92%] rounded-3xl rounded-bl-md border bg-card px-5 py-3 text-[15px] leading-relaxed">{t.a.answer}</p>
            </li>
          ))}
        </ol>
      )}

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="basis-0" style={{ flexGrow: stage === "small" ? 0 : 1, transition: "flex-grow 700ms cubic-bezier(0.22, 1, 0.36, 1)" }} />
      <div className="mx-auto flex min-h-0 w-full max-w-2xl basis-auto flex-col items-center px-6 py-6 text-center short:py-3" style={{ flexGrow: stage === "small" ? 1 : 0, transition: "flex-grow 700ms cubic-bezier(0.22, 1, 0.36, 1)" }}>
        <button type="button" onClick={tapOrb} disabled={voice === "thinking"} className="shrink-0 rounded-full outline-none focus-visible:ring-4 focus-visible:ring-ring/40" aria-label={voice === "listening" ? "Stop listening" : "Talk to the Brain"}>
          <VoiceOrb state={voice} level={level} size={orb.size} drawSize={orb.drawSize} />
        </button>
        <p style={{ marginTop: -orb.size * 0.1, transition: GLIDE }} className={cn("text-sm font-medium uppercase tracking-[0.18em]", voice === "idle" ? "text-muted-foreground" : "text-primary")} role="status">
          {supported || voice !== "idle" ? LABEL[voice] : "Type to ask"}
        </p>

        <div className={cn("w-full", stage === "small" ? "scrollbar-thin order-first mb-2 min-h-0 flex-1 overflow-y-auto" : "mt-8 short:mt-4", stage === "rest" && "min-h-28 short:min-h-0")} aria-live="polite">
          {heard && <p className={cn("text-2xl font-medium leading-snug tracking-tight", voice === "listening" && "text-muted-foreground")}>{heard}</p>}
          {showLast && (
            <div className="mt-6 animate-in fade-in duration-500">
              <p className="text-xl leading-relaxed text-muted-foreground" data-testid="ask-voice-answer">
                {more ? last.a.answer : shortOf(last.a.answer).short}
              </p>
              <div className="mt-4 flex flex-wrap justify-center gap-1">
                <ShowMe answer={last.a} className="mr-1" />
                {shortOf(last.a.answer).rest && (
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setMore(!more)} aria-expanded={more}>
                    {more ? "Less" : "More"}
                  </Button>
                )}
                {last.a.citations.length > 0 && (
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setSources(!sources)} aria-expanded={sources}>
                    {sources ? "Hide sources" : `${last.a.citations.length} ${last.a.citations.length === 1 ? "source" : "sources"}`}
                  </Button>
                )}
              </div>
              {sources && (
                <ol className="mx-auto mt-3 max-w-xl space-y-2 text-left">
                  {last.a.citations.map((c, i) => (
                    <li key={c.id}>
                      <Link href={c.href} className="block rounded-xl border bg-surface px-4 py-3 text-sm hover:border-primary/40">
                        <span className="font-medium">{i + 1}. {c.label}</span>
                        <span className="mt-0.5 block text-xs text-muted-foreground">True from {date(c.validFrom)}{c.validTo ? ` to ${date(c.validTo)}` : ""}</span>
                      </Link>
                    </li>
                  ))}
                  {last.a.lookedIn && <li className="px-1 text-xs text-muted-foreground" data-testid="looked-in">{lookedInLabel(last.a.lookedIn)}</li>}
                </ol>
              )}
            </div>
          )}
          {welcome && (
            <div className="mb-5 short:mb-3">
              <p className="mx-auto max-w-md text-[15px] leading-relaxed text-muted-foreground">{t("ask.greeting")}</p>
              <p className="mt-2 text-xl font-semibold tracking-tight">{t("ask.greetingAsk")}</p>
            </div>
          )}
          {welcome && (
            <div className="flex flex-wrap justify-center gap-1.5">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => void answer(s)} disabled={voice !== "idle"} className="rounded-full border bg-surface px-3 py-1 text-xs transition-colors hover:bg-accent disabled:opacity-50">
                  {s}
                </button>
              ))}
              <button type="button" onClick={() => run("/setup")} disabled={voice !== "idle"} className="rounded-full border border-dashed px-3 py-1 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50">
                /setup
              </button>
            </div>
          )}
          {note && <p className="mt-4 text-sm text-warn-fg">{note}</p>}
          {filed && <p className="mt-4 text-sm text-muted-foreground" role="status">{filed}</p>}
        </div>
      </div>
      <div className="basis-0" style={{ flexGrow: stage === "small" ? 0 : 1, transition: "flex-grow 700ms cubic-bezier(0.22, 1, 0.36, 1)" }} />
      </div>

      <ConnectorPicker open={picker} onOpenChange={setPicker} />
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
    </div>
  );
}

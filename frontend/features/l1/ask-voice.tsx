"use client";

import { History, Keyboard, Mic, Send, Square, Volume2, VolumeX } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import type { AskAnswer } from "@/contracts";
import { Button } from "@/components/ui/button";
import { ConnectorPicker } from "@/features/connect/connector-picker";
import { Interview } from "@/features/setup/interview";
import { useAsk } from "@/lib/api/hooks";
import { date } from "@/lib/format";
import { cn } from "@/lib/utils";
import { VoiceOrb, type VoiceState } from "./voice-orb";
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
const canRecord = () => typeof window !== "undefined" && typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;
const noop = () => () => {};
/** Voice works with the browser's own recognition, or by recording and sending the audio to ElevenLabs. */
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

/** The first two sentences: what is shown and spoken first. The rest waits behind "More". */
function shortOf(answer: string): { short: string; rest: string } {
  const parts = answer.match(/[^.!?]+[.!?]+(\s|$)/g) ?? [answer];
  const short = parts.slice(0, 2).join("").trim();
  return { short, rest: answer.slice(short.length).trim() };
}

/** Full page Ask the Brain with a voice agent: talk or type, hear the answer, see its sources on demand. */
export function AskVoice() {
  const ask = useAsk();
  const supported = useVoiceSupported();
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [heard, setHeard] = useState("");
  const [turns, setTurns] = useState<Turn[]>([]);
  const [speakOut, setSpeakOut] = useState(true);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState("");
  const [note, setNote] = useState("");
  const [sources, setSources] = useState(false);
  const [more, setMore] = useState(false);
  const [earlier, setEarlier] = useState(false);
  const [setup, setSetup] = useState(false);
  const [picker, setPicker] = useState(false);
  const router = useRouter();
  const level = useRef(0);
  const rec = useRef<Recognition | null>(null);
  const recorder = useRef<MediaRecorder | null>(null);
  const mic = useRef<{ stream: MediaStream; stop: () => void } | null>(null);
  const player = useRef<{ stop: () => void } | null>(null);

  // Stop listening and speaking when leaving the page.
  useEffect(
    () => () => {
      rec.current?.abort();
      recorder.current?.stop();
      mic.current?.stop();
      player.current?.stop();
    },
    [],
  );

  /** Opens the mic and keeps `level` at its loudness, which drives the orb while listening. */
  async function openMic(): Promise<MediaStream | null> {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const ac = new AudioContext();
      const an = ac.createAnalyser();
      an.fftSize = 512;
      ac.createMediaStreamSource(stream).connect(an);
      const buf = new Uint8Array(an.fftSize);
      let raf = 0;
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        level.current = Math.min(1, Math.sqrt(sum / buf.length) * 4);
        raf = requestAnimationFrame(tick);
      };
      tick();
      mic.current = {
        stream,
        stop: () => {
          cancelAnimationFrame(raf);
          stream.getTracks().forEach((t) => t.stop());
          void ac.close();
          level.current = 0;
          mic.current = null;
        },
      };
      return stream;
    } catch {
      setNote("The microphone is blocked. Allow it in the browser, or type instead.");
      return null;
    }
  }

  function beginListening() {
    stopSpeaking();
    setNote("");
    setHeard("");
    setSources(false);
    setVoice("listening");
  }

  function listen() {
    const Ctor = recognitionCtor();
    if (!Ctor) {
      if (canRecord()) void listenRecorded();
      else setTyping(true);
      return;
    }
    const r = new Ctor();
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
    r.onerror = (e) => setNote(e.error === "not-allowed" ? "The microphone is blocked. Allow it in the browser, or type instead." : e.error === "no-speech" ? "I did not hear anything. Tap to try again." : "");
    r.onend = () => {
      mic.current?.stop();
      rec.current = null;
      const q = final.trim();
      if (q) void answer(q);
      else setVoice("idle");
    };
    rec.current = r;
    beginListening();
    void openMic();
    r.start();
  }

  /**
   * Browsers without built-in recognition (Firefox) record the question and ElevenLabs transcribes it.
   * Recording stops by itself after a short silence once you have spoken, or when you tap again.
   */
  async function listenRecorded() {
    beginListening();
    const stream = await openMic();
    if (!stream) {
      setVoice("idle");
      return;
    }
    const chunks: Blob[] = [];
    const r = new MediaRecorder(stream);
    recorder.current = r;
    r.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    const startedAt = performance.now();
    let spoke = false;
    let loudAt = startedAt;
    const watch = setInterval(() => {
      const now = performance.now();
      if (level.current > 0.08) {
        spoke = true;
        loudAt = now;
      }
      if ((spoke && now - loudAt > 1300) || now - startedAt > 15000) r.stop();
    }, 100);
    r.onstop = async () => {
      clearInterval(watch);
      mic.current?.stop();
      recorder.current = null;
      if (!spoke) {
        setNote("I did not hear anything. Tap to try again.");
        setVoice("idle");
        return;
      }
      setVoice("thinking");
      try {
        const res = await fetch("/api/voice/listen", { method: "POST", body: new Blob(chunks, { type: r.mimeType || "audio/webm" }) });
        const data = (await res.json()) as { text?: string; error?: string };
        if (!res.ok || !data.text) throw new Error(data.error ?? "No words recognised.");
        void answer(data.text);
      } catch {
        setNote("I could not make that out. Tap to try again, or type instead.");
        setVoice("idle");
      }
    };
    r.start();
  }

  async function answer(q: string) {
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

  /** Speaks with the ElevenLabs voice; the orb follows the real loudness of the audio. Falls back to the browser's voice. */
  async function say(words: string) {
    stopSpeaking();
    try {
      const res = await fetch("/api/voice/speak", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: words }) });
      if (!res.ok) throw new Error("speak failed");
      const url = URL.createObjectURL(await res.blob());
      const audio = new Audio(url);
      const ac = new AudioContext();
      const an = ac.createAnalyser();
      an.fftSize = 512;
      const src = ac.createMediaElementSource(audio);
      src.connect(an);
      an.connect(ac.destination);
      const buf = new Uint8Array(an.fftSize);
      let raf = 0;
      const tick = () => {
        an.getByteTimeDomainData(buf);
        let sum = 0;
        for (const v of buf) sum += ((v - 128) / 128) ** 2;
        level.current = Math.min(1, Math.sqrt(sum / buf.length) * 5);
        raf = requestAnimationFrame(tick);
      };
      const done = () => {
        cancelAnimationFrame(raf);
        level.current = 0;
        URL.revokeObjectURL(url);
        void ac.close();
        if (player.current === handle) player.current = null;
        setVoice((v) => (v === "speaking" ? "idle" : v));
      };
      const handle = { stop: () => { audio.pause(); done(); } };
      player.current = handle;
      audio.onended = done;
      audio.onerror = done;
      setVoice("speaking");
      tick();
      await audio.play();
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
      if (recorder.current?.state === "recording") recorder.current.stop();
    } else if (voice === "speaking") {
      stopSpeaking();
      setVoice("idle");
    } else if (voice === "idle") listen();
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
  const before = turns.slice(0, -1);
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
    <div className="-mx-3 -my-4 flex min-h-[calc(100dvh-3rem)] flex-col sm:-mx-6 sm:-my-5">
      <h1 className="sr-only">Ask the Brain</h1>

      <div className="flex items-center gap-2 px-6 pt-5">
        {before.length > 0 && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setEarlier(!earlier)} aria-expanded={earlier}>
            <History /> Earlier ({before.length})
          </Button>
        )}
        <Button variant="ghost" size="icon-sm" className="ml-auto text-muted-foreground" onClick={() => { setSpeakOut(!speakOut); stopSpeaking(); if (voice === "speaking") setVoice("idle"); }} aria-label={speakOut ? "Turn spoken replies off" : "Turn spoken replies on"} aria-pressed={speakOut}>
          {speakOut ? <Volume2 /> : <VolumeX />}
        </Button>
      </div>

      {earlier && (
        <ol className="mx-auto w-full max-w-2xl space-y-3 px-6 pt-4">
          {before.map((t, i) => (
            <li key={i} className="rounded-xl border bg-surface px-5 py-4">
              <p className="text-sm text-muted-foreground">{t.q}</p>
              <p className="mt-1.5 text-[15px] leading-relaxed">{t.a.answer}</p>
            </li>
          ))}
        </ol>
      )}

      <div className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-center justify-center px-6 py-6 text-center">
        <button type="button" onClick={tapOrb} disabled={voice === "thinking"} className="rounded-full outline-none focus-visible:ring-4 focus-visible:ring-ring/40" aria-label={voice === "listening" ? "Stop listening" : voice === "speaking" ? "Stop speaking" : "Talk to the Brain"}>
          <VoiceOrb state={voice} level={level} size={240} />
        </button>
        <p className={cn("-mt-6 text-sm font-medium uppercase tracking-[0.18em]", voice === "idle" ? "text-muted-foreground" : "text-primary")} role="status">
          {supported || voice !== "idle" ? LABEL[voice] : "Type to ask"}
        </p>

        <div className="mt-8 min-h-28 w-full" aria-live="polite">
          {heard && <p className={cn("text-2xl font-medium leading-snug tracking-tight", voice === "listening" && "text-muted-foreground")}>{heard}</p>}
          {showLast && (
            <div className="mt-6 animate-in fade-in duration-500">
              <p className="text-xl leading-relaxed text-muted-foreground" data-testid="ask-voice-answer">
                {more ? last.a.answer : shortOf(last.a.answer).short}
              </p>
              <div className="mt-4 flex justify-center gap-1">
                {shortOf(last.a.answer).rest && (
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setMore(!more)} aria-expanded={more}>
                    {more ? "Less" : "More"}
                  </Button>
                )}
                {last.a.citations.length > 0 && (
                  <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setSources(!sources)} aria-expanded={sources}>
                    {sources ? "Hide sources" : `${last.a.citations.length} sources`}
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
                </ol>
              )}
            </div>
          )}
          {!heard && turns.length === 0 && (
            <div className="mb-8">
              <p className="mx-auto max-w-md text-[15px] leading-relaxed text-muted-foreground">{t("ask.greeting")}</p>
              <p className="mt-2 text-xl font-semibold tracking-tight">{t("ask.greetingAsk")}</p>
            </div>
          )}
          {!heard && turns.length === 0 && (
            <div className="flex flex-wrap justify-center gap-2">
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => void answer(s)} disabled={voice !== "idle"} className="rounded-full border bg-surface px-4 py-2 text-sm transition-colors hover:bg-accent disabled:opacity-50">
                  {s}
                </button>
              ))}
              <button type="button" onClick={() => run("/setup")} disabled={voice !== "idle"} className="rounded-full border border-dashed px-4 py-2 font-mono text-sm text-muted-foreground transition-colors hover:bg-accent hover:text-foreground disabled:opacity-50">
                /setup
              </button>
            </div>
          )}
          {note && <p className="mt-4 text-sm text-warn-fg">{note}</p>}
        </div>
      </div>

      <ConnectorPicker open={picker} onOpenChange={setPicker} />
      <div className="relative mx-auto flex w-full max-w-2xl items-center justify-center gap-4 px-6 pb-8">
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
            <span className="size-9" aria-hidden />
          </>
        )}
      </div>
    </div>
  );
}

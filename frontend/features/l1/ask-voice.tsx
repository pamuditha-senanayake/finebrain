"use client";

import { Keyboard, Mic, Plus, Send, Square, X } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState, useSyncExternalStore } from "react";
import { Button } from "@/components/ui/button";
import { VoiceSettings } from "@/components/shell/voice-settings";
import { ConnectorPicker } from "@/features/connect/connector-picker";
import { Interview } from "@/features/setup/interview";
import { useConversation } from "@/lib/api/conversation";
import { clearChat, level, say, send, setDraft, stopAll, tap, useVoice, useVoiceSettings } from "@/lib/voice/agent";
import { canRecord } from "@/lib/voice/mic";
import { cn } from "@/lib/utils";
import { AskChat, type Turn } from "./ask-chat";
import { AskHistory } from "./ask-history";
import { AskUpload } from "./ask-upload";
import { GLIDE, useOrbSize, VoiceOrb, type OrbStage, type VoiceState } from "./voice-orb";
import { t } from "@/lib/i18n";

const noop = () => () => {};
/** Voice works by recording and sending the audio to ElevenLabs. */
const useVoiceSupported = () => useSyncExternalStore(noop, canRecord, () => true);

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


/** Full page Lisena with a voice agent: talk or type, hear the answer, see its sources on demand.
 * The voice itself lives in lib/voice/agent.ts, so leaving this page never cuts a reply off; the orb carries on. */
export function AskVoice() {
  const conversation = useConversation();
  const supported = useVoiceSupported();
  const voice = useVoice((s) => s.voice);
  const heard = useVoice((s) => s.heard);
  const note = useVoice((s) => s.note);
  const text = useVoice((s) => s.draft);
  const items = useVoice((s) => s.items);
  const speakOut = useVoiceSettings((s) => s.speakOut);
  const [typingOn, setTyping] = useState(false);
  // Words spoken with "edit before sending" open the box, so they can be fixed before Enter
  const typing = typingOn || !!text;
  const [notice, setNotice] = useState("");
  const [filed, setFiled] = useState("");
  const onFiled = (message: string, ok: boolean) => (ok ? (setFiled(message), setNotice("")) : (setNotice(message), setFiled("")));
  const [setup, setSetup] = useState(false);
  const [picker, setPicker] = useState(false);
  const router = useRouter();

  const ask = (q: string) => void send(q, { speak: true });
  const reset = () => { clearChat(); setNotice(""); };

  function run(cmd: Command) {
    setDraft("");
    setNotice("");
    if (cmd === "/setup") {
      setTyping(false);
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
      else setNotice("Try /setup, /connect or /claude.");
      return;
    }
    setDraft("");
    ask(q);
  }

  // Only answered exchanges show here; the big orb shows the one still thinking
  const turns: Turn[] = items.flatMap((x) => (x.a ? [{ q: x.q, a: x.a }] : []));
  const last = turns[turns.length - 1];
  // The whole chat shows, scrolled to the newest: what was saved before this page opened, then this visit's turns.
  // Saved turns this page opened, minus any already shown from the orb on another page
  const saved: Turn[] = conversation.saved.filter((t) => !turns.some((x) => x.q === t.question && x.a.answer === t.answer)).map((t) => ({ q: t.question, a: { question: t.question, answer: t.answer, citations: [], withheld: 0 } }));
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
        <h1 className="sr-only">Lisena, setup</h1>
        <div className="flex justify-center pt-6">
          <button type="button" onClick={stopAll} className="rounded-full outline-none" aria-label="Stop speaking">
            <VoiceOrb state={voice} level={level} size={120} />
          </button>
        </div>
        <div className="flex-1 px-6 pb-10 pt-2">
          <Interview variant="ask" onQuestion={(q) => { if (speakOut) void say(q); }} onExit={() => { stopAll(); setSetup(false); }} />
        </div>
      </div>
    );
  }

  return (
    <div className="-mx-3 -my-4 flex h-[calc(100dvh-3rem)] flex-col overflow-hidden sm:-mx-6 sm:-my-5">
      <h1 className="sr-only">Lisena</h1>

      <div className="flex items-center gap-2 px-6 pt-5 short:pt-3">
        <AskHistory currentId={conversation.id} onOpen={(id) => { reset(); conversation.open(id); }} />
        {(before.length > 0 || turns.length > 0) && (
          <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => { conversation.startOver(); reset(); }}>
            <Plus /> New
          </Button>
        )}
        <VoiceSettings className="ml-auto text-muted-foreground" />
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        <AskChat turns={chat} className={cn("min-h-0 basis-0", stage !== "small" && "pointer-events-none")} style={{ flexGrow: stage === "small" ? 1 : 0, opacity: stage === "small" ? 1 : 0, transition: MOVE }} />
        <div className="basis-0" style={{ flexGrow: stage === "small" ? 0 : 1, transition: MOVE }} />
        <div className="flex shrink-0 flex-col items-center px-6 pb-4 text-center">
          <div className="relative">
            <button type="button" onClick={tap} className="rounded-full outline-none focus-visible:ring-4 focus-visible:ring-ring/40" aria-label={voice === "listening" ? "Stop listening" : voice === "idle" ? "Talk to Lisena" : "Stop"}>
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
              <input value={text} onChange={(e) => setDraft(e.target.value)} onKeyDown={(e) => { if (e.key === "Escape") { setTyping(false); setDraft(""); } }} placeholder="Ask anything" aria-label="Question" autoFocus className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
              <Button type="submit" size="icon-sm" className="rounded-full" disabled={!text.trim() || voice === "thinking"} aria-label="Ask"><Send /></Button>
              <Button type="button" size="icon-sm" variant="ghost" className="rounded-full text-muted-foreground" onClick={() => { setTyping(false); setDraft(""); }} aria-label="Close typing"><X /></Button>
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
                  <button key={s} type="button" onClick={() => ask(s)} className="rounded-full border bg-surface px-3 py-1 text-xs transition-colors hover:bg-accent">
                    {s}
                  </button>
                ))}
                <button type="button" onClick={() => run("/setup")} className="rounded-full border border-dashed px-3 py-1 font-mono text-xs text-muted-foreground transition-colors hover:bg-accent hover:text-foreground">
                  /setup
                </button>
              </div>
            </div>
          )}
          {(notice || note) && <p className="mt-4 text-sm text-warn-fg">{notice || note}</p>}
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
            <input value={text} onChange={(e) => setDraft(e.target.value)} placeholder={voice === "listening" ? "Listening…" : "Ask anything, or type /"} aria-label="Question" autoFocus className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
            <Button type="submit" size="icon" className="rounded-full" disabled={!text.trim() || voice === "thinking"} aria-label="Ask"><Send /></Button>
            {supported && <Button type="button" size="icon" variant="ghost" className="rounded-full" onClick={() => setTyping(false)} aria-label="Use voice"><Mic /></Button>}
          </form>
        ) : (
          <>
            <Button variant="ghost" size="icon" className="rounded-full text-muted-foreground" onClick={() => setTyping(true)} aria-label="Type instead"><Keyboard /></Button>
            <Button size="icon" className={cn("size-16 rounded-full shadow-lg shadow-primary/25", voice === "listening" && "animate-pulse")} onClick={tap} aria-label={voice === "listening" ? "Stop listening" : voice === "idle" ? "Talk" : "Stop"}>
              {voice !== "idle" ? <Square className="size-5" /> : <Mic className="size-6" />}
            </Button>
            <AskUpload onDone={onFiled} />
          </>
        )}
      </div>
      )}
    </div>
  );
}

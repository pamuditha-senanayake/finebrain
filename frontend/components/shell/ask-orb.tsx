"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { AskAnswer } from "@/contracts";
import { VoiceOrb, type VoiceState } from "@/features/l1/voice-orb";
import { useAsk } from "@/lib/api/conversation";
import { findPage } from "@/lib/ask-go";
import { useCurrentUser } from "@/lib/auth";
import { guideFor } from "@/lib/page-context";
import { snapshotPage } from "@/lib/page-snapshot";
import { useUi } from "@/lib/store";
import { canRecord, openMic, recordQuestion, transcribe } from "@/lib/voice/mic";
import { shortOf, speak, unlockAudio } from "@/lib/voice/speaker";
import { AskBubble } from "./ask-bubble";
import { AskHint } from "./ask-hint";

export type Exchange = { id: number; q: string; a: AskAnswer | null };

/** How many exchanges the bubble keeps; older ones scroll up, and the full history is on the Ask the Brain page. */
const KEEP = 20;

/**
 * Ask the Brain, floating on every page as a glowing orb. Click it or press ⌘J (Ctrl+J) and a bubble opens above it.
 * Every question carries what is on screen, so "what does this mean?" just works. Answers come back as short bubbles;
 * the full history is on the Ask the Brain page. It steps aside on that page and in Workflow Studio.
 */
export function AskOrb() {
  const open = useUi((s) => s.askOpen);
  const setOpen = useUi((s) => s.setAskOpen);
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useCurrentUser();
  const ask = useAsk();
  const [voice, setVoice] = useState<VoiceState>("idle");
  const [items, setItems] = useState<Exchange[]>([]);
  const [note, setNote] = useState("");
  const level = useRef(0);
  const seq = useRef(0);
  const recording = useRef<{ stop: () => void } | null>(null);
  const playback = useRef<{ stop: () => void } | null>(null);
  const hidden = pathname.startsWith("/studio") || pathname.startsWith("/l1/ask");

  // ⌘J or Ctrl+J opens and closes it from anywhere; Esc closes it.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "j") {
        e.preventDefault();
        setOpen(!useUi.getState().askOpen);
      } else if (e.key === "Escape" && useUi.getState().askOpen) setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [setOpen]);

  // Closing stops any listening or speaking.
  useEffect(() => {
    if (open) return;
    recording.current?.stop();
    playback.current?.stop();
  }, [open]);

  async function send(question: string, spoken: boolean) {
    const q = question.trim();
    if (!q || ask.isPending) return;
    unlockAudio();
    const id = ++seq.current;
    setNote("");
    // "Go to the library" goes there at once; no model call.
    const page = findPage(q, user);
    if (page) {
      const answer: AskAnswer = { question: q, answer: `Opening ${page.label}.`, citations: [], withheld: 0 };
      setItems((list) => [...list.slice(1 - KEEP), { id, q, a: answer }]);
      router.push(page.href);
      setTimeout(() => setOpen(false), 500);
      return;
    }
    setItems((list) => [...list.slice(1 - KEEP), { id, q, a: null }]);
    setVoice("thinking");
    let answer: AskAnswer;
    try {
      answer = await ask.mutateAsync({ question: q, page: { ...snapshotPage(), scope: "page" } });
      setItems((list) => list.map((x) => (x.id === id ? { ...x, a: answer } : x)));
    } catch {
      setItems((list) => list.filter((x) => x.id !== id));
      setNote("The brain could not answer, sir. Please try again.");
      setVoice("idle");
      return;
    }
    if (!spoken) return setVoice("idle");
    try {
      setVoice("speaking");
      const p = await speak(shortOf(answer.answer).short, level);
      playback.current = p;
      await p.done;
    } catch {
      // The answer is on screen; a reply that cannot be spoken is not an error worth showing.
    } finally {
      playback.current = null;
      setVoice("idle");
    }
  }

  /** Talk instead of typing: records one question, ElevenLabs turns it into words, and the reply is spoken. */
  async function listen() {
    if (voice === "listening") return recording.current?.stop();
    unlockAudio();
    playback.current?.stop();
    if (!canRecord()) return setNote("Voice is not available in this browser, sir. Please type.");
    setNote("");
    setVoice("listening");
    const mic = await openMic(level);
    if (!mic) {
      setNote("The microphone is blocked, sir. Allow it in the browser.");
      return setVoice("idle");
    }
    const take = recordQuestion(mic, level);
    recording.current = take;
    const audio = await take.done;
    recording.current = null;
    if (!audio) {
      setNote("I did not hear anything, sir.");
      return setVoice("idle");
    }
    setVoice("thinking");
    try {
      const words = await transcribe(audio);
      if (!words) throw new Error("no words");
      void send(words, true);
    } catch {
      setNote("I could not make that out, sir. Please try again.");
      setVoice("idle");
    }
  }

  if (hidden) return null;
  return (
    <div data-ask-ignore>
      {open && (
        <AskBubble items={items} voice={voice} note={note} suggestions={guideFor(pathname).suggestions.slice(0, 2)} onSend={(q) => void send(q, false)} onMic={() => void listen()} onClose={() => setOpen(false)} />
      )}
      {!open && <AskHint />}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        aria-label="Ask the Brain"
        aria-expanded={open}
        title="Ask the Brain (⌘J)"
        className="fixed bottom-4 right-4 z-40 grid size-16 place-items-center rounded-full outline-none transition-transform hover:scale-105 focus-visible:ring-4 focus-visible:ring-ring/40 sm:bottom-6 sm:right-6"
      >
        <VoiceOrb state={voice} level={level} size={52} />
      </button>
    </div>
  );
}

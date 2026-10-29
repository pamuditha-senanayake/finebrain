"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { VoiceOrb } from "@/features/l1/voice-orb";
import { openAddDocument, wantsUpload } from "@/features/l2/add-document";
import { findPage, pagesFor } from "@/lib/ask-go";
import { useCurrentUser } from "@/lib/auth";
import { guideFor } from "@/lib/page-context";
import { useUi } from "@/lib/store";
import { level, listen, send, setRoute, stopListening, tap, useVoice } from "@/lib/voice/agent";
import { cn } from "@/lib/utils";
import { AskBubble } from "./ask-bubble";
import { useTalkKey } from "./voice-settings";

// Config
const HOLD_MS = 250; // holding the talk key this long starts listening; a shorter tap toggles listening instead

/**
 * Lisena, floating on every page as a glowing orb. Click it or press ⌘J (Ctrl+J) and a bubble opens above it.
 * Hold Option (Alt) on any page to talk. The voice lives in lib/voice/agent.ts, so a reply keeps going across pages,
 * and the orb pulses while Lisena listens, thinks or speaks with the bubble closed. It steps aside on the Lisena page.
 */
export function AskOrb() {
  const open = useUi((s) => s.askOpen);
  const setOpen = useUi((s) => s.setAskOpen);
  const pathname = usePathname();
  const router = useRouter();
  const { user } = useCurrentUser();
  const voice = useVoice((s) => s.voice);
  const items = useVoice((s) => s.items);
  const note = useVoice((s) => s.note);
  const talkKey = useTalkKey();
  const busy = voice !== "idle";
  const hidden = pathname.startsWith("/l1/ask") || (pathname.startsWith("/studio") && !busy);

  // "Go to the library", said or typed anywhere, opens that page; the page names also help fix misheard words
  useEffect(() => {
    setRoute((q) => {
      // "Upload a meeting transcript" opens the guided intake wherever you are
      if (wantsUpload(q)) return openAddDocument(), "Add a document";
      const page = findPage(q, user);
      if (page) router.push(page.href);
      return page?.label ?? null;
    }, pagesFor(user).map((page) => page.label));
  }, [router, user]);

  // ⌘J or Ctrl+J opens and closes the bubble; Esc closes it
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

  usePushToTalk();

  return (
    <div data-ask-ignore>
      {open && !hidden && (
        <AskBubble items={items} voice={voice} note={note} suggestions={guideFor(pathname).suggestions.slice(0, 2)} onSend={(q) => void send(q)} onMic={tap} onClose={() => setOpen(false)} />
      )}
      {!hidden && (
        <button
          type="button"
          onClick={() => setOpen(!open)}
          aria-label={busy ? `Lisena, ${voice}` : "Lisena"}
          aria-expanded={open}
          title={`Lisena (⌘J). Hold ${talkKey} to talk.`}
          className="fixed bottom-4 right-4 z-40 grid size-16 place-items-center rounded-full outline-none transition-transform hover:scale-105 focus-visible:ring-4 focus-visible:ring-ring/40 sm:bottom-6 sm:right-6"
        >
          {/* With the bubble closed, a soft ring pulses while she is busy, so the conversation is never lost from view */}
          {busy && !open && <span aria-hidden className={cn("absolute inset-1 rounded-full bg-primary/30", voice === "listening" ? "animate-ping" : "animate-pulse")} />}
          <VoiceOrb state={voice} level={level} size={52} />
        </button>
      )}
    </div>
  );
}

/** Hold Option (Alt) to talk, let go to send. A quick tap starts listening until a pause. Option with another key is left alone. */
function usePushToTalk() {
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let holding = false;
    const cancel = () => {
      if (timer) clearTimeout(timer);
      timer = null;
    };
    const onDown = (e: KeyboardEvent) => {
      if (e.key !== "Alt") return cancel(); // Alt+Tab or a shortcut: not a talk
      if (e.repeat || e.metaKey || e.ctrlKey || e.shiftKey || timer || holding) return;
      timer = setTimeout(() => ((timer = null), (holding = true), void listen(true)), HOLD_MS);
    };
    const onUp = (e: KeyboardEvent) => {
      if (e.key !== "Alt") return;
      e.preventDefault(); // stops Windows browsers focusing their menu bar on a lone Alt
      if (holding) {
        holding = false;
        return stopListening();
      }
      if (!timer) return;
      cancel();
      tap();
    };
    const onBlur = () => {
      cancel();
      if (!holding) return;
      holding = false;
      stopListening();
    };
    window.addEventListener("keydown", onDown);
    window.addEventListener("keyup", onUp);
    window.addEventListener("blur", onBlur);
    return () => (window.removeEventListener("keydown", onDown), window.removeEventListener("keyup", onUp), window.removeEventListener("blur", onBlur));
  }, []);
}

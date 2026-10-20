"use client";

import { ArrowUp, Mic, Square } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useRef, useState, type ReactNode } from "react";
import type { AskAnswer } from "@/contracts";
import { Button } from "@/components/ui/button";
import type { VoiceState } from "@/features/l1/voice-orb";
import { date } from "@/lib/format";
import { lookedInLabel } from "@/lib/looked-in";
import { t } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { shortOf } from "@/lib/voice/speaker";
import { ShowMe } from "./show-me";
import type { Exchange } from "./ask-orb";

type Props = {
  items: Exchange[];
  voice: VoiceState;
  note: string;
  suggestions: string[];
  onSend: (q: string) => void;
  onMic: () => void;
  onClose: () => void;
};

/** The bubbles above the orb: a greeting or the recent exchanges (scroll up for older ones), a one-line composer, and the way to the full chat. */
export function AskBubble({ items, voice, note, suggestions, onSend, onMic, onClose }: Props) {
  const [q, setQ] = useState("");
  const input = useRef<HTMLInputElement>(null);
  const feed = useRef<HTMLDivElement>(null);
  useEffect(() => input.current?.focus(), []);
  // Keep the newest message in view; older ones scroll away above.
  useEffect(() => feed.current?.scrollTo({ top: feed.current.scrollHeight, behavior: "smooth" }), [items, note]);
  const busy = voice === "thinking";

  function submit(text: string) {
    if (!text.trim() || busy) return;
    setQ("");
    onSend(text);
  }

  return (
    <div role="dialog" aria-label="Ask the Brain" data-ask-ignore className="fixed bottom-24 right-4 isolate z-40 flex max-h-[calc(100dvh-11rem)] w-[min(380px,calc(100vw-2rem))] flex-col gap-3 duration-200 animate-in fade-in slide-in-from-bottom-2 sm:bottom-26 sm:right-6">
      {/* Blurs the page behind the chat out to the screen's right edge, fading only on the other sides, so no box shows. */}
      <div aria-hidden className="pointer-events-none absolute -bottom-6 -left-14 -right-6 -top-4 -z-10 bg-background/30 backdrop-blur-md" style={BLUR_EDGES} />
      <div ref={feed} className="scrollbar-thin flex min-h-0 flex-col gap-3 overflow-y-auto pr-1" aria-live="polite">
      {items.length === 0 && (
        <Blob>
          <p className="text-[15px] font-medium">{t("ask.greetingAsk")}</p>
          <div className="mt-3 flex flex-wrap gap-2">
            {suggestions.map((s) => (
              <button key={s} type="button" onClick={() => submit(s)} className="rounded-full border bg-surface px-3 py-1.5 text-sm transition-colors hover:bg-accent">{s}</button>
            ))}
          </div>
        </Blob>
      )}
      {items.map((x) => (
        <Fragment key={x.id}>
          <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-[color-mix(in_oklch,var(--primary)_12%,var(--card))] px-4 py-2 text-[15px] shadow-sm">{x.q}</p>
          {x.a ? <AnswerBlob a={x.a} /> : <Blob><Thinking /></Blob>}
        </Fragment>
      ))}
      {note && <p className="px-2 text-sm text-warn-fg">{note}</p>}
      </div>
      <form className="flex items-center gap-1 rounded-full border bg-card p-1.5 pl-4 shadow-xl" onSubmit={(e) => { e.preventDefault(); submit(q); }}>
        <input ref={input} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask about this page…" aria-label="Question" className="min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground" />
        <Button type="button" size="icon-sm" variant="ghost" className={cn("rounded-full", voice === "listening" && "text-primary")} onClick={onMic} aria-label={voice === "listening" ? "Stop listening" : "Talk"}>
          {voice === "listening" ? <Square /> : <Mic />}
        </Button>
        <Button type="submit" size="icon-sm" className="rounded-full" disabled={!q.trim() || busy} aria-label="Ask"><ArrowUp /></Button>
      </form>
      <div className="flex items-center justify-between px-3 text-xs text-muted-foreground">
        <Link href="/l1/ask" onClick={onClose} className="hover:text-foreground">Open chat</Link>
        <kbd className="font-mono">⌘J</kbd>
      </div>
    </div>
  );
}

function Blob({ children }: { children: ReactNode }) {
  return <div className="max-w-[92%] rounded-3xl rounded-bl-md border bg-card px-5 py-4 shadow-xl">{children}</div>;
}

// Three fades (left, top, bottom) kept where all three overlap; the right side stays fully blurred.
const BLUR_EDGES = {
  maskImage: "linear-gradient(to right, transparent, black 56px), linear-gradient(to bottom, transparent, black 16px), linear-gradient(to top, transparent, black 24px)",
  maskComposite: "intersect",
  WebkitMaskComposite: "source-in",
} as const;

/** The short answer first; the rest and the sources wait behind a click. */
function AnswerBlob({ a }: { a: AskAnswer }) {
  const [more, setMore] = useState(false);
  const [sources, setSources] = useState(false);
  const { short, rest } = shortOf(a.answer);
  return (
    <Blob>
      <p className="text-[15px] leading-relaxed" data-testid="ask-answer">{more ? a.answer : short}</p>
      {(rest || a.citations.length > 0 || a.actions?.length) && (
        <div className="mt-2 flex flex-wrap items-center gap-1">
          <ShowMe answer={a} className="mr-1" />
          {rest && <Button variant="ghost" size="sm" className="-ml-2 text-muted-foreground" onClick={() => setMore(!more)}>{more ? "Less" : "More"}</Button>}
          {a.citations.length > 0 && <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setSources(!sources)}>{sources ? "Hide sources" : `${a.citations.length} ${a.citations.length === 1 ? "source" : "sources"}`}</Button>}
        </div>
      )}
      {sources && (
        <ol className="mt-2 space-y-1.5">
          {a.citations.map((c) => (
            <li key={c.id}>
              <Link href={c.href} className="block rounded-xl border bg-surface px-3 py-2 text-sm hover:border-primary/40">
                <span className="line-clamp-2">{c.label}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">True from {date(c.validFrom)}{c.validTo ? ` to ${date(c.validTo)}` : ""}</span>
              </Link>
            </li>
          ))}
          {a.lookedIn && <li className="px-1 text-xs text-muted-foreground" data-testid="looked-in">{lookedInLabel(a.lookedIn)}</li>}
        </ol>
      )}
    </Blob>
  );
}

function Thinking() {
  return (
    <span className="flex gap-1.5 py-1" role="status" aria-label="Thinking">
      {[0, 1, 2].map((i) => <span key={i} className="size-2 animate-bounce rounded-full bg-primary/70" style={{ animationDelay: `${i * 120}ms` }} />)}
    </span>
  );
}

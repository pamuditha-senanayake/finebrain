"use client";

// ask-chat.tsx: the chat on Ask the Brain, old messages first and the newest last, above the orb.
// Used by: ask-voice.tsx.

import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { AskAnswer } from "@/contracts";
import { ShowMe } from "@/components/shell/show-me";
import { Button } from "@/components/ui/button";
import { date } from "@/lib/format";
import { lookedInLabel } from "@/lib/looked-in";
import { cn } from "@/lib/utils";
import { shortOf } from "@/lib/voice/speaker";

export type Turn = { q: string; a: AskAnswer };

/** Questions on the right, answers on the left. Only the newest answer has More and sources. No scrollbar shows. */
export function AskChat({ turns, className, style }: { turns: Turn[]; className?: string; style?: CSSProperties }) {
  const list = useRef<HTMLDivElement>(null);
  // Keep the newest message in view, like any chat.
  useEffect(() => {
    list.current?.scrollTo({ top: list.current.scrollHeight, behavior: "smooth" });
  }, [turns.length]);

  return (
    <div ref={list} className={cn("scrollbar-none overflow-y-auto", className)} style={style}>
      <ol className="mx-auto flex w-full max-w-2xl flex-col gap-4 px-6 py-4" aria-label="Chat">
        {turns.map((turn, i) => (
          <li key={i} className="flex flex-col gap-2">
            <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary/10 px-4 py-2 text-[15px]">{turn.q}</p>
            {i === turns.length - 1 ? <NewestAnswer a={turn.a} /> : <p className="max-w-[92%] rounded-3xl rounded-bl-md border bg-card px-5 py-3 text-[15px] leading-relaxed">{turn.a.answer}</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

/** The newest answer: the short version first; the rest and the sources wait behind a click. */
function NewestAnswer({ a }: { a: AskAnswer }) {
  const [more, setMore] = useState(false);
  const [sources, setSources] = useState(false);
  const { short, rest } = shortOf(a.answer);
  const count = a.citations.length;

  return (
    <div className="max-w-[92%] rounded-3xl rounded-bl-md border bg-card px-5 py-3 animate-in fade-in duration-500">
      <p className="text-[15px] leading-relaxed" data-testid="ask-voice-answer">{more ? a.answer : short}</p>
      <div className="-ml-2 mt-2 flex flex-wrap items-center gap-1">
        <ShowMe answer={a} className="mr-1" />
        {rest && <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setMore(!more)} aria-expanded={more}>{more ? "Less" : "More"}</Button>}
        {count > 0 && <Button variant="ghost" size="sm" className="text-muted-foreground" onClick={() => setSources(!sources)} aria-expanded={sources}>{sources ? "Hide sources" : `${count} ${count === 1 ? "source" : "sources"}`}</Button>}
      </div>
      {sources && (
        <ol className="mt-2 space-y-2">
          {a.citations.map((c, i) => (
            <li key={c.id}>
              <Link href={c.href} className="block rounded-xl border bg-surface px-4 py-3 text-sm hover:border-primary/40">
                <span className="font-medium">{i + 1}. {c.label}</span>
                <span className="mt-0.5 block text-xs text-muted-foreground">True from {date(c.validFrom)}{c.validTo ? ` to ${date(c.validTo)}` : ""}</span>
              </Link>
            </li>
          ))}
          {a.lookedIn && <li className="px-1 text-xs text-muted-foreground" data-testid="looked-in">{lookedInLabel(a.lookedIn)}</li>}
        </ol>
      )}
    </div>
  );
}

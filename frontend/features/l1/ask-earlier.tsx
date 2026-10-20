"use client";

// ask-earlier.tsx: the earlier chat on Ask the Brain, in a side sheet so the main view never grows.
// Used by: ask-voice.tsx.

import type { AskAnswer } from "@/contracts";
import { Sheet, SheetContent, SheetHeader, SheetTitle } from "@/components/ui/sheet";

type Turn = { q: string; a: AskAnswer };

/** Earlier questions and answers, oldest first, in a sheet from the right. */
export function AskEarlier({ turns, open, onOpenChange }: { turns: Turn[]; open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Sheet open={open} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-lg">
        <SheetHeader className="border-b p-6">
          <SheetTitle className="text-lg">Earlier</SheetTitle>
        </SheetHeader>
        <ol className="flex flex-col gap-4 p-6" aria-label="Earlier chat">
          {turns.map((t, i) => (
            <li key={i} className="flex flex-col gap-2">
              <p className="ml-auto max-w-[85%] rounded-2xl rounded-br-md bg-primary/10 px-4 py-2 text-[15px]">{t.q}</p>
              <p className="max-w-[92%] rounded-3xl rounded-bl-md border bg-card px-5 py-3 text-[15px] leading-relaxed">{t.a.answer}</p>
            </li>
          ))}
        </ol>
      </SheetContent>
    </Sheet>
  );
}

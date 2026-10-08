"use client";

import { Lock, Send, Sparkles } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Textarea } from "@/components/ui/textarea";
import { ThinkingOrb } from "@/components/brain/motion";
import { useAsk } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date } from "@/lib/format";
import { t } from "@/lib/i18n";
import { useUi } from "@/lib/store";

const SUGGESTIONS = ["What is our refund window?", "When does the finebase.lk domain renew?", "What are support hours?", "What is the VAT registration status?"];

export function AskPanel() {
  const open = useUi((s) => s.askOpen);
  const setOpen = useUi((s) => s.setAskOpen);
  const [q, setQ] = useState("");
  const ask = useAsk();
  const { user } = useCurrentUser();
  const submit = (question: string) => {
    if (!question.trim()) return;
    setQ(question);
    ask.mutate(question);
  };
  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetContent className="w-full gap-0 sm:max-w-md">
        <SheetHeader className="border-b">
          <SheetTitle className="flex items-center gap-2">
            <Sparkles className="size-4 text-primary" /> {t("shell.ask")}
          </SheetTitle>
          <SheetDescription>Plain answers with citations. Uses only what {user?.name ?? "you"} may see, and shows when each fact is true.</SheetDescription>
        </SheetHeader>
        <div className="flex-1 space-y-4 overflow-auto p-4" aria-live="polite">
          {!ask.data && !ask.isPending && (
            <div className="space-y-2">
              <p className="text-xs text-muted-foreground">Try:</p>
              {SUGGESTIONS.map((s) => (
                <button key={s} type="button" onClick={() => submit(s)} className="block w-full rounded-lg border px-3 py-2 text-left text-sm hover:bg-accent">
                  {s}
                </button>
              ))}
            </div>
          )}
          {ask.isPending && (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <ThinkingOrb kind="retrieval" /> Retrieving facts you may see…
            </div>
          )}
          {ask.error && <p className="text-sm text-risk">{ask.error.message}</p>}
          {ask.data && (
            <div className="space-y-3">
              <p className="text-xs text-muted-foreground">{ask.data.question}</p>
              <p className="text-sm leading-relaxed" data-testid="ask-answer">
                {ask.data.answer}
                {ask.data.citations.map((c, i) => (
                  <sup key={c.id} className="ml-0.5 font-mono text-[10px] text-primary">
                    [{i + 1}]
                  </sup>
                ))}
              </p>
              {ask.data.citations.length > 0 && (
                <ol className="space-y-1.5">
                  {ask.data.citations.map((c, i) => (
                    <li key={c.id} className="rounded-lg border bg-surface p-2 text-xs">
                      <span className="mr-1 font-mono text-primary">[{i + 1}]</span>
                      <Link href={c.href} className="font-medium hover:underline" onClick={() => setOpen(false)}>
                        {c.label}
                      </Link>
                      <div className="mt-0.5 text-muted-foreground">
                        {c.kind} · true from {date(c.validFrom)}
                        {c.validTo ? ` to ${date(c.validTo)}` : ", still valid"}
                      </div>
                    </li>
                  ))}
                </ol>
              )}
              {ask.data.withheld > 0 && (
                <p className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <Lock className="size-3" /> {ask.data.withheld} matching facts are above your access level and were not used.
                </p>
              )}
            </div>
          )}
        </div>
        <form
          className="flex items-end gap-2 border-t p-3"
          onSubmit={(e) => {
            e.preventDefault();
            submit(q);
          }}
        >
          <Textarea value={q} onChange={(e) => setQ(e.target.value)} placeholder="Ask a question about the company" aria-label="Question" className="min-h-10 resize-none" rows={1} onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && (e.preventDefault(), submit(q))} />
          <Button type="submit" size="icon" aria-label="Ask" disabled={ask.isPending}>
            <Send />
          </Button>
        </form>
      </SheetContent>
    </Sheet>
  );
}

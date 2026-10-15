"use client";

import { BookOpen, Eraser, Hammer, MessageSquareText, Send, Sparkles, Wrench, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, type ReactNode } from "react";
import type { ApplyResult, ChatReply, StudioCard, Suggestion, WorkflowDetail } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ThinkingOrb } from "@/components/brain/motion";
import { useStudioChat, useStudioReview } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import type { Highlight } from "@/lib/studio/graph";
import { cn } from "@/lib/utils";
import { KindIcon, MatchCard } from "./cards";
import { ProposalCard } from "./proposal-card";
import { StorySummary } from "./story-card";
import { msgId, useStudio, type ChatMessage, type Focus } from "./state";
import { stepOf } from "./steps";

const EMPTY: ChatMessage[] = [];

/** The first screen offers four ways in, all story first: describe a problem, read the story, fix, build. */
const STARTERS: { icon: LucideIcon; label: string; prompt: string }[] = [
  { icon: MessageSquareText, label: "Describe a problem", prompt: "The problem is …" },
  { icon: BookOpen, label: "What problem does this workflow solve?", prompt: "What problem does this workflow solve?" },
  { icon: Wrench, label: "What is broken right now?", prompt: "What is broken in this workflow?" },
  { icon: Hammer, label: "What should we build next?", prompt: "What should we build next?" },
];

/** The story the chat drafted last and is waiting on: it goes back with the next message so the person can confirm it. */
function openDraft(thread: ChatMessage[]) {
  for (let i = thread.length - 1; i >= 0; i--) {
    const m = thread[i];
    if (m.role === "assistant") return m.reply.story;
  }
  return null;
}

export function StudioChat({
  workflowId,
  detail,
  focus,
  now,
  onFocus,
  onSwitch,
  onShowDiagram,
  toolbar,
}: {
  workflowId: string;
  detail: WorkflowDetail | undefined;
  focus: Focus;
  now: number;
  onFocus: (f: Focus) => void;
  onSwitch: (workflowId: string) => void;
  onShowDiagram: (h: Highlight) => void;
  toolbar?: ReactNode;
}) {
  const thread = useStudio((s) => s.threads[workflowId] ?? EMPTY);
  const push = useStudio((s) => s.push);
  const patch = useStudio((s) => s.patch);
  const clear = useStudio((s) => s.clear);
  const draft = useStudio((s) => s.draft);
  const setDraft = useStudio((s) => s.setDraft);
  const setStep = useStudio((s) => s.setStep);
  const chat = useStudioChat();
  const rev = useStudioReview();
  const { user } = useCurrentUser();
  const endRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);
  const busy = chat.isPending || rev.isPending;

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [thread.length, busy]);

  useEffect(() => {
    if (draft) inputRef.current?.focus();
  }, [draft]);

  const receive = (reply: ChatReply) => {
    const target = reply.workflowId ?? workflowId;
    push(target, { id: msgId(), role: "assistant", reply });
    if (reply.focus) onFocus(reply.focus);
    // A new part has no id to focus yet, so turn the parts pane to its step instead.
    const step = reply.proposal && reply.proposal.input.kind !== "workflow" ? stepOf(reply.proposal.input.kind) : null;
    if (step && !reply.focus) setStep(target, step);
    if (reply.story || reply.proposal?.input.patch.story) setStep(target, "story");
    if (reply.workflowId && reply.workflowId !== workflowId) onSwitch(reply.workflowId);
  };
  const fail = (e: unknown) => push(workflowId, { id: msgId(), role: "notice", tone: "risk", text: e instanceof Error ? e.message : "The assistant could not answer." });

  const send = (text: string) => {
    const message = text.trim();
    if (!message || busy) return;
    setDraft("");
    push(workflowId, { id: msgId(), role: "user", text: message });
    const history: { role: "user" | "assistant"; text: string }[] = [];
    for (const m of thread.slice(-6)) {
      if (m.role === "user") history.push({ role: "user", text: m.text });
      else if (m.role === "assistant") history.push({ role: "assistant", text: m.reply.answer });
    }
    chat.mutate({ workflowId, message, focus, history, story: openDraft(thread) }, { onSuccess: receive, onError: fail });
  };

  const pick = (s: Suggestion) => {
    if (busy) return;
    if (s.input) {
      push(workflowId, { id: msgId(), role: "user", text: s.label });
      rev.mutate({ input: s.input, workflowId }, { onSuccess: receive, onError: fail });
    } else if (s.prompt.includes("…")) {
      setDraft(s.prompt);
    } else send(s.prompt);
  };

  const applied = (messageId: string, r: ApplyResult) => {
    patch(workflowId, messageId, (m) => (m.role === "assistant" ? { ...m, applied: r } : m));
    push(workflowId, { id: msgId(), role: "notice", tone: r.status === "applied" ? "ok" : "info", text: r.message, href: r.changeRequestId ? `/l2/versioning/${r.changeRequestId}` : undefined });
    // A new workflow from a confirmed story: open it and ask what to build first, so the story carries on there.
    if (r.status === "applied" && r.targetId.startsWith("wf-") && r.targetId !== workflowId) {
      const next = r.targetId;
      const ask = "What should we build first?";
      onSwitch(next);
      setStep(next, "story");
      push(next, { id: msgId(), role: "user", text: ask });
      // A promise, not mutate callbacks: this chat unmounts while the new workflow loads, and callbacks would be dropped.
      chat.mutateAsync({ workflowId: next, message: ask, focus: null, history: [], story: null }).then((reply) => push(next, { id: msgId(), role: "assistant", reply }), (e) => push(next, { id: msgId(), role: "notice", tone: "risk", text: e instanceof Error ? e.message : "The assistant could not answer." }));
      return;
    }
    if (r.status === "applied" && r.targetId) {
      const it = detail?.items.find((i) => i.id === r.targetId);
      onFocus(it ? { kind: it.kind, id: it.id } : r.targetId.startsWith("wf-") ? { kind: "workflow", id: r.targetId } : focus);
    }
  };

  const openCard = (c: StudioCard) => onFocus({ kind: c.kind, id: c.targetId });
  const focused = focus && focus.kind !== "workflow" ? detail?.items.find((i) => i.id === focus.id) ?? null : null;

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex items-center gap-2 border-b px-4 py-3">
        {toolbar}
        {user?.tier === "L2" && <span className="truncate text-[11px] text-muted-foreground">Changes go to approval</span>}
        {thread.length > 0 && (
          <Button size="xs" variant="ghost" className="ml-auto text-muted-foreground" onClick={() => clear(workflowId)} aria-label="Clear conversation">
            <Eraser /> Clear
          </Button>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-6 overflow-y-auto px-4 py-6" aria-live="polite">
        {thread.length === 0 && (
          <div className="mx-auto flex min-h-full max-w-md flex-col justify-center py-6">
            <h2 className="text-2xl font-semibold tracking-tight">Start with the problem</h2>
            <p className="mt-2 text-base leading-relaxed text-muted-foreground">Tell me what goes wrong today. I turn it into cases, then into the workflow.</p>
            <div className="mt-8 space-y-2.5">
              {STARTERS.map((s) => (
                <button
                  key={s.label}
                  type="button"
                  disabled={busy}
                  onClick={() => pick({ label: s.label, prompt: s.prompt, tone: "neutral" })}
                  className="group flex w-full items-center gap-3.5 rounded-xl border bg-surface px-4 py-3.5 text-left text-[15px] transition-colors hover:border-foreground/20 hover:bg-accent disabled:opacity-50"
                >
                  <s.icon className="size-[18px] shrink-0 text-muted-foreground group-hover:text-foreground" aria-hidden />
                  <span className="flex-1">{s.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}

        {thread.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[85%] rounded-2xl rounded-br-md bg-primary px-4 py-2.5 text-[15px] leading-relaxed text-primary-foreground">{m.text}</div>
            </div>
          ) : m.role === "notice" ? (
            <div key={m.id} className={cn("mx-auto w-fit max-w-[90%] rounded-full border px-3.5 py-1.5 text-center text-xs", m.tone === "ok" ? "border-ok/40 bg-ok/10 text-ok" : m.tone === "risk" ? "border-risk/40 bg-risk/10 text-risk" : "bg-surface text-muted-foreground")} role="status">
              {m.text}{" "}
              {m.href && (
                <Link href={m.href} className="font-medium underline">
                  Open
                </Link>
              )}
            </div>
          ) : (
            <div key={m.id} className="flex gap-3">
              <span className="mt-0.5 grid size-8 shrink-0 place-items-center rounded-full bg-primary/10" aria-hidden>
                <Sparkles className="size-4 text-primary" />
              </span>
              <div className="min-w-0 flex-1 space-y-3">
                <p className="text-[15px] leading-relaxed">{m.reply.answer}</p>
                {m.reply.story && <StorySummary story={m.reply.story.story} />}
                {m.reply.bullets.length > 0 && (
                  <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground marker:text-border">
                    {m.reply.bullets.map((b, i) => (
                      <li key={i} className="break-words">{b}</li>
                    ))}
                  </ul>
                )}
                {m.reply.cards.length > 0 && (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                    {m.reply.cards.slice(0, 4).map((c) => (
                      <MatchCard key={c.id} card={c} now={now} onOpen={openCard} />
                    ))}
                  </div>
                )}
                {m.reply.proposal && <ProposalCard proposal={m.reply.proposal} detail={detail} applied={m.applied} onApplied={(r) => applied(m.id, r)} onFix={pick} onShowDiagram={onShowDiagram} />}
                {m.reply.suggestions.length > 0 && !m.applied && (
                  <div className="flex flex-wrap gap-2">
                    {m.reply.suggestions.map((s) => (
                      <SuggestionChip key={s.label} s={s} onPick={pick} disabled={busy} />
                    ))}
                  </div>
                )}
              </div>
            </div>
          ),
        )}

        {busy && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground" role="status">
            <ThinkingOrb kind={rev.isPending ? "judgment" : "retrieval"} size={14} />
            {rev.isPending ? "The Edit Review Agent is checking the whole workflow…" : "Reading the workflow…"}
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="border-t px-4 py-3"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
        {focused && (
          <div className="mb-2 flex items-center gap-1.5 text-xs text-muted-foreground">
            <span>About</span>
            <span className="inline-flex max-w-[70%] items-center gap-1.5 rounded-full border bg-surface py-0.5 pl-2 pr-1 text-foreground">
              <KindIcon kind={focused.kind} className="size-3" />
              <span className="truncate">{focused.name}</span>
              <button type="button" className="grid size-4 place-items-center rounded-full hover:bg-accent" onClick={() => onFocus(null)} aria-label="Stop focusing this part">
                <X className="size-3" />
              </button>
            </span>
          </div>
        )}
        <div className="flex items-end gap-2">
          <Textarea
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                send(draft);
              }
            }}
            placeholder={user?.tier === "L3" ? "Ask, or suggest a change…" : focused ? `What should change in ${focused.name}?` : "Describe a change, or ask anything…"}
            className="max-h-40 min-h-12 resize-none text-[15px]"
            aria-label="Message the studio assistant"
          />
          <Button type="submit" size="icon" disabled={!draft.trim() || busy} aria-label="Send">
            <Send />
          </Button>
        </div>
      </form>
    </div>
  );
}

function SuggestionChip({ s, onPick, disabled }: { s: Suggestion; onPick: (s: Suggestion) => void; disabled?: boolean }) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={() => onPick(s)}
      className={cn(
        "inline-flex max-w-full items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-left text-sm transition-colors disabled:opacity-50",
        s.tone === "primary" ? "border-primary/50 bg-primary/10 text-foreground hover:bg-primary/15" : s.tone === "fix" ? "border-warn/50 bg-warn/10 hover:bg-warn/20" : "bg-surface hover:bg-accent",
      )}
    >
      {s.tone === "fix" && <Wrench className="size-3 shrink-0" aria-hidden />}
      <span className="truncate">{s.label}</span>
    </button>
  );
}

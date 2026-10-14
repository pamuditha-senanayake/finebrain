"use client";

import { Eraser, Send, Sparkles, Wrench } from "lucide-react";
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
import { MatchCard } from "./cards";
import { ProposalCard } from "./proposal-card";
import { msgId, useStudio, type ChatMessage, type Focus } from "./state";

const EMPTY: ChatMessage[] = [];

function starters(detail: WorkflowDetail | undefined): Suggestion[] {
  const items = detail?.items ?? [];
  const policy = items.find((i) => i.kind === "policy");
  const skill = items.find((i) => i.kind === "skill");
  return [
    { label: "What is broken in this workflow?", prompt: "What is broken in this workflow?", tone: "fix" },
    ...(policy ? [{ label: `Make ${policy.name} stricter`, prompt: `Make ${policy.name} stricter`, tone: "primary" as const }] : []),
    ...(skill ? [{ label: `Tell me about ${skill.name}`, prompt: `Tell me about ${skill.name}`, tone: "neutral" as const }] : []),
    { label: "Add a scheduler", prompt: `Add a scheduler that runs ${skill?.name.toLowerCase() ?? "a skill"} every weekday at 8am`, tone: "neutral" },
    { label: "Rewrite the workflow description", prompt: "Improve the description of this workflow", tone: "neutral" },
    { label: "Which tools are shared?", prompt: "Which tools are shared?", tone: "neutral" },
    { label: policy ? `What changed in ${policy.name}?` : "What can you do?", prompt: policy ? `What changed in ${policy.name}?` : "help", tone: "neutral" },
  ];
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
    chat.mutate({ workflowId, message, focus, history }, { onSuccess: receive, onError: fail });
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
    if (r.status === "applied" && r.targetId) {
      const it = detail?.items.find((i) => i.id === r.targetId);
      onFocus(it ? { kind: it.kind, id: it.id } : r.targetId.startsWith("wf-") ? { kind: "workflow", id: r.targetId } : focus);
    }
  };

  const openCard = (c: StudioCard) => onFocus({ kind: c.kind, id: c.targetId });

  return (
    <div className="flex h-full min-h-0 flex-col bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b px-3 py-2">
        <Sparkles className="size-4 text-primary" aria-hidden />
        <div className="min-w-0 flex-1">
          <h2 className="text-sm font-semibold">Studio assistant</h2>
          <p className="truncate text-[11px] text-muted-foreground">Say what you want changed. Every edit is checked by the Edit Review Agent before anyone confirms it.</p>
        </div>
        {toolbar}
        {thread.length > 0 && (
          <Button size="xs" variant="ghost" onClick={() => clear(workflowId)} aria-label="Clear conversation">
            <Eraser /> Clear
          </Button>
        )}
      </div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto px-3 py-4" aria-live="polite">
        {thread.length === 0 && (
          <div className="mx-auto max-w-2xl py-6 text-center">
            <div className="ambient relative mx-auto mb-3 grid size-12 place-items-center rounded-2xl border bg-surface">
              <Sparkles className="size-5 text-primary" aria-hidden />
            </div>
            <p className="text-sm font-medium">Edit {detail?.workflow.name ?? "this workflow"} by talking it through</p>
            <p className="mt-1 text-xs text-muted-foreground">
              Ask about any part, or describe a change loosely: &ldquo;make refunds stricter&rdquo;, &ldquo;move the weekly report to Fridays&rdquo;, &ldquo;add topic churn&rdquo;. I suggest concrete options, show what else it affects, and route it to whoever has to approve.
            </p>
            <div className="mt-4 flex flex-wrap justify-center gap-1.5">
              {starters(detail).map((s) => (
                <SuggestionChip key={s.label} s={s} onPick={pick} disabled={busy} />
              ))}
            </div>
          </div>
        )}

        {thread.map((m) =>
          m.role === "user" ? (
            <div key={m.id} className="flex justify-end">
              <div className="max-w-[80%] rounded-2xl rounded-br-md bg-primary px-3 py-2 text-sm text-primary-foreground">{m.text}</div>
            </div>
          ) : m.role === "notice" ? (
            <div key={m.id} className={cn("mx-auto w-fit max-w-[90%] rounded-full border px-3 py-1 text-center text-[11px]", m.tone === "ok" ? "border-ok/40 bg-ok/10 text-ok" : m.tone === "risk" ? "border-risk/40 bg-risk/10 text-risk" : "bg-surface text-muted-foreground")} role="status">
              {m.text}{" "}
              {m.href && (
                <Link href={m.href} className="font-medium underline">
                  Open
                </Link>
              )}
            </div>
          ) : (
            <div key={m.id} className="flex gap-2.5">
              <span className="mt-0.5 grid size-7 shrink-0 place-items-center rounded-full bg-primary/10" aria-hidden>
                <Sparkles className="size-3.5 text-primary" />
              </span>
              <div className="min-w-0 flex-1 space-y-2.5">
                <p className="text-sm leading-relaxed">{m.reply.answer}</p>
                {m.reply.bullets.length > 0 && (
                  <ul className="list-disc space-y-0.5 pl-5 text-xs text-muted-foreground marker:text-border">
                    {m.reply.bullets.map((b, i) => (
                      <li key={i} className="break-words">{b}</li>
                    ))}
                  </ul>
                )}
                {m.reply.cards.length > 0 && (
                  <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3 2xl:grid-cols-4">
                    {m.reply.cards.slice(0, 4).map((c) => (
                      <MatchCard key={c.id} card={c} now={now} onOpen={openCard} />
                    ))}
                  </div>
                )}
                {m.reply.proposal && <ProposalCard proposal={m.reply.proposal} detail={detail} applied={m.applied} onApplied={(r) => applied(m.id, r)} onFix={pick} onShowDiagram={onShowDiagram} />}
                {m.reply.suggestions.length > 0 && !m.applied && (
                  <div className="flex flex-wrap gap-1.5">
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
          <div className="flex items-center gap-2 text-xs text-muted-foreground" role="status">
            <ThinkingOrb kind={rev.isPending ? "judgment" : "retrieval"} size={14} />
            {rev.isPending ? "The Edit Review Agent is checking the whole workflow…" : "Reading the workflow…"}
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        className="border-t p-2.5"
        onSubmit={(e) => {
          e.preventDefault();
          send(draft);
        }}
      >
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
            placeholder={user?.tier === "L3" ? "Ask about this workflow, or suggest a change for its DRI…" : "Describe a change, or ask about any part of this workflow…"}
            className="max-h-40 min-h-11 resize-none text-sm"
            aria-label="Message the studio assistant"
          />
          <Button type="submit" size="icon" disabled={!draft.trim() || busy} aria-label="Send">
            <Send />
          </Button>
        </div>
        <p className="mt-1 px-1 text-[10px] text-muted-foreground">Enter sends, Shift+Enter adds a line. Nothing changes until you confirm a proposal.</p>
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
        "inline-flex max-w-full items-center gap-1 rounded-full border px-2.5 py-1 text-left text-xs transition-colors disabled:opacity-50",
        s.tone === "primary" ? "border-primary/40 bg-primary/5 text-primary hover:bg-primary/10" : s.tone === "fix" ? "border-warn/50 bg-warn/10 hover:bg-warn/20" : "bg-surface hover:bg-accent",
      )}
    >
      {s.tone === "fix" && <Wrench className="size-3 shrink-0" aria-hidden />}
      <span className="truncate">{s.label}</span>
    </button>
  );
}

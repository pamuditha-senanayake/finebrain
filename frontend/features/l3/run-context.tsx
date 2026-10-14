"use client";

import { useMemo } from "react";
import Link from "next/link";
import type { Conversation, Run } from "@/contracts";
import { useLookup } from "@/components/brain/names";
import { Section, StatusChip } from "@/components/brain/primitives";
import { useConversations } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

/** The person or system a run acted for: the customer when there is a conversation, otherwise the system that triggered it. */
export function useRunContext() {
  const { data } = useConversations();
  return useMemo(() => {
    const byRun = new Map<string, Conversation>();
    const byId = new Map<string, Conversation>();
    for (const c of data ?? []) {
      byRun.set(c.runId, c);
      byId.set(c.id, c);
    }
    const conversationOf = (r: Run): Conversation | null => byRun.get(r.id) ?? (r.conversationId ? byId.get(r.conversationId) ?? null : null);
    // Without a conversation, a customer or lead code in the subject still names who the run was for.
    const actorOf = (r: Run): string => conversationOf(r)?.customer ?? r.subject.match(/\b(?:CUS|LEAD)-\d+/)?.[0] ?? "System";
    return { conversationOf, actorOf };
  }, [data]);
}

/** What the agent was given: who asked, the input, and the conversation so far. */
export function RunInput({ run, conversation, actor, className }: { run: Run; conversation: Conversation | null; actor: string; className?: string }) {
  const lookup = useLookup();
  return (
    <Section title="Input and conversation" className={className}>
      <dl className="mb-3 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-xs">
        <dt className="text-muted-foreground">Actor</dt>
        <dd className="font-medium">{actor}{conversation && <span className="ml-1.5 font-normal text-muted-foreground">via {conversation.channel}</span>}</dd>
        <dt className="text-muted-foreground">Input</dt>
        <dd>{run.subject}</dd>
        {conversation && (
          <>
            <dt className="text-muted-foreground">Topic</dt>
            <dd>{conversation.topic}</dd>
          </>
        )}
      </dl>
      {conversation ? (
        <>
          <ol className="space-y-2.5" aria-label="Conversation">
            {conversation.messages.map((m) => (
              <li key={m.id} className={cn("flex flex-col gap-0.5", m.from === "customer" ? "items-start" : "items-end")}>
                <span className="text-[10px] text-muted-foreground">{m.from === "customer" ? actor : m.author} · {relTime(m.at)}</span>
                <div className={cn("max-w-[92%] rounded-2xl px-3 py-1.5 text-[13px]", m.from === "customer" ? "rounded-bl-md bg-muted" : m.from === "human" ? "rounded-br-md bg-warn/20" : "rounded-br-md bg-primary/12")}>{m.text}</div>
                {m.citations.length > 0 && <span className="text-[10px] text-muted-foreground">cites {m.citations.map((c) => c.label).join(", ")}</span>}
              </li>
            ))}
          </ol>
          <div className="mt-3 flex flex-wrap items-center gap-2 text-xs">
            <StatusChip tone={conversation.status === "human" ? "warn" : conversation.status === "closed" ? "neutral" : "agent"}>{conversation.status === "human" ? `taken over by ${conversation.takenOverBy ? lookup.name(conversation.takenOverBy) : "a person"}` : conversation.status}</StatusChip>
            <Link href={`/l3/conversations/${conversation.id}`} className="text-primary hover:underline">Open the conversation</Link>
          </div>
        </>
      ) : (
        <p className="text-xs text-muted-foreground">No conversation. This run was started by {actor === "System" ? "the system (a schedule or a sensor event)" : actor}, and the input above is everything the agent was given.</p>
      )}
    </Section>
  );
}

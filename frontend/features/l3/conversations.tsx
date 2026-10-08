"use client";

import { Eye, Hand, Lock, MessageSquareReply, Send, Undo2, Wand2, XCircle } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";
import type { Conversation } from "@/contracts";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Beam, ThinkingOrb } from "@/components/brain/motion";
import { AgentChip, useLookup } from "@/components/brain/names";
import { CritBadge, EmptyState, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useConversation, useConversations, useOp } from "@/lib/api/hooks";
import { toast } from "sonner";
import { canView, useCurrentUser } from "@/lib/auth";
import { date, dateTime, relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function ConversationList({ activeId }: { activeId?: string }) {
  const conversations = useConversations();
  return (
    <QueryView query={conversations} rows={5}>
      {(list) => (
        <ul className="space-y-1.5" aria-label="Conversations">
          {[...list]
            .sort((a, b) => (a.updatedAt < b.updatedAt ? 1 : -1))
            .map((c) => {
              const blocked = c.proposedActions.some((p) => p.status === "blocked");
              const escalated = c.messages.some((m) => m.from === "system" && m.text.startsWith("Escalated"));
              return (
                <li key={c.id}>
                  <Link href={`/l3/conversations/${c.id}`} aria-current={c.id === activeId ? "page" : undefined} className={cn("block rounded-lg border bg-card p-2.5 text-sm hover:border-primary/40", c.id === activeId && "border-primary/50 bg-accent/50")}>
                    <div className="flex items-center gap-2">
                      <span className="truncate font-medium">{c.customer.split(" · ")[0]}</span>
                      <span className="text-[10px] uppercase text-muted-foreground">{c.channel}</span>
                      <span className="ml-auto text-[11px] text-muted-foreground">{relTime(c.updatedAt)}</span>
                    </div>
                    <div className="mt-0.5 truncate text-xs text-muted-foreground">{c.topic}</div>
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      <Status value={c.status} />
                      {escalated && c.status === "agent" && <StatusChip tone="warn">escalated</StatusChip>}
                      {blocked && <StatusChip tone="risk">action blocked</StatusChip>}
                      {c.skillifiedTo && <StatusChip tone="info">skillified</StatusChip>}
                    </div>
                  </Link>
                </li>
              );
            })}
        </ul>
      )}
    </QueryView>
  );
}

export function ConversationsIndex() {
  return (
    <div>
      <PageHeader title="Live conversations" description="Customer care transcripts stream in with the agent's reasoning and proposed actions. Take over, hand back, or Skillify what you handled." />
      <div className="grid gap-4 lg:grid-cols-[340px_1fr]">
        <ConversationList />
        <div className="max-lg:hidden">
          <EmptyState title="Pick a conversation" description="Escalated and blocked conversations are marked in the list." />
        </div>
      </div>
    </div>
  );
}

export function ConversationDetailPage() {
  const { id } = useParams<{ id: string }>();
  return (
    <div>
      <PageHeader eyebrow={<Link href="/l3/conversations" className="hover:underline">Live conversations</Link>} title="Conversation" />
      <div className="grid gap-4 lg:grid-cols-[300px_1fr]">
        <div className="max-lg:hidden">
          <ConversationList activeId={id} />
        </div>
        <ConversationDetail id={id} />
      </div>
    </div>
  );
}

function Masked({ conv }: { conv: Conversation }) {
  const [revealed, setRevealed] = useState<string | null>(null);
  const reveal = useOp<{ targetId: string; field: string }>("revealPersonal");
  const [customerId, maskedName] = conv.customer.split(" · ");
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="font-medium">{customerId}</span>
      <span className="text-muted-foreground">{revealed ?? maskedName}</span>
      {!revealed && maskedName && (
        <Button
          size="xs"
          variant="ghost"
          aria-label="Reveal customer name (audited)"
          onClick={() =>
            reveal.mutate(
              { targetId: conv.id, field: "customer name" },
              { onSuccess: (r) => setRevealed((r as { value: string }).value) },
            )
          }
        >
          <Eye /> Reveal
        </Button>
      )}
      {revealed && <Badge variant="outline" className="text-[10px]">revealed and audited</Badge>}
    </span>
  );
}

export function ConversationDetail({ id }: { id: string }) {
  const conversation = useConversation(id);
  const { user } = useCurrentUser();
  const lookup = useLookup();
  const router = useRouter();
  const [text, setText] = useState("");
  const takeover = useOp<{ conversationId: string }>("takeover", { success: "You took over the conversation" });
  const handback = useOp<{ conversationId: string }>("handback", { success: "Handed back to the agent" });
  const send = useOp<{ conversationId: string; text: string }>("sendMessage");
  const close = useOp<{ conversationId: string; note: string }>("closeConversation", { success: "Conversation closed" });
  const skillify = useOp<{ conversationId: string }>("skillify");

  return (
    <QueryView query={conversation}>
      {(c) => {
        const mine = c.status === "human" && c.takenOverBy === user?.id;
        const canAct = !!user;
        return (
          <div className="grid gap-4 xl:grid-cols-[1fr_300px]">
            <Section
              title={c.topic}
              description={<span className="flex flex-wrap items-center gap-2"><Masked conv={c} /> · {c.channel} · <AgentChip id={c.agentId} /></span>}
              actions={<Status value={c.status} />}
            >
              <Beam active={c.status === "agent" && c.messages.some((m) => m.text.startsWith("Escalated"))} className="rounded-xl" color="var(--warn)">
                <ol className="space-y-3 rounded-xl bg-surface/50 p-3" aria-label="Transcript" aria-live="polite">
                  {c.messages.map((m) => (
                    <li key={m.id} className={cn("flex", m.from === "customer" ? "justify-start" : m.from === "system" ? "justify-center" : "justify-end")}>
                      {m.from === "system" ? (
                        <p className="max-w-[85%] rounded-full bg-muted px-3 py-1 text-center text-[11px] text-muted-foreground">{m.text}</p>
                      ) : (
                        <div className={cn("max-w-[85%] rounded-2xl px-3 py-2 text-sm", m.from === "customer" ? "rounded-bl-sm border bg-card" : m.from === "agent" ? "rounded-br-sm bg-agent/10" : "rounded-br-sm bg-primary text-primary-foreground")}>
                          <div className="mb-0.5 text-[10px] font-medium opacity-70">
                            {m.author} · {dateTime(m.at, lookup.tz)}
                          </div>
                          {m.text}
                          {m.citations.length > 0 && (
                            <div className="mt-1.5 flex flex-wrap gap-1">
                              {m.citations.map((ci) => (
                                <Link key={ci.id} href={`/l2/vault?fact=${ci.id}`} className="rounded bg-background/70 px-1.5 py-0.5 text-[10px] text-foreground hover:underline">
                                  {ci.label} · from {date(ci.validFrom, lookup.tz)}
                                </Link>
                              ))}
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  ))}
                  {c.status === "agent" && !c.messages.some((m) => m.text.startsWith("Escalated")) && (
                    <li className="flex items-center justify-end gap-2 text-xs text-muted-foreground">
                      <ThinkingOrb kind="judgment" size={12} /> agent is watching this thread
                    </li>
                  )}
                </ol>
              </Beam>
              {mine ? (
                <form
                  className="mt-3 flex items-end gap-2"
                  onSubmit={(e) => {
                    e.preventDefault();
                    if (!text.trim()) return;
                    send.mutate({ conversationId: c.id, text }, { onSuccess: () => setText("") });
                  }}
                >
                  <Textarea value={text} onChange={(e) => setText(e.target.value)} placeholder="Reply as yourself" aria-label="Reply" rows={2} className="min-h-12" />
                  <Button type="submit" size="icon" aria-label="Send reply" disabled={send.isPending}>
                    <Send />
                  </Button>
                </form>
              ) : (
                c.status === "human" && <p className="mt-3 text-xs text-muted-foreground">{lookup.name(c.takenOverBy ?? "")} is handling this conversation.</p>
              )}
            </Section>
            <div className="space-y-4">
              <Section title="Agent reasoning">
                <p className="text-sm text-muted-foreground">{c.reasoningSummary}</p>
              </Section>
              <Section title="Proposed actions">
                <ul className="space-y-2">
                  {c.proposedActions.length === 0 && <li className="text-xs text-muted-foreground">None</li>}
                  {c.proposedActions.map((p) => (
                    <li key={p.id} className="rounded-lg border p-2 text-sm">
                      <div className="flex items-center gap-2">
                        <CritBadge level={p.criticality} />
                        <span className="font-medium">{p.label}</span>
                      </div>
                      <div className="mt-1 flex items-center gap-2 text-xs text-muted-foreground">
                        {p.status === "blocked" ? <Lock className="size-3 text-risk" /> : <MessageSquareReply className="size-3" />}
                        <span className={cn(p.status === "blocked" && "text-risk")}>{p.status}</span> · {p.tool}
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{p.reason}</p>
                      {p.status === "blocked" && (
                        <Link href="/l2/security" className="mt-1 inline-block text-xs text-primary hover:underline">
                          See the decision log
                        </Link>
                      )}
                    </li>
                  ))}
                </ul>
              </Section>
              <Section title="Human in the loop">
                <div className="flex flex-col gap-2">
                  {c.status === "agent" && (
                    <Button onClick={() => takeover.mutate({ conversationId: c.id })} disabled={!canAct || takeover.isPending} data-testid="takeover">
                      <Hand /> Take over
                    </Button>
                  )}
                  {mine && (
                    <>
                      <Button variant="outline" onClick={() => handback.mutate({ conversationId: c.id })} disabled={handback.isPending}>
                        <Undo2 /> Hand back to agent
                      </Button>
                      <Button variant="outline" onClick={() => close.mutate({ conversationId: c.id, note: "Resolved by care" })} disabled={close.isPending}>
                        <XCircle /> Close as resolved
                      </Button>
                    </>
                  )}
                  {(c.takenOverBy || c.status === "closed") && (
                    <Button
                      variant={c.skillifiedTo ? "outline" : "default"}
                      data-testid="skillify"
                      onClick={() => {
                        const open = (crId: string) => (canView(user, "L2") ? router.push(`/l2/versioning/${crId}`) : toast.success("Draft skill is on a sandbox branch. An L2 steward will test it and send it for approval."));
                        if (c.skillifiedTo) open(c.skillifiedTo);
                        else skillify.mutate({ conversationId: c.id }, { onSuccess: (cr) => open((cr as { id: string }).id) });
                      }}
                      disabled={skillify.isPending}
                    >
                      <Wand2 /> {c.skillifiedTo ? "Open draft skill" : "Skillify"}
                    </Button>
                  )}
                  <p className="text-[11px] text-muted-foreground">Skillify turns how you handled this into a draft skill on a new sandbox branch. Never do one off work.</p>
                </div>
              </Section>
              <Section title="Run">
                <Link href={`/l3/runs/${c.runId}`} className="text-sm text-primary hover:underline">
                  Open run trace
                </Link>
              </Section>
            </div>
          </div>
        );
      }}
    </QueryView>
  );
}

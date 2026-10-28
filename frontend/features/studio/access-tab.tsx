"use client";

import { Check, MessageSquarePlus, ShieldCheck, TriangleAlert } from "lucide-react";
import { useState } from "react";
import type { StudioItem, WorkflowDetail } from "@/contracts";
import { Button } from "@/components/ui/button";
import { StatusChip } from "@/components/brain/primitives";
import { AccessCheckDialog } from "@/features/l2/access-check";
import { KindIcon } from "./cards";
import type { Focus } from "./state";

type Props = { detail: WorkflowDetail; item: StudioItem | null; onFocus: (f: Focus) => void; onAsk: (prompt: string) => void };

const list = (v: unknown): string[] => (Array.isArray(v) ? v.map(String) : []);

/** The tools an agent reaches: those of the skills it runs. */
function toolsOf(detail: WorkflowDetail, agent: StudioItem): StudioItem[] {
  const ids = new Set(detail.items.filter((i) => i.kind === "skill" && list(i.fields.agents).includes(agent.id)).flatMap((s) => list(s.fields.tools)));
  return detail.items.filter((i) => i.kind === "tool" && ids.has(i.id));
}

function AgentAccess({ agent, detail, onFocus, onAsk, onCheck }: { agent: StudioItem; detail: WorkflowDetail; onFocus: Props["onFocus"]; onAsk: Props["onAsk"]; onCheck: (id: string) => void }) {
  const held = list(agent.fields.capabilities);
  const tools = toolsOf(detail, agent);
  return (
    <li className="space-y-3 rounded-xl border bg-card p-3">
      <div className="flex items-center justify-between gap-2">
        <button type="button" className="flex min-h-8 items-center gap-2 text-left text-sm font-medium hover:underline" onClick={() => onFocus({ kind: "agent", id: agent.id })}>
          <KindIcon kind="agent" className="size-4" />{agent.name}
        </button>
        <StatusChip tone={agent.fields.accessLevel === "restricted" ? "risk" : "neutral"}>reads {String(agent.fields.accessLevel ?? "internal")}</StatusChip>
      </div>
      <div className="space-y-1">
        <p className="text-[13px] text-muted-foreground">Can do</p>
        {held.length === 0 ? <p className="text-sm">Nothing yet</p> : <ul className="flex flex-wrap gap-1.5">{held.map((c) => <li key={c} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[13px]">{c}</li>)}</ul>}
      </div>
      {tools.length > 0 && (
        <div className="space-y-1">
          <p className="text-[13px] text-muted-foreground">Tools it uses</p>
          <ul className="space-y-1">
            {tools.map((t) => {
              const need = String(t.fields.capability ?? "");
              const ok = !need || held.includes(need);
              return (
                <li key={t.id} className="flex items-start gap-2 text-sm">
                  {ok ? <Check className="mt-0.5 size-4 shrink-0" aria-hidden /> : <TriangleAlert className="mt-0.5 size-4 shrink-0 text-warn-fg" aria-hidden />}
                  <span>{t.name}{need && <span className="text-muted-foreground"> · needs {need}</span>}{!ok && <strong className="font-medium"> · missing</strong>}</span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="outline" onClick={() => onCheck(agent.id)}><ShieldCheck /> Check</Button>
        <Button size="sm" variant="outline" onClick={() => onAsk(`Change what ${agent.name} may do: `)}><MessageSquarePlus /> Change in chat</Button>
      </div>
    </li>
  );
}

export function AccessTab({ detail, item, onFocus, onAsk }: Props) {
  const [checking, setChecking] = useState<string | null>(null);
  const agents = item?.kind === "agent" ? [item] : detail.items.filter((i) => i.kind === "agent");
  return (
    <div className="space-y-3">
      <p className="text-sm text-muted-foreground">What each agent may do. Changes go through review.</p>
      {agents.length === 0 ? (
        <div className="space-y-3 rounded-xl border border-dashed p-4">
          <p className="text-sm">No agent yet. Add one and give it only what it needs.</p>
          <Button size="sm" onClick={() => onAsk(`Add an agent to ${detail.workflow.name} that can only: `)}><MessageSquarePlus /> Add an agent</Button>
        </div>
      ) : (
        <ul className="space-y-3" aria-label="Agent access">
          {agents.map((a) => <AgentAccess key={a.id} agent={a} detail={detail} onFocus={onFocus} onAsk={onAsk} onCheck={setChecking} />)}
        </ul>
      )}
      <AccessCheckDialog key={checking ?? "none"} open={!!checking} agentId={checking ?? undefined} onOpenChange={(open) => !open && setChecking(null)} />
    </div>
  );
}

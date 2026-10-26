"use client";

import { AlertOctagon, AlertTriangle, ArrowRight, CheckCircle2, Info, Network, Send, ShieldCheck, Wrench } from "lucide-react";
import Link from "next/link";
import { Suspense, lazy, useMemo, useState } from "react";
import type { ApplyResult, Proposal, Suggestion, WorkflowDetail } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Textarea } from "@/components/ui/textarea";
import { CommitButton } from "@/components/brain/motion";
import { CritBadge, StatusChip } from "@/components/brain/primitives";
import { useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { NO_HIGHLIGHT, type Highlight } from "@/lib/studio/graph";
import { cn } from "@/lib/utils";
import { KindIcon } from "./cards";

// React.lazy, not next/dynamic: the canvas chunk loads only when a proposal is on screen.
const WorkflowDiagram = lazy(() => import("./workflow-diagram"));

const VERDICT = {
  minimal: { tone: "ok" as const, label: "Minimal impact", icon: CheckCircle2 },
  moderate: { tone: "warn" as const, label: "Moderate impact", icon: AlertTriangle },
  breaking: { tone: "risk" as const, label: "Breaks the workflow", icon: AlertOctagon },
};

export function highlightOf(p: Proposal): Highlight {
  // The workflow itself is not a node: wording edits leave the map plain, status changes and deletes light every part.
  if (p.input.kind === "workflow") return p.review.affected.length > 1 ? { target: null, affected: new Set(p.review.affected.slice(1).map((a) => a.id)), broken: new Set() } : NO_HIGHLIGHT;
  const target = p.input.targetId;
  const broken = new Set(p.review.findings.filter((f) => f.severity === "break" && f.ref).map((f) => f.ref!.id));
  const affected = new Set(p.review.affected.map((a) => a.id).filter((id) => id !== target && !broken.has(id)));
  return { target, affected, broken };
}

export function ProposalCard({
  proposal,
  detail,
  applied,
  onApplied,
  onFix,
  onShowDiagram,
}: {
  proposal: Proposal;
  detail: WorkflowDetail | undefined;
  applied?: ApplyResult;
  onApplied: (r: ApplyResult) => void;
  onFix: (s: Suggestion) => void;
  onShowDiagram: (h: Highlight) => void;
}) {
  const rv = proposal.review;
  const { user } = useCurrentUser();
  const drafting = user?.tier === "L2";
  const v = VERDICT[rv.verdict];
  const [ack, setAck] = useState(false);
  const [note, setNote] = useState("");
  const [showNote, setShowNote] = useState(false);
  const apply = useOp<{ input: Proposal["input"]; acknowledgeBreaking: boolean; note: string }>("studioApply");
  const suggest = useOp<{ input: Proposal["input"]; note: string }>("studioSuggest");
  const hl = useMemo(() => highlightOf(proposal), [proposal]);
  const newWorkflow = proposal.input.kind === "workflow" && proposal.input.intent === "create";  // the open workflow is not the one being made
  const inDiagram = !!detail && !newWorkflow && (proposal.input.kind !== "tool" || detail.items.some((i) => i.id === proposal.input.targetId));
  const viewOnly = rv.authority.route === "view_only";
  const blocked = rv.verdict === "breaking" && !ack;

  return (
    <section className={cn("overflow-hidden rounded-xl border bg-card shadow-xs", rv.verdict === "breaking" ? "border-risk/40" : rv.verdict === "moderate" ? "border-warn/40" : "border-ok/30")} aria-label={`Proposal: ${proposal.title}`}>
      <header className="flex flex-wrap items-center gap-2 border-b bg-surface/60 px-3 py-2">
        <KindIcon kind={proposal.input.kind} />
        <h3 className="min-w-0 flex-1 truncate text-sm font-semibold">{proposal.title}</h3>
        <StatusChip tone={v.tone}>
          <v.icon className="size-3" aria-hidden /> {v.label}
        </StatusChip>
        <CritBadge level={rv.criticality} showLabel />
      </header>

      <div className="space-y-3 p-3">
        <div className="grid gap-3 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
          <div className="min-w-0">
            <div className="mb-1 text-[11px] font-medium uppercase tracking-wide text-muted-foreground">What changes</div>
            <ul className="space-y-1">
              {proposal.changes.map((c) => (
                <li key={c.field} className="rounded-lg bg-surface/70 px-2 py-1.5 text-xs">
                  <div className="font-medium">{c.label}</div>
                  <div className="mt-0.5 flex flex-wrap items-baseline gap-1.5">
                    {c.before !== null && <span className="break-words text-muted-foreground line-through decoration-risk/60">{c.before}</span>}
                    {c.before !== null && c.after !== null && <ArrowRight className="size-3 shrink-0 self-center text-muted-foreground" aria-hidden />}
                    {c.after !== null && <span className="break-words font-medium text-foreground">{c.after}</span>}
                  </div>
                </li>
              ))}
            </ul>
          </div>

          <div className="min-w-0 rounded-lg border bg-background/60 p-2.5">
            <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold">
              <ShieldCheck className="size-3.5 text-primary" aria-hidden /> {rv.reviewer}
            </div>
            <p className="text-xs text-muted-foreground">{rv.summary}</p>
            <ul className="mt-2 space-y-1">
              {rv.findings.map((f, i) => {
                const Icon = f.severity === "break" ? AlertOctagon : f.severity === "warn" ? AlertTriangle : Info;
                return (
                  <li key={i} className="flex gap-1.5 text-xs">
                    <Icon className={cn("mt-0.5 size-3.5 shrink-0", f.severity === "break" ? "text-risk" : f.severity === "warn" ? "text-warn-fg" : "text-muted-foreground")} aria-label={f.severity} />
                    <span>{f.text}</span>
                  </li>
                );
              })}
            </ul>
            {rv.fixes.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1.5">
                {rv.fixes.map((s) => (
                  <Button key={s.label} size="xs" variant="outline" onClick={() => onFix(s)} disabled={!!applied}>
                    <Wrench /> {s.label}
                  </Button>
                ))}
              </div>
            )}
            <p className="mt-2 text-[11px] text-muted-foreground">{rv.criticalityReasons.join("; ")}.</p>
          </div>
        </div>
        <div className="min-w-0 space-y-2">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">Effect on the whole workflow</div>
            {inDiagram && (
              <Button size="xs" variant="ghost" onClick={() => onShowDiagram(hl)}>
                <Network /> Open full diagram
              </Button>
            )}
          </div>
          {inDiagram && detail ? (
            <div className="h-[280px]">
              <Suspense fallback={<div className="h-full animate-pulse rounded-xl border bg-surface" />}>
                <WorkflowDiagram detail={detail} highlight={hl} compact />
              </Suspense>
            </div>
          ) : (
            <p className="rounded-lg border border-dashed p-3 text-xs text-muted-foreground">{proposal.input.intent === "create" ? "New item. It appears on the diagram once it exists." : "This item sits outside the current workflow."}</p>
          )}
          <div className="flex flex-wrap gap-1 text-[11px]">
            <span className="text-muted-foreground">Touches:</span>
            {rv.affected.slice(0, 10).map((a) => (
              <span key={a.id} className={cn("inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5", hl.broken.has(a.id) && "border-risk/50 text-risk", a.id === hl.target && "border-primary/50")} title={a.how}>
                <KindIcon kind={a.kind} className="size-3" /> {a.name}
              </span>
            ))}
          </div>
          {rv.otherWorkflows.length > 0 && (
            <div className="rounded-lg bg-warn/10 px-2 py-1.5 text-[11px]">
              <span className="font-medium">Also changes {rv.otherWorkflows.length} other workflow{rv.otherWorkflows.length > 1 ? "s" : ""}:</span> {rv.otherWorkflows.map((w) => w.name).join(", ")}
            </div>
          )}
        </div>
      </div>
      <footer className="space-y-2 border-t bg-surface/40 px-3 py-2.5">
        {applied ? (
          <div className={cn("flex flex-wrap items-center gap-2 text-xs", applied.status === "applied" ? "text-ok" : "text-foreground")} role="status">
            {applied.status === "applied" ? <CheckCircle2 className="size-4" aria-hidden /> : <Send className="size-4 text-primary" aria-hidden />}
            <span>{applied.message}</span>
            {applied.changeRequestId && (
              <Link href={`/l2/versioning/${applied.changeRequestId}`} className="font-medium text-primary hover:underline">
                Open change request
              </Link>
            )}
          </div>
        ) : (
          <>
            <p className="text-xs">
              <span className="font-medium">{rv.authority.route === "apply" ? "You can confirm this." : rv.authority.route === "approval" ? (drafting ? `Draft only. Goes to ${rv.authority.approver}.` : `Needs ${rv.authority.approver}.`) : "View only."}</span>{" "}
              <span className="text-muted-foreground">{rv.authority.reason}</span>
            </p>
            {rv.verdict === "breaking" && !viewOnly && (
              <label className="flex items-start gap-2 text-xs">
                <Checkbox checked={ack} onCheckedChange={(c) => setAck(c === true)} className="mt-0.5" />
                <span>I read what breaks. Send it with the review attached{rv.fixes.length ? ", or apply the fixes above first" : ""}.</span>
              </label>
            )}
            {showNote && <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="Why this change? The approver sees this note." className="min-h-14 text-xs" aria-label="Note for the approver" />}
            <div className="flex flex-wrap items-center gap-2">
              {viewOnly ? (
                <Button size="sm" variant="outline" disabled={suggest.isPending} onClick={() => suggest.mutate({ input: proposal.input, note }, { onSuccess: (r) => onApplied({ status: "routed", targetId: proposal.input.targetId ?? "", revisionId: null, changeRequestId: null, message: (r as { message: string }).message }) })}>
                  <Send /> Suggest to the DRI
                </Button>
              ) : (
                <CommitButton size="sm" criticality={rv.criticality} disabled={blocked || apply.isPending} onClick={() => apply.mutate({ input: proposal.input, acknowledgeBreaking: ack, note }, { onSuccess: (r) => onApplied(r as ApplyResult) })}>
                  {rv.authority.route === "apply" ? <><CheckCircle2 /> Confirm and apply</> : <><Send /> {drafting ? "Draft and send for approval" : `Send to ${rv.authority.approver}`}</>}
                </CommitButton>
              )}
              {!showNote && (
                <Button size="sm" variant="ghost" onClick={() => setShowNote(true)}>
                  Add a note
                </Button>
              )}
            </div>
          </>
        )}
      </footer>
    </section>
  );
}

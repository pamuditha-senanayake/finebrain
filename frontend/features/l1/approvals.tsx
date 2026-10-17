"use client";

import { Check, MessageSquareWarning, Share2, UserCheck, X } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import type { Approval } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Textarea } from "@/components/ui/textarea";
import { ChangeRequestSummary } from "@/components/brain/change-request";
import { CommitButton } from "@/components/brain/motion";
import { PersonChip, useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { CritBadge, EmptyState, KeyValue, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useApproval, useApprovals, useChangeRequest, useGrants, useHumans, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { relTime } from "@/lib/format";
import { approverFor, canApprove } from "@/lib/governance/criticality";
import { cn } from "@/lib/utils";

function waitingOn(a: Approval, userId: string | undefined, tier: string | undefined, max: number) {
  if (!userId || a.status !== "pending") return false;
  if (a.votes.some((v) => v.by === userId && v.decision === "approve")) return false;
  return (a.requiredApprovers.tier === tier || a.delegatedTo === userId) && max >= a.criticality;
}

export function ApprovalsInbox({ embedded = false }: { embedded?: boolean }) {
  const approvals = useApprovals();
  const { user } = useCurrentUser();
  const router = useRouter();
  const [tab, setTab] = useState<"mine" | "pending" | "decided">("mine");
  const list = useMemo(() => {
    const all = approvals.data ?? [];
    const filtered = tab === "decided" ? all.filter((a) => a.status !== "pending") : tab === "pending" ? all.filter((a) => a.status === "pending") : all.filter((a) => waitingOn(a, user?.id, user?.tier, user?.maxApprovalCriticality ?? 0));
    return [...filtered].sort((a, b) => (tab === "decided" ? (a.createdAt < b.createdAt ? 1 : -1) : b.criticality - a.criticality || (a.dueAt < b.dueAt ? -1 : 1)));
  }, [approvals.data, tab, user]);
  return (
    <div>
      {!embedded && <PageHeader title="All approvals" description="Sorted by criticality, then deadline. C4 needs two L1 approvers. Requests expire and can be delegated, never silently skipped." />}
      <ToggleGroup type="single" value={tab} onValueChange={(v) => v && setTab(v as typeof tab)} variant="outline" size="sm" className="mb-5" aria-label="Which approvals">
        <ToggleGroupItem value="mine" className="px-3 text-xs">Waiting on me</ToggleGroupItem>
        <ToggleGroupItem value="pending" className="px-3 text-xs">All pending</ToggleGroupItem>
        <ToggleGroupItem value="decided" className="px-3 text-xs">Decided</ToggleGroupItem>
      </ToggleGroup>
      <QueryView query={approvals}>
        {() =>
          list.length === 0 ? (
            <EmptyState title={tab === "mine" ? "Nothing is waiting on you" : "No approvals here"} />
          ) : (
            <SimpleTable
              label="All approvals"
              rows={list}
              getRowId={(a) => a.id}
              onRowClick={(a) => router.push(`/l1/approvals/${a.id}`)}
              rowClassName={() => "align-middle"}
              columns={[
                { id: "crit", header: "Level", className: "w-16", cell: (a) => <CritBadge level={a.criticality} /> },
                {
                  id: "title",
                  header: "Approval",
                  cell: (a) => (
                    <div className="max-w-md py-0.5">
                      <Link href={`/l1/approvals/${a.id}`} className="font-medium hover:text-primary hover:underline" data-testid={`approval-${a.id}`} onClick={(e) => e.stopPropagation()}>
                        {a.title}
                      </Link>
                      <p className="mt-1 line-clamp-1 text-xs text-muted-foreground">{a.summary}</p>
                      <p className="mt-1 text-[11px] text-muted-foreground/80">Drafted by {a.drafter.name}</p>
                    </div>
                  ),
                },
                { id: "due", header: "Due", className: "whitespace-nowrap text-xs text-muted-foreground", cell: (a) => relTime(a.dueAt) },
                {
                  id: "votes",
                  header: "Votes",
                  className: "whitespace-nowrap text-xs tabular",
                  cell: (a) => `${new Set(a.votes.filter((v) => v.decision === "approve").map((v) => v.by)).size} of ${a.requiredApprovers.count} ${a.requiredApprovers.tier}`,
                },
                { id: "dri", header: "DRI", cell: (a) => <PersonChip id={a.dri} /> },
                { id: "status", header: "Status", cell: (a) => <Status value={a.status} /> },
              ]}
            />
          )
        }
      </QueryView>
    </div>
  );
}

export function ApprovalDetail() {
  const { id } = useParams<{ id: string }>();
  const approval = useApproval(id);
  const crId = approval.data?.subject.kind === "change_request" ? approval.data.subject.id : "";
  const cr = useChangeRequest(crId);
  const grants = useGrants();
  const humans = useHumans();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const router = useRouter();
  const [comment, setComment] = useState("");
  const [delegateTo, setDelegateTo] = useState("");
  const decide = useOp<{ approvalId: string; decision: string; comment: string; delegateTo?: string | null }>("decide");

  return (
    <div className="mx-auto max-w-5xl">
      <QueryView query={approval}>
        {(a) => {
          const approvedBy = a.votes.filter((v) => v.decision === "approve").map((v) => v.by);
          const blocker = user ? canApprove({ id: user.id, tier: user.tier, maxApprovalCriticality: user.maxApprovalCriticality }, a.criticality, approvedBy) : "Pick a persona";
          const draftedByMe = a.drafter.kind === "human" && a.drafter.id === user?.id;
          const notTested = a.subject.kind === "change_request" && cr.data && (!cr.data.tests || !cr.data.impactPreview);
          const reason = a.status !== "pending" ? `This approval is ${a.status}.` : blocker ?? (draftedByMe ? "You drafted this change. Someone else must approve it." : notTested ? "Run sandbox tests and the replay first." : null);
          const grant = a.subject.kind === "grant" ? grants.data?.find((g) => g.id === a.subject.id) : null;
          const req = approverFor(a.criticality);
          const isMerge = a.subject.kind === "change_request";
          const act = (decision: "approve" | "reject" | "request_changes" | "delegate") =>
            decide.mutate(
              { approvalId: a.id, decision, comment, delegateTo: decision === "delegate" ? delegateTo : null },
              {
                onSuccess: (res) => {
                  setComment("");
                  const r = res as Approval;
                  if (r.status === "approved") router.push(isMerge ? `/l2/versioning/${a.subject.id}` : "/l1/digest?tab=evidence");
                },
              },
            );
          return (
            <div>
              <PageHeader eyebrow={<Link href="/l1/digest?tab=approvals" className="hover:underline">To review</Link>} title={a.title} description={a.summary} actions={<Status value={a.status} />} />
              <div className="grid gap-6 lg:grid-cols-[1fr_340px]">
                <div className="space-y-6">
                  {isMerge ? (
                    <QueryView query={cr}>{(c) => <ChangeRequestSummary cr={c} />}</QueryView>
                  ) : grant ? (
                    <Section title="Access being granted" description="Read this before granting. You can revoke at any time.">
                      <KeyValue items={[["Source", grant.source], ["Scope", grant.scope], ["Retention", `${grant.retentionDays} days`], ["Agents", grant.agents.map((x) => lookup.name(x)).join(", ")], ["How to revoke", grant.revoke], ["Status", <Status key="s" value={grant.status} />]]} />
                    </Section>
                  ) : null}
                  <Section title="Evidence">
                    <ul className="flex flex-wrap gap-1.5 text-xs">
                      {a.evidence.length === 0 && <li className="text-muted-foreground">No linked evidence</li>}
                      {a.evidence.map((e) => (
                        <li key={e} className="rounded bg-muted px-1.5 py-0.5 font-mono">{e}</li>
                      ))}
                    </ul>
                  </Section>
                </div>
                <div className="space-y-4 lg:sticky lg:top-16 lg:self-start">
                  <Section title="Decision">
                    <KeyValue
                      className="mb-3"
                      items={[
                        ["Criticality", <CritBadge key="c" level={a.criticality} showLabel />],
                        ["Needs", req.label],
                        ["Drafter", a.drafter.name],
                        ["DRI", <PersonChip key="d" id={a.dri} />],
                        ["Due", relTime(a.dueAt)],
                      ]}
                    />
                    <div className="mb-3">
                      <div className="mb-1 text-xs text-muted-foreground">
                        Approvals {new Set(approvedBy).size} of {a.requiredApprovers.count}
                        {a.requiredApprovers.count > 1 && " (two person rule)"}
                      </div>
                      <div className="flex gap-1">
                        {Array.from({ length: a.requiredApprovers.count }).map((_, i) => (
                          <div key={i} className={cn("h-1.5 flex-1 rounded-full", i < new Set(approvedBy).size ? "bg-ok" : "bg-muted")} />
                        ))}
                      </div>
                      <ul className="mt-2 space-y-1 text-xs">
                        {a.votes.map((v, i) => (
                          <li key={i} className="flex items-center gap-1.5">
                            {v.decision === "approve" ? <UserCheck className="size-3 text-ok" /> : <MessageSquareWarning className="size-3 text-warn-fg" />}
                            {lookup.name(v.by)} · {v.decision.replace("_", " ")} {relTime(v.at)}
                            {v.comment && <span className="truncate text-muted-foreground">“{v.comment}”</span>}
                          </li>
                        ))}
                      </ul>
                    </div>
                    {a.status === "pending" && (
                      <>
                        <Textarea value={comment} onChange={(e) => setComment(e.target.value)} placeholder="Comment (optional)" aria-label="Comment" rows={2} className="mb-2" />
                        <CommitButton criticality={a.criticality} className="w-full" disabled={!!reason || decide.isPending} onClick={() => act("approve")} data-testid="approve">
                          <Check /> {isMerge ? (a.criticality >= 3 ? "Approve and merge to Production" : "Approve and merge") : "Grant access"}
                        </CommitButton>
                        {reason && <p className="mt-1.5 text-[11px] text-muted-foreground" role="note">{reason}</p>}
                        <div className="mt-2 grid grid-cols-2 gap-2">
                          <Button variant="outline" size="sm" disabled={!user || user.tier === "L3" || decide.isPending} onClick={() => act("request_changes")}>
                            Request changes
                          </Button>
                          <Button variant="outline" size="sm" className="text-risk" disabled={!user || user.tier === "L3" || decide.isPending} onClick={() => act("reject")}>
                            <X /> Reject
                          </Button>
                        </div>
                        <div className="mt-2 flex gap-2">
                          <Select value={delegateTo} onValueChange={setDelegateTo}>
                            <SelectTrigger size="sm" className="flex-1 text-xs" aria-label="Delegate to">
                              <SelectValue placeholder="Delegate to…" />
                            </SelectTrigger>
                            <SelectContent>
                              {(humans.data ?? [])
                                .filter((h) => h.id !== user?.id && h.maxApprovalCriticality >= a.criticality)
                                .map((h) => (
                                  <SelectItem key={h.id} value={h.id}>
                                    {h.name}
                                  </SelectItem>
                                ))}
                            </SelectContent>
                          </Select>
                          <Button variant="outline" size="sm" disabled={!delegateTo || decide.isPending} onClick={() => act("delegate")}>
                            <Share2 /> Delegate
                          </Button>
                        </div>
                      </>
                    )}
                  </Section>
                </div>
              </div>
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

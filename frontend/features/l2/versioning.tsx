"use client";

import { FlaskConical, GitMerge, History, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, lazy, useMemo, useState } from "react";
import type { ChangeRequest, Commit } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ChangeRequestSummary, StructuredDiff } from "@/components/brain/change-request";
import { DataTable, type Column } from "@/components/brain/data-table";
import { Beam, CommitButton } from "@/components/brain/motion";
import { PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, LoadingState, Mono, PageHeader, QueryView, Section, Status } from "@/components/brain/primitives";
import { useApproval, useBranches, useChangeRequest, useChangeRequests, useCommits, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { dateTime, relTime } from "@/lib/format";

// React.lazy, not next/dynamic: the chunk loads only when this view renders, never on route prefetch.
const BranchGraph = lazy(() => import("./branch-graph"));

export function Versioning() {
  const crs = useChangeRequests();
  const branches = useBranches();
  const commits = useCommits("main");
  const router = useRouter();
  const params = useSearchParams();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const [rollbackTo, setRollbackTo] = useState<Commit | null>(null);
  const rollback = useOp<{ commitId: string }>("rollback", { success: "Rolled back. A revert commit is on main." });
  const crColumns: Column<ChangeRequest>[] = useMemo(
    () => [
      { id: "crit", header: "Level", width: "56px", value: (c) => c.criticality, cell: (c) => <CritBadge level={c.criticality} /> },
      { id: "title", header: "Change request", width: "minmax(220px,2fr)", value: (c) => c.title, cell: (c) => <span className="truncate font-medium">{c.title}</span> },
      { id: "kind", header: "Kind", width: "80px", value: (c) => c.kind, hideOnMobile: true, cell: (c) => <span className="text-muted-foreground">{c.kind}</span> },
      { id: "branch", header: "Branch", width: "minmax(160px,1fr)", value: (c) => c.fromBranch, hideOnMobile: true, cell: (c) => <Mono className="truncate">{c.fromBranch}</Mono> },
      { id: "drafter", header: "Drafter", width: "140px", value: (c) => c.drafter.name, hideOnMobile: true, cell: (c) => <span className="truncate">{c.drafter.name}</span> },
      { id: "status", header: "Status", width: "140px", value: (c) => c.status, cell: (c) => <Status value={c.status} /> },
      { id: "created", header: "Opened", width: "100px", value: (c) => c.createdAt, hideOnMobile: true, cell: (c) => <span className="text-muted-foreground">{relTime(c.createdAt)}</span> },
    ],
    [],
  );
  const commitColumns: Column<Commit>[] = useMemo(
    () => [
      { id: "id", header: "Commit", width: "90px", value: (c) => c.id, cell: (c) => <Mono>{c.id.slice(0, 8)}</Mono> },
      { id: "message", header: "Message", width: "minmax(240px,2fr)", value: (c) => c.message, cell: (c) => <span className="truncate">{c.message}{c.tag && <span className="ml-2 rounded bg-ok/10 px-1 text-[10px] text-ok">{c.tag}</span>}</span> },
      { id: "author", header: "Author", width: "150px", value: (c) => c.author.name, hideOnMobile: true, cell: (c) => <span className="truncate">{c.author.name}</span> },
      { id: "crit", header: "Level", width: "56px", value: (c) => c.criticality, cell: (c) => <CritBadge level={c.criticality} /> },
      { id: "at", header: "When", width: "120px", value: (c) => c.createdAt, hideOnMobile: true, cell: (c) => <span className="text-muted-foreground">{dateTime(c.createdAt, lookup.tz)}</span> },
      { id: "actions", header: "", width: "92px", cell: (c) => (user && user.tier !== "L3" ? <Button size="xs" variant="ghost" onClick={(e) => { e.stopPropagation(); setRollbackTo(c); }}><RotateCcw /> Roll back</Button> : null) },
    ],
    [lookup.tz, user],
  );
  const later = rollbackTo ? (commits.data ?? []).filter((c) => c.createdAt > rollbackTo.createdAt) : [];
  return (
    <div>
      <PageHeader title="Versioning" description="Git for the graph. Every change is a commit, main is Production, staging runs in shadow, and each sandbox is a branch tested against recorded runs." />
      <Tabs defaultValue={params.get("commit") ? "main" : "crs"}>
        <TabsList>
          <TabsTrigger value="crs">Change requests</TabsTrigger>
          <TabsTrigger value="branches">Branches</TabsTrigger>
          <TabsTrigger value="main">Commits on main</TabsTrigger>
        </TabsList>
        <TabsContent value="crs" className="mt-3">
          <QueryView query={crs}>
            {(list) => <DataTable label="Change requests" data={list} columns={crColumns} getRowId={(c) => c.id} onRowClick={(c) => router.push(`/l2/versioning/${c.id}`)} initialSort={{ id: "created", desc: true }} height="calc(100dvh - 300px)" />}
          </QueryView>
        </TabsContent>
        <TabsContent value="branches" className="mt-3 space-y-3">
          <QueryView query={branches}>
            {(bs) => (
              <>
                <Suspense fallback={<LoadingState rows={4} label="Loading branch graph" />}><BranchGraph branches={bs} commits={commits.data ?? []} /></Suspense>
                <ul className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
                  {bs.map((b) => (
                    <li key={b.id} className="rounded-lg border bg-card p-3 text-sm">
                      <div className="flex items-center justify-between gap-2">
                        <Mono className="truncate font-medium">{b.name}</Mono>
                        <Status value={b.status} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">{b.description}</p>
                      <p className="mt-1 text-[11px] text-muted-foreground">
                        {b.env} · by {b.createdBy.name} · {relTime(b.createdAt)}
                      </p>
                    </li>
                  ))}
                </ul>
              </>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="main" className="mt-3">
          <QueryView query={commits}>
            {(cs) => <DataTable label="Commits on main" data={cs} columns={commitColumns} getRowId={(c) => c.id} initialSort={{ id: "at", desc: true }} height="calc(100dvh - 300px)" rowClassName={(c) => (c.id === params.get("commit") ? "bg-primary/10" : undefined)} />}
          </QueryView>
        </TabsContent>
      </Tabs>
      <Dialog open={!!rollbackTo} onOpenChange={(o) => !o && setRollbackTo(null)}>
        <DialogContent className="sm:max-w-2xl">
          <DialogHeader>
            <DialogTitle>Roll back main to {rollbackTo?.id.slice(0, 8)}</DialogTitle>
            <DialogDescription>Before anything reverts, here is what changes. {later.length} later commits are reverted.</DialogDescription>
          </DialogHeader>
          <div className="max-h-[50vh] overflow-auto">
            <ul className="space-y-1 text-xs">
              {later.slice(0, 40).map((c) => (
                <li key={c.id} className="flex items-center gap-2">
                  <CritBadge level={c.criticality} /> <Mono>{c.id.slice(0, 8)}</Mono> {c.message}
                  <span className="ml-auto text-muted-foreground">affects {c.changes.map((x) => x.label).join(", ")}</span>
                </li>
              ))}
            </ul>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setRollbackTo(null)}>Cancel</Button>
            <CommitButton criticality={3} disabled={rollback.isPending || later.length === 0} onClick={() => rollbackTo && rollback.mutate({ commitId: rollbackTo.id }, { onSuccess: () => setRollbackTo(null) })}>
              <History /> Roll back
            </CommitButton>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export function ChangeRequestDetail() {
  const { id } = useParams<{ id: string }>();
  const cr = useChangeRequest(id);
  const approval = useApproval(cr.data?.approvalId ?? "");
  const crs = useChangeRequests();
  const commits = useCommits(cr.data?.fromBranch);
  const { user } = useCurrentUser();
  const check = useOp<{ changeRequestId: string }>("runChecks", { success: "Sandbox tests and replay finished" });
  return (
    <div className="mx-auto max-w-5xl">
      <QueryView query={cr}>
        {(c) => {
          const conflictWith = c.status === "conflict" ? (crs.data ?? []).find((o) => o.id !== c.id && o.status === "merged" && o.changes.some((x) => c.changes.some((y) => y.nodeId === x.nodeId))) : null;
          return (
            <div>
              <PageHeader eyebrow={<Link href="/l2/versioning" className="hover:underline">Versioning</Link>} title={c.title} description={<span className="inline-flex flex-wrap items-center gap-1">Drafted by {c.drafter.name} · DRI <PersonChip id={c.dri} /></span>} />
              <div className="grid gap-4 lg:grid-cols-[1fr_300px]">
                <ChangeRequestSummary cr={c} />
                <div className="space-y-4 lg:sticky lg:top-16 lg:self-start">
                  <Section title="Next step">
                    {["draft", "changes_requested"].includes(c.status) && (
                      <Beam className="rounded-lg">
                        <div className="space-y-2">
                          <p className="text-xs text-muted-foreground">Nothing goes live blind. Run the eval suite in the sandbox and replay recent real runs to see the effect.</p>
                          <Button className="w-full" onClick={() => check.mutate({ changeRequestId: c.id })} disabled={check.isPending || !user || user.tier === "L3"} data-testid="run-checks">
                            <FlaskConical /> Run sandbox tests and replay
                          </Button>
                          {user?.tier === "L3" && <p className="text-[11px] text-muted-foreground">An L2 steward runs the checks.</p>}
                        </div>
                      </Beam>
                    )}
                    {c.status === "awaiting_approval" && approval.data && (
                      <div className="space-y-2 text-sm">
                        <p>Waiting for {approval.data.requiredApprovers.count} {approval.data.requiredApprovers.tier} approval{approval.data.requiredApprovers.count > 1 ? "s" : ""}.</p>
                        <Button asChild className="w-full" variant="outline">
                          <Link href={`/l1/approvals/${approval.data.id}`}>Open the approval</Link>
                        </Button>
                      </div>
                    )}
                    {c.status === "merged" && (
                      <p className="flex items-center gap-1.5 text-sm text-ok">
                        <GitMerge className="size-4" /> Merged {c.mergedAt && relTime(c.mergedAt)}. Live in Production.
                      </p>
                    )}
                    {["rejected", "expired"].includes(c.status) && <p className="text-sm text-muted-foreground">This change request is {c.status}.</p>}
                    {c.status === "conflict" && <p className="text-sm text-risk">Another branch changed the same node. Resolve below.</p>}
                  </Section>
                  <Section title="Commits on the branch">
                    <ul className="space-y-1.5 text-xs">
                      {(commits.data ?? []).map((cm) => (
                        <li key={cm.id}>
                          <Mono>{cm.id.slice(0, 8)}</Mono> {cm.message}
                          <div className="text-muted-foreground">{cm.author.name} · {relTime(cm.createdAt)}</div>
                        </li>
                      ))}
                    </ul>
                  </Section>
                  <Section title="Audit">
                    <Link href={`/l1/audit?correlation=${encodeURIComponent(c.correlationId)}`} className="text-xs text-primary hover:underline">
                      Every step of this change in the audit trail
                    </Link>
                  </Section>
                </div>
              </div>
              {conflictWith && (
                <Section title="Conflict resolution" description="Both sides with their evidence. Pick a side by editing the draft, then run checks again." className="mt-4">
                  <div className="grid gap-3 md:grid-cols-2">
                    <div>
                      <div className="mb-1 text-xs font-medium">This branch</div>
                      <StructuredDiff cr={c} />
                    </div>
                    <div>
                      <div className="mb-1 text-xs font-medium">Already on main ({conflictWith.title})</div>
                      <StructuredDiff cr={conflictWith} />
                    </div>
                  </div>
                </Section>
              )}
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

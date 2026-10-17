"use client";

import { KeyRound, ShieldOff, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import type { EvidenceRequest } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CommitButton } from "@/components/brain/motion";
import { PersonChip, useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { EmptyState, KeyValue, PageHeader, QueryView, SampleBadge, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useEvidenceRequests, useGrants, useObligations, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";

/** Row actions: upload a document, or grant a data source instead. Also states how a request was fulfilled. */
function RequestActions({ req }: { req: EvidenceRequest }) {
  const lookup = useLookup();
  const fileRef = useRef<HTMLInputElement>(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const upload = useOp<{ requestId: string; fileName: string; sizeKb: number }>("uploadEvidence", { success: "Evidence filed. A fact with provenance was recorded." });
  const grant = useOp<{ requestId: string }>("requestGrant", { success: "Grant requested. C4 needs two L1 approvals." });
  const g = req.suggestedGrant;
  return (
    <div data-testid={`evidence-${req.id}`}>
      {req.status === "open" && (
        <div className="flex flex-wrap gap-2">
          <input
            ref={fileRef}
            type="file"
            className="sr-only"
            aria-label={`Upload evidence for ${req.item}`}
            data-testid={`upload-${req.id}`}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) upload.mutate({ requestId: req.id, fileName: f.name, sizeKb: f.size / 1024 });
            }}
          />
          <Button size="xs" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            <Upload /> Upload document
          </Button>
          {g && (
            <Button size="xs" variant="outline" onClick={() => setGrantOpen(true)}>
              <KeyRound /> Grant a data source
            </Button>
          )}
        </div>
      )}
      {req.status === "awaiting_grant_approval" && (
        <p className="text-xs text-muted-foreground">
          Needs two L1 approvals. <Link href="/l1/digest?tab=approvals" className="text-primary hover:underline">Open approvals</Link>
        </p>
      )}
      {req.fulfilledBy && <p className="text-xs text-ok">Fulfilled by {req.fulfilledBy.kind === "upload" ? "an upload" : "a granted source"} ({req.fulfilledBy.ref}).</p>}
      {g && (
        <Dialog open={grantOpen} onOpenChange={setGrantOpen}>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Grant access: {g.source}</DialogTitle>
              <DialogDescription>Check exactly what you are granting before anything is granted.</DialogDescription>
            </DialogHeader>
            <KeyValue items={[["Scope", g.scope], ["Retention", `${g.retentionDays} days`], ["Agents that will use it", g.agents.map((a) => lookup.name(a)).join(", ")], ["How to revoke", g.revoke], ["Approval", "C4: two L1 approvers"]]} />
            <DialogFooter>
              <Button variant="outline" onClick={() => setGrantOpen(false)}>
                Cancel
              </Button>
              <CommitButton criticality={4} onClick={() => grant.mutate({ requestId: req.id }, { onSuccess: () => setGrantOpen(false) })} disabled={grant.isPending}>
                <KeyRound /> Request grant
              </CommitButton>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  );
}

function RequestTable({ rows, label }: { rows: EvidenceRequest[]; label: string }) {
  const lookup = useLookup();
  const obligations = useObligations();
  return (
    <SimpleTable
      label={label}
      rows={rows}
      getRowId={(r) => r.id}
      columns={[
        { id: "item", header: "Evidence", className: "font-medium", cell: (r) => r.item },
        { id: "obligation", header: "For obligation", className: "text-xs", cell: (r) => obligations.data?.find((o) => o.id === r.obligationId)?.title ?? r.obligationId },
        {
          id: "due",
          header: "Due",
          className: "whitespace-nowrap text-xs",
          cell: (r) => date(obligations.data?.find((o) => o.id === r.obligationId)?.dueAt ?? r.dueAt, lookup.tz),
        },
        { id: "requested", header: "Requested", className: "whitespace-nowrap text-xs text-muted-foreground", cell: (r) => relTime(r.createdAt) },
        { id: "from", header: "From", cell: (r) => <PersonChip id={r.requestedFrom} /> },
        {
          id: "status",
          header: "Status",
          cell: (r) => (
            <div className="flex flex-wrap items-center gap-1.5">
              <Status value={r.status} />
              {r.escalationLevel > 0 && <StatusChip tone={r.escalationLevel >= 3 ? "risk" : "warn"}>escalation {r.escalationLevel}</StatusChip>}
            </div>
          ),
        },
        { id: "actions", header: "Action", cell: (r) => <RequestActions req={r} /> },
      ]}
    />
  );
}

export function EvidenceRequests({ embedded = false }: { embedded?: boolean }) {
  const requests = useEvidenceRequests();
  const grants = useGrants();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const revoke = useOp<{ grantId: string }>("revokeGrant", { success: "Access revoked" });
  return (
    <div>
      {!embedded && <PageHeader title="Evidence requests" description="When the system needs proof, the DRI uploads a document or grants a data source. Requests start early and escalate as deadlines approach." actions={<SampleBadge />} />}
      <QueryView query={requests} empty={<EmptyState title="No evidence requests" description="Run the readiness scheduler in L2 to look for gaps." action={<Button asChild size="sm" variant="outline"><Link href="/l2/readiness">Readiness scheduler</Link></Button>} />}>
        {(list) => {
          const open = list.filter((r) => r.status !== "fulfilled");
          const mineFirst = [...open].sort((a, b) => Number(b.requestedFrom === user?.id) - Number(a.requestedFrom === user?.id));
          const done = list.filter((r) => r.status === "fulfilled");
          return (
            <div className="space-y-8">
              <section aria-label="Open requests">
                <h2 className="mb-2 text-sm font-semibold">Open ({open.length})</h2>
                {open.length === 0 ? <EmptyState title="Nothing open" /> : <RequestTable label="Open requests" rows={mineFirst} />}
              </section>
              {done.length > 0 && (
                <section aria-label="Fulfilled requests">
                  <h2 className="mb-2 text-sm font-semibold">Fulfilled ({done.length})</h2>
                  <RequestTable label="Fulfilled requests" rows={done} />
                </section>
              )}
            </div>
          );
        }}
      </QueryView>
      <Section plain title="Data source grants" className="mt-5">
        <QueryView query={grants} rows={2}>
          {(gs) => (
            <SimpleTable
              label="Data source grants"
              rows={gs}
              getRowId={(g) => g.id}
              columns={[
                { id: "source", header: "Source", className: "font-medium", cell: (g) => g.source },
                { id: "scope", header: "Scope", className: "text-xs text-muted-foreground", cell: (g) => g.scope },
                { id: "retention", header: "Retention", className: "whitespace-nowrap text-xs", cell: (g) => `${g.retentionDays} days` },
                { id: "agents", header: "Agents", className: "text-xs", cell: (g) => g.agents.map((a) => lookup.name(a)).join(", ") },
                { id: "status", header: "Status", cell: (g) => <Status value={g.status} /> },
                {
                  id: "actions",
                  header: "",
                  className: "w-24 text-right",
                  cell: (g) =>
                    g.status === "active" && user && user.tier !== "L3" ? (
                      <Button size="xs" variant="outline" onClick={() => revoke.mutate({ grantId: g.id })}>
                        <ShieldOff /> Revoke
                      </Button>
                    ) : null,
                },
              ]}
            />
          )}
        </QueryView>
      </Section>
    </div>
  );
}

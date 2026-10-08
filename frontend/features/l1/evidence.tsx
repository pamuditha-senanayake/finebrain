"use client";

import { KeyRound, ShieldOff, Upload } from "lucide-react";
import Link from "next/link";
import { useRef, useState } from "react";
import type { EvidenceRequest } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { CommitButton } from "@/components/brain/motion";
import { PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, KeyValue, PageHeader, QueryView, SampleBadge, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useEvidenceRequests, useGrants, useObligations, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";

function RequestCard({ req }: { req: EvidenceRequest }) {
  const lookup = useLookup();
  const obligations = useObligations();
  const ob = obligations.data?.find((o) => o.id === req.obligationId);
  const fileRef = useRef<HTMLInputElement>(null);
  const [grantOpen, setGrantOpen] = useState(false);
  const upload = useOp<{ requestId: string; fileName: string; sizeKb: number }>("uploadEvidence", { success: "Evidence filed. A fact with provenance was recorded." });
  const grant = useOp<{ requestId: string }>("requestGrant", { success: "Grant requested. C4 needs two L1 approvals." });
  const g = req.suggestedGrant;
  return (
    <li className="rounded-xl border bg-card p-4" data-testid={`evidence-${req.id}`}>
      <div className="flex flex-wrap items-start justify-between gap-2">
        <div className="min-w-0">
          <h3 className="text-sm font-semibold">{req.item}</h3>
          <p className="text-xs text-muted-foreground">
            for {ob?.title ?? req.obligationId} · due {date(ob?.dueAt ?? req.dueAt, lookup.tz)} · requested {relTime(req.createdAt)}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {req.escalationLevel > 0 && <StatusChip tone={req.escalationLevel >= 3 ? "risk" : "warn"}>escalation {req.escalationLevel}</StatusChip>}
          <Status value={req.status} />
        </div>
      </div>
      <div className="mt-2 text-xs">From <PersonChip id={req.requestedFrom} /></div>
      {req.status === "open" && (
        <div className="mt-3 flex flex-wrap gap-2">
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
          <Button size="sm" onClick={() => fileRef.current?.click()} disabled={upload.isPending}>
            <Upload /> Upload document
          </Button>
          {g && (
            <Button size="sm" variant="outline" onClick={() => setGrantOpen(true)}>
              <KeyRound /> Grant a data source instead
            </Button>
          )}
        </div>
      )}
      {req.status === "awaiting_grant_approval" && (
        <p className="mt-3 text-xs text-muted-foreground">
          Grant requested. It needs two L1 approvals. <Link href="/l1/approvals" className="text-primary hover:underline">Open approvals</Link>
        </p>
      )}
      {req.fulfilledBy && <p className="mt-3 text-xs text-ok">Fulfilled by {req.fulfilledBy.kind === "upload" ? "an upload" : "a granted source"} ({req.fulfilledBy.ref}).</p>}
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
    </li>
  );
}

export function EvidenceRequests() {
  const requests = useEvidenceRequests();
  const grants = useGrants();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const revoke = useOp<{ grantId: string }>("revokeGrant", { success: "Access revoked" });
  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader title="Evidence requests" description="When the system needs proof, the DRI uploads a document or grants a data source. Requests start early and escalate as deadlines approach." actions={<SampleBadge />} />
      <QueryView query={requests} empty={<EmptyState title="No evidence requests" description="Run the readiness scheduler in L2 to look for gaps." action={<Button asChild size="sm" variant="outline"><Link href="/l2/readiness">Readiness scheduler</Link></Button>} />}>
        {(list) => {
          const open = list.filter((r) => r.status !== "fulfilled");
          const mineFirst = [...open].sort((a, b) => Number(b.requestedFrom === user?.id) - Number(a.requestedFrom === user?.id));
          const done = list.filter((r) => r.status === "fulfilled");
          return (
            <div className="space-y-5">
              <section aria-label="Open requests">
                <h2 className="mb-2 text-sm font-semibold">Open ({open.length})</h2>
                {open.length === 0 ? <EmptyState title="Nothing open" /> : <ul className="space-y-2">{mineFirst.map((r) => <RequestCard key={r.id} req={r} />)}</ul>}
              </section>
              {done.length > 0 && (
                <section aria-label="Fulfilled requests">
                  <h2 className="mb-2 text-sm font-semibold">Fulfilled ({done.length})</h2>
                  <ul className="space-y-2">{done.map((r) => <RequestCard key={r.id} req={r} />)}</ul>
                </section>
              )}
            </div>
          );
        }}
      </QueryView>
      <Section title="Data source grants" className="mt-5">
        <QueryView query={grants} rows={2}>
          {(gs) => (
            <ul className="divide-y">
              {gs.map((g) => (
                <li key={g.id} className="flex flex-wrap items-center gap-3 py-2 text-sm">
                  <div className="min-w-0 flex-1">
                    <div className="font-medium">{g.source}</div>
                    <div className="text-xs text-muted-foreground">
                      {g.scope} · {g.retentionDays} days · {g.agents.map((a) => lookup.name(a)).join(", ")}
                    </div>
                  </div>
                  <Status value={g.status} />
                  {g.status === "active" && user && user.tier !== "L3" && (
                    <Button size="xs" variant="outline" onClick={() => revoke.mutate({ grantId: g.id })}>
                      <ShieldOff /> Revoke
                    </Button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </QueryView>
      </Section>
    </div>
  );
}

"use client";

import { CheckCircle2, ShieldOff } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import type { EvidenceRequest, Grant } from "@/contracts";
import { Button } from "@/components/ui/button";
import { CardPager, Folded } from "@/components/brain/card-pager";
import { PersonChip, useLookup } from "@/components/brain/names";
import { EmptyState, PageHeader, QueryView, SampleBadge, Status, StatusChip } from "@/components/brain/primitives";
import { useEvidenceRequests, useGrants, useObligations, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date } from "@/lib/format";
import { RequestActions } from "./evidence-actions";

/** Proof the system still needs: one open request at a time, mine first, then soonest due. Done things and grants are folded. ?req= opens on one. */
export function EvidenceRequests({ embedded = false }: { embedded?: boolean }) {
  const requests = useEvidenceRequests();
  const { user } = useCurrentUser();
  const startAt = useSearchParams().get("req");
  return (
    <div>
      {!embedded && <PageHeader title="Evidence" description="Proof we still need." actions={<SampleBadge />} />}
      <QueryView query={requests} empty={<EmptyState title="Nothing needed" action={<Button asChild size="sm" variant="outline"><Link href="/l2/readiness">Check readiness</Link></Button>} />}>
        {(list) => {
          const mine = (r: EvidenceRequest) => Number(r.requestedFrom === user?.id);
          const open = list.filter((r) => r.status !== "fulfilled").sort((a, b) => mine(b) - mine(a) || (a.dueAt < b.dueAt ? -1 : 1));
          const done = list.filter((r) => r.status === "fulfilled");
          return (
            <div>
              {open.length === 0 ? <EmptyState title="Nothing open" /> : <CardPager items={open} getId={(r) => r.id} render={(r) => <RequestCard req={r} />} label="Open requests" startAt={startAt} />}
              {done.length > 0 && (
                <Folded title={`Fulfilled (${done.length})`}>
                  <ul className="space-y-3" aria-label="Fulfilled requests">{done.map((r) => <FulfilledLine key={r.id} req={r} />)}</ul>
                </Folded>
              )}
            </div>
          );
        }}
      </QueryView>
      <GrantsFold />
    </div>
  );
}

function RequestCard({ req }: { req: EvidenceRequest }) {
  const lookup = useLookup();
  const obligations = useObligations();
  const ob = obligations.data?.find((o) => o.id === req.obligationId);
  return (
    <article className="space-y-6 rounded-2xl border bg-card p-8">
      <div className="space-y-2">
        <div className="flex flex-wrap gap-2">
          <Status value={req.status} />
          {req.escalationLevel > 0 && <StatusChip tone={req.escalationLevel >= 3 ? "risk" : "warn"}>Reminder {req.escalationLevel}</StatusChip>}
        </div>
        <h2 className="text-xl font-semibold leading-snug">{req.item}</h2>
        <p className="text-[15px] text-muted-foreground">
          {ob?.title ?? req.obligationId} · due {date(ob?.dueAt ?? req.dueAt, lookup.tz)}
        </p>
      </div>
      <PersonChip id={req.requestedFrom} />
      <RequestActions req={req} />
    </article>
  );
}

function FulfilledLine({ req }: { req: EvidenceRequest }) {
  const how = req.fulfilledBy?.kind === "upload" ? "an upload" : "a granted source";
  return (
    <li className="flex items-start gap-3 rounded-xl border bg-card p-4">
      <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-ok" aria-hidden />
      <div>
        <p className="text-[15px] font-medium">{req.item}</p>
        {req.fulfilledBy && <p className="mt-1 text-[14px] text-muted-foreground">Fulfilled by {how}</p>}
      </div>
    </li>
  );
}

/** Data sources the system may read, folded: they change rarely. A steward or leader can revoke an active one. */
function GrantsFold() {
  const grants = useGrants();
  if (!grants.data?.length) return null;
  return (
    <Folded title={`Data sources (${grants.data.length})`}>
      <ul className="space-y-3" aria-label="Data source grants">{grants.data.map((g) => <GrantLine key={g.id} grant={g} />)}</ul>
    </Folded>
  );
}

function GrantLine({ grant }: { grant: Grant }) {
  const { user } = useCurrentUser();
  const revoke = useOp<{ grantId: string }>("revokeGrant", { success: "Access revoked" });
  return (
    <li className="flex items-center justify-between gap-4 rounded-xl border bg-card p-4">
      <div className="space-y-1">
        <p className="text-[15px] font-medium">{grant.source}</p>
        <p className="text-[14px] text-muted-foreground">{grant.scope} · {grant.retentionDays} days</p>
      </div>
      {grant.status === "active" && user && user.tier !== "L3" ? (
        <Button size="sm" variant="outline" onClick={() => revoke.mutate({ grantId: grant.id })}>
          <ShieldOff /> Revoke
        </Button>
      ) : (
        <Status value={grant.status} />
      )}
    </li>
  );
}

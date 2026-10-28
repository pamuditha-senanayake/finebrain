"use client";

import { Check, Minus, PencilRuler, ShieldCheck, ShieldOff } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { Agent, Grant } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { AgentChip, PersonChip, useLookup } from "@/components/brain/names";
import { CritBadge, Mono, QueryView, Status, StatusChip } from "@/components/brain/primitives";
import { useAccessHomes, useAccessRules, useAccessTiers, useAgents, useGrants, useHumans, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";

// Config
const LEVELS = ["public", "internal", "confidential", "restricted"] as const;
const TONE = { restricted: "risk", confidential: "warn" } as const;
const EMPTY = "text-[15px] text-muted-foreground";

export function AgentsTab({ onCheck }: { onCheck: (agentId: string) => void }) {
  const agents = useAgents();
  const homes = useAccessHomes().data ?? {};
  return (
    <QueryView query={agents}>
      {(as) => as.length === 0 ? <p className={EMPTY}>No agents yet. Add one in Studio.</p> : (
        <ul className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {as.map((a: Agent) => (
            <li key={a.id} className="space-y-4 rounded-2xl border bg-card p-5">
              <div className="flex items-center justify-between gap-2">
                <AgentChip id={a.id} />
                <StatusChip tone={TONE[a.accessLevel as keyof typeof TONE] ?? "neutral"}>{a.tier} · reads {a.accessLevel}</StatusChip>
              </div>
              {a.capabilities.length === 0 ? <p className={EMPTY}>Can do nothing yet</p> : (
                <ul className="flex flex-wrap gap-1.5" aria-label="Can do">{a.capabilities.map((c) => <li key={c}><Mono className="rounded bg-muted px-1.5 py-0.5 text-[13px]">{c}</Mono></li>)}</ul>
              )}
              <div className="flex gap-2">
                <Button size="sm" variant="outline" onClick={() => onCheck(a.id)}><ShieldCheck /> Check</Button>
                {homes[a.id] ? (
                  <Button size="sm" variant="outline" asChild><Link href={`/studio?wf=${homes[a.id]}&focus=${a.id}`}><PencilRuler /> Edit in Studio</Link></Button>
                ) : <Button size="sm" variant="outline" disabled title="Not part of a Studio workflow yet"><PencilRuler /> Edit in Studio</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}
    </QueryView>
  );
}

export function PeopleTab() {
  const humans = useHumans();
  return (
    <QueryView query={humans}>
      {(hs) => (
        <>
          <table className="mini-table w-full text-[15px]">
            <thead className="text-left"><tr><th className="py-2 font-medium">Person</th><th className="py-2 font-medium">Tier</th><th className="py-2 font-medium">Roles</th><th className="py-2 font-medium">Approves up to</th></tr></thead>
            <tbody>
              {hs.map((h) => (
                <tr key={h.id} className="border-t">
                  <td className="py-3"><PersonChip id={h.id} /></td>
                  <td className="py-3">{h.tier}</td>
                  <td className="py-3">{h.roles.join(", ")}</td>
                  <td className="py-3">{h.maxApprovalCriticality > 0 ? <CritBadge level={h.maxApprovalCriticality} /> : <span className="text-muted-foreground">Cannot approve</span>}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-[14px] text-muted-foreground">Tiers and roles come from your people directory. Change them there.</p>
        </>
      )}
    </QueryView>
  );
}

export function RulesTab() {
  const rules = useAccessRules();
  const tiers = useAccessTiers();
  return (
    <div className="space-y-8">
      <QueryView query={tiers}>
        {(ts) => (
          <section aria-label="Data each tier reads">
            <h2 className="mb-3 text-[15px] font-semibold">Who reads what</h2>
            <table className="mini-table w-full text-[15px]">
              <thead className="text-left"><tr><th className="py-2 font-medium">Tier</th>{LEVELS.map((l) => <th key={l} className="py-2 font-medium capitalize">{l}</th>)}</tr></thead>
              <tbody>
                {ts.map((t) => (
                  <tr key={t.tier} className="border-t">
                    <td className="py-3 font-medium">{t.tier}</td>
                    {LEVELS.map((l) => <td key={l} className="py-3">{t.reads.includes(l) ? <><Check className="size-4" aria-hidden /><span className="sr-only">Reads {l}</span></> : <><Minus className="size-4 text-muted-foreground" aria-hidden /><span className="sr-only">Cannot read {l}</span></>}</td>)}
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
      </QueryView>
      <QueryView query={rules}>
        {(rs) => (
          <section aria-label="Rules">
            <h2 className="mb-3 text-[15px] font-semibold">Rules</h2>
            <ul className="grid gap-4 md:grid-cols-2">
              {rs.map((r) => (
                <li key={r.id} className="space-y-1.5 rounded-2xl border bg-card p-5">
                  <div className="flex items-center justify-between gap-2"><span className="text-[15px] font-medium">{r.name}</span><StatusChip tone={r.sensitivity === "restricted" ? "risk" : "neutral"}>{r.sensitivity}</StatusChip></div>
                  <p className="text-[14px] text-muted-foreground">{r.description}</p>
                  {r.requiresCapability && <p className="text-[14px]">Needs <Mono>{r.requiresCapability}</Mono></p>}
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[14px] text-muted-foreground">These are the rules every action meets. To change what an agent may do, edit it in Studio.</p>
          </section>
        )}
      </QueryView>
    </div>
  );
}

function SourceLine({ grant, onRevoke, canRevoke }: { grant: Grant; onRevoke: (g: Grant) => void; canRevoke: boolean }) {
  const lookup = useLookup();
  return (
    <li className="flex flex-wrap items-center gap-4 rounded-2xl border bg-card p-5">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="text-[15px] font-medium">{grant.source}</p>
        <p className="text-[14px] text-muted-foreground">{grant.scope} · {grant.retentionDays} days · {grant.agents.map((a) => lookup.name(a)).join(", ")}</p>
      </div>
      {grant.status === "active" && canRevoke ? <Button size="sm" variant="outline" onClick={() => onRevoke(grant)}><ShieldOff /> Revoke</Button> : <Status value={grant.status} />}
    </li>
  );
}

export function SourcesTab() {
  const grants = useGrants();
  const { user } = useCurrentUser();
  const [target, setTarget] = useState<Grant | null>(null);
  const revoke = useOp<{ grantId: string }>("revokeGrant", { success: "Access revoked" });
  return (
    <>
      <QueryView query={grants}>
        {(gs) => gs.length === 0 ? <p className={EMPTY}>No data sources connected. Ask for one from an evidence request.</p> : (
          <ul className="space-y-4" aria-label="Data sources">{gs.map((g) => <SourceLine key={g.id} grant={g} onRevoke={setTarget} canRevoke={!!user && user.tier !== "L3"} />)}</ul>
        )}
      </QueryView>
      <Dialog open={!!target} onOpenChange={(open) => !open && setTarget(null)}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>Revoke {target?.source}?</DialogTitle>
            <DialogDescription>Agents lose this access at once. Work that needs it will go to a person. You can ask for it again later.</DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setTarget(null)}>Keep access</Button>
            <Button variant="destructive" disabled={revoke.isPending} onClick={() => target && revoke.mutate({ grantId: target.id }, { onSuccess: () => setTarget(null) })}>Revoke access</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
}

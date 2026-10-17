"use client";

import { ArrowRight, Moon, Wrench } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import type { DigestItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { CritBadge, EmptyState, PageHeader, QueryView, Section } from "@/components/brain/primitives";
import { useApprovals, useDigest, useEvidenceRequests, useOp } from "@/lib/api/hooks";
import { ApprovalsInbox } from "@/features/l1/approvals";
import { EvidenceRequests } from "@/features/l1/evidence";
import { useCurrentUser } from "@/lib/auth";
import { dateTime } from "@/lib/format";
import { cn } from "@/lib/utils";

function ItemTable({ items, empty, label }: { items: DigestItem[]; empty: string; label: string }) {
  return (
    <SimpleTable
      label={label}
      rows={items}
      getRowId={(i) => i.id}
      empty={empty}
      columns={[
        { id: "crit", header: "Level", className: "w-16", cell: (i) => <CritBadge level={i.criticality} /> },
        { id: "title", header: "Item", className: "font-medium", cell: (i) => i.title },
        { id: "detail", header: "Detail", className: "text-muted-foreground", cell: (i) => i.detail },
        {
          id: "open",
          header: "",
          className: "w-20 text-right",
          cell: (i) =>
            i.href ? (
              <Link href={i.href} className="text-xs text-primary hover:underline" aria-label={`Open ${i.title}`}>
                Open <ArrowRight className="inline size-3" />
              </Link>
            ) : null,
        },
      ]}
    />
  );
}

function Metric({ label, value, tone }: { label: string; value: number; tone?: "ok" | "warn" }) {
  return (
    <div className="px-5 py-4">
      <dt className="text-[11px] font-medium uppercase tracking-[0.07em] text-muted-foreground">{label}</dt>
      <dd className={cn("mt-2 text-[26px] font-semibold leading-none tracking-tight tabular", tone === "ok" && "text-ok", tone === "warn" && "text-warn-fg")}>{value}</dd>
    </div>
  );
}

const TABS = ["summary", "approvals", "evidence"] as const;
type Tab = (typeof TABS)[number];

/** Everything waiting for the owner, whenever they log in: the overnight summary, approvals and evidence requests. */
export function Digest() {
  const params = useSearchParams();
  const router = useRouter();
  const asked = params.get("tab");
  const tab: Tab = TABS.includes(asked as Tab) ? (asked as Tab) : "summary";
  const approvals = useApprovals();
  const evidence = useEvidenceRequests();
  const pendingApprovals = approvals.data?.filter((a) => a.status === "pending").length ?? 0;
  const openEvidence = evidence.data?.filter((r) => r.status !== "fulfilled").length ?? 0;
  const count = (n: number) => (n ? <span className="ml-1.5 tabular text-muted-foreground">{n}</span> : null);
  return (
    <div>
      <PageHeader title="To review" description="What needs you now." />
      <Tabs value={tab} onValueChange={(v) => router.replace(v === "summary" ? "/l1/digest" : `/l1/digest?tab=${v}`, { scroll: false })}>
        <TabsList className="mb-6">
          <TabsTrigger value="summary">Summary</TabsTrigger>
          <TabsTrigger value="approvals" data-testid="tab-approvals">Approvals{count(pendingApprovals)}</TabsTrigger>
          <TabsTrigger value="evidence" data-testid="tab-evidence">Evidence{count(openEvidence)}</TabsTrigger>
        </TabsList>
        <TabsContent value="summary">
          <Summary />
        </TabsContent>
        <TabsContent value="approvals">
          <ApprovalsInbox embedded />
        </TabsContent>
        <TabsContent value="evidence">
          <EvidenceRequests embedded />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function Summary() {
  const digest = useDigest();
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const run = useOp("runOvernightReview", { success: "Overnight review finished" });
  return (
    <div>
      {user && user.tier !== "L3" && (
        <div className="mb-6 flex justify-end">
          <Button variant="outline" size="sm" onClick={() => run.mutate({})} disabled={run.isPending}>
            <Moon /> Run overnight review now
          </Button>
        </div>
      )}
      <QueryView query={digest} empty={<EmptyState title="No digest yet" description="The Quality Supervisor writes one every night at 02:00." />}>
        {(d) => {
          if (!d) return null;
          const fixes = d.items.filter((i) => i.kind === "auto_fix");
          const drafted = d.items.filter((i) => i.kind === "drafted");
          const waiting = d.items.filter((i) => i.kind === "waiting");
          return (
            <div className="space-y-12">
              <div className="space-y-3">
                <p className="text-xs text-muted-foreground">
                  Generated by {d.generatedBy} at {dateTime(d.generatedAt, lookup.tz)} for {d.date}.
                </p>
                <dl className="grid grid-cols-2 divide-x divide-y overflow-hidden rounded-2xl border bg-card shadow-xs md:grid-cols-5 md:divide-y-0" aria-label="Overnight metrics">
                <Metric label="Runs reviewed" value={d.runs} />
                <Metric label="Failures found" value={d.failures} tone={d.failures ? "warn" : "ok"} />
                <Metric label="Fixes applied (C0, C1)" value={fixes.length} tone="ok" />
                <Metric label="Drafted for review" value={drafted.length} />
                <Metric label="Waiting on approvals" value={waiting.length} />
                </dl>
              </div>
              <div className="space-y-12">
                <Section plain title={<span className="flex items-center gap-1.5"><Wrench className="size-3.5" /> Applied automatically</span>} description="Routine and low changes. Logged, reversible, tests passing.">
                  <div data-testid="digest-applied">
                    <ItemTable label="Applied automatically" items={fixes} empty="No automatic fixes last night." />
                  </div>
                </Section>
                <Section plain title="Drafted, needs a decision" description="C2 and above go to the right person through the criticality matrix.">
                  <div data-testid="digest-drafted">
                    <ItemTable label="Drafted, needs a decision" items={drafted} empty="Nothing drafted." />
                  </div>
                </Section>
                <Section plain title="Waiting on approvals">
                  <ItemTable label="Waiting on approvals" items={waiting} empty="Inbox zero." />
                </Section>
                <Section plain title="Failures found, by class">
                  <SimpleTable
                    label="Failures by class"
                    rows={d.failureClasses}
                    getRowId={(f) => f.name}
                    empty="No failures."
                    columns={[
                      { id: "name", header: "Class", className: "font-medium", cell: (f) => <span className="capitalize">{f.name}</span> },
                      { id: "count", header: "Count", align: "right", className: "w-24", cell: (f) => f.count },
                      {
                        id: "share",
                        header: "Share",
                        className: "w-1/2",
                        cell: (f) => (
                          <div className="h-1.5 rounded-full bg-muted">
                            <div className="h-1.5 rounded-full bg-warn" style={{ width: `${(f.count / Math.max(...d.failureClasses.map((x) => x.count))) * 100}%` }} />
                          </div>
                        ),
                      },
                    ]}
                  />
                </Section>
              </div>
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

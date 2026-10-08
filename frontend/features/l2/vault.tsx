"use client";

import { Scale } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import type { Fact } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { Beam } from "@/components/brain/motion";
import { useLookup } from "@/components/brain/names";
import { EmptyState, KeyValue, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useDocuments, useFacts, useLibrarian, useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";

export function Vault() {
  const facts = useFacts();
  const librarian = useLibrarian();
  const documents = useDocuments();
  const lookup = useLookup();
  const params = useSearchParams();
  const router = useRouter();
  const factId = params.get("fact");
  const { user } = useCurrentUser();
  const propose = useOp<{ itemId: string }>("librarianPropose", { success: "Proposal drafted as one change request" });
  const selected = facts.data?.find((f) => f.id === factId) ?? null;
  const columns: Column<Fact>[] = useMemo(
    () => [
      { id: "statement", header: "Fact", width: "minmax(260px,2.4fr)", value: (f) => f.statement, cell: (f) => <span className="truncate">{f.statement}</span> },
      { id: "status", header: "Status", width: "100px", value: (f) => f.status, cell: (f) => <Status value={f.status} /> },
      { id: "valid", header: "True from", width: "110px", value: (f) => f.validFrom, hideOnMobile: true, cell: (f) => <span className="text-muted-foreground">{date(f.validFrom, lookup.tz)}</span> },
      { id: "until", header: "Until", width: "100px", value: (f) => f.validTo ?? "9999", hideOnMobile: true, cell: (f) => <span className="text-muted-foreground">{f.validTo ? date(f.validTo, lookup.tz) : "now"}</span> },
      { id: "recorded", header: "Learned", width: "100px", value: (f) => f.recordedAt, hideOnMobile: true, cell: (f) => <span className="text-muted-foreground">{relTime(f.recordedAt)}</span> },
      { id: "verified", header: "Verified by", width: "130px", value: (f) => (f.verifiedBy ? lookup.name(f.verifiedBy) : ""), hideOnMobile: true, cell: (f) => (f.verifiedBy ? <span className="truncate">{lookup.name(f.verifiedBy)}</span> : <span className="text-warn-fg">unverified</span>) },
      { id: "deps", header: "Dependents", width: "84px", align: "right", value: (f) => f.dependents.length, cell: (f) => f.dependents.length },
    ],
    [lookup],
  );
  useEffect(() => {
    if (factId) document.getElementById("fact-detail")?.scrollIntoView({ block: "nearest" });
  }, [factId]);
  return (
    <div>
      <PageHeader title="Ground truth vault" description="Verified facts with provenance, valid time, recorded time and dependents. The librarian queue holds conflicts, stale facts, duplicates, orphans and unverified claims." />
      <Tabs defaultValue={factId ? "facts" : "queue"}>
        <TabsList>
          <TabsTrigger value="queue">Librarian queue {librarian.data && <span className="ml-1 text-muted-foreground">{librarian.data.filter((i) => i.status === "open").length}</span>}</TabsTrigger>
          <TabsTrigger value="facts">Facts</TabsTrigger>
        </TabsList>
        <TabsContent value="queue" className="mt-3">
          <QueryView query={librarian} empty={<EmptyState title="The librarian queue is empty" />}>
            {(items) => (
              <ul className="space-y-3">
                {items.map((item, i) => (
                  <li key={item.id}>
                    <Beam active={item.kind === "conflict" && item.status === "open" && i === 0} className="rounded-xl">
                      <div className="rounded-xl border bg-card p-4" data-testid={`librarian-${item.id}`}>
                        <div className="flex flex-wrap items-center gap-2">
                          <StatusChip tone={item.kind === "conflict" ? "risk" : item.kind === "stale" || item.kind === "unverified" ? "warn" : "neutral"}>{item.kind}</StatusChip>
                          <h3 className="text-sm font-semibold">{item.title}</h3>
                          <span className="ml-auto"><Status value={item.status} /></span>
                        </div>
                        <p className="mt-1.5 text-sm text-muted-foreground">{item.detail}</p>
                        {item.factIds.length > 0 && (
                          <ul className="mt-2 flex flex-wrap gap-1.5">
                            {item.factIds.map((f) => (
                              <li key={f}>
                                <Link href={`/l2/vault?fact=${f}`} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] hover:underline">{f}</Link>
                              </li>
                            ))}
                          </ul>
                        )}
                        {item.proposal && (
                          <div className="mt-3 rounded-lg bg-surface p-3 text-sm">
                            <div className="mb-1 flex items-center gap-1.5 text-xs font-medium"><Scale className="size-3.5" /> Librarian proposal</div>
                            <KeyValue items={[["Winning source", item.proposal.winningSource], ["New validity from", date(item.proposal.newValidFrom, lookup.tz)], ["Dependents updated", item.proposal.dependents.map((d) => d.label).join(", ") || "none"]]} />
                          </div>
                        )}
                        <div className="mt-3 flex gap-2">
                          {item.status === "open" && (
                            <Button size="sm" onClick={() => propose.mutate({ itemId: item.id }, { onSuccess: (cr) => router.push(`/l2/versioning/${(cr as { id: string }).id}`) })} disabled={propose.isPending || !user || user.tier === "L3"} data-testid={`propose-${item.id}`}>
                              {item.kind === "conflict" ? "Propose resolution" : "Draft fix"}
                            </Button>
                          )}
                          {item.changeRequestId && (
                            <Button size="sm" variant="outline" asChild>
                              <Link href={`/l2/versioning/${item.changeRequestId}`}>Open change request</Link>
                            </Button>
                          )}
                          {item.policyId && (
                            <Button size="sm" variant="ghost" asChild>
                              <Link href={`/l2/policies/${item.policyId.split("@")[0]}`}>Policy timeline</Link>
                            </Button>
                          )}
                        </div>
                      </div>
                    </Beam>
                  </li>
                ))}
              </ul>
            )}
          </QueryView>
        </TabsContent>
        <TabsContent value="facts" className="mt-3 grid gap-4 xl:grid-cols-[1fr_340px]">
          <QueryView query={facts}>
            {(fs) => <DataTable label="Facts" data={fs} columns={columns} getRowId={(f) => f.id} onRowClick={(f) => router.replace(`/l2/vault?fact=${f.id}`)} initialSort={{ id: "recorded", desc: true }} height="calc(100dvh - 280px)" rowClassName={(f) => (f.id === factId ? "bg-primary/10" : undefined)} />}
          </QueryView>
          <div id="fact-detail">
            <Section title={selected ? "Fact" : "Select a fact"}>
              {selected ? (
                <div className="space-y-3 text-sm">
                  <p className="font-medium">{selected.statement}</p>
                  <KeyValue
                    items={[
                      ["Value", selected.value],
                      ["True in the world", `${date(selected.validFrom, lookup.tz)} → ${selected.validTo ? date(selected.validTo, lookup.tz) : "now"}`],
                      ["Learned by the system", date(selected.recordedAt, lookup.tz)],
                      ["Verified by", selected.verifiedBy ? lookup.name(selected.verifiedBy) : "not verified"],
                      ["Status", <Status key="s" value={selected.status} />],
                      ["Sensitivity", selected.sensitivity],
                    ]}
                  />
                  <div>
                    <div className="mb-1 text-xs font-medium">Evidence</div>
                    {selected.evidence.map((e, i) => (
                      <blockquote key={i} className="rounded-md border-l-2 border-primary bg-surface p-2 text-xs">
                        “{e.quote}”
                        <div className="mt-1 text-muted-foreground">
                          {documents.data?.find((d) => d.id === e.documentId)?.title ?? e.documentId}
                          {e.page ? `, page ${e.page}` : ""}
                        </div>
                      </blockquote>
                    ))}
                  </div>
                  <div>
                    <div className="mb-1 text-xs font-medium">What depends on it</div>
                    <ul className="space-y-1 text-xs">
                      {selected.dependents.length === 0 && <li className="text-muted-foreground">Nothing yet</li>}
                      {selected.dependents.map((d) => (
                        <li key={d.id}><Mono className="text-muted-foreground">{d.type}</Mono> {d.label}</li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : (
                <p className="text-xs text-muted-foreground">Facts carry their evidence, when they are true, when the system learned them, who verified them, and what depends on them.</p>
              )}
            </Section>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}

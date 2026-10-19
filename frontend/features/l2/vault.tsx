"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import type { Fact } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { DataTable, type Column } from "@/components/brain/data-table";
import { SimpleTable } from "@/components/brain/simple-table";
import { useLookup } from "@/components/brain/names";
import { EmptyState, KeyValue, Mono, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useDocuments, useFacts, useLibrarian, useOp, useTenantId } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date, relTime } from "@/lib/format";
import { LibrarianActions } from "./librarian-actions";

export function Vault() {
  const facts = useFacts();
  const librarian = useLibrarian();
  const documents = useDocuments();
  const lookup = useLookup();
  const params = useSearchParams();
  const router = useRouter();
  const factId = params.get("fact");
  const { user } = useCurrentUser();
  const real = useTenantId() === "finebase-hq";
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
              <SimpleTable
                label="Librarian queue"
                rows={items}
                getRowId={(i) => i.id}
                columns={[
                  { id: "kind", header: "Type", cell: (i) => <StatusChip tone={i.kind === "conflict" ? "risk" : i.kind === "stale" || i.kind === "unverified" ? "warn" : "neutral"}>{i.kind}</StatusChip> },
                  {
                    id: "title",
                    header: "Item",
                    cell: (i) => (
                      <div className="max-w-lg space-y-1.5">
                        <div className="font-medium" data-testid={`librarian-${i.id}`}>{i.title}</div>
                        <p className="line-clamp-3 text-xs leading-relaxed text-muted-foreground" title={i.detail}>{i.detail}</p>
                        {i.proposal && (
                          <p className="text-xs">
                            <span className="text-muted-foreground">Proposal:</span> {i.proposal.winningSource} wins, valid from {date(i.proposal.newValidFrom, lookup.tz)}
                            {i.proposal.dependents.length > 0 && <span className="text-muted-foreground"> · updates {i.proposal.dependents.map((d) => d.label).join(", ")}</span>}
                          </p>
                        )}
                      </div>
                    ),
                  },
                  {
                    id: "facts",
                    header: "Facts",
                    cell: (i) => (
                      <div className="flex max-w-[180px] flex-col items-start gap-1">
                        {i.factIds.map((f) => (
                          <Link key={f} href={`/l2/vault?fact=${f}`} className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] hover:underline">{f}</Link>
                        ))}
                      </div>
                    ),
                  },
                  { id: "status", header: "Status", cell: (i) => <Status value={i.status} /> },
                  {
                    id: "actions",
                    header: "Fix",
                    cell: (i) => (
                      <div className="flex flex-wrap gap-1.5">
                        {real && <LibrarianActions item={i} />}
                        {!real && i.status === "open" && (
                          <Button size="xs" onClick={() => propose.mutate({ itemId: i.id }, { onSuccess: (cr) => router.push(`/l2/versioning/${(cr as { id: string }).id}`) })} disabled={propose.isPending || !user || user.tier === "L3"} data-testid={`propose-${i.id}`}>
                            {i.kind === "conflict" ? "Propose resolution" : "Draft fix"}
                          </Button>
                        )}
                        {i.changeRequestId && (
                          <Button size="xs" variant="outline" asChild>
                            <Link href={`/l2/versioning/${i.changeRequestId}`}>Change request</Link>
                          </Button>
                        )}
                        {i.policyId && (
                          <Button size="xs" variant="ghost" asChild>
                            <Link href={`/l2/policies/${i.policyId.split("@")[0]}`}>Policy timeline</Link>
                          </Button>
                        )}
                      </div>
                    ),
                  },
                ]}
              />
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
                          <Link href={`/l2/library?doc=${e.documentId}`} className="hover:text-foreground hover:underline">
                            {documents.data?.find((d) => d.id === e.documentId)?.title ?? e.documentId}
                          </Link>
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

"use client";

import { ChevronRight, FileText, Folder as FolderIcon, Search } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useMemo, useState } from "react";
import type { Document, Fact } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { useLookup } from "@/components/brain/names";
import { SimpleTable } from "@/components/brain/simple-table";
import { KeyValue, PageHeader, QueryView, Section, Status, StatusChip } from "@/components/brain/primitives";
import { useDocuments, useFacts, useFilingRules, useTenantId } from "@/lib/api/hooks";
import { ForgetCard, ReceiptList } from "./forget-card";
import { date } from "@/lib/format";
import { FOLDERS, folderOf, searchDocuments } from "@/lib/library";
import { cn } from "@/lib/utils";

const SHOWN = 60;

export function LibraryView() {
  const documents = useDocuments();
  const facts = useFacts();
  const lookup = useLookup();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const [folderId, setFolderId] = useState<string>(() => {
    const doc = documents.data?.find((d) => d.id === params.get("doc"));
    return doc ? folderOf(doc).id : FOLDERS[0].id;
  });
  const [query, setQuery] = useState("");
  const openId = params.get("doc");

  const factsByDoc = useMemo(() => {
    const map = new Map<string, Fact[]>();
    for (const f of facts.data ?? []) for (const e of f.evidence) map.set(e.documentId, [...(map.get(e.documentId) ?? []), f]);
    return map;
  }, [facts.data]);

  const setDoc = (id: string | null) => {
    const next = new URLSearchParams(params.toString());
    if (id) next.set("doc", id);
    else next.delete("doc");
    const qs = next.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  };

  return (
    <div>
      <PageHeader title="Library" description="Every document, filed into folders as it arrives." />
      <QueryView query={documents}>
        {(docs) => {
          const counts = new Map<string, number>();
          for (const d of docs) counts.set(folderOf(d).id, (counts.get(folderOf(d).id) ?? 0) + 1);
          const folders = FOLDERS.filter((f) => counts.get(f.id));
          const folder = folders.find((f) => f.id === folderId) ?? folders[0];
          const searching = query.trim().length > 1;
          const hits = searching ? searchDocuments(docs, factsByDoc, query) : docs.filter((d) => folderOf(d).id === folder?.id).sort((a, b) => (a.uploadedAt < b.uploadedAt ? 1 : -1)).map((doc) => ({ doc, score: 0, reason: null }));
          const open = docs.find((d) => d.id === openId) ?? null;
          return (
            <div className="grid gap-8 lg:grid-cols-[240px_1fr]">
              <nav aria-label="Folders" className="space-y-1">
                {folders.map((f) => (
                  <button
                    key={f.id}
                    type="button"
                    onClick={() => {
                      setFolderId(f.id);
                      setQuery("");
                    }}
                    aria-current={!searching && f.id === folder?.id ? "true" : undefined}
                    className={cn("flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-[14.5px] text-muted-foreground transition-colors hover:bg-sidebar-accent hover:text-foreground", !searching && f.id === folder?.id && "bg-sidebar-accent font-medium text-foreground")}
                  >
                    <FolderIcon className="size-4 shrink-0" aria-hidden />
                    <span className="truncate">{f.name}</span>
                    <span className="ml-auto text-xs tabular text-muted-foreground">{counts.get(f.id)}</span>
                  </button>
                ))}
              </nav>

              <div className="min-w-0 space-y-5">
                <div className="relative">
                  <Search className="pointer-events-none absolute left-3.5 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" aria-hidden />
                  <input
                    type="search"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Search by name or meaning"
                    aria-label="Search documents by name or meaning"
                    data-testid="library-search"
                    className="h-11 w-full rounded-xl border bg-card pl-10 pr-4 text-[15px] shadow-xs outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/50"
                  />
                </div>
                <h2 className="text-[15px] font-semibold">{searching ? `${hits.length} found` : folder?.name}</h2>
                {hits.length === 0 ? (
                  <p className="text-sm text-muted-foreground">Nothing matches. Try other words.</p>
                ) : (
                  <ul className="divide-y overflow-hidden rounded-xl border bg-card" aria-label="Documents">
                    {hits.slice(0, SHOWN).map(({ doc, reason }) => (
                      <li key={doc.id}>
                        <button type="button" onClick={() => setDoc(doc.id)} className="flex w-full items-start gap-3 px-4 py-3.5 text-left transition-colors hover:bg-sidebar-accent/60" data-testid={`doc-${doc.id}`}>
                          <FileText className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-[15px] font-medium">{doc.title}</span>
                            <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                              {searching ? `${folderOf(doc).name} · ` : ""}
                              {date(doc.uploadedAt, lookup.tz)}
                            </span>
                            {reason && <span className="mt-1 block truncate text-xs text-foreground/80">Says: {reason}</span>}
                          </span>
                          <ChevronRight className="mt-0.5 size-4 shrink-0 text-muted-foreground" aria-hidden />
                        </button>
                      </li>
                    ))}
                  </ul>
                )}
                {hits.length > SHOWN && <p className="text-xs text-muted-foreground">Showing {SHOWN} of {hits.length}. Search to narrow down.</p>}
                <FilingRules />
              </div>

              <DocumentSheet doc={open} facts={open ? (factsByDoc.get(open.id) ?? []) : []} onClose={() => setDoc(null)} onFolder={(id) => { setFolderId(id); setQuery(""); setDoc(null); }} />
            </div>
          );
        }}
      </QueryView>
    </div>
  );
}

/** One document, opened: where it is filed, what it says, and its details. */
function DocumentSheet({ doc, facts, onClose, onFolder }: { doc: Document | null; facts: Fact[]; onClose: () => void; onFolder: (folderId: string) => void }) {
  const lookup = useLookup();
  const folder = doc ? folderOf(doc) : null;
  const [removing, setRemoving] = useState(false);
  const removable = useTenantId() === "finebase-hq" && !!doc && (doc.extractionStatus === "done" || doc.extractionStatus === "retired");
  return (
    <Sheet open={!!doc} onOpenChange={(o) => !o && onClose()}>
      <SheetContent side="right" className="w-full gap-0 overflow-y-auto p-0 sm:max-w-lg">
        {doc && folder && (
          <>
            <SheetHeader className="border-b p-6">
              <button type="button" onClick={() => onFolder(folder.id)} className="flex w-fit items-center gap-1.5 text-xs font-medium text-muted-foreground hover:text-foreground hover:underline">
                <FolderIcon className="size-3.5" aria-hidden /> {folder.name}
              </button>
              <SheetTitle className="text-lg leading-snug">{doc.title}</SheetTitle>
              <SheetDescription>Added {date(doc.uploadedAt, lookup.tz)} by {lookup.name(doc.uploadedBy)}</SheetDescription>
              {(doc.extractionStatus === "retired" || doc.extractionStatus === "erased") && <Status value={doc.extractionStatus} />}
            </SheetHeader>
            <div className="space-y-8 p-6">
              {doc.receipt && (
                <section>
                  <h3 className="mb-3 text-[15px] font-semibold">Receipt</h3>
                  <ReceiptList receipt={doc.receipt} />
                </section>
              )}
              {doc.extractionStatus !== "erased" && <section>
                <h3 className="mb-3 text-[15px] font-semibold">What it says</h3>
                {facts.length === 0 ? (
                  <p className="text-sm text-muted-foreground">No facts taken from this document yet.</p>
                ) : (
                  <ul className="space-y-3">
                    {facts.map((f) => (
                      <li key={f.id} className="rounded-xl border bg-card p-4">
                        <p className="text-[14.5px] font-medium leading-snug">{f.statement}</p>
                        {f.evidence
                          .filter((e) => e.documentId === doc.id)
                          .map((e, i) => (
                            <blockquote key={i} className="mt-2 border-l-2 border-primary pl-3 text-[13px] text-muted-foreground">
                              “{e.quote}”{e.page ? ` · page ${e.page}` : ""}
                            </blockquote>
                          ))}
                        <div className="mt-2 flex items-center gap-3">
                          <Status value={f.status} />
                          <Link href={`/l2/vault?fact=${f.id}`} className="text-xs text-primary hover:underline">
                            Open in ground truth
                          </Link>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </section>}
              {doc.extractionStatus !== "erased" && <section>
                <h3 className="mb-3 text-[15px] font-semibold">Details</h3>
                <KeyValue
                  items={[
                    ["Folder", folder.name],
                    ["Source", doc.source],
                    ["Sensitivity", <StatusChip key="s" tone={doc.sensitivity === "restricted" ? "risk" : doc.sensitivity === "confidential" ? "warn" : "neutral"}>{doc.sensitivity}</StatusChip>],
                    ["Personal data", doc.personalData ? "Yes, masked" : "None"],
                    ["Kept for", `${Math.round(doc.retentionDays / 365)} years`],
                    ["Size", `${doc.sizeKb.toLocaleString()} KB`],
                    ["Area", lookup.cluster(doc.clusterId)],
                  ]}
                />
              </section>}
              {removable && (
                <Button variant="outline" onClick={() => setRemoving(true)}>
                  Remove
                </Button>
              )}
              {removing && <ForgetCard documentId={doc.id} retired={doc.extractionStatus === "retired"} onClose={() => setRemoving(false)} />}
            </div>
          </>
        )}
      </SheetContent>
    </Sheet>
  );
}

/** How new material is filed. Folded away: most people never need it. */
function FilingRules() {
  const rules = useFilingRules();
  const lookup = useLookup();
  return (
    <details className="group pt-4">
      <summary className="cursor-pointer list-none text-[13px] font-medium text-muted-foreground hover:text-foreground">
        <ChevronRight className="mr-1 inline size-3.5 transition-transform group-open:rotate-90" aria-hidden />
        How filing works
      </summary>
      <Section plain className="mt-4" description="New files go to a folder by their type. These rules set the area, sensitivity and how long they are kept.">
        <QueryView query={rules} rows={3}>
          {(rs) => (
            <SimpleTable
              label="Filing rules"
              rows={rs}
              getRowId={(r) => r.id}
              columns={[
                { id: "match", header: "Matches", className: "font-medium", cell: (r) => r.match },
                { id: "cluster", header: "Area", cell: (r) => lookup.cluster(r.clusterId) },
                { id: "sens", header: "Sensitivity", cell: (r) => r.sensitivity },
                { id: "ret", header: "Kept for", align: "right", cell: (r) => `${Math.round(r.retentionDays / 365)} years` },
              ]}
            />
          )}
        </QueryView>
      </Section>
    </details>
  );
}

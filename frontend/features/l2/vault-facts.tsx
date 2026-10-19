"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useEffect, useMemo } from "react";
import type { Fact } from "@/contracts";
import { DataTable, type Column } from "@/components/brain/data-table";
import { useLookup } from "@/components/brain/names";
import { KeyValue, Mono, QueryView, Section, Status } from "@/components/brain/primitives";
import { useDocuments, useFacts } from "@/lib/api/hooks";
import { date, relTime } from "@/lib/format";

/** Every fact true now, with its proof. Picking a row opens its evidence beside the list. */
export function VaultFacts() {
  const facts = useFacts();
  const lookup = useLookup();
  const router = useRouter();
  const factId = useSearchParams().get("fact");
  const selected = facts.data?.find((f) => f.id === factId) ?? null;
  const columns: Column<Fact>[] = useMemo(
    () => [
      { id: "statement", header: "Fact", width: "minmax(260px,2.4fr)", value: (f) => f.statement, cell: (f) => <span className="truncate">{f.statement}</span> },
      { id: "status", header: "Status", width: "110px", value: (f) => f.status, cell: (f) => <Status value={f.status} /> },
      { id: "valid", header: "True from", width: "110px", value: (f) => f.validFrom, hideOnMobile: true, cell: (f) => <span className="text-muted-foreground">{date(f.validFrom, lookup.tz)}</span> },
      { id: "recorded", header: "Learned", width: "100px", value: (f) => f.recordedAt, hideOnMobile: true, cell: (f) => <span className="text-muted-foreground">{relTime(f.recordedAt)}</span> },
    ],
    [lookup],
  );
  useEffect(() => {
    if (factId) document.getElementById("fact-detail")?.scrollIntoView({ block: "nearest" });
  }, [factId]);
  return (
    <div className="grid gap-6 xl:grid-cols-[1fr_360px]">
      <QueryView query={facts}>
        {(fs) => <DataTable label="Facts" data={fs} columns={columns} getRowId={(f) => f.id} onRowClick={(f) => router.replace(`/l2/vault?tab=facts&fact=${f.id}`)} initialSort={{ id: "recorded", desc: true }} height="calc(100dvh - 280px)" rowClassName={(f) => (f.id === factId ? "bg-primary/10" : undefined)} />}
      </QueryView>
      <div id="fact-detail">
        <Section title={selected ? "Fact" : "Pick a fact"}>
          {selected ? <FactDetail fact={selected} /> : <p className="text-[15px] text-muted-foreground">Its proof shows here.</p>}
        </Section>
      </div>
    </div>
  );
}

function FactDetail({ fact }: { fact: Fact }) {
  const lookup = useLookup();
  const documents = useDocuments();
  return (
    <div className="space-y-5 text-[15px]">
      <p className="font-medium">{fact.statement}</p>
      <KeyValue
        items={[
          ["Value", fact.value],
          ["True", `${date(fact.validFrom, lookup.tz)} → ${fact.validTo ? date(fact.validTo, lookup.tz) : "now"}`],
          ["Learned", date(fact.recordedAt, lookup.tz)],
          ["Verified by", fact.verifiedBy ? lookup.name(fact.verifiedBy) : "not verified"],
          ["Status", <Status key="s" value={fact.status} />],
        ]}
      />
      {fact.evidence.map((e, i) => (
        <blockquote key={i} className="rounded-lg border-l-2 border-primary bg-surface p-3 text-[14px]">
          “{e.quote}”
          <div className="mt-1.5 text-[13px] text-muted-foreground">
            <Link href={`/l2/library?doc=${e.documentId}`} className="hover:text-foreground hover:underline">
              {documents.data?.find((d) => d.id === e.documentId)?.title ?? e.documentId}
            </Link>
            {e.page ? `, page ${e.page}` : ""}
          </div>
        </blockquote>
      ))}
      {fact.dependents.length > 0 && (
        <ul className="space-y-1 text-[13px]">
          {fact.dependents.map((d) => (
            <li key={d.id}><Mono className="text-muted-foreground">{d.type}</Mono> {d.label}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

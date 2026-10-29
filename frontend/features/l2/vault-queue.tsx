"use client";

import { ChevronLeft, ChevronRight } from "lucide-react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState } from "react";
import type { LibrarianItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { EmptyState, StatusChip } from "@/components/brain/primitives";
import { useLookup } from "@/components/brain/names";
import { useOp, useTenantId } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { date } from "@/lib/format";
import { LibrarianActions } from "./librarian-actions";
import { realTenants } from "@/lib/flags";

const KIND = {
  unverified: { label: "To verify", tone: "warn" },
  conflict: { label: "Conflict", tone: "risk" },
  stale: { label: "Out of date", tone: "warn" },
  duplicate: { label: "Duplicate", tone: "neutral" },
  orphan: { label: "No source", tone: "neutral" },
} as const;

/** What waits for review, one card at a time. Settled items stay out of the way. ?item= opens on one. */
export function VaultQueue({ items }: { items: LibrarianItem[] }) {
  const waiting = items.filter((i) => i.status !== "resolved");
  const asked = useSearchParams().get("item");
  const [at, setAt] = useState(() => Math.max(0, waiting.findIndex((i) => i.id === asked)));
  if (waiting.length === 0) return <EmptyState title="Nothing to review" description={`${items.length} settled`} />;
  const i = Math.min(at, waiting.length - 1);
  const n = waiting.length;
  return (
    <section className="mx-auto max-w-2xl space-y-4">
      <div className="flex items-center justify-between">
        <span className="text-[15px] text-muted-foreground">{i + 1} of {n}</span>
        <div className="flex gap-2">
          <Button size="icon-sm" variant="outline" disabled={i === 0} onClick={() => setAt(i - 1)} aria-label="Back"><ChevronLeft /></Button>
          <Button size="icon-sm" variant="outline" disabled={i === n - 1} onClick={() => setAt(i + 1)} aria-label="Next"><ChevronRight /></Button>
        </div>
      </div>
      <div key={waiting[i].id} className="animate-in fade-in slide-in-from-right-2 duration-300" role="group" aria-roledescription="slide" aria-label={`Item ${i + 1} of ${n}`}>
        <ItemCard item={waiting[i]} />
      </div>
    </section>
  );
}

function ItemCard({ item }: { item: LibrarianItem }) {
  const kind = KIND[item.kind];
  return (
    <article className="space-y-6 rounded-2xl border bg-card p-8" data-testid={`librarian-${item.id}`}>
      <div className="space-y-3">
        <StatusChip tone={kind.tone}>{item.status === "proposed" ? "Waiting for approval" : kind.label}</StatusChip>
        <h2 className="text-xl font-semibold leading-snug">{item.title}</h2>
        <p className="text-[15px] leading-relaxed text-muted-foreground">{item.detail}</p>
      </div>
      {item.kind === "conflict" && item.factIds[0] && (
        <Link href={`/l2/vault?tab=facts&fact=${item.factIds[0]}`} className="block text-[15px] text-primary hover:underline">See the current fact</Link>
      )}
      {item.proposal && <Proposal proposal={item.proposal} />}
      <Actions item={item} />
    </article>
  );
}

function Proposal({ proposal }: { proposal: NonNullable<LibrarianItem["proposal"]> }) {
  const lookup = useLookup();
  return (
    <p className="rounded-xl bg-surface p-4 text-[15px]">
      {proposal.winningSource} wins from {date(proposal.newValidFrom, lookup.tz)}.
      {proposal.dependents.length > 0 && <span className="text-muted-foreground"> {proposal.dependents.length} relied on the old fact.</span>}
    </p>
  );
}

/** Finebase HQ settles items for real; the demo tenants keep their mock librarian, which drafts a change request. */
function Actions({ item }: { item: LibrarianItem }) {
  const real = realTenants.has(useTenantId());
  const router = useRouter();
  const { user } = useCurrentUser();
  const propose = useOp<{ itemId: string }>("librarianPropose", { success: "Proposal drafted as one change request" });
  return (
    <div className="flex flex-wrap items-center gap-2">
      {real && <LibrarianActions item={item} />}
      {!real && item.status === "open" && (
        <Button size="sm" onClick={() => propose.mutate({ itemId: item.id }, { onSuccess: (cr) => router.push(`/l2/versioning/${(cr as { id: string }).id}`) })} disabled={propose.isPending || !user || user.tier === "L3"} data-testid={`propose-${item.id}`}>
          {item.kind === "conflict" ? "Propose fix" : "Draft fix"}
        </Button>
      )}
      {item.changeRequestId && (
        <Button size="sm" variant="outline" asChild>
          <Link href={`/l2/versioning/${item.changeRequestId}`}>Change request</Link>
        </Button>
      )}
    </div>
  );
}

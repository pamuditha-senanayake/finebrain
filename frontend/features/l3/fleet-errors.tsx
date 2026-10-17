"use client";

import { ChevronRight } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import type { Run } from "@/contracts";
import { useLookup } from "@/components/brain/names";
import { useRuns } from "@/lib/api/hooks";
import { relTime } from "@/lib/format";
import { cn } from "@/lib/utils";

const SHOWN = 8;

/** Where a failed run can be looked at: its conversation when it had one, otherwise its trace. */
const hrefOf = (r: Run) => (r.conversationId ? `/l3/conversations/${r.conversationId}` : `/l3/runs/${r.id}`);

/** Failed and blocked runs, grouped by what went wrong. Pick a group to see its runs and jump into one. */
export function FleetErrors() {
  const failed = useRuns({ status: "failed", limit: 400 });
  const blocked = useRuns({ status: "blocked", limit: 200 });
  const lookup = useLookup();
  const [open, setOpen] = useState<string | null>(null);

  const groups = useMemo(() => {
    const by = new Map<string, Run[]>();
    for (const r of [...(failed.data ?? []), ...(blocked.data ?? [])]) {
      const key = r.failureClass ?? "unclassified";
      by.set(key, [...(by.get(key) ?? []), r]);
    }
    return [...by.entries()].map(([name, runs]) => ({ name, runs: runs.sort((a, b) => (a.startedAt < b.startedAt ? 1 : -1)) })).sort((a, b) => b.runs.length - a.runs.length || a.name.localeCompare(b.name));
  }, [failed.data, blocked.data]);

  if (groups.length === 0) return null;
  const current = groups.find((g) => g.name === open) ?? null;
  return (
    <section aria-label="Errors by type" className="mb-8">
      <h2 className="mb-3 text-[15px] font-semibold">Errors</h2>
      <div className="flex flex-wrap gap-2" role="tablist" aria-label="Error types">
        {groups.map((g) => (
          <button
            key={g.name}
            type="button"
            role="tab"
            aria-selected={g.name === open}
            onClick={() => setOpen(g.name === open ? null : g.name)}
            data-testid={`error-group-${g.name}`}
            className={cn("flex items-center gap-2 rounded-full border bg-card px-4 py-2 text-[14px] capitalize transition-colors hover:border-risk/50", g.name === open && "border-risk/60 bg-risk/10")}
          >
            {g.name}
            <span className="tabular text-risk">{g.runs.length}</span>
          </button>
        ))}
      </div>
      {current && (
        <ul className="mt-4 divide-y overflow-hidden rounded-xl border bg-card" aria-label={`${current.name} runs`}>
          {current.runs.slice(0, SHOWN).map((r) => (
            <li key={r.id}>
              <Link href={hrefOf(r)} className="flex items-center gap-3 px-4 py-3 transition-colors hover:bg-sidebar-accent/60">
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[14.5px] font-medium">{r.subject}</span>
                  <span className="mt-0.5 block truncate text-xs text-muted-foreground">
                    {lookup.name(r.agentId)} · {relTime(r.startedAt)}
                  </span>
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">{r.conversationId ? "Open chat" : "Open run"}</span>
                <ChevronRight className="size-4 shrink-0 text-muted-foreground" aria-hidden />
              </Link>
            </li>
          ))}
          {current.runs.length > SHOWN && (
            <li className="px-4 py-2.5 text-xs text-muted-foreground">
              {current.runs.length - SHOWN} more in <Link href="/l3/runs" className="text-primary hover:underline">running history</Link>
            </li>
          )}
        </ul>
      )}
    </section>
  );
}

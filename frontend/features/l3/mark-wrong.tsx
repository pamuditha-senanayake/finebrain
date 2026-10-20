"use client";

import { Sparkles, ThumbsDown } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import type { Run } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { useLookup } from "@/components/brain/names";
import { Section } from "@/components/brain/primitives";
import { useOp, useTenantId } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { dateTime } from "@/lib/format";

/** Accountability: anyone who sees a wrong outcome records it here. The note stays on the run and the agent. */
export function MarkWrong({ run }: { run: Run }) {
  const lookup = useLookup();
  const { user } = useCurrentUser();
  const [open, setOpen] = useState(false);
  const [note, setNote] = useState("");
  const mark = useOp<{ runId: string; note: string }>("markRunWrong", { success: "Recorded. The agent's DRI was told." });

  if (run.markedWrong) {
    return (
      <Section title="Marked wrong" className="border-risk/40">
        <p className="text-[14.5px]">{run.markedWrong.note}</p>
        <p className="mt-2 text-xs text-muted-foreground">
          {lookup.name(run.markedWrong.by)} · {dateTime(run.markedWrong.at, lookup.tz)}
        </p>
        <DraftFix run={run} />
      </Section>
    );
  }
  if (!user || run.status === "running") return null;
  if (!open) {
    return (
      <Button variant="outline" size="sm" className="w-full" onClick={() => setOpen(true)} data-testid="mark-wrong">
        <ThumbsDown /> Mark as wrong
      </Button>
    );
  }
  return (
    <Section title="What went wrong?">
      <Textarea value={note} onChange={(e) => setNote(e.target.value)} placeholder="For example: refunded outside the 30 day window" aria-label="What went wrong" rows={3} autoFocus />
      <div className="mt-3 flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={() => setOpen(false)}>
          Cancel
        </Button>
        <Button size="sm" disabled={!note.trim() || mark.isPending} onClick={() => mark.mutate({ runId: run.id, note }, { onSuccess: () => setOpen(false) })}>
          Record
        </Button>
      </div>
    </Section>
  );
}

/** Skillify (Finebase HQ): Claude drafts one skill or policy change that would have prevented this. The workflow's DRI approves it. */
function DraftFix({ run }: { run: Run }) {
  const { user } = useCurrentUser();
  const real = useTenantId() === "finebase-hq";
  const draft = useOp<{ runId: string }>("draftFix", { success: "Fix drafted. It waits for the owner's approval." });
  if (run.fixApprovalId) {
    return (
      <Link href={`/l1/approvals/${run.fixApprovalId}`} className="mt-4 inline-block text-[15px] text-primary hover:underline">
        Fix drafted · open it
      </Link>
    );
  }
  if (!real || !user || user.tier === "L3") return null;
  return (
    <Button variant="outline" size="sm" className="mt-4" onClick={() => draft.mutate({ runId: run.id })} disabled={draft.isPending} data-testid="draft-fix">
      <Sparkles /> {draft.isPending ? "Drafting…" : "Draft a fix"}
    </Button>
  );
}

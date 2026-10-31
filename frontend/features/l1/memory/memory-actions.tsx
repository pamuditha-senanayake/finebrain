"use client";

// memory-actions.tsx: the two things a person does on the Living memory: say a surprise is a normal way of working (it
// becomes a pattern), and send a skill drafted from traces to an L1 user, choosing the workflow it joins first.
// Stewards and leaders act; anyone else sees why they cannot. On sample data the buttons say they work on a live workspace.
// Used by: trace-timeline.tsx, features/l2/skills-from-traces.tsx. Uses: lib/api/hooks (useOp, useStudioWorkflows), lib/auth.
import { useState } from "react";
import type { ExtractedSkill } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { useOp, useStudioWorkflows } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";
import { cn } from "@/lib/utils";

// Config
const MAY_ACT = new Set(["L1", "L2"]);

/** Why a person cannot act here, or null when they can. */
function blocker(tier: string | undefined, sample: boolean): string | null {
  if (sample) return "Sample data: this works on a live workspace.";
  if (!tier || !MAY_ACT.has(tier)) return "Only a steward or a leader can do this.";
  return null;
}

export function ConfirmSurprise({ traceId, sample }: { traceId: string; sample: boolean }) {
  const { user } = useCurrentUser();
  const confirm = useOp<{ traceId: string }>("memoryConfirm", { success: "Kept as a normal way of working" });
  const why = blocker(user?.tier, sample);
  return (
    <div className="space-y-2 rounded-2xl border p-5">
      <p className="text-[15px]">This work did not match a known pattern.</p>
      <p className="text-[13px] text-muted-foreground">If it is how the company works now, keep it as a pattern. Similar work will then count as normal.</p>
      <Button onClick={() => confirm.mutate({ traceId })} disabled={!!why || confirm.isPending || confirm.isSuccess}>
        {confirm.isSuccess ? "Kept as normal" : "Keep as a normal way of working"}
      </Button>
      {why && <p className="text-[13px] text-muted-foreground">{why}</p>}
    </div>
  );
}

export function SendDraft({ skill, sample }: { skill: ExtractedSkill; sample: boolean }) {
  const { user } = useCurrentUser();
  const [open, setOpen] = useState(false);
  const why = skill.state !== "draft" ? "Already sent for review." : blocker(user?.tier, sample);
  return (
    <div className="space-y-2">
      <Button onClick={() => setOpen(true)} disabled={!!why}>Send to an L1 user for review</Button>
      {why && <p className="text-[13px] text-muted-foreground">{why}</p>}
      {open && <SendDialog skill={skill} onClose={() => setOpen(false)} />}
    </div>
  );
}

// Step one, choose where the skill belongs; step two, send. Nothing goes live until an L1 user approves it.
function SendDialog({ skill, onClose }: { skill: ExtractedSkill; onClose: () => void }) {
  const workflows = useStudioWorkflows();
  const [chosen, setChosen] = useState<string | null>(null);
  const send = useOp<{ draftId: string; workflowId: string }>("memorySendDraft", { success: "Sent to an L1 user for review" });
  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Send “{skill.name}” for review</DialogTitle>
          <DialogDescription>Choose the workflow this skill joins. An L1 user approves it before it goes live.</DialogDescription>
        </DialogHeader>
        <ul className="max-h-72 space-y-1.5 overflow-y-auto" role="radiogroup" aria-label="Workflow">
          {(workflows.data ?? []).map((flow) => (
            <li key={flow.id}>
              <button type="button" role="radio" aria-checked={chosen === flow.id} onClick={() => setChosen(flow.id)}
                className={cn("w-full rounded-xl border px-4 py-2.5 text-left text-[15px] hover:bg-muted focus-visible:outline-2 focus-visible:outline-ring", chosen === flow.id && "border-foreground/40 bg-muted")}>
                {flow.name}
              </button>
            </li>
          ))}
          {workflows.isLoading && <li className="text-[13px] text-muted-foreground">Loading workflows…</li>}
          {workflows.data?.length === 0 && <li className="text-[13px] text-muted-foreground">No workflows yet. Create one in Workflow Studio first.</li>}
        </ul>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Back</Button>
          <Button disabled={!chosen || send.isPending} onClick={() => chosen && send.mutate({ draftId: skill.id, workflowId: chosen }, { onSuccess: onClose })}>
            {send.isPending ? "Sending…" : "Next: send for review"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

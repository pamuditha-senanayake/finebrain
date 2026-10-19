"use client";

// Remove a document (step 10): choose Retire or Erase, look at what depends on it, then confirm. Erase asks twice.
// The server sets the level and counts the confirmations. Used by library.tsx.
import { useState } from "react";
import type { ForgetReceipt, ForgetReview } from "@/contracts";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { StatusChip } from "@/components/brain/primitives";
import { useForget, type ForgetMode } from "@/lib/api/forget";

const CHOICES: { mode: ForgetMode; label: string; hint: string }[] = [
  { mode: "retire", label: "Retire", hint: "No longer true. Stays in history." },
  { mode: "erase", label: "Erase", hint: "Gone for good." },
];

/** What a removal cleared, one line per layer. */
export function ReceiptList({ receipt }: { receipt: ForgetReceipt }) {
  return (
    <div className="space-y-3">
      <ul className="divide-y rounded-xl border bg-card text-[14.5px]" aria-label="Receipt">
        {receipt.layers.map((l) => (
          <li key={l.layer} className="flex items-center justify-between gap-4 px-4 py-2.5">
            <span className="font-medium">{l.layer}</span>
            <span className="text-muted-foreground">{l.result === "cleared" ? l.note : l.result === "kept" ? `Kept: ${l.note}` : "Nothing there"}</span>
          </li>
        ))}
      </ul>
      {!receipt.verified && <p className="text-sm text-risk">Not clean yet: {receipt.failed.join(", ")}. Confirm again to retry.</p>}
    </div>
  );
}

export function ForgetCard({ documentId, retired, onClose }: { documentId: string; retired: boolean; onClose: () => void }) {
  const { start, confirm } = useForget();
  const [mode, setMode] = useState<ForgetMode | null>(null);
  const [review, setReview] = useState<ForgetReview | null>(null);
  const [reason, setReason] = useState("");
  const busy = start.isPending || confirm.isPending;
  const failed = start.error ?? confirm.error;
  const finished = review !== null && review.status !== "review" && review.receipt?.verified;
  const choices = retired ? CHOICES.filter((c) => c.mode === "erase") : CHOICES;

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{finished ? "Done" : review ? (review.mode === "erase" ? "Erase this?" : "Retire this?") : "Remove"}</DialogTitle>
          <DialogDescription>{finished ? "" : review ? review.warning || "Ready." : "Pick one."}</DialogDescription>
        </DialogHeader>

        {!review && (
          <div className="space-y-4">
            <div className="grid gap-3 sm:grid-cols-2">
              {choices.map((c) => (
                <button key={c.mode} type="button" onClick={() => setMode(c.mode)} aria-pressed={mode === c.mode}
                  className={`rounded-xl border p-4 text-left transition-colors hover:bg-sidebar-accent ${mode === c.mode ? "border-primary bg-sidebar-accent" : ""}`}>
                  <span className="block text-[15px] font-medium">{c.label}</span>
                  <span className="mt-1 block text-sm text-muted-foreground">{c.hint}</span>
                </button>
              ))}
            </div>
            <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Why? (optional)" aria-label="Why"
              className="h-11 w-full rounded-xl border bg-card px-4 text-[15px] outline-none placeholder:text-muted-foreground focus-visible:ring-2 focus-visible:ring-ring/50" />
          </div>
        )}

        {review && !finished && (
          <div className="space-y-4">
            <StatusChip tone={review.mode === "erase" ? "risk" : "warn"}>C{review.level}</StatusChip>
            <div>
              <h3 className="mb-2 text-[15px] font-semibold">Used by</h3>
              {review.dependents.length === 0 ? (
                <p className="text-sm text-muted-foreground">Nothing.</p>
              ) : (
                <ul className="space-y-1 text-[14.5px]">{review.dependents.map((d) => <li key={d.id}>{d.label} <span className="text-muted-foreground">· {d.type}</span></li>)}</ul>
              )}
            </div>
            {review.receipt && <ReceiptList receipt={review.receipt} />}
          </div>
        )}

        {finished && review.receipt && <ReceiptList receipt={review.receipt} />}
        {failed && <p role="alert" className="text-sm text-risk">{failed instanceof Error ? failed.message : "Could not remove."}</p>}

        <DialogFooter>
          {finished ? (
            <Button onClick={onClose}>Close</Button>
          ) : (
            <>
              <Button variant="outline" onClick={onClose} disabled={busy}>Cancel</Button>
              {!review ? (
                <Button disabled={!mode || busy} onClick={() => mode && start.mutate({ documentId, mode, reason }, { onSuccess: setReview })}>Review</Button>
              ) : (
                <Button variant={review.mode === "erase" ? "destructive" : "default"} disabled={busy} onClick={() => confirm.mutate(review.requestId, { onSuccess: setReview })}>
                  {review.mode === "erase" ? (review.confirmationsLeft > 1 ? "Erase" : "Erase for good") : "Retire"}
                </Button>
              )}
            </>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

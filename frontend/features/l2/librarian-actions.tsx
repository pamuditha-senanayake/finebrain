"use client";

import { Check, X } from "lucide-react";
import type { LibrarianItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";

/** Accept or Reject one open review item (step 14). A conflict waits for its change request, so it shows nothing here. */
export function LibrarianActions({ item }: { item: LibrarianItem }) {
  const { user } = useCurrentUser();
  const accept = useOp<{ itemId: string }>("librarianAccept", { success: "Added to ground truth" });
  const reject = useOp<{ itemId: string }>("librarianReject", { success: "Rejected" });
  if (item.status !== "open" || item.kind === "conflict" || !user || user.tier === "L3") return null;
  const busy = accept.isPending || reject.isPending;
  return (
    <div className="flex flex-wrap gap-1.5">
      <Button size="xs" onClick={() => accept.mutate({ itemId: item.id })} disabled={busy} data-testid={`accept-${item.id}`}>
        <Check /> Accept
      </Button>
      <Button size="xs" variant="outline" onClick={() => reject.mutate({ itemId: item.id })} disabled={busy} data-testid={`reject-${item.id}`}>
        <X /> Reject
      </Button>
    </div>
  );
}

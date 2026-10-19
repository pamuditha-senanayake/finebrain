"use client";

import { Check, GitPullRequest, X } from "lucide-react";
import { useRouter } from "next/navigation";
import type { LibrarianItem } from "@/contracts";
import { Button } from "@/components/ui/button";
import { useOp } from "@/lib/api/hooks";
import { useCurrentUser } from "@/lib/auth";

/** Accept or Reject one open review item (step 14). A conflict gets one Propose fix: the librarian drafts a change request. */
export function LibrarianActions({ item }: { item: LibrarianItem }) {
  const { user } = useCurrentUser();
  const router = useRouter();
  const accept = useOp<{ itemId: string }>("librarianAccept", { success: "Added to ground truth" });
  const reject = useOp<{ itemId: string }>("librarianReject", { success: "Rejected" });
  const propose = useOp<{ itemId: string }>("librarianPropose", { success: "Proposal drafted" });
  if (item.status !== "open" || !user || user.tier === "L3") return null;
  if (item.kind === "conflict") {
    const opened = (answer: unknown) => {
      const id = (answer as { id: string | null }).id; // null when the current fact is kept: nothing to review
      if (id) router.push(`/l2/versioning/${id}`);
    };
    return (
      <Button size="xs" onClick={() => propose.mutate({ itemId: item.id }, { onSuccess: opened })} disabled={propose.isPending} data-testid={`propose-${item.id}`}>
        <GitPullRequest /> Propose fix
      </Button>
    );
  }
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

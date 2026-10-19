"use client";

// A decision on an approval. The real brain answers {ok} at once and records the vote a moment later, when its bus
// delivers it, so the page waits for the vote to appear before it refreshes. The mock answers with the approval itself.
// Used by: features/l1/approvals.tsx. Uses: client.ts.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { z } from "zod";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiGet, apiPost } from "./client";

// Config
const WAIT_MS = 300;
const TRIES = 20;

export type DecideArgs = { approvalId: string; decision: string; comment: string; delegateTo?: string | null; votesBefore: number };

async function recorded(args: DecideArgs): Promise<C.Approval> {
  // Poll until the vote shows, or the approval closes; give up quietly after about six seconds
  let approval = await apiGet(`approvals/${args.approvalId}`, C.Approval);
  for (let i = 0; i < TRIES && approval.status === "pending" && approval.votes.length <= args.votesBefore; i++) {
    await new Promise((resolve) => setTimeout(resolve, WAIT_MS));
    approval = await apiGet(`approvals/${args.approvalId}`, C.Approval);
  }
  return approval;
}

export function useDecide() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: async ({ votesBefore, ...body }: DecideArgs) => {
      const answer = await apiPost("ops/decide", body, z.unknown());
      const parsed = C.Approval.safeParse(answer);
      return parsed.success ? parsed.data : recorded({ ...body, votesBefore });
    },
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId] }),
    onError: (e) => {
      reportError(e, { op: "decide" });
      toast.error(e instanceof Error ? e.message : "Action failed");
    },
  });
}

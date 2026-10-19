"use client";

// Removing a document (step 10): look first, then confirm. Retire needs one confirmation, erase two. The server counts
// them and sets the level; this file only sends the clicks.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiPost } from "./client";

export type ForgetMode = "retire" | "erase";

export function useForget() {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  const refresh = () => qc.invalidateQueries({ queryKey: ["t", tenantId, "documents"] });
  const start = useMutation({
    mutationFn: (args: { documentId: string; mode: ForgetMode; reason: string }) =>
      apiPost(`documents/${args.documentId}/forget`, { mode: args.mode, reason: args.reason }, C.ForgetReview),
    onError: (e) => reportError(e, { op: "documents.forget" }),
  });
  const confirm = useMutation({
    mutationFn: (requestId: string) => apiPost(`forget/${requestId}/confirm`, {}, C.ForgetReview),
    onSuccess: (review) => review.status !== "review" && refresh(),
    onError: (e) => reportError(e, { op: "documents.forget.confirm" }),
  });
  return { start, confirm };
}

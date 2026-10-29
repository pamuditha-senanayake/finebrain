"use client";

// spending.ts: A4's spending. The month against the budget, and adding, fixing or removing a spend. Backend spending.py.
import { useMutation, useQueryClient } from "@tanstack/react-query";
import * as C from "@/contracts";
import { reportError } from "@/lib/errors";
import { useUi } from "@/lib/store";
import { apiPost } from "./client";
import { useResource } from "./hooks";

export const useSpending = () => useResource("spending", C.SpendingSummary);

export type SpendInput = { vendor: string; amount: string | number; currency: string; category: string; repeats?: string; paid_on?: string };

function useSpendWrite<T>(op: string, call: (input: T) => Promise<C.Spend>) {
  const qc = useQueryClient();
  const tenantId = useUi((s) => s.tenantId);
  return useMutation({
    mutationFn: call,
    onSuccess: () => qc.invalidateQueries({ queryKey: ["t", tenantId, "spending"] }),
    onError: (e) => reportError(e, { op }),
  });
}

export const useAddSpend = () => useSpendWrite("spending.add", (spend: SpendInput) => apiPost("spending", spend, C.Spend));
export const useRemoveSpend = () => useSpendWrite("spending.remove", (id: string) => apiPost(`spending/${id}`, { remove: true }, C.Spend));

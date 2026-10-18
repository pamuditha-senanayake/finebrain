"use client";

// Ask the Brain keeps one conversation per tenant and person, so the brain remembers what was said earlier,
// even after a reload. The panel and the voice page share it. Mock tenants send no id back, so nothing is kept.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { z } from "zod";
import * as C from "@/contracts";
import { currentPersonaId, useUi } from "@/lib/store";
import { apiGet, apiPost } from "./client";

type Conversations = { byKey: Record<string, string>; set: (key: string, id: string | null) => void };

const useConversations = create<Conversations>()(
  persist(
    (set) => ({
      byKey: {},
      set: (key, id) => set((s) => {
        const { [key]: _old, ...rest } = s.byKey;
        return { byKey: id ? { ...rest, [key]: id } : rest };
      }),
    }),
    { name: "cb.ask.v1", storage: createJSONStorage(() => localStorage) },
  ),
);

function useConversationKey() {
  const tenantId = useUi((s) => s.tenantId);
  const persona = useUi((s) => s.personaByTenant[s.tenantId]);
  return `${tenantId}:${persona ?? currentPersonaId()}`;
}

export type AskInput = { question: string; page?: { path: string; scope: "page" | "system" } };

/** Asks inside the current conversation and keeps the id the brain sends back. */
export function useAsk() {
  const key = useConversationKey();
  return useMutation({
    mutationFn: async (input: AskInput) => {
      const conversationId = useConversations.getState().byKey[key];
      const answer = await apiPost("ask", { ...input, conversationId }, C.AskAnswer);
      if (answer.conversationId) useConversations.getState().set(key, answer.conversationId);
      return answer;
    },
  });
}

/** The conversation's earlier turns, read once when the page opens, and a way to start over. */
export function useConversation() {
  const key = useConversationKey();
  const id = useConversations((s) => s.byKey[key]) ?? null;
  // Only the turns from before this page opened; newer ones are already on screen.
  const [openedWith] = useState(id);
  const saved = useQuery({
    queryKey: ["ask-turns", key, openedWith],
    queryFn: ({ signal }) => apiGet(`ask/turns?conversation=${encodeURIComponent(openedWith ?? "")}`, z.array(C.AskTurn), signal),
    enabled: !!openedWith,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });
  return { saved: id && id === openedWith ? saved.data ?? [] : [], startOver: () => useConversations.getState().set(key, null) };
}

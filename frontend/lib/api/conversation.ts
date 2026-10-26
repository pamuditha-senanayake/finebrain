"use client";

// Ask the Brain keeps one conversation per tenant and person, so the brain remembers what was said earlier,
// even after a reload. The panel and the voice page share it. Mock tenants send no id back, so nothing is kept.
// Every chat stays on the backend; the history lists them, and after a long quiet the next question starts a new one.
import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { z } from "zod";
import * as C from "@/contracts";
import { realTenants } from "@/lib/flags";
import { currentPersonaId, useUi } from "@/lib/store";
import { apiGet, apiPost } from "./client";

// Config
const QUIET_STARTS_NEW_MS = 4 * 60 * 60 * 1000; // after 4 hours without a question, the next one opens a fresh chat

type Conversations = { byKey: Record<string, string>; usedAt: Record<string, number>; set: (key: string, id: string | null) => void };

const useConversations = create<Conversations>()(
  persist(
    (set) => ({
      byKey: {},
      usedAt: {},
      set: (key, id) => set((s) => {
        const byKey = { ...s.byKey };
        if (id) byKey[key] = id;
        else delete byKey[key];
        return { byKey, usedAt: { ...s.usedAt, [key]: Date.now() } };
      }),
    }),
    { name: "cb.ask.v1", storage: createJSONStorage(() => localStorage) },
  ),
);

/** The chat to continue, or undefined when it has been quiet too long. A chat saved before usedAt existed stays live. */
function liveId(s: Pick<Conversations, "byKey" | "usedAt">, key: string): string | undefined {
  const usedAt = s.usedAt?.[key];
  return usedAt && Date.now() - usedAt > QUIET_STARTS_NEW_MS ? undefined : s.byKey[key];
}

function useConversationKey() {
  const tenantId = useUi((s) => s.tenantId);
  const persona = useUi((s) => s.personaByTenant[s.tenantId]);
  return `${tenantId}:${persona ?? currentPersonaId()}`;
}

export type AskInput = { question: string; page?: { path: string; scope: "page" | "system"; title?: string; snapshot?: string }; signal?: AbortSignal };

/** Asks inside the current conversation and keeps the id the brain sends back. */
export function useAsk() {
  const key = useConversationKey();
  return useMutation({
    mutationFn: async ({ signal, ...input }: AskInput) => {
      const conversationId = liveId(useConversations.getState(), key);
      const answer = await apiPost("ask", { ...input, conversationId }, C.AskAnswer, signal);
      if (answer.conversationId) useConversations.getState().set(key, answer.conversationId);
      return answer;
    },
  });
}

/** The conversation's earlier turns, read when the page opens or an old chat is picked, and a way to start over. */
export function useConversation() {
  const key = useConversationKey();
  const id = useConversations((s) => liveId(s, key)) ?? null;
  // Only the turns from before this page opened (or the picked chat's); newer ones are already on screen.
  const [openedWith, setOpenedWith] = useState(id);
  const saved = useQuery({
    queryKey: ["ask-turns", key, openedWith],
    queryFn: ({ signal }) => apiGet(`ask/turns?conversation=${encodeURIComponent(openedWith ?? "")}`, z.array(C.AskTurn), signal),
    enabled: !!openedWith,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
  });

  // Step 1: continue a chat from the history
  function open(chatId: string) {
    useConversations.getState().set(key, chatId);
    setOpenedWith(chatId);
  }

  return {
    id,
    saved: id && id === openedWith ? saved.data ?? [] : [],
    open,
    startOver: () => useConversations.getState().set(key, null),
  };
}

/** This person's past chats, newest first. Only real tenants keep chats, so demo tenants show none. */
export function useConversationList(enabled: boolean) {
  const key = useConversationKey();
  const tenantId = useUi((s) => s.tenantId);
  return useQuery({
    queryKey: ["ask-conversations", key],
    queryFn: ({ signal }) => apiGet("ask/conversations", z.array(C.AskConversation), signal),
    enabled: enabled && realTenants.has(tenantId),
    staleTime: 0,
  });
}

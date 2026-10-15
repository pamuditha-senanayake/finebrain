"use client";

import { create } from "zustand";
import type { ApplyResult, ChatReply, StudioKind } from "@/contracts";
import type { StepKey } from "./steps";

export type Focus = { kind: StudioKind; id: string } | null;

export type ChatMessage =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; reply: ChatReply; applied?: ApplyResult }
  | { id: string; role: "notice"; text: string; tone: "ok" | "info" | "risk"; href?: string };

type StudioState = {
  threads: Record<string, ChatMessage[]>;
  focus: Record<string, Focus>;
  /** Which step the parts pane shows, per workflow. Unset means the pane picks one. */
  step: Record<string, StepKey>;
  draft: string;
  push: (workflowId: string, m: ChatMessage) => void;
  patch: (workflowId: string, id: string, fn: (m: ChatMessage) => ChatMessage) => void;
  clear: (workflowId: string) => void;
  setFocus: (workflowId: string, f: Focus) => void;
  setStep: (workflowId: string, s: StepKey) => void;
  setDraft: (v: string) => void;
};

let seq = 0;
export const msgId = () => `m${Date.now().toString(36)}${(seq++).toString(36)}`;

/** One conversation per workflow, kept for the browser session so switching workflows does not lose a thread. */
export const useStudio = create<StudioState>()((set) => ({
  threads: {},
  focus: {},
  step: {},
  draft: "",
  push: (w, m) => set((s) => ({ threads: { ...s.threads, [w]: [...(s.threads[w] ?? []), m] } })),
  patch: (w, id, fn) => set((s) => ({ threads: { ...s.threads, [w]: (s.threads[w] ?? []).map((m) => (m.id === id ? fn(m) : m)) } })),
  clear: (w) => set((s) => ({ threads: { ...s.threads, [w]: [] } })),
  setFocus: (w, f) => set((s) => ({ focus: { ...s.focus, [w]: f } })),
  setStep: (w, step) => set((s) => ({ step: { ...s.step, [w]: step } })),
  setDraft: (draft) => set({ draft }),
}));

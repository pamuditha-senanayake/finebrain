"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import type { Env } from "@/contracts";

export const DEFAULT_PERSONA: Record<string, string> = { "demo-fbl": "h-founder", scale: "sh-0", "finebase-hq": "h-pamuditha" };

type UiState = {
  tenantId: string;
  personaByTenant: Record<string, string>;
  clusterId: string;
  env: { kind: Env; branch: string };
  askOpen: boolean;
  paletteOpen: boolean;
  notificationsOpen: boolean;
  sidebarCollapsed: boolean;
  setTenant: (id: string) => void;
  setPersona: (id: string) => void;
  setCluster: (id: string) => void;
  setEnv: (kind: Env, branch?: string) => void;
  setAskOpen: (open: boolean) => void;
  setPaletteOpen: (open: boolean) => void;
  setNotificationsOpen: (open: boolean) => void;
  toggleSidebar: () => void;
};

export const useUi = create<UiState>()(
  persist(
    (set) => ({
      tenantId: "demo-fbl",
      personaByTenant: { ...DEFAULT_PERSONA },
      clusterId: "all",
      env: { kind: "production", branch: "main" },
      askOpen: false,
      paletteOpen: false,
      notificationsOpen: false,
      sidebarCollapsed: false,
      setTenant: (tenantId) => set({ tenantId, clusterId: "all" }),
      setPersona: (id) => set((s) => ({ personaByTenant: { ...s.personaByTenant, [s.tenantId]: id } })),
      setCluster: (clusterId) => set({ clusterId }),
      setEnv: (kind, branch) => set({ env: { kind, branch: branch ?? (kind === "production" ? "main" : kind === "staging" ? "staging" : "sandbox") } }),
      setAskOpen: (askOpen) => set({ askOpen }),
      setPaletteOpen: (paletteOpen) => set({ paletteOpen }),
      setNotificationsOpen: (notificationsOpen) => set({ notificationsOpen }),
      toggleSidebar: () => set((s) => ({ sidebarCollapsed: !s.sidebarCollapsed })),
    }),
    {
      name: "cb.ui.v1",
      version: 1,
      // Version 1 renamed the Finebase Labs demo tenant from "finebase" to "demo-fbl".
      migrate: (stored) => {
        const state = (stored ?? {}) as { tenantId?: string; personaByTenant?: Record<string, string> };
        const { finebase, ...others } = state.personaByTenant ?? {};
        return { ...state, tenantId: state.tenantId === "finebase" ? "demo-fbl" : state.tenantId, personaByTenant: { ...others, ...(finebase ? { "demo-fbl": finebase } : {}) } };
      },
      storage: createJSONStorage(() => localStorage),
      partialize: (s) => ({ tenantId: s.tenantId, personaByTenant: s.personaByTenant, clusterId: s.clusterId, env: s.env, sidebarCollapsed: s.sidebarCollapsed }),
    },
  ),
);

export function currentPersonaId() {
  const s = useUi.getState();
  return s.personaByTenant[s.tenantId] ?? DEFAULT_PERSONA[s.tenantId] ?? "";
}

export function usePersonaId() {
  return useUi((s) => s.personaByTenant[s.tenantId] ?? DEFAULT_PERSONA[s.tenantId] ?? "");
}

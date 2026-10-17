"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";
import { NAV, type NavItem } from "@/lib/nav";

/**
 * Which pages people actually open, so unused ones can be removed first.
 * Kept in this browser for now; the same events can go to the backend later.
 */
type Usage = { opens: Record<string, { count: number; lastAt: string }>; record: (href: string) => void; reset: () => void };

export const useUsage = create<Usage>()(
  persist(
    (set) => ({
      opens: {},
      record: (href) => set((s) => ({ opens: { ...s.opens, [href]: { count: (s.opens[href]?.count ?? 0) + 1, lastAt: new Date().toISOString() } } })),
      reset: () => set({ opens: {} }),
    }),
    { name: "cb.usage.v1", storage: createJSONStorage(() => localStorage), partialize: (s) => ({ opens: s.opens }) },
  ),
);

const ITEMS: NavItem[] = NAV.flatMap((a) => a.items);
const under = (path: string, href: string) => path === href || path.startsWith(`${href}/`);

/** The nav item a path belongs to, so a detail page counts toward its page. */
export function navItemFor(path: string): NavItem | null {
  return ITEMS.find((i) => (i.exact ? path === i.href : under(path, i.href)) || (i.also ?? []).some((h) => under(path, h))) ?? null;
}

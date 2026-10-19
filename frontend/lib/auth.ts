"use client";

import type { Human, Tier } from "@/contracts";
import { useHumans } from "@/lib/api/hooks";
import { usePersonaId } from "@/lib/store";

/**
 * Auth adapter. The mock provider impersonates a seeded persona (role switcher).
 * An SSO provider replaces `useCurrentUser` with the signed in identity and sends a bearer token.
 */
export type AuthProviderKind = "mock" | "sso";
export const authProvider: AuthProviderKind = process.env.NEXT_PUBLIC_AUTH_PROVIDER === "sso" ? "sso" : "mock";

export function useCurrentUser(): { user: Human | null; isLoading: boolean; error: unknown; retry: () => void } {
  const personaId = usePersonaId();
  const humans = useHumans();
  return { user: humans.data?.find((h) => h.id === personaId) ?? null, isLoading: humans.isLoading, error: humans.error, retry: () => void humans.refetch() };
}

export type Area = Tier | "research";

/** Role guards, following the ChainSight tiers: higher tiers can look down, never up. */
export function canView(user: Human | null, area: Area): boolean {
  if (!user) return false;
  if (area === "research") return user.roles.includes("research") || user.roles.includes("founder");
  const rank: Record<Tier, number> = { L1: 1, L2: 2, L3: 3 };
  return rank[user.tier] <= rank[area];
}

export function homeFor(user: Human | null): string {
  if (!user) return "/l1";
  if (user.roles.includes("research")) return "/research";
  return user.tier === "L1" ? "/l1" : user.tier === "L2" ? "/l2/graph" : "/l3";
}

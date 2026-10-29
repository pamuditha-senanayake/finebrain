// Typed feature flags. Read at build time from NEXT_PUBLIC_* so disabled features are compiled out.
export const flags = {
  /** Research Console routes, navigation and bundles. Off removes them completely (see next.config.ts). */
  research: process.env.NEXT_PUBLIC_FLAG_RESEARCH === "enabled",
  /** Persona impersonation for development and demos. Never enable in production builds. */
  roleSwitcher: process.env.NEXT_PUBLIC_ROLE_SWITCHER !== "disabled",
  /** Browser mocks (MSW). Disable and set NEXT_PUBLIC_API_BASE_URL to use the real backend. */
  mocks: process.env.NEXT_PUBLIC_API_MOCKING !== "disabled",
  /** Mock live event stream. Tests turn it off for stable screens. */
  mockStream: process.env.NEXT_PUBLIC_MOCK_STREAM !== "off",
} as const;

export type FlagName = keyof typeof flags;

export const config = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "",
  liveSource: (process.env.NEXT_PUBLIC_LIVE_SOURCE ?? "mock") as "mock" | "sse",
} as const;

/** Tenants served by the real backend. Their requests skip the mocks and their live updates come over SSE.
 *  The demo tenants (demo-fbl, Scale Demo) stay on mock data. */
export const realTenants = new Set(["finebase-hq", "finebase-hq-2"]);

/** Which backend serves each real tenant. One backend process serves one tenant; HQ-2 runs beside HQ on its own port. */
const tenantBase: Record<string, string> = { "finebase-hq-2": process.env.NEXT_PUBLIC_API_BASE_URL_HQ2 ?? "http://localhost:8001" };
export const apiBaseFor = (tenantId: string): string => tenantBase[tenantId] ?? config.apiBaseUrl;

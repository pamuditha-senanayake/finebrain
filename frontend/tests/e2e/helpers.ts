import { expect, type Page } from "@playwright/test";

export const ROUTES: { path: string; persona: string; label: string }[] = [
  { path: "/", persona: "h-founder", label: "home" },
  { path: "/l1", persona: "h-founder", label: "l1-overview" },
  { path: "/l1/digest", persona: "h-founder", label: "l1-digest" },
  { path: "/l1/ask", persona: "h-founder", label: "l1-ask" },
  { path: "/l1/digest?tab=approvals", persona: "h-founder", label: "l1-approvals" },
  { path: "/l1/approvals/apr-sentinel-grant", persona: "h-founder", label: "l1-approval-detail" },
  { path: "/l1/entity", persona: "h-fd", label: "l1-entity" },
  { path: "/l1/digest?tab=evidence", persona: "h-fd", label: "l1-evidence" },
  { path: "/l1/analytics", persona: "h-founder", label: "l1-analytics" },
  { path: "/l1/audit", persona: "h-founder", label: "l1-audit" },
  { path: "/l2/graph", persona: "h-sec", label: "l2-graph" },
  { path: "/l2/versioning", persona: "h-aiops", label: "l2-versioning" },
  { path: "/l2/versioning/cr-sentinel-grant", persona: "h-aiops", label: "l2-change-request" },
  { path: "/l2/library", persona: "h-ks", label: "l2-library" },
  { path: "/l2/vault", persona: "h-ks", label: "l2-vault" },
  { path: "/l2/policies", persona: "h-ks", label: "l2-policies" },
  { path: "/l2/policies/refund-window", persona: "h-ks", label: "l2-policy-detail" },
  { path: "/l2/skills", persona: "h-aiops", label: "l2-skills" },
  { path: "/l2/skills/refund-standard", persona: "h-aiops", label: "l2-skill-editor" },
  { path: "/l2/resolver", persona: "h-aiops", label: "l2-resolver" },
  { path: "/l2/templates", persona: "h-aiops", label: "l2-templates" },
  { path: "/l2/sensors", persona: "h-aiops", label: "l2-sensors" },
  { path: "/l2/loops", persona: "h-aiops", label: "l2-loops" },
  { path: "/l2/loops/loop-website", persona: "h-aiops", label: "l2-loop-detail" },
  { path: "/l2/readiness", persona: "h-ks", label: "l2-readiness" },
  { path: "/l2/security", persona: "h-sec", label: "l2-security" },
  { path: "/l3", persona: "h-op", label: "l3-fleet" },
  { path: "/l3/agents/a-refund", persona: "h-op", label: "l3-agent" },
  { path: "/l3/runs", persona: "h-op", label: "l3-runs" },
  { path: "/l3/runs/run-1042", persona: "h-op", label: "l3-run" },
  { path: "/l3/conversations", persona: "h-op", label: "l3-conversations" },
  { path: "/l3/conversations/conv-1042", persona: "h-op", label: "l3-conversation" },
  { path: "/l3/escalations", persona: "h-op", label: "l3-escalations" },
  { path: "/l3/templates", persona: "h-op", label: "l3-template-board" },
  { path: "/studio?wf=wf-refunds", persona: "h-founder", label: "studio-chat" },
  { path: "/studio?wf=wf-billing&view=diagram", persona: "h-aiops", label: "studio-diagram" },
  { path: "/studio?wf=wf-care&view=parts", persona: "h-op", label: "studio-parts-l3" },
  { path: "/research/skills", persona: "h-research", label: "research" },
];

/** Sets tenant and persona in the persisted UI store before the app boots. */
export async function setPersona(page: Page, persona: string, tenant = "demo-fbl") {
  await page.addInitScript(
    ([p, t]) => {
      // Apply once per tab, so later persona switches in the test survive navigation.
      if (sessionStorage.getItem("cb.e2e.persona")) return;
      sessionStorage.setItem("cb.e2e.persona", p);
      const key = "cb.ui.v1";
      const current = JSON.parse(localStorage.getItem(key) ?? "null");
      const state = current?.state ?? { clusterId: "all", env: { kind: "production", branch: "main" } };
      state.tenantId = t;
      state.personaByTenant = { ...(state.personaByTenant ?? {}), [t]: p };
      localStorage.setItem(key, JSON.stringify({ state, version: 1 }));
    },
    [persona, tenant] as const,
  );
}

/** Switches persona through the role switcher on the home page, the way a person would, then returns to the same page. */
export async function switchPersona(page: Page, persona: string) {
  const back = page.url();
  await page.goto("/");
  await page.getByTestId("role-switcher").click();
  await page.getByTestId(`persona-${persona}`).click();
  await page.goto(back);
}

export async function resetDemo(page: Page) {
  await page.goto("/");
  await page.evaluate(() => {
    localStorage.removeItem("cb.mock.journal.v1");
  });
}

export function collectConsoleErrors(page: Page) {
  const errors: string[] = [];
  page.on("console", (m) => {
    if (m.type() === "error") errors.push(m.text());
  });
  page.on("pageerror", (e) => errors.push(e.message));
  return errors;
}

export async function waitForApp(page: Page) {
  await expect(page.locator("main h1").first()).toBeVisible();
}

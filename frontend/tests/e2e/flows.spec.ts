// The seven flows from the definition of done, run end to end through the UI on mock data.
import { expect, test, type Locator, type Page } from "@playwright/test";
import { setPersona, switchPersona } from "./helpers";

async function selectOption(page: Page, trigger: string, option: string | RegExp) {
  await page.getByRole("combobox", { name: trigger }).click();
  await page.getByRole("option", { name: option }).click();
}

/** Pages a one-card-at-a-time list (components/brain/card-pager.tsx) to the card containing text, and returns that card. */
async function showCard(pager: Locator, text: string): Promise<Locator> {
  const back = pager.getByRole("button", { name: "Back" });
  const next = pager.getByRole("button", { name: "Next" });
  const card = pager.getByRole("group").filter({ hasText: text });
  await expect(pager.getByRole("group")).toBeVisible();
  while (await back.isEnabled()) await back.click();
  while (!(await card.count()) && (await next.isEnabled())) await next.click();
  await expect(card).toBeVisible();
  return card;
}

test("1. refund outside policy: escalate, take over, Skillify, sandbox replay, C3 approval, merge, audit", async ({ page }) => {
  await setPersona(page, "h-op");
  await page.goto("/l3/escalations");
  await page.getByRole("row", { name: /CUS-1042/ }).click();
  await expect(page).toHaveURL(/\/l3\/conversations\/conv-1042/);
  await expect(page.getByText(/Escalated to customer care/)).toBeVisible();

  await page.getByTestId("takeover").click();
  await expect(page.getByText(/took over from the Refund Agent/)).toBeVisible();
  await page.getByRole("textbox", { name: "Reply" }).fill("I've asked our head of customer success to review a full refund for you today.");
  await page.getByRole("button", { name: "Send reply" }).click();
  await expect(page.getByText(/review a full refund for you today/)).toBeVisible();
  await page.getByTestId("skillify").click();
  await expect(page.getByText(/Skillified by Amaya Gunawardena/)).toBeVisible();

  // An L2 steward tests the draft in a sandbox and replays recent runs.
  await switchPersona(page, "h-aiops");
  await page.goto("/l2/versioning");
  await page.getByRole("row", { name: /New skill: Late refund with DRI approval/ }).click();
  await expect(page.getByText("sandbox/skillify-conv-1042").first()).toBeVisible();
  await page.getByTestId("run-checks").click();
  await expect(page.getByTestId("impact-summary")).toContainText("37 of the last 412");
  await expect(page.getByText("awaiting approval").first()).toBeVisible();

  // L2 cannot approve C3. The L1 DRI approves and merges.
  await switchPersona(page, "h-hcs");
  await page.goto("/l1/digest?tab=approvals");
  await page.getByRole("link", { name: /New skill: Late refund with DRI approval/ }).click();
  await page.getByTestId("approve").click();
  await expect(page).toHaveURL(/\/l2\/versioning\//);
  await expect(page.getByText(/Merged .* Live in Production/).first()).toBeVisible();

  await page.goto("/l2/skills/refund-late-annual");
  await expect(page.getByRole("heading", { name: /Late refund with DRI approval v1/ })).toBeVisible();
  await expect(page.getByText("active").first()).toBeVisible();

  await page.goto("/l1/audit?correlation=conv%3Aconv-1042");
  for (const action of ["conversation.taken_over", "conversation.skillified", "change_request.tested", "approval.approved", "change_request.merged"]) {
    await expect(page.getByRole("cell", { name: action, exact: true })).toBeVisible();
  }
});

test("2. tax readiness: scheduler finds missing proof 21 days ahead, DRI uploads, readiness turns green", async ({ page }) => {
  await setPersona(page, "h-ks");
  await page.goto("/l2/readiness");
  await page.getByTestId("run-scheduler").click();
  const gap = await showCard(page.getByTestId("gaps"), "Input VAT invoices for September");
  await expect(gap.getByRole("link", { name: "Request sent" })).toBeVisible();

  await switchPersona(page, "h-fd");
  await page.goto("/l1/digest?tab=evidence");
  const open = page.getByRole("region", { name: "Open requests" });

  // The grant path shows scope, retention, agents and revoke before anything is granted.
  await (await showCard(open, "Input VAT invoices")).getByRole("button", { name: /Grant a data source/ }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toContainText("September 2026 only");
  await expect(dialog).toContainText("90 days");
  await expect(dialog).toContainText("Compliance Agent");
  await expect(dialog).toContainText("Revoke");
  await dialog.getByRole("button", { name: "Cancel" }).click();

  for (const item of ["Input VAT invoices", "Bank statement"]) {
    const card = await showCard(open, item);
    await expect(card).toContainText("VAT return, September 2026");
    await card.locator('input[type="file"]').setInputFiles({ name: `${item}.pdf`, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 sample") });
    await expect(open.getByRole("group").filter({ hasText: item })).toHaveCount(0);
  }
  // Fulfilled requests are folded away and say how they were fulfilled.
  await page.getByText(/^Fulfilled \(/).click();
  for (const item of ["Input VAT invoices", "Bank statement"]) {
    await expect(page.getByRole("list", { name: "Fulfilled requests" }).getByRole("listitem").filter({ hasText: item }).first()).toContainText("Fulfilled by an upload");
  }

  await page.goto("/l1/entity?ob=ob-vat-sep");
  const vat = page.getByTestId("obligation-ob-vat-sep");
  await expect(vat.getByTestId("readiness")).toHaveText("100%");
  await expect(vat.getByText("Ready", { exact: true })).toBeVisible();

  await page.goto("/l2/vault");
  await page.getByRole("tab", { name: "Facts" }).click();
  await page.getByRole("row", { name: /Input VAT invoices for September .* received/ }).click();
  await expect(page.getByText(/Provided as evidence for/)).toBeVisible();
});

test("3. policy drift: librarian proposes invalidation, dependents update in one change request, as of slider shows both versions", async ({ page }) => {
  await setPersona(page, "h-ks");
  await page.goto("/l2/policies/refund-window");
  // The drift marker sits on the timeline at its date; opening it shows the signal.
  await page.getByRole("button", { name: /Observed behaviour shows a drift point/ }).click();
  await expect(page.getByRole("region", { name: "Freshness signal" })).toContainText("Observed behaviour shows a drift point");

  await page.goto("/l2/vault?item=lib-refund-window"); // the queue shows one card at a time; this opens it on the drift item
  await page.getByTestId("propose-lib-refund-window").click();
  await expect(page).toHaveURL(/\/l2\/versioning\//);
  await expect(page.getByText(/Refund window changes from 30 to 14 days for annual plans, valid from 1 November/)).toBeVisible();
  const diff = page.getByRole("table", { name: "Structured diff" });
  for (const dep of ["Refund inside policy", "Refund register", "Pricing page, refund section"]) await expect(diff).toContainText(dep);
  await page.getByTestId("run-checks").click();
  await expect(page.getByText("awaiting approval").first()).toBeVisible();

  await switchPersona(page, "h-hcs");
  await page.goto("/l1/digest?tab=approvals");
  await page.getByRole("link", { name: /Invalidate refund window v3/ }).click();
  await page.getByTestId("approve").click();
  await expect(page.getByText(/Merged .* Live in Production/).first()).toBeVisible();

  await page.goto("/l2/policies/refund-window");
  await expect(page.getByTestId("true-then")).toContainText("v3");
  const slider = page.getByRole("slider", { name: "As of date" });
  await slider.focus();
  await page.keyboard.press("End");
  await expect(page.getByTestId("true-then")).toContainText("v4");
  await expect(page.getByTestId("believed-then")).toContainText("v4");
  await page.keyboard.press("Home");
  await expect(page.getByTestId("true-then")).toContainText(/v1|No version/);
});

test("4. website loop: Clarity friction, sandbox branch, impact preview, A/B experiment, kept and recorded as learning", async ({ page }) => {
  await setPersona(page, "h-aiops");
  await page.goto("/l2/loops/loop-website");
  const exp = page.getByTestId("experiment-exp-pricing-toggle");
  await expect(exp).toContainText("312 rage clicks on the pricing toggle");
  await exp.getByRole("button", { name: /Preview on a sandbox branch/ }).click();
  await expect(exp).toContainText("sandbox/exp-pricing-toggle");
  await exp.getByRole("button", { name: /Start A\/B experiment/ }).click();
  await expect(exp.getByText("running")).toBeVisible();
  await exp.getByRole("button", { name: "Conclude" }).click();
  await expect(exp.getByText("concluded")).toBeVisible();
  await exp.getByRole("button", { name: /Keep and ship/ }).click();
  await expect(exp.getByText(/Learning:/)).toBeVisible();
  await expect(exp.getByText(/awaiting approval/)).toBeVisible();
});

test("5. blocked action: denial in the decision log, locked edge in view as, Sentinel grant needs two L1 approvals", async ({ page }) => {
  await setPersona(page, "h-sec");
  await page.goto("/l2/security");
  const denied = page.getByRole("row", { name: /billing\.refund \(LKR 12,000\)/ });
  await expect(denied).toBeVisible();
  await expect(denied).toContainText("deny");

  await page.goto("/l2/graph");
  await selectOption(page, "View as", "View as Care Agent");
  const locked = page.getByTestId("locked-edges");
  await expect(locked).toContainText("Care Agent → billing.refund");
  await expect(locked).toContainText("refund:issue");

  await switchPersona(page, "h-hcs");
  await page.goto("/l1/approvals/apr-sentinel-grant");
  await page.getByTestId("approve").click();
  await expect(page.getByText(/Approvals 1 of 2/)).toBeVisible();
  await expect(page.getByTestId("approve")).toBeDisabled();
  await expect(page.getByRole("note")).toContainText(/two person rule/);

  await switchPersona(page, "h-founder");
  await page.goto("/l1/approvals/apr-sentinel-grant");
  await page.getByTestId("approve").click();
  await expect(page).toHaveURL(/\/l2\/versioning\/cr-sentinel-grant/);
  await expect(page.getByText(/Merged .* Live in Production/).first()).toBeVisible();
  await page.goto("/l3/agents/a-care");
  await expect(page.getByText("refund:issue")).toBeVisible();
});

test("6. overnight improvement: C0 and C1 fixes applied, the rest drafted, morning digest reports both", async ({ page }) => {
  await setPersona(page, "h-founder");
  await page.goto("/l1/digest");
  await expect(page.getByTestId("digest-applied")).toContainText("Refreshed Revenue health");
  await expect(page.getByTestId("digest-applied")).toContainText('Resolver synonym "chargeback"');
  await expect(page.getByTestId("digest-drafted")).toContainText("Billing dunning: retry once before the reminder");
  await page.getByRole("button", { name: /Run overnight review now/ }).click();
  await expect(page.getByText("Overnight review finished")).toBeVisible();
  await expect(page.getByTestId("digest-applied").getByText("C0")).toBeVisible();
  await expect(page.getByTestId("digest-applied").getByText("C1")).toBeVisible();
});

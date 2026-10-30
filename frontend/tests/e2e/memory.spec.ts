// Living memory, walked as a first-time owner would: glance, open an area, read its drift, follow the traces,
// open one trace, then find the skills drafted from traces and the drifting policy (Docs/CB_Living_Memory_Screens.md).
import { expect, test } from "@playwright/test";
import { collectConsoleErrors, setPersona } from "./helpers";

test("glance → area → drift → traces → one trace", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await setPersona(page, "h-founder");
  await page.goto("/l1/memory");

  // Step 1: the glance shows the four figures and the legend of areas
  await expect(page.getByRole("heading", { name: "Living memory" })).toBeVisible();
  await expect(page.getByText("Traces this week")).toBeVisible();
  const customers = page.getByRole("button", { name: /^Customers: \d+ traces this week/ }).first();
  await expect(customers).toBeVisible();

  // Step 2: opening Customers writes it to the address and shows one area card
  await customers.click();
  await expect(page).toHaveURL(/area=customer_care/);
  const card = page.getByTestId("area-card");
  await expect(card.getByRole("heading", { name: "Customers" })).toBeVisible();
  await expect(card.getByText("Skill drift")).toBeVisible();

  // Step 3: drift opens as cards, one at a time
  await card.getByRole("button", { name: /See drift/ }).click();
  const pager = page.getByTestId("drift-pager");
  await expect(pager.getByText("1 of 2")).toBeVisible();
  // Each drift shows its draft fix and where it stands: the refund skill fix is waiting for an L1 user
  await expect(pager.getByText(/Draft fix:/)).toBeVisible();
  await expect(pager.getByRole("list", { name: "Status: Waiting" })).toBeVisible();

  // Step 4: the traces list lands filtered to the area and to drift
  await page.getByTestId("drift-pager").getByRole("link", { name: "See drifting traces" }).click();
  await expect(page).toHaveURL(/traces\?area=customer_care&flag=drift/);
  await expect(page.getByText(/\d+ traces/).first()).toBeVisible();

  // Step 5: one trace reads from start to end in six numbered stages
  await page.getByRole("link", { name: /Refund request · CUS-1042/ }).click();
  const stages = page.getByRole("list", { name: "Trace, start to end" });
  await expect(stages.getByRole("heading", { name: "How it ended" })).toBeVisible();
  await expect(stages.getByText(/Why: 41 days since purchase/)).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("skills from traces and the drifting policy", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await setPersona(page, "h-aiops");
  await page.goto("/l2/skills");
  await page.getByRole("tab", { name: /From traces/ }).click();
  await expect(page.getByTestId("skill-drafts").getByRole("heading", { name: "Late refund approved by a person" })).toBeVisible();

  await setPersona(page, "h-ks");
  await page.goto("/l2/policies");
  await expect(page.getByRole("link", { name: "Drifting" })).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("new ways of working wait in To review, one at a time", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await setPersona(page, "h-founder");
  await page.goto("/l1/digest?tab=new");
  const pager = page.getByTestId("surprise-pager");
  await expect(pager.getByRole("link", { name: "Open the trace" })).toBeVisible();
  // Sample data says the button works on a live workspace, rather than pretending to keep the pattern
  await expect(pager.getByText("Sample data: this works on a live workspace.")).toBeVisible();
  await pager.getByRole("link", { name: "Open the trace" }).click();
  await expect(page).toHaveURL(/\/l1\/memory\/traces\//);
  expect(errors, errors.join("\n")).toEqual([]);
});

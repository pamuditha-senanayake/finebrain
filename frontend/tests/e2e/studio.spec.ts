// Workflow Studio end to end on mock data: who may change what, and where each edit goes.
import { expect, test, type Page } from "@playwright/test";
import { setPersona } from "./helpers";

async function ask(page: Page, message: string) {
  const box = page.getByRole("textbox", { name: "Message the studio assistant" });
  await box.fill(message);
  await page.getByRole("button", { name: "Send", exact: true }).click();
  const proposal = page.locator('section[aria-label^="Proposal:"]').last();
  await expect(proposal).toBeVisible();
  return proposal;
}

test("8a. the workflow owner applies a low risk edit straight away", async ({ page }) => {
  await setPersona(page, "h-founder");
  await page.goto("/studio?wf=wf-meetings&view=chat");
  const proposal = await ask(page, "add topic demos to the meetings workflow");
  await proposal.getByRole("button", { name: /Confirm and apply/ }).click();
  await expect(proposal.getByRole("status")).toContainText(/Applied\./);
});

test("8b. an L2 policy change is drafted on a sandbox branch and waits for approval", async ({ page }) => {
  await setPersona(page, "h-aiops");
  await page.goto("/studio?wf=wf-refunds&view=chat");
  const proposal = await ask(page, "make the refund window stricter");
  await expect(proposal).toContainText("21 days");
  await proposal.getByRole("button", { name: /Draft and send for approval|Send to/ }).click();
  const link = proposal.getByRole("link", { name: "Open change request" });
  await expect(link).toBeVisible();
  await link.click();
  await expect(page).toHaveURL(/\/l2\/versioning\//);
  await expect(page.getByText(/sandbox\/studio-/).first()).toBeVisible();
});

test("8c. L3 can only suggest an edit to the workflow DRI", async ({ page }) => {
  await setPersona(page, "h-op");
  await page.goto("/studio?wf=wf-refunds&view=chat");
  const proposal = await ask(page, "pause the refund agent");
  await expect(proposal.getByRole("button", { name: /Confirm and apply|Draft and send/ })).toHaveCount(0);
  await proposal.getByRole("button", { name: /Suggest to the DRI/ }).click();
  await expect(proposal.getByRole("status")).toContainText(/Sent to/);
});

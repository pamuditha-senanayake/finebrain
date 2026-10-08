import { expect, test } from "@playwright/test";
import { collectConsoleErrors, ROUTES, setPersona } from "./helpers";

test.describe("every route renders with a clean console", () => {
  for (const r of ROUTES) {
    test(`${r.label} (${r.path})`, async ({ page }) => {
      test.skip(r.path.startsWith("/research") && process.env.PW_SKIP_RESEARCH === "1");
      const errors = collectConsoleErrors(page);
      await setPersona(page, r.persona);
      await page.goto(r.path);
      await expect(page.locator("h1").first()).toBeVisible();
      await expect(page.getByRole("status", { name: /loading/i })).toHaveCount(0, { timeout: 15_000 });
      await expect(page.getByRole("alert").filter({ hasText: /something went wrong|do not have access/i })).toHaveCount(0);
      await page.waitForTimeout(400);
      expect(errors, errors.join("\n")).toEqual([]);
    });
  }
});

test("command palette opens, searches entities and navigates", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await setPersona(page, "h-founder");
  await page.goto("/l1");
  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByPlaceholder(/Search or jump/).fill("Refund Agent");
  await page.getByRole("option", { name: /Agent\s*Refund Agent/ }).click();
  await expect(page).toHaveURL(/\/l3\/agents\/a-refund/);
  await page.keyboard.press("ControlOrMeta+k");
  await expect(page.getByPlaceholder(/Search or jump/)).toBeVisible();
  expect(errors, errors.join("\n")).toEqual([]);
});

test("Ask the Brain answers with citations and valid time", async ({ page }) => {
  await setPersona(page, "h-founder");
  await page.goto("/l1");
  await page.getByRole("button", { name: "Ask the Brain" }).click();
  await page.getByRole("button", { name: "What is our refund window?" }).click();
  await expect(page.getByTestId("ask-answer")).toContainText("30 days");
  await expect(page.getByText(/true from/).first()).toBeVisible();
});

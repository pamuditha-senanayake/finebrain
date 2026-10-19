// Step 11: find and show. A search result opens its page with the thing lit; the match stepper moves one match at a time.
import { expect, test } from "@playwright/test";
import { setPersona } from "./helpers";

test("a run found in the palette opens on its row, locked on", async ({ page }) => {
  await setPersona(page, "sh-6", "scale");
  await page.goto("/l3/runs");
  await expect(page.getByText(/^[\d,]+ rows$/)).toBeVisible({ timeout: 30_000 });
  const subject = await page.evaluate(async () => (await (await fetch("/api/t/scale/lists/runs?limit=1&offset=412", { headers: { "x-persona": "sh-6" } })).json()).items[0].subject as string);
  await page.keyboard.press("Control+k");
  await page.locator("[cmdk-input]").fill(subject.slice(0, 24));
  await page.locator("[cmdk-item]", { hasText: subject }).first().click();
  await expect(page).toHaveURL(/focus=run%3A|focus=run:/);
  await expect(page.locator("[data-focus-lock]")).toBeVisible();
  await expect(page.locator("[data-focus-lock]")).toContainText(subject);
});

test("the stepper goes through the matches one at a time", async ({ page }) => {
  await setPersona(page, "sh-6", "scale");
  await page.goto("/l3/runs");
  await expect(page.getByText(/^[\d,]+ rows$/)).toBeVisible({ timeout: 30_000 });
  await page.getByLabel("Search Agent running history").fill("Reconciliation");
  const count = page.getByTestId("match-count");
  await expect(count).toHaveText(/^1 of [\d,]+$/);
  await page.getByRole("button", { name: "Next match" }).click();
  await expect(count).toHaveText(/^2 of [\d,]+$/);
  await expect(page.locator("[data-focus-lock]")).toBeVisible();
  await page.getByRole("button", { name: "Previous match" }).click();
  await expect(count).toHaveText(/^1 of [\d,]+$/);
});

test("filter chips show what is applied, and one button clears them", async ({ page }) => {
  await setPersona(page, "sh-6", "scale");
  await page.goto("/l3/runs");
  await expect(page.getByText(/^[\d,]+ rows$/)).toBeVisible({ timeout: 30_000 });
  await page.getByRole("combobox", { name: "Filter by status" }).click();
  await page.getByRole("option", { name: /^escalated/ }).click();
  await expect(page.getByLabel("Applied filters")).toContainText("escalated");
  await page.getByRole("button", { name: "Clear" }).click();
  await expect(page.getByLabel("Applied filters")).toHaveCount(0);
});

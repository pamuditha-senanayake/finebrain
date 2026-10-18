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
  // The glowing orb opens a bubble; ⌘J does the same. The question carries what is on screen.
  await page.getByRole("button", { name: "Ask the Brain" }).click();
  const bubble = page.getByRole("dialog", { name: "Ask the Brain" });
  await bubble.getByRole("textbox", { name: "Question" }).fill("What is our refund window?");
  await bubble.getByRole("button", { name: "Ask", exact: true }).click();
  await expect(page.getByTestId("ask-answer")).toContainText("30 days");
  await bubble.getByRole("button", { name: /source/ }).click();
  await expect(page.getByText(/True from/).first()).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(bubble).toBeHidden();
  await page.keyboard.press("ControlOrMeta+j");
  await expect(bubble).toBeVisible();
});

test("conversation list: Needs a human filter and search find the escalated refund", async ({ page }) => {
  await setPersona(page, "h-op");
  await page.goto("/l3/conversations");
  const list = page.getByRole("list", { name: "Conversations" });
  await page.getByRole("radio", { name: /Needs a human/ }).click();
  await expect(list.getByRole("link").first()).toBeVisible();
  for (const item of await list.getByRole("listitem").all()) await expect(item).toContainText("needs a human");
  await page.getByRole("radio", { name: /^All/ }).click();
  await page.getByRole("textbox", { name: "Search conversations" }).fill("conv-1042");
  await expect(list.getByRole("link")).toHaveCount(1);
  await expect(list.getByRole("link").first()).toHaveAttribute("href", "/l3/conversations/conv-1042");
});

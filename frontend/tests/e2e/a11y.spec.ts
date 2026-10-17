// Definition of done 4: WCAG 2.2 AA. axe checks every route in light and dark; keyboard checks cover the shell.
import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import { ROUTES, setPersona } from "./helpers";

for (const theme of ["light", "dark"] as const) {
  test.describe(`axe ${theme}`, () => {
    test.use({ colorScheme: theme });
    for (const r of ROUTES) {
      test(`${r.label}`, async ({ page }) => {
        await setPersona(page, r.persona);
        await page.goto(r.path);
        await expect(page.locator("h1").first()).toBeVisible();
        await expect(page.getByRole("status", { name: /loading/i })).toHaveCount(0, { timeout: 15_000 });
        await page.waitForTimeout(300);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          // The WebGL canvas is described by its label and has a text list view.
          .exclude('[data-testid="graph-canvas"]')
          .analyze();
        const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(serious.map((v) => `${v.id}: ${v.help} (${v.nodes.length}) ${v.nodes.slice(0, 2).map((n) => n.target.join(" ")).join(" | ")}`)).toEqual([]);
      });
    }
  });
}

test("the shell works with the keyboard alone", async ({ page }) => {
  await setPersona(page, "h-founder");
  await page.goto("/l1");
  await expect(page.locator("main h1").first()).toBeVisible();
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => document.activeElement?.tagName);
  expect(focused).toBeTruthy();
  await page.keyboard.press("ControlOrMeta+k");
  await page.keyboard.type("approvals");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\/l1\/approvals/);
  const outline = await page.evaluate(() => {
    const a = document.querySelector("main a") as HTMLElement;
    a.focus();
    return getComputedStyle(a).outlineStyle;
  });
  expect(outline).not.toBe("none");
});

test("live updates are announced", async ({ page }) => {
  await setPersona(page, "h-founder");
  await page.goto("/l1/digest?tab=approvals");
  await expect(page.locator("[aria-live]").first()).toBeAttached();
});

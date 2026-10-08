// Definition of done 3: screenshots for every route and persona, light and dark, at 1440 and 390 pixels.
import { expect, test } from "@playwright/test";
import { ROUTES, setPersona } from "./helpers";

const PERSONAS = ["h-founder", "h-fd", "h-hcs", "h-ks", "h-aiops", "h-sec", "h-op", "h-research"];
const HOME: Record<string, string> = { "h-founder": "/l1", "h-fd": "/l1", "h-hcs": "/l1", "h-ks": "/l2/graph", "h-aiops": "/l2/graph", "h-sec": "/l2/graph", "h-op": "/l3", "h-research": "/research/skills" };
const SIZES = [
  { name: "1440", width: 1440, height: 900 },
  { name: "390", width: 390, height: 844 },
];
const THEMES = ["light", "dark"] as const;

const targets = [
  ...ROUTES.map((r) => ({ label: r.label, path: r.path, persona: r.persona })),
  ...PERSONAS.map((p) => ({ label: `persona-${p}`, path: HOME[p], persona: p })),
];

for (const theme of THEMES) {
  for (const size of SIZES) {
    test.describe(`${theme} ${size.name}`, () => {
      test.use({ colorScheme: theme, reducedMotion: "reduce", viewport: { width: size.width, height: size.height } });
      for (const t of targets) {
        test(t.label, async ({ page }) => {
          await setPersona(page, t.persona);
          await page.goto(t.path);
          await expect(page.locator("h1").first()).toBeVisible();
          await expect(page.getByRole("status", { name: /loading/i })).toHaveCount(0, { timeout: 15_000 });
          await page.waitForTimeout(600);
          await page.screenshot({ path: `screenshots/${theme}-${size.name}/${t.label}.png`, fullPage: size.name === "1440", animations: "disabled" });
        });
      }
    });
  }
}

// Flow 7: with the research flag off, the console's routes, navigation and bundles are gone and the build passes.
import { existsSync, readdirSync, readFileSync, statSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { expect, test } from "@playwright/test";
import { setPersona } from "./helpers";

const DIST = join(process.env.NORESEARCH_DIR ?? join(tmpdir(), "cb-noresearch"), ".next");

function walk(dir: string): string[] {
  if (!existsSync(dir)) return [];
  return readdirSync(dir).flatMap((f) => {
    const p = join(dir, f);
    return statSync(p).isDirectory() ? walk(p) : [p];
  });
}

test("7. research removal: no routes, no navigation, no bundles", async ({ page }) => {
  const res = await page.goto("/research");
  expect(res?.status()).toBe(404);
  const res2 = await page.goto("/research/skills");
  expect(res2?.status()).toBe(404);

  await setPersona(page, "h-founder");
  await page.goto("/l1");
  await expect(page.locator("main h1").first()).toBeVisible();
  await expect(page.getByRole("tab", { name: /Research/ })).toHaveCount(0);
  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByPlaceholder(/Search or jump/).fill("Research Console");
  await expect(page.getByRole("option", { name: /Research Console/ })).toHaveCount(0);

  const files = walk(join(DIST, "static"));
  expect(files.length).toBeGreaterThan(0);
  const leaking = files.filter((f) => f.endsWith(".js") && /ResearchConsole|parseExperimentOutput|Research metrics/.test(readFileSync(f, "utf8")));
  expect(leaking, leaking.join("\n")).toEqual([]);
  expect(walk(join(DIST, "server", "app")).some((f) => f.slice(DIST.length).includes("research"))).toBe(false);
});

// Research Lab screens on a demo tenant (mock data): the four papers show, a paper with no Lab run shows its SAMPLE metrics,
// and every Lab screen explains that the Lab runs on Finebase HQ instead of failing. The live flow on HQ (upload, lock,
// run, resume, verdict) was walked by hand in the browser; the backend tests cover it end to end.
import { expect, test } from "@playwright/test";
import { collectConsoleErrors, setPersona } from "./helpers";

test("the four papers, a sample paper, and the Lab explaining where it runs", async ({ page }) => {
  const errors = collectConsoleErrors(page);
  await setPersona(page, "h-research");

  await page.goto("/research");
  const papers = page.getByRole("list", { name: "Papers" });
  await expect(papers.getByRole("link")).toHaveCount(4);
  await expect(papers.getByText("No run yet")).toHaveCount(4);

  await papers.getByRole("link", { name: /Freshness/ }).click();
  await expect(page).toHaveURL(/\/research\/policies/);
  await expect(page.getByText("Sample metrics")).toBeVisible();
  await expect(page.getByRole("button", { name: "CSV" })).toBeDisabled();

  for (const path of ["/research/lab", "/research/lab/new", "/research/prereg"]) {
    await page.goto(path);
    await expect(page.getByText("The Lab runs on Finebase HQ. Switch tenant in the top bar to use it.")).toBeVisible();
  }
  expect(errors, errors.join("\n")).toEqual([]);
});

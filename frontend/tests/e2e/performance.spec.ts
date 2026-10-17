// Definition of done 5: a 10,000 row table scrolls smoothly, a 2,000 node graph stays interactive,
// and heavy visual libraries stay out of each route's initial bundle.
import { expect, test } from "@playwright/test";
import { setPersona } from "./helpers";

test("a table with more than 10,000 rows scrolls smoothly and stays virtualized", async ({ page }) => {
  await setPersona(page, "sh-6", "scale");
  await page.goto("/l3/runs");
  const count = page.getByText(/^[\d,]+ rows$/);
  await expect(count).toBeVisible({ timeout: 30_000 });
  const total = Number((await count.textContent())!.replace(/[^\d]/g, ""));
  expect(total).toBeGreaterThanOrEqual(10_000);
  const rendered = await page.locator('[role="table"][aria-label="Runs"] [role="row"]').count();
  expect(rendered).toBeLessThan(120);

  const frames = await page.evaluate(async () => {
    const el = document.querySelector('[role="table"][aria-label="Runs"] .overflow-auto') as HTMLElement;
    const gaps: number[] = [];
    let last = performance.now();
    const step = el.scrollHeight / 120;
    for (let i = 0; i < 120; i++) {
      el.scrollTop += step;
      await new Promise((r) => requestAnimationFrame(() => r(null)));
      const now = performance.now();
      gaps.push(now - last);
      last = now;
    }
    gaps.sort((a, b) => a - b);
    return { p95: gaps[Math.floor(gaps.length * 0.95)], atBottom: el.scrollTop + el.clientHeight >= el.scrollHeight - 2 };
  });
  expect(frames.atBottom).toBe(true);
  expect(frames.p95).toBeLessThan(50);
});

test("a graph with more than 2,000 nodes stays interactive", async ({ page }) => {
  await setPersona(page, "sh-5", "scale");
  await page.goto("/l2/graph");
  const canvas = page.getByTestId("graph-canvas");
  await expect(canvas).toBeVisible({ timeout: 30_000 });
  const nodes = Number((await canvas.getAttribute("aria-label"))!.match(/with (\d+) nodes/)![1]);
  expect(nodes).toBeGreaterThanOrEqual(2_000);

  const t0 = Date.now();
  await page.getByLabel("fact", { exact: true }).click();
  await page.getByLabel("document", { exact: true }).click();
  const box = (await canvas.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
  await page.mouse.wheel(0, -400);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width / 2 + 80, box.y + box.height / 2 + 40, { steps: 8 });
  await page.mouse.up();
  const busy = await page.evaluate(async () => {
    const t = performance.now();
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(() => r(null))));
    return performance.now() - t;
  });
  expect(busy).toBeLessThan(200);
  expect(Date.now() - t0).toBeLessThan(5_000);
});

test("heavy visual libraries are not in the initial bundle of other routes", async ({ request, baseURL }) => {
  // The initial bundle is every script the route's HTML loads up front.
  for (const route of ["/l1", "/l1/digest?tab=approvals", "/l3", "/l2/policies"]) {
    const html = await (await request.get(`${baseURL}${route}`)).text();
    const srcs = [...html.matchAll(/<script[^>]+src="([^"]+\.js)"/g)].map((m) => m[1]);
    expect(srcs.length, route).toBeGreaterThan(0);
    for (const src of srcs) {
      const js = await (await request.get(`${baseURL}${src}`)).text();
      expect(js, `${route} ${src}`).not.toContain("react-flow__");
      expect(js, `${route} ${src}`).not.toContain("graphology");
    }
  }
});

test("the graph route loads its WebGL code only when the graph renders", async ({ page }) => {
  const loaded: string[] = [];
  page.on("response", async (r) => {
    if (r.request().resourceType() === "script" && /graphology/.test(await r.text().catch(() => ""))) loaded.push(r.url());
  });
  await setPersona(page, "h-sec");
  await page.goto("/l2/graph");
  await expect(page.getByTestId("graph-canvas")).toBeVisible({ timeout: 30_000 });
  expect(loaded.length).toBeGreaterThan(0);
});

// Plays every Workflow Studio use case in the running app and records one screenshot per moment, with the boxes
// of what to highlight. Output: ../video/studio/shots/*.png and ../video/studio/manifest.js (window.MANIFEST).
// Usage: node scripts/video/studio-record.mjs   (app on STUDIO_URL, default http://localhost:3000)
import { chromium } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "../../../video/studio");
const BASE = process.env.STUDIO_URL ?? "http://localhost:3000";
rmSync(join(OUT, "shots"), { recursive: true, force: true });
mkdirSync(join(OUT, "shots"), { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, colorScheme: "dark" });
const page = await context.newPage();
page.setDefaultTimeout(20_000);
const manifest = [];

async function settle(ms = 1200) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.getByText(/Reading the workflow|Edit Review Agent is checking|Searching what you may see|Reading Brain/).first().waitFor({ state: "detached", timeout: 15_000 }).catch(() => {});
  await page.waitForTimeout(ms);
}

async function as(persona) {
  await page.evaluate((p) => {
    const k = "cb.ui.v1";
    const cur = JSON.parse(localStorage.getItem(k) ?? "null");
    const state = cur?.state ?? { clusterId: "all", env: { kind: "production", branch: "main" }, personaByTenant: {} };
    state.tenantId = "finebase";
    state.personaByTenant = { ...(state.personaByTenant ?? {}), finebase: p };
    localStorage.setItem(k, JSON.stringify({ state, version: 0 }));
  }, persona);
}

async function go(path) {
  await page.goto(`${BASE}${path}`);
  await settle(1500);
}

/** One screenshot plus the boxes of the given targets, in CSS pixels of the 1440x900 viewport. */
async function shot(id, targets = []) {
  const boxes = [];
  for (const t of targets) {
    const loc = t.first();
    await loc.scrollIntoViewIfNeeded().catch(() => {});
    await page.waitForTimeout(250);
    const b = await loc.boundingBox().catch(() => null);
    if (b) boxes.push({ x: Math.round(b.x), y: Math.round(b.y), w: Math.round(b.width), h: Math.round(b.height) });
  }
  await page.waitForTimeout(400);
  const file = `shots/${String(manifest.length + 1).padStart(2, "0")}-${id}.png`;
  await page.screenshot({ path: join(OUT, file) });
  manifest.push({ id, file, boxes });
  console.log(`  ✓ ${id} (${boxes.length} box${boxes.length === 1 ? "" : "es"})`);
}

const box = () => page.getByRole("textbox", { name: "Message the studio assistant" });
async function type(text) {
  await box().fill(text);
}
async function send(text) {
  await type(text);
  await box().press("Enter");
  await settle();
}
const pane = () => page.getByRole("region", { name: "Workflow parts" });
const chip = (name) => page.getByRole("button", { name, exact: true });
const lastProposal = () => page.locator('section[aria-label^="Proposal:"]').last();
const lastAnswer = () => page.locator("p.leading-relaxed").last();

await page.goto(`${BASE}/`);
await page.evaluate(() => localStorage.clear());
await as("h-founder");

// 1. The first look: chat on the left, the workflow's story on the right.
await go("/studio?wf=wf-refunds");
await shot("start", [page.getByRole("heading", { name: "Start with the problem" }).locator(".."), pane()]);

// 2. Every workflow carries its story: the problem and its cases.
await chip("What problem does this workflow solve?").click();
await settle();
await shot("story", [lastAnswer(), pane().getByText("Problem").first().locator("..")]);

// 3-4. A new problem, in plain words, becomes BDD cases on the right.
await go("/studio?wf=wf-web");
await type("Leads go cold because nobody follows up for days");
await shot("problem-type", [box()]);
await box().press("Enter");
await settle(1800);
await shot("problem-cases", [page.getByText("Each case is written out on the right.").locator(".."), pane()]);

// 5. Add a case the chat missed.
await send("Add another case: a lead books a demo on a weekend");
await shot("add-case", [pane().locator("div.rounded-xl.border.bg-card").last()]);

// 6-7. Confirm the cases; the workflow is created and the chat asks what to build first.
await page.getByText("Yes, that is right", { exact: true }).last().click();
await settle();
await shot("confirm", [lastProposal()]);
await lastProposal().getByRole("button", { name: /Confirm and apply/ }).click();
await settle(3000);
await shot("created", [lastAnswer(), pane()]);

// 8-9. Build one case into a part; it fills in on the right and goes to approval.
await page.getByText(/^Build: /).first().click();
await settle(1800);
await shot("build", [pane().locator("div.ring-2").first()]);
await shot("build-route", [lastProposal().getByRole("button", { name: /Send to|Draft and send|Confirm and apply/ })]);

// 10-12. Change a rule: the part shows old and new values while the review checks the whole workflow.
await go("/studio?wf=wf-refunds");
await send("make the refund window stricter");
await shot("rule-change", [page.locator('[data-part="refunds.policy.refund-window"]')]);
await shot("review", [lastProposal()]);
await lastProposal().getByRole("button", { name: /Send to|Draft and send|Confirm and apply/ }).click();
await settle();
await shot("rule-sent", [lastProposal().getByRole("status")]);

// 13-14. What is broken, and a one click fix.
await go("/studio?wf=wf-meetings");
await chip("What is broken right now?").click();
await settle();
await shot("broken", [lastAnswer(), page.getByRole("navigation", { name: "Steps" })]);
const fix = page.locator("button").filter({ has: page.locator("svg.lucide-wrench") }).last();
if (await fix.count()) {
  await fix.click();
  await settle(1800);
  await shot("fix", [lastProposal()]);
}

// 15-16. Click a part to steer the chat, then edit it as a form.
await go("/studio?wf=wf-refunds");
await page.getByRole("button", { name: /Rules & tools/ }).click();
await settle(800);
await pane().getByRole("button", { name: /Refund auto threshold/ }).first().click();
await settle(800);
await shot("focus", [page.locator('[data-part="refunds.policy.refund-auto-threshold"]'), page.getByText("About", { exact: true }).locator("..")]);
await pane().getByRole("button", { name: "Edit" }).click();
await settle(800);
await shot("form", [page.locator('[data-part="refunds.policy.refund-auto-threshold"]')]);

// 17-18. Tools: ready-made first, custom code only when asked, tested in a sandbox.
await go("/studio?wf=wf-refunds");
await send("add a tool that issues a refund");
await shot("tool-ready", [lastAnswer(), page.locator('[data-part="tool:billing.refund"]')]);
await page.getByText("Write custom code instead", { exact: true }).last().click();
await settle(1800);
await shot("tool-custom", [pane().locator("div.ring-2").first(), lastProposal().getByText(/sandbox test run/).first()]);

// 19-20. The map, and history and links for the whole workflow.
await go("/studio?wf=wf-billing&view=diagram");
await settle(2500);
await shot("map", [pane()]);
await go("/studio?wf=wf-refunds");
await page.getByRole("button", { name: "About this workflow" }).click();
await settle(900);
await page.getByRole("tab", { name: "Versions" }).click().catch(() => {});
await settle(700);
await shot("history", [page.getByRole("dialog")]);

// 21-22. Who may change what: L2 drafts for approval, L3 can only suggest.
await as("h-aiops");
await go("/studio?wf=wf-refunds");
await send("make the refund window stricter");
await shot("l2", [lastProposal().getByRole("button", { name: /Draft and send|Send to/ })]);
await as("h-op");
await go("/studio?wf=wf-refunds");
await send("pause the refund agent");
await shot("l3", [lastProposal().getByRole("button", { name: /Suggest to the DRI/ })]);

// 23-24. Ask the Brain: one box, and it asks whether you mean this page or the whole system.
await as("h-founder");
await go("/l1");
await page.getByRole("button", { name: "Ask the Brain" }).click();
await page.waitForTimeout(600);
const panel = page.getByRole("complementary", { name: "Ask the Brain" });
await panel.getByRole("textbox", { name: "Question" }).fill("What is our refund window?");
await panel.getByRole("button", { name: "Ask", exact: true }).click();
await settle(900);
await shot("ask-choose", [panel.getByRole("group", { name: "What is this about" })]);
await panel.getByRole("group", { name: "What is this about" }).getByRole("button", { name: "Whole system" }).click();
await settle(3000);
await shot("ask-answer", [page.getByTestId("ask-answer")]);

writeFileSync(join(OUT, "manifest.js"), `// Written by frontend/scripts/video/studio-record.mjs\nwindow.MANIFEST = ${JSON.stringify(manifest, null, 1)};\n`);
console.log(`saved ${manifest.length} shots`);
await browser.close();

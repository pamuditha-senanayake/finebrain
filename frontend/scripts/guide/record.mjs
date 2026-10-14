// Plays every guide scenario in the running app (default http://localhost:3100) and records one screenshot per step.
// Output: ../video/guide/shots/*.png and ../video/guide/manifest.js (window.MANIFEST) for the video composer.
import { chromium } from "@playwright/test";
import { mkdirSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CHAPTERS, PERSONAS, SCENARIOS } from "./scenarios.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const OUT = join(here, "../../../video/guide");
const BASE = process.env.GUIDE_URL ?? "http://localhost:3100";
rmSync(join(OUT, "shots"), { recursive: true, force: true });
mkdirSync(join(OUT, "shots"), { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, colorScheme: "light", reducedMotion: "reduce" });
const page = await context.newPage();
page.setDefaultTimeout(15_000);

async function settle() {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.getByRole("status", { name: /loading/i }).first().waitFor({ state: "detached", timeout: 10_000 }).catch(() => {});
  await page.waitForTimeout(450);
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

await page.goto(`${BASE}/`);
await page.evaluate(() => localStorage.clear());
await as("h-founder");

const manifest = { chapters: CHAPTERS, personas: PERSONAS, scenarios: [] };
let n = 0;
for (const sc of SCENARIOS) {
  console.log(`▶ ${sc.title}`);
  const out = { id: sc.id, chapter: sc.chapter, feature: sc.feature, title: sc.title, persona: sc.persona, why: sc.why, steps: [] };
  let persona = sc.persona;
  for (const st of sc.steps) {
    if (st.as) {
      await as(st.as);
      persona = st.as;
    }
    if (st.go) {
      await page.goto(`${BASE}${st.go}`);
    } else if (st.as) {
      await page.reload();
    }
    await settle();
    const shot = st.shot ?? (st.act ? "before" : "after");
    if (st.act && shot === "after") {
      await st.act(page);
      await settle();
    }
    let box = null;
    if (st.target) {
      const loc = st.target(page).first();
      await loc.scrollIntoViewIfNeeded().catch(() => {});
      await page.waitForTimeout(150);
      box = await loc.boundingBox().catch(() => null);
    }
    const file = `shots/${String(++n).padStart(3, "0")}-${sc.id}.png`;
    await page.screenshot({ path: join(OUT, file) });
    const url = new URL(page.url());
    if (st.act && shot === "before") {
      await st.act(page);
      await settle();
    }
    if (st.after) {
      await st.after(page);
      await settle();
    }
    out.steps.push({ kw: st.kw, text: st.text, shot: file, box: box && { x: box.x, y: box.y, w: box.width, h: box.height }, action: st.act ? (shot === "before" ? "click" : "type") : "see", persona, path: url.pathname + url.search });
  }
  manifest.scenarios.push(out);
}
writeFileSync(join(OUT, "manifest.js"), `window.MANIFEST = ${JSON.stringify(manifest, null, 1)};\n`);
console.log(`recorded ${n} steps in ${manifest.scenarios.length} scenarios`);
await browser.close();

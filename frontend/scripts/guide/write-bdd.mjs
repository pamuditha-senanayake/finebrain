// Writes the BDD user guide (Docs/Company_Brain_User_Guide_BDD.md) from the same scenarios the video plays.
import { writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { CHAPTERS, PERSONAS, SCENARIOS } from "./scenarios.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "../../../Docs/Company_Brain_User_Guide_BDD.md");
const START = {
  "h-founder": "Brain overview, then Morning digest", "h-fd": "Entity protection, then Evidence requests", "h-hcs": "Approvals",
  "h-ks": "Ground truth vault (librarian queue)", "h-aiops": "Versioning (change requests)", "h-sec": "Security and access",
  "h-op": "Escalations, then Live conversations", "h-research": "Research Console",
};

const lines = [];
const w = (s = "") => lines.push(s);
w("# Company Brain User Guide (BDD scenarios)");
w();
w("Every use case of the Company Brain console, written as Given, When, Then scenarios. The guide video plays these same scenarios on the real app (`video/guide/company_brain_user_guide.mp4`). The scenarios live in `frontend/scripts/guide/scenarios.mjs`; this file is generated from them by `node scripts/guide/write-bdd.mjs`.");
w();
w("## What Company Brain is");
w();
w("A governed layer where AI agents run company operations (customer care, refunds, billing, sales, scheduling, website changes, tax readiness) using company knowledge, under policies and security that people control.");
w();
w("| Tier | Who | What you do there |");
w("|---|---|---|");
w("| L1 Command | Founders, directors, DRIs | Follow progress and risk, approve high criticality changes, provide evidence, protect the legal entity |");
w("| L2 Governance | Stewards and supervisor agents | Author and test skills, policies, security, templates and knowledge before anything ships |");
w("| L3 Operations floor | Worker agents and operators | Agents do the work. Operators watch live, inspect runs, take over and Skillify |");
w();
w("Every function is a loop: **sensor** (notices what happened), **policy** (decides what is allowed), **tool** (does the work), **quality gate** (checks the result), **learning** (improves overnight).");
w();
w("## Where to start");
w();
w("Pick your persona from the menu in the top right of any screen. Higher tiers can look down, never up.");
w();
w("| Persona | Role | Tier | Start here |");
w("|---|---|---|---|");
for (const [id, p] of Object.entries(PERSONAS)) w(`| ${p.name} | ${p.title} | ${p.tier} | ${START[id]} |`);
w();
w("## How to read a scenario");
w();
w("| Keyword | Meaning |");
w("|---|---|");
w("| Given | The situation, the screen and who you are |");
w("| When | What you do |");
w("| Then | What you should see |");
w("| And | One more of the line above |");
w();
w("Criticality decides who approves: C0 automatic, C1 L2 supervisor agent, C2 L2 steward, C3 the L1 DRI, C4 two L1 approvers.");
w();
let n = 0;
for (const ch of CHAPTERS) {
  const list = SCENARIOS.filter((s) => s.chapter === ch.id);
  if (!list.length) continue;
  w(`## ${ch.label}`);
  w();
  for (const sc of list) {
    n++;
    const p = PERSONAS[sc.persona];
    const route = sc.steps.find((s) => s.go)?.go ?? "/";
    w(`### ${n}. ${sc.title}`);
    w();
    w(`**Persona:** ${p.name}, ${p.title} (${p.tier}) · **Screen:** \`${route}\``);
    w();
    w(`**Why it matters:** ${sc.why}`);
    w();
    w("```gherkin");
    w(`Feature: ${sc.feature}`);
    w();
    w(`  Scenario: ${sc.title}`);
    for (const st of sc.steps) w(`    ${st.kw} ${st.text}`);
    w("```");
    w();
  }
}
w("## Why use Company Brain in an enterprise");
w();
w("| Benefit | What it means | Where you see it |");
w("|---|---|---|");
w("| Work finishes without people, safely | Agents resolve routine work inside their skills and capabilities | Brain overview, Fleet |");
w("| Approval weight follows criticality | Routine changes flow, consequential ones stop for the right DRI, C4 needs two L1 approvers | Approvals |");
w("| Nothing goes live blind | Sandbox tests, replay of real runs and a plain language diff before any approval | Versioning |");
w("| Ground truth you can trust | Every fact has evidence, valid time, recorded time and a verifier; conflicts are caught | Ground truth vault, Policy registry |");
w("| Security at the moment of action | Agents cannot exceed their capabilities or the person they act for; every decision is logged | Security and access, View as |");
w("| Never do one off work | Skillify turns how a person handled a case into a tested, versioned skill | Live conversations |");
w("| Protects the legal entity | Deadlines watched 21 days ahead, evidence requested early, scoped and revocable data grants | Entity protection, Evidence requests |");
w("| Complete accountability | One named DRI per object and a read only audit trail of every action | Audit trail |");
w("| Built for enterprise scale | Hundreds of agents and tens of thousands of runs, versioned and rollbackable like git | Scale Demo tenant |");
w();
w("All tenant data in the console is deterministic demo data. Dates, tax rules and amounts are samples, not legal or tax guidance.");
writeFileSync(out, lines.join("\n") + "\n");
console.log(`wrote ${out} with ${n} scenarios`);

# Living memory: build plan

Date: 2026-10-30. Status: plan only. Nothing is built yet. We go one stage at a time, and each stage waits for approval before the next one starts.

## What we agreed

| Decision | In short |
|---|---|
| Brain areas | The 8 fixed domains already in `item_tags.py`: Customers, Money, Rules, Staff, Operations (with suppliers), Sales, Product, Other. Access is checked in every area rather than being an area. Each company picks its own at setup |
| Patterns | Each area keeps a few typical patterns, about 20 to 50. A new trace is compared only with its own area's patterns |
| Similar traces | Raise the pattern's count, then move the full trace to raw storage (S3) |
| Different traces | Raise to a person. Their answer can become a new pattern |
| Traces | One record per piece of work, from start to end: input, area, steps, policy version, skill version, access decisions, outcome, and the why |
| Manual work | Refunds made outside Finebrain (for example in Stripe) become traces too, flagged within policy or outside policy |
| Drift | Three kinds: skill drift, policy drift and security drift |
| Skillify | Goes beyond fixing one run. It extracts new skill drafts from patterns |
| Fixes from drift (added 2026-10-30) | Skill drift drafts a skill change, policy drift drafts a policy change. An L1 user approves both. Each drift shows its state: detected, sent to L1, waiting for approval, approved, resolved. A 14-day re-check resolves it or reopens it |
| New page | "Living memory", placed under Brain overview. It does not replace Brain overview yet |
| Order | Frontend and its contracts first, then the pipeline, then connect the two |

## Stages

| # | Stage | Main output | Done when |
|---|---|---|---|
| 1 | Final memory architecture | `Docs/CB_Living_Memory_Architecture.md` (dated), a "superseded" note on the old memory docs, an updated draw.io | One doc describes the memory and nothing contradicts it |
| 2 | Frontend design and API contracts | Page flow and every state, zod contracts, mock fixtures | Every fixture parses against its contract in a unit test |
| 3 | Frontend build on mock data | Living memory page with the full-page 3D globe of areas, Traces, a "From traces" tab in Skills, drift on the policy registry | Every state checked in the browser, Playwright walk passes, data is labelled "Sample" |
| 4 | Pipeline contracts and walking skeleton | New contracts K16 to K19, a thin end-to-end path | One refund flows trace → area → pattern → drift → skill draft in a test |
| 5 | Thicken the memory | Area registry, pattern store, triage, raw storage, nightly tidy, manual-work traces | The CLAUDE.md real-use bar is met for the memory stages |
| 6 | Thicken drift and fixes | Skill, policy and security drift checks, skill and policy drafts, L1 approval, drift states, the 14-day re-check | Each check and each state change is tested on known cases |
| 7 | Backend routes and connection | FastAPI routes that match the stage 2 contracts, frontend switched from mock to live | Contract tests pass on both sides, and the page shows live Finebase HQ data |
| 8 | Real-use bar and demo | Real infra tests, many-worker tests, volume script, updated demo guides and scorecard | Everything on the CLAUDE.md list, with gaps named out loud |

## Stage details

### 1. Final memory architecture

1. Write `CB_Living_Memory_Architecture.md`, dated 2026-10-30, covering:
   - areas, patterns, triage and tiers
   - the trace record
   - the three drift kinds
   - skill extraction
   - budgets: patterns per area, triage time, and the number of tokens per question
2. Map what exists today onto it: S3 routing, `stages_tiers.py`, `stages_cold.py`, weekly counts, `drift_signal.py`, Skillify, and the S10 trace.
3. Put a one-line "superseded by" header on `CB_Memory_Architecture.md`, `CB_Graph_and_Memory_Plan.md` and section 7 of `Finebrain_Living_Memory_Thinking.md`.
4. Update `CB_Reasoning_Layer_Fit.drawio` so it shows areas and patterns.

### 2. Frontend design and API contracts

1. Design the flow: what a first-time viewer sees, what a click opens, and how they get back.
2. Design every state: loading, empty, error, and Sample-only.
3. Write the zod contracts in `frontend/contracts/memory.ts`:
   - `MemoryMap`: each area with its traces, patterns, authored and extracted skills, the three drift counts and conflicts
   - `AreaDetail`: one area's patterns and recent changes
   - `TraceList`: paged, filtered by area and by flag
   - `TraceDetail`: the timeline from start to end, plus the why
   - `ExtractedSkill`: the pattern, its draft steps, its support count and its review state
   - `DriftItem`: the kind, the area, the evidence and the state
4. Write mock fixtures that look like realistic Finebase cases, plus a unit test that parses every fixture.

### 3. Frontend build on mock data

1. Add a nav item, "Living memory", under Brain overview.
2. Build the 3D dot brain with three.js (the project already uses it in `graph-canvas-3d.tsx`):
   - a brain shape made of dots, with a coloured region for each area
   - dots that ripple away from the cursor
   - callout lines with a round end and straight segments
   - counts for each area
   - a calm 2D fallback when reduced motion is on
3. Clicking an area opens one area card at a time, with Next and Back. It shows the traces, skills and the three drift counts.
4. Build Traces: a list, then a detail view drawn as a numbered timeline (input, area, steps, policy, skill, access, outcome, why).
5. Add a "From traces" tab in Skills: extracted skill drafts, each with how many traces support it and its review state.
6. Show drift in the policy registry's Freshness column and on the area card.
7. Check it in the browser at phone and desktop widths, by keyboard, and in dark mode. Add a Playwright walk.

### 4. Pipeline contracts and walking skeleton

1. New contracts in `backend/app/pipeline/`:
   - K16 TraceRecord: S10 to the trace store
   - K17 AreaMatch: triage's area, pattern, similarity, and normal or surprise
   - K18 DriftFlag: skill, policy or security, with evidence
   - K19 SkillDraft: from a pattern to a K13 change request
2. Build thin stages, in memory, that pass each contract along.
3. Write one test that walks a refund through every contract.

### 5. Thicken the memory

1. Area registry per tenant, chosen at setup, with Other as the overflow. When Other keeps growing, a person can promote it to its own area.
2. Pattern store in Postgres, read by area and pattern key, never by listing everything.
3. Triage compares only inside the area, with no Claude call. A similar trace raises the count and goes to raw storage. A different one goes to To review, surprises first.
4. Manual-work traces from the Stripe connector, each checked against the policy valid on its date.
5. Nightly tidy in S13: merge similar patterns, drop rare ones, keep each area inside its budget.
6. Two workers, atomic claims, and designed failure outcomes.

### 6. Thicken drift and skill extraction

1. Skill drift: the share of an area's recent traces that follow the skill's steps, compared week to week. This is our own simple fitness score. pm4py stays outside the app.
2. Policy drift: `drift_signal.py` over each area's pattern counts, plus the rate of manual work outside policy.
3. Security drift: every action in a trace has an allow decision for the right tier and the right person. A missing or mismatched decision is flagged.
4. Skill extraction: first a step sequence taken from a well-supported pattern, with no Claude call. Then an optional Claude pass names the steps. The draft opens as a Skillify change request.
5. Policy drafts: policy drift writes the new value with a valid-from date, as a change request.
6. L1 approval for every skill and policy fix. Security drift goes to L1 as an incident with no draft.
7. Drift states (detected, sent to L1, waiting for approval, approved, resolved), with rejection returning to detected.
8. The 14-day re-check after a fix goes live: resolve it, or reopen it with a note.

### 7. Backend routes and connection

1. Add FastAPI routes under `/api/t/{tenant}/memory/…`, one for each stage 2 contract.
2. Check the OpenAPI schema against the zod contracts.
3. Switch the frontend from mock to live, keeping the mock for the demo workspace.
4. Seed Finebase HQ with realistic traces, so the live page has real numbers.

### 8. Real-use bar and demo

1. Write `tests/test_memory_real.py` on Postgres, Valkey, Redpanda and Temporal.
2. Write `scripts/memory_volume.py` with thousands of traces, timing triage against its budget.
3. Walk the page in the browser as a first-time viewer, through every state.
4. Update the three demo guides and the scorecard, with gaps named.

## For the presentation in two days

Stages 1 to 3 fit in two days. The brain will then run on mock data. To avoid misleading the panel, it shows a "Sample" badge, and we say the live connection is the next stage. If there is time, a thin part of stage 7 can show live counts that already exist (runs, access decisions, drift results) on Finebase HQ.

## Risks

| Risk | How we handle it |
|---|---|
| Showing extracted skills that do not exist yet | They stay labelled Sample until stage 6 is built |
| Model credit is low (about $6.50) | Extraction and triage work without Claude first. Ask before any paid run |
| The 3D brain looks busy | Calm motion, one accent colour, a reduced-motion fallback, few words |
| Old memory docs conflict | Stage 1 marks them superseded |

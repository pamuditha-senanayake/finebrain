# Company Brain: plan for steps 10 to 16

Version 1, 19 October 2026. This file hands the next steps to a new session. Read it first, then build one step at a time. Each step has its own scope, files and done check, so you can ask for "step 11" on its own.

## 1. Where the work stands

| Area | Status |
|---|---|
| Branch | `feature/backend-build`, pushed. Not merged to `main`. |
| Lane A (S1 to S10) | Built: capture, normalize, route, retrieve, reason, govern, decide, act, record. Real Claude, Voyage, OPA, Temporal, Kafka, Postgres, Valkey and S3 when Docker runs; memory twins otherwise. |
| Step 9 | Built: Finebase HQ on the real backend (9a), Ask the Brain with memory, cold start, voice, the floating orb, page view and uploads (9b), graph screens (9c), Studio writes with S14 versioning (9d), Studio chat on Claude (9e) |
| Memory design | `Docs/CB_Memory_Architecture.md` and `.drawio`. 13a and 13b built (tags, entities, narrow first); 13c to 13e not yet |
| Lanes B, C, D | Built: Lane B in step 14, Lane D in step 16, Lane C in step 15 (see their status rows in the system reference). |
| Tests | 226 backend tests pass (`cd backend && uv run pytest -q`); 43 skip without Docker. 43 frontend unit tests pass (`cd frontend && npx vitest run`). 39 e2e tests fail, all of them already failing before step 9 (contrast, keyboard, performance). |

## 2. Read before you build

| Read | Why |
|---|---|
| `CLAUDE.md` | House rules: calm screens with few words, one thing at a time, one accent colour, files of 150 lines or less, a fixed folder for each kind of file |
| `Docs/CB_System_Reference.md` | Layers, stages, contracts, storage, and the status row of every step so far (section 11) |
| `Docs/CB_Memory_Architecture.md` | The memory design that step 13 builds |
| `backend/app/api/routes.py` | How Finebase HQ serves the console. Screens not built yet answer `[]` or 501, never demo data. |
| `frontend/scripts/check-contracts.ts` | Checks every served shape against the console's zod contracts. Run it with the API up. |

| Run | Command |
|---|---|
| Backend API (memory mode, no Docker) | `cd backend && HQ_REAL_PARTS=none uv run fastapi dev app/main.py --port 8000` |
| All infra (Docker) | `backend/scripts/dev_up.sh`, then start the API without `HQ_REAL_PARTS` |
| Console | `cd frontend && npm run dev` (port 3000). Finebase HQ is the real tenant; demo-fbl and Scale Demo stay on mocks. |
| Contract check | `cd frontend && npx tsx scripts/check-contracts.ts` |

Rules that held so far: commit after each sub-step, keep each test file next to its job in `backend/tests/`, and never let the browser decide impact or approval.

## 3. The steps

Suggested order: 10, then 11 and 12 (either order), then 13, then 14 to 16. Step 10 comes first so every memory layer in step 13 is built with a way to forget.

### Step 10: Forgetting knowledge across every layer (done, see the status row in the system reference)

Two kinds of removal:

| Kind | Meaning | What happens |
|---|---|---|
| Retire | No longer true | The item's valid time closes. "As of last month" still finds it; today's search does not. |
| Erase | Must be gone (personal data, legal) | Content is purged from every layer. A tombstone keeps who, when and why, never the content. |

| Sub-step | Builds | Files |
|---|---|---|
| 10.1 Layer registry | Every storage layer registers a forget handler (`retire(item)`, `erase(item)`, `verify(item)`). A layer added later must register one. | new `backend/app/pipeline/forget.py` |
| 10.2 Today's layers | Graph knowledge node (a close version), search index (delete or replace the chunk: `store_chunks.py`), S3 original, Library record, PII vault values (only if no other record uses them), Valkey caches. Run traces keep their story, but the source shows as removed. | `store_chunks.py`, `store_s3.py`, `store_postgres.py`, `stages_file.py` |
| 10.3 Review first | Before removal, list what depends on the item (policies or facts that cite it, skills governed by them) and set the level: removing a document is C3, deleting ground truth is C4, erasing personal data follows the data request register. Reuse the Studio review pattern and S8 approvals. | new `backend/app/api/forget_review.py`, reuse `studio_approvals.py` |
| 10.4 The job | A Temporal workflow (or in-process when Temporal is off) runs each handler, then verifies: search again and find nothing. It issues a receipt listing every layer cleared, and writes a hash-chained audit entry. | `temporal_flow.py`, `audit.py` |
| 10.5 Console | Library: "Remove" on a document opens the review card (Retire or Erase, what depends on it, who must approve). To review shows the approval. The receipt is shown on the document. | `frontend/features/l2/library.tsx`, contracts in `frontend/contracts/knowledge.ts` |

Done when: removing an uploaded document makes Ask stop citing it, the receipt lists every layer, an "as of" query still finds a retired item, and an erased item leaves only its tombstone.

### Step 11: Find and highlight (done, see the status row in the system reference)

| Sub-step | Builds | Files |
|---|---|---|
| 11.1 Search with targets | `GET search?q=` on HQ returns hits with `href` plus `focus: {kind, id, field?, span?}`. Uses Postgres full text over runs, documents, policies, skills and conversations, and the hybrid search for knowledge. | new `backend/app/api/search.py`, contract `SearchHit` in `frontend/contracts/ops.ts` |
| 11.2 One focus link | `?focus=kind:id` (and `&span=start:end`) works on every page. A shared hook finds the element marked `data-focus-id`, scrolls to it, opens its detail if it lives in a drawer, and pulses the accent ring for about three seconds. | new `frontend/lib/focus.ts`, mark rows and cards with `data-focus-id` |
| 11.3 Sentence highlight | Documents and policies light the matching sentence with the CSS Custom Highlight API | `frontend/lib/focus.ts`, policy and library detail views |
| 11.4 Ask shows the way | Ask answers carry `actions` (already in the `AskAnswer` contract) with focus links; the orb bubble and the Ask page show one "Show me" button | `backend/app/api/ask.py`, `components/shell/ask-bubble.tsx`, `features/l1/ask-voice.tsx` |
| 11.5 Command palette | ⌘K search results open with focus | `components/shell/command-palette.tsx` |

Done when: asking "where is the refund window?" opens the policy page with that sentence lit, and a ⌘K result lands on the exact row.

### Step 12: Lists of thousands (done, see the status row in the system reference)

| Sub-step | Builds | Files |
|---|---|---|
| 12.1 Server side query | List endpoints take `q`, filters, `cursor` and `around=id`. They return a page, the total, and the target's position. Never filter thousands of rows in the browser. | `backend/app/api/lists.py` (runs, conversations, documents, audit, access decisions) |
| 12.2 Jump to row | The virtualized `DataTable` takes a target index, scrolls to it and highlights the row with the step 11 focus ring | `frontend/components/brain/data-table.tsx` |
| 12.3 Match stepper | "3 of 23 matches", with Next and Back, one match at a time (the house rule). Filter chips show what is applied, with one clear button. | shared component in `frontend/components/brain/` |
| 12.4 Facet counts | Counts per filter value come from the server | `lists.py` |
| 12.5 Proof | Seed 10,000 runs in a test and measure | `backend/tests/`, `frontend/tests/e2e/performance.spec.ts` |

Done when: finding one run among 10,000 opens on its row in under a second, and scrolling stays smooth.

### Step 13: Memory and storage (13a and 13b done, see the status row in the system reference)

| Sub-step | Builds |
|---|---|
| 13a Four tags | Tenant, area, entity and time on every item at S2 and S11, plus entity matching (one node per real thing) |
| 13b Narrowing first | S5 filters by the four tags before any vector search |
| 13c Four tiers | Hot, warm, cold and raw, each with a fixed budget; a value score; a job that moves items between tiers. Each tier registers step 10 forget handlers. |
| 13d The Distiller | Nightly (a Temporal schedule): the summary ladder (day, week, month per entity), duplicate merging, version chains, and the core field dictionary |
| 13e Shared commons | Knowledge shared across workflows without copying |

Done when: retrieval cost stays flat as stored data grows (measured), nightly summaries appear, and forgetting an item also clears it from summaries.

### Step 14: Lane B (documents into verified facts) (done, see the status row in the system reference)

Full S11 filing rules, S12 fact extraction with evidence, the librarian queue and the ground-truth vault on the HQ backend. It replaces the thin S11 from step 9b. Done when an uploaded contract becomes reviewed facts in the vault.

### Step 15: Lane C (learning) (done, see the status row in the system reference)

S13: weekly signal counts and the spike check (the Trends tab goes live on HQ; contract `TrendCard`), the nightly review, and skillify drafting Studio proposals through the same review. Done when a real unusual week shows up in Trends.

### Step 16: Lane D (readiness and evidence) (done, see the status row in the system reference)

S15: obligations, readiness and evidence requests on HQ (K15 GapDetected). Done when a missing filing shows up as a gap with an owner.

## 4. Open items to settle alongside

| Item | Why |
|---|---|
| Docker on by default | Without it, HQ data, conversations and uploads live in memory and are lost when the backend restarts |
| A second L1, or a delegate | Finebase HQ has one L1. Changes at C3 or above that the L1 drafts cannot be approved, and C4 needs two L1 leaders. This includes the refund worker's missing `reply.draft` capability (open question 10 in the system reference). |
| 39 older e2e failures | Colour contrast, keyboard and performance tests that already failed before step 9 |
| Stray file | `CB_Memory_Architecture.md` at the repo root is an untracked copy of the one in `Docs/`. Delete it after a look. |

## 5. How to ask a session for a step

Say: "Read `Docs/CB_Plan_Steps_10_to_16.md`, then plan step N in detail. Don't execute yet." After you accept the plan, say "build step N". Each step ends with tests, the contract check, a browser check on Finebase HQ, a status row in `Docs/CB_System_Reference.md`, and a commit on `feature/backend-build`.

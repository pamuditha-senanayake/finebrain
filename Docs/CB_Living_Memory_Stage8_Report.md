# Living memory, stage 8 report: the real-use bar and the demo

Date: 2026-10-31. Branch: `living-memory`. Plan: `CB_Living_Memory_Build_Plan.md`, stage 8. This closes the build. Stages 5 to 7 have their own reports.

## What stage 8 built

| Part | What it does | Where |
|---|---|---|
| Plain names | Drift cards, patterns and traces name skills and policies the way Studio does ("Refund policy", "Refund handling"), read from the graph by id. Skill fixes list readable steps ("Plan checked → Customer told"). Access reasons are in words. Work with no run record is named by its steps. | `api/memory_views.py`, `stages_memory.py`, `trace-timeline.tsx` |
| New ways in To review | A "New ways" tab shows work that matched no known pattern, one card at a time with Back and Next. Each card opens its trace, or keeps the work as normal. The map's "Waiting" figure opens this tab. | `features/l1/memory/surprises.tsx`, `features/l1/digest.tsx` |
| One answer per press | Keep and Send take an atomic claim (Valkey `SET NX`, freed after 60 s if a worker crashes). A decision finds its skill draft by key, never by listing drafts. | `api/memory_fixes.py` |
| 12-week volume | `memory_volume.py --weeks 12` moves the refund skill to a new path and spikes late hand refunds in the latest week. The night must raise exactly one skill drift and one policy drift. | `scripts/memory_volume.py` |
| Every state walked | Live HQ in light, dark and black. Phone width. Sample data. An unknown trace. The backend down. New ways' own empty state can't be reached on HQ or the sample, so it was read in code, not seen. | Browser check, below |
| Guides and scorecard | Each demo guide has a one-minute "Only if asked" part and a Q&A answer. The scorecard says what the memory adds to each paper, and why no percentage moves. | `CB_*_Demo_Guide.md`, `CB_Research_Progress_Scorecard.md` |

## The real-use bar (CLAUDE.md), for the whole living memory

| Rule | Status | Evidence |
|---|---|---|
| Every visit tested | Met | A trace triaged again, a drift raised again, a redelivered decision, a surprise kept twice, a draft sent twice. Each gives one result (stages 5 to 8 tests). |
| Real infra | Met | `test_memory_real.py` on Postgres, Valkey, Redpanda and SeaweedFS. The Distiller's Temporal schedule runs the night (its own tests). |
| Many workers | Met | Two workers triaging one trace, two raising one drift, and two people pressing Keep on one surprise each give one result. The Keep test fails 3 of 3 times without the claim. |
| Failures designed | Met | Stores down, a missed message, a fix Studio refuses, two threads on one connection, an unknown trace, the backend down. Each has a tested or walked outcome. |
| No scans | Met | Counts are indexed. Pages use keyset cursors. Flags, reviews, drafts and names are read by key. |
| One source of truth | Met | Names and policies come from the graph, fixes go through Studio, and approvers follow S8. The seed script reads the policy in force from the graph. |
| Volume | Met | Below |
| Gaps said out loud | Below | |

## Volume, 12 weeks

12,000 traces over 12 weeks, 1,200 of them redelivered.

| Where | Triage per trace | p95 | Drift night | Tidy night | Rules |
|---|---|---|---|---|---|
| Memory | 0.05 ms | 0.04 ms | under 0.1 s | 0.5 s | Hold |
| Postgres, Valkey, S3 | 4.05 ms | 5.29 ms | under 0.1 s | 49.8 s (10,000 frozen, the night's cap) | Hold |

The night raised exactly one skill drift, one policy drift and one security flag (18 rogue traces, all kept as evidence), plus one skill draft. Triage stays far inside its 50 ms budget. The default 2-week run still holds as well.

## Walked in the browser

| State | What a first-time viewer sees |
|---|---|
| Live map, light, dark, black | 111 traces this week, 8 patterns, 2 drifting, 21 waiting. Every label is visible. |
| Area card and drift | Plain names. Skill and policy fixes are both waiting for an L1 user, and each links to its change request. |
| New ways | 1 of 21, one card at a time. Seeded work is named by its steps ("Page read to copy changed"). |
| Phone (390 px) | No sideways scroll. The To review tabs scroll within themselves. |
| Unknown trace | "Trace not found", with a way back to all traces (it used to say "Not connected yet") |
| Backend down | "Not connected: the brain behind this workspace did not answer", with Retry and Open demo |
| Sample data | The Sample badge, and buttons that say they work on a live workspace |

## Found and fixed during stage 8

- **Unknown trace:** an unknown trace said "Not connected yet". It now says "Trace not found" whenever the memory itself answers.
- **Phone tabs:** the four To review tabs pushed the page sideways on a phone.
- **Seeded subjects:** seeded work, which has no run record, was titled by its input id.
- **Volume read-back rule:** the rule sampled frozen traces by index, which was wrong once the count passed the night's cap. It now checks that every sampled trace reads back, warm or cold.
- **"Suggested" wording:** it now shows only when Studio could not open the fix (sent to L1 with no change request), not for every drift without one.

## Tests

The full backend suite: 1,137 passed. Frontend memory unit tests: 18 passed. The e2e memory walk, now with New ways: 3 passed. The six product flows: passed.

## Gaps

| # | Gap | When |
|---|---|---|
| 1 | Drafts and fixes are written by rule, not by Claude. Skill drafts are not induced or scored with alignment fitness. | A Claude drafting pass, under the model credit rule; induction is the Skills paper's main work |
| 2 | A path change of one step is absorbed by near-match triage, so it can't show as skill drift | A product decision: count near matches toward drift |
| 3 | HQ's 12 weeks of memory history are generated by `seed_memory.py`. Only 19 traces are real work. | Say so in every demo. Real history grows from here. |
| 4 | The HQ skill fix opened before stage 8 still lists raw step keys. It waits for review, so its text was not changed underneath the reviewer. | It closes when L1 decides |
| 5 | The 03:00 night under `fastapi dev`: a reload can leave the old worker holding the port without answering (stage 7) | Restart the dev server cleanly before demos |
| 6 | Two app-wide accessibility failures predate the memory: the accent colour is 4.41:1 on white (AA needs 4.5:1), and the command palette's top answer for "approvals" no longer opens Approvals. 41 of the a11y tests fail on this branch. Two of them (a contrast case and the palette) were rerun on the code before stage 8 and fail there too. | A separate fix: a slightly darker accent, and the palette test |
| 7 | There's no Stripe connector. Hand refunds reach the memory only through the shop's table (stage 5). | When a Stripe connector is built |

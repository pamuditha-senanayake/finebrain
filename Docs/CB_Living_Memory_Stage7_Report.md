# Living memory, stage 7 report: the page on live data

Date: 2026-10-30. Branch: `living-memory`. Plan: `CB_Living_Memory_Build_Plan.md`, stage 7. Design: `CB_Living_Memory_Screens.md`.

## What stage 7 built

| Part | What it does | Where |
|---|---|---|
| Memory routes | Every memory path the page reads (map, area, traces, one trace, drafts) is served from the live stores, in the page's own shapes | `api/memory_views.py`, `api/routes.py` |
| Contract copies | Pydantic copies of the page's zod contracts. A fixture recorded from the backend is parsed by the zod contracts themselves, so the two can't drift apart unseen. | `api/ui_models_memory.py`, `scripts/memory_contract_fixture.py`, `tests/unit/memory-live.test.ts` |
| Not connected | A workspace without the memory stores gets 501, and an unknown trace or area gets 404. The page says so plainly, with Retry and Open demo. | `api/routes.py`, `features/l1/memory/memory.tsx` |
| Keep a surprise | A steward or leader marks a surprise as a normal way of working, and it becomes a pattern. Anyone else sees why they can't. | `api/memory_fixes.py`, `memory-actions.tsx` |
| Send a draft | A skill drafted from traces is sent for review. You choose its workflow first, and it opens a Studio change request at L1 level. The draft follows the decision. | `api/memory_fixes.py`, `memory-actions.tsx`, `features/l2/skills-from-traces.tsx` |
| Missed messages | A drift whose message never reached the fixer is sent on at night | `api/memory_fixes.py` (`sync`) |
| Access detail | Each access check on a trace carries its rule, reason and time | `contracts_memory.py`, `stages_memory.py` |
| Seed history | 12 weeks of realistic work: steady areas, a refund skill moving to a new path, late hand refunds spiking, and two new ways of working left for a person to review | `scripts/seed_memory.py` |

## Checked in the browser on live data

The production build was run against the Finebase HQ backend as an L1 user (persona `h-pamuditha`), in light and dark.

| Screen | Result |
|---|---|
| Map | 19 traces this week, all in Customers, and 19 waiting. No failing requests. |
| Area card | Traces, patterns of 50, skills, and the three drift lines all show "No drift" |
| Traces, waiting | 19 rows. Each opens its trace. |
| One trace | The six steps, the surprise badge, and an enabled "Keep as a normal way of working" button |
| From traces | Says plainly that no skills have been found yet, and why (a pattern needs 20 traces) |

Fixed during the check: steps showed "0 ms" when no time was measured, and access lines ended with a stray dot. Both are now left out when empty.

## Seeded Finebase HQ, then ran its night

`seed_memory.py --hq` kept 1,082 traces over 12 weeks. The night was then run with Claude off (plain summaries, no model credit).

| What | Result |
|---|---|
| Map | 111 traces this week, 8 patterns, 2 drifts (1 skill, 1 policy), 21 waiting |
| Skill drift | Its fix opened as change request `cr_53f03a819063`, now waiting for an L1 user |
| Policy drift | Studio refused the drafted window, so the drift was sent to the L1 leaders to decide (see below) |
| From traces | 3 drafts, each with Send to an L1 user for review |
| The night | 693 traces older than 30 days were frozen to S3, as designed |

Found and fixed on live data:

- **A refused fix stopped the whole night.** When Studio refused a drafted change (here, the window it drafted was already in force), the error escaped. That failed the night and every drift after it. A refused fix now goes to the L1 leaders without a draft, and the night goes on (`memory_fixes.open_fix`, tested).
- **The audit chain forked under two threads.** The API's request thread and its background loop write the audit through one Postgres connection, and the advisory lock doesn't block a second thread on the same connection. Both took the same number, and the night failed on its audit line. A thread lock now makes them take turns (`audit.PostgresAudit`). The new test fails without it and passes with it.
- **The seed used the seed file's policy, not the graph.** Live HQ has refund policy v6 (a 45-day window). The script judged its traces against v3 (30 days), so it made a policy drift toward a window already in force. The script now reads the version in force on each trace's day from the graph.
- **HQ cleaned and seeded again (2026-10-31).** The 1,082 seeded traces (389 in Postgres, 693 frozen in S3), their 8 patterns, their match and review records, the false policy drift and its notice were removed. The skill drift and its change request were kept: the seed's skill traces are the same either way. Seeded again, every refund is held to v6 (45 days). The night opened the policy fix as change request `cr_73b6768cc0dc` (up to 60 days), and both fixes now wait for an L1 user.
- **The card said "Draft fix" for a drift with no change request.** It now says "Suggested", and that an L1 user decides.

## The real-use bar (CLAUDE.md)

| Rule | Status | Evidence |
|---|---|---|
| Every visit tested | Met | Keeping a surprise a second time, or sending a draft a second time, is refused with "already answered" (409). A kept surprise leaves the waiting list. |
| Real infra | Met | The routes read the Postgres stores. The live check ran against Postgres, Valkey and Redpanda. |
| Many workers | Partly | Drift fixes keep stage 6's unique open-flag index. Two people pressing Keep or Send at the same moment aren't tested yet (gap 6). |
| Failures designed | Met | Missing stores → 501 and Not connected. Unknown id → 404. No right to act → the button says why. Missed message → night catch-up. |
| No scans | Met | Lists are cursor pages by area and flag, and every detail is read by id |
| One source of truth | Met | The page reads the live stores. Fixes and drafts go through Studio. |
| Volume | From stage 6 | The routes add no hot-path work to triage |
| Gaps said out loud | Below | |

## Gaps

| # | Gap | When |
|---|---|---|
| 1 | When the API runs as `fastapi dev`, a reload can leave the old worker holding `127.0.0.1:8000` without answering. That hid a second server and made the night look hung. The dev reloader only; not seen under `fastapi run`. | Watch; restart the dev server cleanly before demos |
| 2 | A path change of one step is absorbed by near-match triage, so it can't show as skill drift. Only bigger changes do. | A product decision: count near matches toward drift |
| 3 | Surprises show on the trace page and the Waiting link, but not yet in To review | Stage 8 |
| 4 | Drafts and fixes are written by rule, not by Claude | A Claude drafting pass, under the model credit rule |
| 5 | Some reasons on a trace are raw rule ids (for example `capability_and_tier`) | Plain names in stage 8 |
| 6 | Keep and Send check "already answered" before acting, but don't take a claim, so two presses at the same moment aren't proven to give one result | Stage 8 |
| 7 | Drift cards show the subject's id (`policy_refund`), and the skill fix lists raw step keys | Plain names in stage 8 |
| 8 | `test_s5_real.py` (stage 5 refunds) failed once in a full run while the live HQ backend shared the infra, then passed on its own | Watch in later full runs |

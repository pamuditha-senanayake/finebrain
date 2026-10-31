# Living memory, stage 5 report: the memory on real infrastructure

Date: 2026-10-30. Branch: `living-memory`. Plan: `CB_Living_Memory_Build_Plan.md`, stage 5. Design: `CB_Living_Memory_Architecture.md`.

## What stage 5 built

| Step | What it does | Commit |
|---|---|---|
| 5a | Trace and pattern stores in Postgres, each with an in-memory twin, plus the per-company area registry | `1768ac3` |
| 5b | The memory follows the pipeline on the bus: access decisions kept by run, a finished run becomes a trace (K16), each trace is claimed and triaged (K17), and a surprise waits in To review | `641cf8f` |
| 5c | Refunds people make by hand, read from the shop's own refunds table, become outside traces checked against the policy in force that day | `704a661` |
| 5d | The night, as a step of the 03:00 Distiller: old traces to S3, alike patterns merged, idle patterns removed, and reports for a person | `049479d` |
| 5e | Volume run, outage tests, this report | this commit |

## The real-use bar (CLAUDE.md)

| Rule | Status | Evidence |
|---|---|---|
| Every visit tested | Met | A run that pauses for approval or the customer becomes a trace only when it ends (`test_memory_flow.py`). Redeliveries, late access decisions and a second poll each change nothing. |
| Real infra | Met for Postgres, Valkey, Redpanda, S3 and OPA | `test_memory_real.py` runs Anna's refund through all of them and reads K16 and K17 back from Redpanda. The store and tidy tests also run on Postgres and S3. |
| Many workers | Met | Two workers triaging one trace give one match and one review item, on Postgres plus Valkey. They never both add the 50th pattern (a per-area lock), never count one trace twice, and never both tidy one night or poll one shop. |
| Failures designed | Met | See the outage table below. |
| No scans | Met on the hot path | Triage reads one area's patterns by key. Traces page by keyset cursor. The night reads the oldest traces through an index. See gap 4 for the shop's refunds table. |
| One source of truth | Met | Areas are S2's domain list. Policy checks read the graph. Outside work reads the shop's own table. |
| Volume | Met | `scripts/memory_volume.py`, results below |
| Gaps said out loud | Below | |

## Volume

`uv run python scripts/memory_volume.py 5000 [--real]`. Each run sends 5,000 realistic traces across the eight areas: steady patterns, a step more in 15%, surprises in 1%, refunds by hand in 5%. A person confirms each new way of working, and 500 traces are redelivered. Then the night moves everything to cold.

| Where | Triage per trace | p95 | Budget | The night (5,000 traces to cold) | Rules |
|---|---|---|---|---|---|
| Memory | 0.03 ms | 0.02 ms | 50 ms | 0.1 s | Hold |
| Postgres, Valkey, S3 | 2.46 ms | 3.81 ms | 50 ms | 16.4 s | Hold |

The rules checked after each run:
- Every trace has exactly one match.
- Pattern counts equal the normal matches, so nothing is counted twice.
- No area is over its budget.
- Each surprise was raised for review exactly once.
- Every frozen trace reads back from S3.

## Outages

| Outage | Outcome | Test |
|---|---|---|
| Trace store down while keeping a trace | Refused, kept as a dead letter. A replay keeps it and triages it once. | `test_memory_outage.py` |
| Valkey down while claiming a trace | Nothing matched while down. A replay finishes it, with one review item. | `test_memory_outage.py` |
| Records store down after triage counted | A dead letter. The replay triages again, and the trace still counts once. | `test_memory_outage.py` |
| Another worker holds the trace | Retryable error: replayed after the claim times out (60 s), never skipped | `test_memory_flow.py` |
| A broken message | A dead letter with the whole original, for replay after a fix | `test_memory_flow.py` |
| Shop database down, or the shop can't even be found | Counted and logged, and the next pass tries again. The polling loop for customer messages keeps running. | `test_memory_outage.py` |
| Crash before the shop cursor moves | The next poll re-reads and keeps nothing twice | `test_memory_outside.py` |
| S3 down at night | Nothing leaves Postgres without its copy in S3. The night fails loudly and runs again the next night. | `test_memory_outage.py` |

## Found and fixed during stage 5

- **Paused runs:** a run that paused published its record twice, and the trace froze at the unfinished state. Traces are now built only when a run ends.
- **Counter calls:** the wrong signature sent every trace to the dead-letter topic.
- **Forgetting:** traces keep "why" lines that can quote a document, so erasing a document now scrubs them (a new forgetting layer).
- **Merges:** merging two patterns could count a trace twice if both held it. Merges now recount from the cases themselves.
- **Polling:** if the records store was down, the refund poll could raise into the shared polling loop. It now never raises.
- **Volume script:** clearing a Valkey key set scans every key once per member, which made the first real run take over 15 minutes. The script now discards only the keys it needs. Product code never clears a Valkey set.

## Gaps

| # | Gap | When |
|---|---|---|
| 1 | A trace's "policies in force" is empty for runs, because the run record doesn't carry the policy versions. Outside traces do carry them. | Stage 6 reads them from the graph |
| 2 | Temporal isn't part of the memory tests. The night runs inside the Distiller, whose Temporal schedule already has its own tests. | Covered by the Distiller's tests; no new work planned |
| 3 | Surprises are kept as records (`memory_review`), but To review doesn't show them yet, and confirming one is a function call, not a button | Stage 7 (routes and screens) |
| 4 | The shop's refunds table has no index on refund time, so each 5-minute poll reads it in time order with a limit of 200. Fine off the hot path, but a very large shop needs the index. | Flag it in the connection test |
| 5 | There's no Stripe connector. Refunds made in Stripe reach the memory only when they also land in the shop's table. | When a Stripe connector is built |
| 6 | Policy drafts, L1 approval, drift states and the 14-day re-check are designed and in the contracts, but the checks that raise them on real data are stage 6 | Stage 6 |
| 7 | The page still shows sample data | Stage 7 |

# Living memory, stage 6 report: drift and fixes on real data

Date: 2026-10-30. Branch: `living-memory`. Plan: `CB_Living_Memory_Build_Plan.md`, stage 6. Design: `CB_Living_Memory_Architecture.md`, sections 7, 8 and 8b.

## What stage 6 built

| Part | What it does | Where |
|---|---|---|
| Policies in force | A run's trace names the policies it was held to, each at the version valid when the work started. Those are the policies its workflow names, or, when it names none, the one S7 checks for the proposed action. This closes stage 5's gap 1. | `stages_memory_flow.py`, `stages_memory.py` |
| Drift store | One open flag per subject and kind (two workers raising at once still make one), its state and the history of how it got there. Read by id, area, state and change request. | `store_drift.py` |
| Security drift | Raised the moment triage sees a finished action whose access said deny, and again on a late deny. Zero tolerance and no draft: it goes to the L1 leaders as an incident. | `stages_memory_drift.py`, `api/memory_fixes.py` |
| Skill drift (nightly) | A skill whose usual path falls 10 points below its usual share. The draft fix is the path people now take. Read from the pattern counts. | `stages_memory_drift.py` |
| Policy drift (nightly) | Outside-policy work spikes, on the same bar as the Trends tab. For the refund window, the draft is a new window covering 90% of the late work, rounded up to 5 days. | `stages_memory_drift.py` |
| Skill drafts (K19) | A pattern no skill covers, with at least 20 traces and 90% ending the same way, becomes one draft, published on `skills.drafted` | `stages_memory_drift.py` |
| Fixes for an L1 user | A skill or policy drift opens a Studio change request at C3 or higher, so an L1 user approves it. A drift that can't be drafted on its own is still sent to L1 to decide. | `api/memory_fixes.py` |
| Drift states | detected → sent to L1 → waiting (the approval is out) → approved (merged) → resolved. A rejection, a request for changes or a merge conflict sends it back to detected, with the reason. | `api/memory_fixes.py` |
| 14-day re-check | During the 14 days, a returning drift is noted on the flag. The night reopens it with a note, or resolves it after 14 quiet days. | `stages_memory_drift.py` |
| The night | The Distiller's 03:00 night now also runs the drift checks, the re-checks, and a catch-up on decisions whose message arrived before Studio applied them | `api/distiller.py` |

## The real-use bar (CLAUDE.md)

| Rule | Status | Evidence |
|---|---|---|
| Every visit tested | Met | A drift raised again joins the open flag. A redelivered flag or approval message changes nothing. A drift that comes back during its re-check is reopened. A rejected fix can be raised again. |
| Real infra | Met | `test_memory_real.py`: a security drift is kept in Postgres and read back from Redpanda (K18). The drift store tests run on Postgres. The fix tests use the real Studio, S8 approvals and S14 merge. |
| Many workers | Met | Two workers raising one drift at once make one flag (a unique index on open flags). Two workers triaging one trace give one result. |
| Failures designed | Met | See the outage table below |
| No scans | Met | Drift reads pattern counts by pattern id. Flags are read by id, state, area and change request. |
| One source of truth | Met | Policies come from the graph, fixes go through Studio, and approvers follow S8's rules |
| Volume | Met | `scripts/memory_volume.py`, results below |
| Gaps said out loud | Below | |

## Volume

5,000 traces, with 500 redelivered. 0.2% of them show a rogue agent finishing work its access check denied.

| Where | Triage per trace | p95 | Drift night | Tidy night | Rules |
|---|---|---|---|---|---|
| Memory | 0.09 ms | 0.10 ms | under 0.1 s | 0.3 s | Hold |
| Postgres, Valkey, S3 | 5.45 ms | 10.62 ms | under 0.1 s | 35.7 s | Hold |

Exactly one security flag was raised for the rogue agent, carrying its 5 finished traces as evidence, and no subject has two open flags. The 50 ms triage budget holds. On the same machine, stage 5 measured 2.46 ms. The difference is the security check, plus normal run-to-run variation.

## Outages

| Outage | Outcome | Test |
|---|---|---|
| Drift store down at triage | Nothing is kept as done. A replay raises the drift once. | `test_memory_outage.py` |
| A decision's message arrives before Studio has applied it | The night catches up from the change request's own status | `test_memory_fixes.py` |
| The "waiting" message is lost | The night's catch-up still moves the drift on | `test_memory_fixes.py` |
| A fix can't be drafted on its own | Sent to L1 to decide, never dropped | `test_memory_fixes.py` |
| The same drift raised twice, by two workers or two nights | One flag, more evidence | `test_memory_drift.py` |

## Found and fixed during stage 6

- **Lost security drift:** a security drift could be lost if raising it failed after triage had saved its match, because a replay saw the match and stopped. The check now runs before the match is saved.
- **Late deny on replay:** a late access decision now re-checks security every time, not only on its first attach, so a replay can't skip it.
- **Workflows without policies:** a workflow that names no policies used to leave a run's trace empty. It now falls back to the policy S7 checks for the action.
- **Volume script rule:** it counted escalated rogue work as drift. Escalating after a denied check is the right behaviour, so only finished work counts.

## Gaps

| # | Gap | When |
|---|---|---|
| 1 | Drafts are written by rule, not by Claude. A skill fix adds the new path as one step's text, and a policy fix is only automatic for the refund window (other policies go to L1 without a draft). | A Claude drafting pass, under the model credit rule |
| 2 | K19 skill drafts are kept and published, but "Send for review" (opening a change request to create the skill) needs its button | Stage 7 |
| 3 | The volume run covers 2 weeks of traffic, so its night raises no skill or policy drift (each needs 3 weeks). Those two checks are proven by the unit tests on longer series. | A 12-week volume run |
| 4 | The page still shows sample data, and drift states aren't on screen from real data yet | Stage 7 |
| 5 | The full backend suite passed apart from one real-infra test (1,124 passed). That test was fixed and its file passed twice afterwards. One earlier run of the real tests also showed a `KeyError` once, which didn't come back in two later runs. | Watch in the next full run |

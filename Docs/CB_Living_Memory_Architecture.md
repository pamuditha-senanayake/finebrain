# Living memory architecture

Date: 2026-10-30. Status: **final, current.** This is the one memory design we build from now on.

It replaces `CB_Memory_Architecture.md` (whose knowledge part is folded in here, unchanged), `CB_Graph_and_Memory_Plan.md`, and section 7 of `Finebrain_Living_Memory_Thinking.md`. Build order: `CB_Living_Memory_Build_Plan.md`. Diagram: `CB_Reasoning_Layer_Fit.drawio`.

## In one line

Every piece of work leaves a trace. Each trace goes to one brain area and is compared only with that area's few typical patterns. Similar traces are counted and archived. Different ones go to a person. Changes in the patterns show drift, and steady patterns become skills.

## 1. Two kinds of memory, one set of areas

| Kind | What it holds | Status |
|---|---|---|
| Knowledge | Facts, documents, policies, summaries | Built (steps 13 to 15), unchanged |
| Work | Traces: how each action started, ran and ended | New |

Both use the same areas, so a question, a fact and a trace about refunds all live in Customers.

## 2. Brain areas

The areas are the fixed domain list that already tags every item at S2 (`item_tags.py`). We reuse it instead of making a second list, so there is one source of truth.

| Area | Key | Holds |
|---|---|---|
| Customers | `customer_care` | Questions, complaints, refunds, replies |
| Money | `finance` | Invoices, payments, tax, budgets, spending |
| Rules | `legal` | Contracts, terms, compliance |
| Staff | `people` | Hiring, payroll, leave, HR |
| Operations | `operations` | Processes, suppliers, logistics, tools |
| Sales | `sales` | Leads, deals, pricing |
| Product | `product` | Features, releases, product docs |
| Other | `general` | Anything that fits nowhere else |

- **Access is not an area.** It is checked in every area, on every trace (section 7).
- **Per company.** Setup turns areas on or off. A florist may never use Product.
- **The list never grows.** When a pattern in Other keeps growing, a person moves it into an area. The axis stays fixed, so searching never spreads out.

## 3. The trace

One trace per piece of work, from start to end. It is built at S10 from the run record (K10), the access decisions (K6) and the context bundle (K4). Work done outside Finebrain, such as a refund made in Stripe, arrives through its connector and becomes a trace too.

| Field | Meaning |
|---|---|
| `trace_id`, `tenant_id` | Which trace, which company |
| `area` | One area from section 2 |
| `source` | `finebrain` (a run) or `outside` (a connector event, such as Stripe) |
| `started_at`, `ended_at` | When it began and ended |
| `input_ref` | The signal that started it |
| `steps` | Activity ids in order, from the skill's alphabet (`activities.py`) |
| `policies` | Each policy version read, with its valid time |
| `skill` | The skill version followed, if any |
| `access` | Every access decision: action, tier, capabilities, on behalf of, allow or deny |
| `outcome` | How it ended, and who decided |
| `why` | One short line per judgment step. Today this is the step's `reason` |
| `policy_check` | `within`, `outside` or `unknown`, against the policy valid on that date |
| `pattern_id`, `match` | The pattern it joined, and `normal` or `surprise` |

## 4. Patterns

A pattern is one typical way work goes in an area. For example: "refund within the window, approved automatically, customer told".

- **Key:** area + skill + step sequence + outcome + policy check. Traces with the same key are the same pattern.
- **Budget:** at most 50 patterns per area, starting near 20. A fixed number, never a percentage.
- **Counts:** each pattern counts its traces per week. Drift reads these counts.
- **Example traces:** each pattern keeps 5 recent traces, so a person can see what it looks like.

## 5. Triage: normal or surprise

Triage runs after S10 on every trace. It makes no Claude call.

1. **Exact match.** Look up the pattern key in that area. A hit means normal.
2. **Near match.** If there is no exact hit, compare the step sequence with the area's patterns (edit distance) and the input with each pattern's centre (embedding). Close enough means normal.
3. **Normal.** Add one to the pattern's week count. The trace stays warm for 30 days, then goes cold.
4. **Surprise.** The trace goes to To review, ordered by surprise, then urgency, then risk. The person's answer either joins it to a pattern or starts a new one.

Triage reads one area's patterns by key and never lists every trace, so its cost stays flat as traces grow.

## 6. Tiers

| Tier | Knowledge | Work | Store |
|---|---|---|---|
| Hot | Best open items, searched first | Patterns and their counts | Postgres, cached in Valkey |
| Warm | Entities, current facts, summaries | Traces from the last 30 days | Postgres, by area |
| Cold | Closed facts, old detail | Older traces, compressed | S3 |
| Raw | Originals, 90 days | Original connector events, 90 days | S3, never searched |

Every tier has a fixed budget. The nightly tidy keeps each one inside it.

## 7. Drift: three kinds

| Kind | Question | Signal | Raised when | Reuses |
|---|---|---|---|---|
| Skill drift | Do people still follow this skill? | Weekly share of an area's traces that follow the skill's steps | It drops 10 points or more below its 12-week median | Weekly counts (`stages_learn.py`) |
| Policy drift | Is this rule still how we work? | Pattern shares over time, plus the rate of work outside policy | The drift signal fires, or outside-policy work spikes (3 times the usual week, at least 5) | `drift_signal.py`, `stages_spike.py` |
| Security drift | Did every action have the right access? | Each trace's actions against its access decisions | Any action with no allow decision, the wrong tier, or the wrong on-behalf-of person. Zero tolerance | K6 decisions, OPA |

Every flag goes to To review with the traces as evidence. Nothing changes by itself: section 8b says how a drift becomes an approved fix.

## 8b. From drift to a fix (added 2026-10-30)

**An L1 user approves every fix**, for skills and policies alike. The area or workflow owner can prepare and comment on it, but the decision is L1's. Nobody approves their own change, as everywhere else.

What each kind of drift drafts:

| Drift | Draft | Example |
|---|---|---|
| Skill drift | A skill change that matches how people now work | Add "check annual plan" before the refund step |
| Policy drift | A policy change: the new value, with a valid-from date | Refund window: 30 to 45 days, from 1 December |
| Security drift | No draft. It goes straight to an L1 user as an incident, because access must never drift | An action ran without an allow decision |

**Every drift shows where it stands**, as a numbered step line on its card:

| # | State | Meaning |
|---|---|---|
| 1 | Detected | The nightly check raised it, with the traces as evidence |
| 2 | Sent to L1 | The draft fix is written and sent to an L1 user |
| 3 | Waiting for approval | An L1 user has it in To review |
| 4 | Approved | The change is live (a new skill version, or a closed and a new policy version) |
| 5 | Resolved | The re-check confirmed the drift dropped |

If an L1 user rejects the fix, the drift goes back to Detected with their reason. A rejected fix is never sent again unchanged.

**Re-check after approval.** For 14 days after the change goes live, the nightly check watches the same signal:

- If it falls back inside its bar (the skill is followed again, or outside-policy work returns to its usual week), the drift becomes **Resolved**.
- If it does not, the drift is **reopened** and goes back to Detected, with a note that the approved fix did not work.
- Security drift resolves only after 14 days with zero actions without an allow decision.

## 8. Skills from traces

This is Skillify grown up. Today Skillify drafts a fix for one run someone marked wrong. Now it also drafts new skills from patterns.

1. **Pick.** A pattern with at least 20 traces, where 90% or more end the same way, and that no skill covers or that differs from its skill.
2. **Draft.** Turn the pattern's step sequence into skill steps. This makes no Claude call. An optional Claude pass then gives the steps plain names.
3. **Check.** Score the draft against held-out traces of the same area (fitness). The research paper does this with pm4py outside the app. The product uses its own simple follow rate.
4. **Propose.** The draft opens as a change request drafted by Skillify (K13). An L1 user approves it (section 8b). Nothing goes live before that.

The Skills page gets a "From traces" tab that lists these drafts with their support counts.

## 9. Nightly tidy (S13)

The existing Distiller keeps its jobs: value scores, summaries, merging duplicates and raw expiry. It also gains new ones:

- merge near-identical patterns
- move patterns unused for 90 days to cold
- keep every area inside its budget
- run the three drift checks
- re-check drift whose fix went live in the last 14 days, then resolve or reopen it
- pick candidates for skill extraction
- report patterns growing in Other

## 10. Answering a question

This is unchanged: route to the area and entities, run a scoped search with hot items first and at most 2 hops, then fit the result into about 6k tokens. "Have we seen this before?" now also reads the area's patterns, which is one small lookup.

## 11. New contracts

| Contract | From → to | Carries | Transport |
|---|---|---|---|
| K16 TraceRecord | S10 → trace store | The trace in section 3 | Kafka `traces.recorded` |
| K17 AreaMatch | Triage → pattern store, To review | Area, pattern, similarity, normal or surprise | Kafka `traces.matched` |
| K18 DriftFlag | S13 → S8 To review | Kind, area, subject (skill, policy or agent), evidence trace ids, state (section 8b), draft fix, re-check result | Kafka `drift.flags` |
| K19 SkillDraft | S13 → S14 via Studio | Pattern, draft steps, support, follow rate | Becomes a K13 change request |

Each key starts with the tenant, as with every topic today.

## 12. Built and new

| Piece | Status |
|---|---|
| Areas (domain tags at S2) | Built |
| Knowledge tiers, value scores, summaries, commons, version chains | Built |
| Run record with steps, activity ids and reasons, trace in S3 | Built |
| Access decisions with tier, capabilities and latency | Built |
| Weekly counts, spike check, drift signal | Built |
| Skillify fix for one wrong run | Built |
| Trace record (K16) joining run, access and policy versions | New |
| Outside-work traces and the policy check | New |
| Patterns, triage (K17) and work tiers | New |
| Three drift kinds (K18) | New. The signals are built, the per-area checks are new |
| Skill drafts from patterns (K19) | New |
| Policy drafts from drift, L1 approval, drift states, re-check (section 8b) | New |
| Living memory page, Traces, the "From traces" tab | New |

## 13. Starting numbers

| Setting | Start at |
|---|---|
| Areas | 8, fixed |
| Patterns per area | 20 to start, 50 at most |
| Example traces per pattern | 5 |
| Warm traces | 30 days |
| Raw originals | 90 days |
| Triage time per trace | Under 50 ms, no Claude call |
| Skill draft support | At least 20 traces, 90% same outcome |
| Skill drift bar | 10 points below the 12-week median |
| Security drift bar | 0 |
| Re-check window after a fix | 14 days |
| Context per question | About 6k tokens |

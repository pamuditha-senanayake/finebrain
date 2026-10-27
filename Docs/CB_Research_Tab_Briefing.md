# Finebrain: briefing for the Research tab

27 October 2026. Written from the code on `main` (commit `a7bc601`).

This file tells the research chat what Finebrain is, what is built, what data exists, and what the Research tab looks like today. At the end are the questions we need answered so we can build the Research tab.

## 1. What Finebrain is

Finebrain (the "Company Brain") is a governed layer where AI agents run company operations under policies and security that people control.

| Idea | Meaning |
|---|---|
| Signals in, governed actions out | A message (chat, email, upload) becomes a task, an agent reasons, governance checks it, then a tool acts once |
| Nothing acts before governance | Every proposed action passes S7 Govern before S9 Act may call a tool |
| Approval weight follows risk | Criticality C0 to C4 decides who approves |
| Nothing is overwritten | Graph changes are commits. Facts close their valid time instead of being updated |
| Answers cite what is stored | Agents and Ask the Brain may only cite items they were given |

Test company: **Finebase HQ** (real backend, LKR, Asia/Colombo). The live scenario is a refund request in the website chat on finebaselabs.com. Two demo tenants (Finebase Labs demo, Scale Demo) run on mock data in the browser.

## 2. The console: four areas in the side panel

| Area | Who | Screens |
|---|---|---|
| L1 Command | Founder, directors, DRIs (owners) | Overview, Ask the Brain, To review (approvals, evidence), Use in Claude, Workflow Studio, Entity protection, Analytics, Trends, Audit, Setup |
| L2 Governance | Stewards, supervisor agents | Vault, Security, Knowledge graph (with Versions), Library, Policies, Skills, Resolver, Templates, Connections, Loops, Readiness, Workflow Studio |
| L3 Operations | Operators, worker agents | Conversations, Escalations, Fleet, Runs, Template board |
| Research | Research analyst, founder | Research Console (one page today, see section 9) |

Higher tiers can look down, never up. L1 sees L2 and L3. L2 sees L3. Research is seen by the research persona and the founder.

## 3. Tech stack

| Layer | Tech |
|---|---|
| Frontend | Next.js 16 App Router, React 19, TypeScript, Tailwind v4, shadcn/ui, TanStack Query and Table, zod contracts, Recharts, Sigma.js graph, React Flow |
| API | FastAPI (Python, uv), SSE live stream |
| Event bus | Kafka (Redpanda locally), one DLQ per consumer |
| Data | Postgres 17 + pgvector, Valkey, S3 (SeaweedFS locally), Temporal |
| Access | OPA (Rego), mirrored in Python |
| Models | Claude Sonnet 5.5 (reasoning), Haiku (routing tie breaks, grader, filing, extraction, summaries), Opus 5.5 (conflict resolution, nightly grouping), Voyage (embeddings, rerank), ElevenLabs (voice) |

Size today: 164 backend Python files, 91 backend test files, about 200 frontend source files.

## 4. The pipeline: 15 stages in 4 lanes

| Lane | Turns | Stages | Status |
|---|---|---|---|
| A | A signal into a governed action | S1 to S10 | Built, S1 to S10 at "ready for real use" |
| B | A document into verified facts | S11 Ingest, S12 Librarian, S14 Version | Built |
| C | Finished runs into better skills and policies | S13 Learn, S14, approvals in S8 | Built (no evals or replay yet) |
| D | Deadlines into early evidence requests | S15 Readiness | Built |

| Stage | Job |
|---|---|
| S1 Capture | Verify and store the raw message once |
| S2 Normalize | Mask personal data (vault), dedup, tag entities, flag prompt injection |
| S3 Route | Match a rule to an activity, read its owner agent and pinned skill version |
| S4 Orchestrate | Start a run, or join a later chat message to the open run |
| S5 Retrieve | Access-filtered, bitemporal, scoped hybrid search |
| S6 Reason | Claude plans and proposes an action with citations |
| S7 Govern | Access (OPA), policy rules, quality gates, criticality, route |
| S8 Decide | Approvals, delegation, expiry, takeover, waiting for the customer |
| S9 Act | Call the outside tool once (idempotency key) |
| S10 Record | Run record, trace, hash-chained audit, live UI |
| S11 Ingest | File, parse, chunk, embed, extract fact candidates |
| S12 Librarian | Compare candidates with ground truth: verify, duplicate, out of date, conflict |
| S13 Learn | Weekly counts, spike check, Mark as wrong, Skillify, nightly review |
| S14 Version | Git for the graph: commit, change request, merge, release |
| S15 Readiness | Obligations, gaps, evidence requests, reminders |

Contracts between stages are K1 to K15 (Pydantic in backend, zod in frontend). Every message in a run shares one `correlation_id`.

## 5. Research area 1: temporal validity (validate and invalidate)

This is the most complete part. Time is stored two ways everywhere it matters.

| Concept | How it is built |
|---|---|
| Two times | Valid time (`valid_from`, `valid_to`: when it was true) and record time (`recorded_at`: when we stored it) |
| As of search | S5 takes `as_of_valid` and `as_of_recorded`; filter is `valid_from <= t < valid_to` and `recorded_at <= r` |
| Graph versions | `graph_nodes` is append only: `(tenant, branch, node_type, node_id, version)`, `commit_id`, `recorded_at`. A newer version supersedes; a `_closed` version ends a node; `history()` and `at_version()` still show the past |
| Skill pinning | S3 pins the skill version at routing, so a change mid run cannot affect it |
| Policy versions | Each policy has versions; an old one gets `valid_to` and `supersededBy`. The Policies screen has an "as of" slider |
| Fact lifecycle | Fact status: `verified`, `unverified`, `stale`, `conflicted`, `superseded` |
| Validate (Lane B) | Claude Haiku extracts a fact only when its quote is found word for word. The librarian makes a review item; a steward accepts (C2) and S14 writes a verified fact node |
| Invalidate (conflict) | When two sources disagree, Claude Opus proposes which wins and from when (newer source wins with no model). A C3 change request; the L1 approval closes the old fact exactly where the new one starts, so "as of" still finds the old one. Real example on HQ: refund window 30 days replaced by 45 days |
| Re-check before acting | Before S9 acts on an approval, a newer released policy makes S7 run again |
| Forgetting | Retire (valid time ends, as of search still finds it) or Erase (gone from every layer, a tombstone keeps who, when, why). Retire is C3, erase is C4 |
| Cold history | Closed facts older than 30 days move to cold (S3); only a question about the past reads cold |
| Readiness from facts | An obligation item is proven only by a verified fact true now and about that period; retiring the proof reopens the gap |

| Gap (not built yet) | Note |
|---|---|
| Freshness signals on real data | The Policy contract has `driftPointAt`, `conformance`, `conflictingEvidence`, `outdatedRelianceRate`, but HQ fills them with fixed values (no drift detection yet) |
| Memory inspector and time slider over the graph | Proposed in `CB_Graph_and_Memory_Plan.md` |
| Re-checking open items after a conflict merges | Not built |
| Dependents beyond runs and Ask answers | Not built |
| Near-duplicates by meaning | Only identical passages merge |

## 6. Research area 2: skills

| Concept | How it is built |
|---|---|
| Activity at the center | A Workflow Studio workflow is an activity: one owner agent, one skill, its policies, the connections it listens to |
| Skill | Versioned graph node: steps (retrieval, judgment, tool, quality gate), allowed tools, policies, required capabilities, eval suite, DRI, origin (`authored`, `skillify`, `overnight`) |
| Tool limit | S6 may only call the skill's allowed tools, with strict schemas; bad calls get schema feedback twice, then escalate |
| Hard checks in code | A refund must name a payment S5 found for this customer, cite it, and not exceed what is left |
| Mark as wrong | Anyone can mark a run wrong once with a note; the DRI is told |
| Skillify | Claude Sonnet drafts one skill or policy change from a wrong run; Studio review checks it; it becomes a change request the DRI approves |
| Nightly review | 02:00 Colombo on Temporal: failures by type, wrong runs grouped by Claude Opus, one fix per group (C0 and C1 applied at once, the rest a change request), morning digest |
| Studio review | Every change gets a verdict (minimal, moderate, breaking), criticality with reasons, affected parts, other workflows hit, and a route (apply, approval, view only). Server side, never trusted from the browser |
| Skill health (UI contract) | `taskSuccess`, `consistencyPassK`, `k`, `conformance` |

| Gap | Note |
|---|---|
| Conformance (documented steps vs observed run steps) | HQ sets conformance equal to task success; no real step matching yet |
| pass^k consistency | HQ returns 0; no eval suites or repeated runs yet |
| Evals and replay | Not built (Lane C) |

## 7. Research area 3: policies and governance

| Concept | How it is built |
|---|---|
| Policy as data | Graph node with rule params (refund: window days, auto limit in minor units, currency, approver tier) plus its wording in knowledge, read by key |
| Policy check (S7) | Rules `refund.window`, `refund.auto_limit`, `refund.not_refunded_before`; the payment is read from the shop database at decision time |
| Quality gates | Citations, amount, confidence 0.6, Claude Haiku grader (fails closed). A failed gate goes back to S6 once, then escalates |
| Criticality | C0 auto and logged, C1 L2 supervisor agent, C2 L2 steward, C3 L1 DRI, C4 two different L1 leaders plus 24 h cooling |
| Bumps | Money, personal data, public content, legal or tax, more than one cluster: +1 each. Waived when the policy explicitly allows the action within its limits (`policy_auto_approval`). Prompt injection flag means at least C2 |
| Approvals (S8) | Drafter never approves; expiry goes to the delegate once then escalates, never auto approves; edits never pay more |
| Change control | Studio and Skillify changes are K13 commits; L1's own change applies at once (logged), L2's waits for an L1 |
| Policy versions screen | Statement, rule, validFrom, validTo, recordedAt, supersededBy, evidence, dependents (skills governed) |

## 8. Research area 4: security

| Concept | How it is built |
|---|---|
| Access decision (K6) | OPA Rego: `missing_capability`, then `sensitivity_by_tier`, then `on_behalf_of`, else allow. First failing check names the reason |
| Sensitivity | public, internal, confidential, restricted. L3 cannot read restricted |
| On behalf of | An agent acting for a person sees only what that person may see |
| Fail closed | OPA unreachable means deny (`opa_unreachable`) |
| Retrieval filter | S5 counts withheld items (`denied_count`) and logs every read decision on `access.decisions` |
| Personal data | Masked at S2 (emails, phones, NIC, cards with Luhn, addresses, names); real values in an encrypted vault (pgcrypto) |
| Prompt injection | `possible_prompt_injection` flag; customer text and documents quoted as data |
| Audit | Append-only, SHA-256 hash-chained `audit_log` with `verify_chain` |
| Least privilege tools | Shop database read through a read-only user; refunds through a refund-only user; one transaction, idempotency key |
| Data source grants | Asking for a grant is a C4 approval |
| Leak scan | Display text and step reasons scanned for personal data before the UI |

## 9. The Research tab today

Route `/research` and `/research/[paper]`. Files: `frontend/features/research/console.tsx` (135 lines), `import-adapter.ts`, contract `frontend/contracts/research.ts`.

| Property | Today |
|---|---|
| Purpose | "Monitoring only, read only, removable." Aggregates the same events the product records into research metrics for a four paper program |
| Removable | Flag `NEXT_PUBLIC_FLAG_RESEARCH=disabled` removes routes, nav and bundles at build time; lint forbids product code from importing it; e2e test `research-removal.spec.ts` |
| Tabs | Skills, Policies, Security, Integration |
| Layout | A grid of metric cards: big number, sparkline, definition, condition |
| Data | Mock only. Every value is SAMPLE. On Finebase HQ the backend answers an empty list |
| Import | Upload a JSON array of `ResearchSnapshot` from the research execution repository; imported values count as real |
| Export | CSV and JSON, blocked for sample values |

Contract today:

```ts
ResearchMetric   = { key, label, definition, value, unit: "ratio"|"percent"|"ms"|"count", condition, series: [{ x, y }] }
ResearchPaper    = "skills" | "policies" | "security" | "integration"
ResearchSnapshot = { paper, title, isSample, source, takenAt, metrics: ResearchMetric[] }
```

Sample metrics already defined:

| Paper | Metrics |
|---|---|
| Skills | Skill conformance to observed runs, documented vs observed gap, task success, consistency pass^k (k=8) |
| Policies | Policies with an active freshness signal, actions under expired policy, drift detection recall, drift detection delay, "as of now" returns current version |
| Security | Leakage rate (graph enforcement), leakage rate (retrieval-time filtering baseline), unauthorized invocations denied, enforcement latency p95 |
| Integration | Task completion (brain vs retrieval only baseline), pass^1, pass^8, stale answer rate |

Problems with the current page (against our design rules): it shows many cards at once, small text (10 to 11 px), no real data, no way to run or inspect an experiment, and nothing per case.

## 10. Data the backend already records (what research can read)

| Store | What is there | Useful for |
|---|---|---|
| `graph_nodes` | Every version of rules, skills, agents, policies, tools, workflows, facts, knowledge, with commit and record time | Temporal validity, policy versions, skill versions |
| `chunks` | Knowledge with `valid_from`, `valid_to`, `recorded_at`, domain, entity ids, tier, embedding | As of correctness, stale answers, retrieval |
| `records` (versioned by kind) | `run_started`, `run_turn`, `run_waiting`, `run_mark`, `conversation_*`, `ask_turn`, `fact_candidate`, `librarian_item`, `change_request`, `skillify`, `trend`, `digest`, `evidence_request`, `forget_request`, `payment_refunded`, `distiller_run`, `tier_run` | Run outcomes, human touch, wrong runs, learning loop |
| `audit_log` | Hash chained: approvals requested and decided, actions executed, runs completed, access decisions | Governance and security metrics, tamper evidence |
| `access.decisions` topic and log | Every allow and deny with rule id, reason, principal, on behalf of, latency | Leakage, denial rate, enforcement latency |
| Run traces in S3 | `traces/{run_id}.json`: every turn, bundle, proposed action, verdict, approval, result | Conformance, citations, step-level analysis |
| `item_uses` | Which run or answer cited which item | Outdated reliance, stale answer rate |
| `signal_counts`, `signal_count_cases` | Weekly counts per skill, agent, channel | Trends and drift onset |
| `entities`, `entity_links` | One entity per real thing, typed links | Scope and leakage analysis |

Tools to generate load: `scripts/seed_runs.py 10000`, `demos/send_to_hq.py`, volume scripts `scripts/s1_volume.py` to `s9_volume.py`, benchmarks `bench_retrieve.py`, `bench_tiers.py`, `chat_latency.py`.

## 11. Measured numbers so far

| What | Number |
|---|---|
| Chat pipeline S1 to S9 without models | about 0.1 s (0.2 s with Temporal), was 7.6 s |
| S6 reasoning turn | 2 to 3.5 s |
| S7 grounding check | about 1.8 s |
| Scoped meaning search | 3 to 5 ms p50 from 10,000 to 500,000 items |
| Scoped word search | 1.3 to 1.4 ms p50 |
| List of 10,000 runs | about 0.1 s per page |
| Spike check on HQ | 10 refund requests vs usual 3 (3.3x) raised a trend |

## 12. Design rules any Research screen must follow

| Rule | Meaning |
|---|---|
| Few words | Labels of 1 to 3 words; detail behind a click |
| One thing at a time | Rich items (cases, experiments, findings) as one card with Back and Next |
| Spacious | Body 15 px or more, nothing important below 12 px |
| Show what matters now | Hide empty or finished, collapse the rest |
| One accent colour | Only for "happening now" or the main action |
| Every state designed | Loading, empty with a way forward, error with a fix, success, disabled with a reason |
| Accessible | WCAG 2.2 AA, keyboard, labels, nothing by colour alone |
| Honest data | Sample values always marked and never exportable as results |
| Read only | The Research tab must never change the product |

## 13. What we need from the research chat

Please answer these so we can build the Research tab. Tables are easiest for us.

| # | Question |
|---|---|
| 1 | Which papers and research questions should the tab serve? Keep Skills, Policies, Security, Integration, or rename (for example Temporal validity, Skills, Policies, Security governance)? |
| 2 | For each paper: the exact metrics, their formula, unit, and which stored data (section 10) feeds each one |
| 3 | For each paper: the baseline or comparison condition (for example retrieval-time filtering vs graph enforcement) and how to run it |
| 4 | Experiments: should the tab run experiments inside the product (inject a drift, replay runs as of a date, attack with a restricted principal), or only read results from a separate research repository? |
| 5 | Test sets: golden questions, injected drifts, attack cases. Who writes them and in what format? |
| 6 | Temporal validity: which tests prove validate and invalidate are correct (as of correctness, stale answer rate, actions under expired policy, drift detection recall and delay)? |
| 7 | Skills: how to measure conformance (documented steps vs observed trace steps) and pass^k (which k, how many repeats) |
| 8 | Security governance: which threat model and attacks (prompt injection, privilege escalation, on behalf of misuse, leakage), and what counts as a leak |
| 9 | What each screen should show first: a headline result, a per-case drill down, a comparison chart, or an experiment log |
| 10 | Export: which formats and fields the papers need (CSV, JSON, LaTeX tables, figures) |
| 11 | Statistics: sample sizes, confidence intervals, significance tests to show |
| 12 | Anything from the research the product should change (for example new fields on facts or policies, new signals) |

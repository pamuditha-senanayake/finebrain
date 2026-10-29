# Company Brain: Progress Presentation 1 (research context)

28 October 2026. Project KND_CDAP_DS_07, SLIIT. This file is the full context for building the first progress presentation. Every number here comes from a run we made, from a public paper we name, or from our proposal. Nothing is estimated unless it says so.

## 0. How to use this file

| Item | Rule |
|---|---|
| Audience | Panel at Progress Presentation 1 (PP1). A second progress presentation (PP2) follows, so nothing is shown as 100% done |
| Source of truth | The code on `main` and the Lab's stored results. The four stage reports in `Docs/` hold the detail |
| Old numbers | The proposal slide quoted figures from our separate ICAC paper (9 policies, 1,200 traces, 240 tasks, +33 to 40 points, p < 10^-15, 89.3% recall). They come from that paper's own setup and are **not** used here. This file uses only the new results |
| Tone | Say what worked, what did not, and what is left. Gaps are part of the story |

## 1. The project in one view

| | |
|---|---|
| Product | **Company Brain (Finebrain)**: a governed knowledge layer for enterprise AI support agents. It keeps policies versioned in time, runs skills as checked steps, and checks permission at the moment an agent acts |
| Research question | Can an agent's knowledge layer stay current, executable and safe while the company's policies change? |
| Three research components | Policies (freshness), Skills (executable procedures), Security (enforcement at the call) |
| Supervisor | Ms. Dinusha Premasiri |
| Co-supervisor | Dr. Janaka Alawatugoda |

| Member | ID | Component | Proposal title |
|---|---|---|---|
| Pamuditha Senanayake | IT22079718 | Policies | Versioned policies that expire on evidence: detect and invalidate stale operational policy in a bitemporal graph |
| Udayanga Weerakoon | IT23142428 | Skills | Executable skills from enterprise support traces |
| Imashi Dissanayake | IT23423510 | Security (Trust and Governance) | Invocation-time enforcement for agent skills under RBAC and ABAC |

## 2. Headline achievements

| # | Achievement | Evidence |
|---|---|---|
| 1 | **First paper accepted at ICAC 2026**: "Bitemporal Policy Invalidation (BTPI) for LLM Enterprise Agents" | A separate, initial paper. Four more papers are planned (section 10) |
| 2 | A working product, not a mock-up: the full pipeline S1 to S15 runs on real infrastructure with real Claude and Voyage models | 219 commits since 8 October 2026; 989 backend tests, 66 frontend tests, 2 end-to-end tests |
| 3 | A **Research Lab** inside the product that runs experiments through the real pipeline, with locked preregistrations and statistics | 15 of 18 build steps done |
| 4 | **Policies:** on a public benchmark (FiscalQA Pro), Finebrain matched the published best system: 99.5% strict score against their 98.3% | Our run, their questions, their scorer, their prompt |
| 5 | **Security:** the retrieval filter cut restricted items reaching the agent from 100% to 0% (900 episodes), with no loss of benign work | 1,960 episodes on real infra |
| 6 | **Skills:** the authored skill made the agent end every case as the policy says, 8 times out of 8 (pass^8 = 1.0), against 62.5% without the skill's steps | 256 runs on real infra |
| 7 | Tested on four public benchmarks we ran ourselves: FiscalQA Pro, AgentDojo, tau3-bench, Padella and Vinci drift logs | Section 7 |
| 8 | Total model spend about **$40**, inside the proposal's LLM budget of 22,000 LKR (about $73) | Section 9 |

## 3. Overall progress

Each component's percentage is the mean of its proposal objectives, each scored for how much is built and measured (tables in section 6). The product and Lab percentages count finished build steps.

| Part | Progress | Why not higher |
|---|---|---|
| Product platform (pipeline, console, live tenant) | **75%** | Email sender, MCP access, some stages still below the full real-use bar |
| Research Lab (experiment infrastructure) | **80%** | Stage 4 left: integration experiment, field metrics, exports |
| Policies component | **60%** | Automatic invalidation from behaviour not built; agent actions not yet measured; drift detector below its bars |
| Security component | **70%** | Baseline separation not shown (the model refused every attack); latency 20 ms against 10 ms; ABCD not used |
| Skills component | **45%** | Skill induction from traces, the main objective, starts in PP2 |
| **Whole project** | **about 60%** | On track for PP2: the platform and Lab are mostly done, so PP2 is mainly research runs |

## 4. The product: what is built

### 4.1 The pipeline

| Lane | Stages | What it does | Status |
|---|---|---|---|
| A, act | S1 Capture to S10 Record | Receive a message, route it to an activity, start a run, retrieve as-of-time knowledge, reason with Claude Sonnet, govern (access, policy, quality gates), get approval, act on outside systems, record an audit trail | Done |
| B, learn documents | S11 Ingest, S12 Librarian | Turn uploaded documents into verified facts; the librarian compares new facts with the current ones | Done |
| C, learning | S13 Learn | Weekly counts, spikes, drift signal | Done |
| Version | S14 | Git for the graph: commit, merge, release; nodes close instead of being deleted | Done |
| D, readiness | S15 | Finds missing evidence early, hourly | Done |

### 4.2 Platform and screens

| Area | What exists |
|---|---|
| Infrastructure | Postgres with pgvector, Valkey, Redpanda (Kafka), Temporal, S3 (SeaweedFS), OPA policy engine, all in Docker Compose |
| Models | Claude Sonnet 5.5 (reasoning), Haiku 5.5 (routing, grading, answers), Opus 5.5 (librarian), Voyage (embeddings and rerank) |
| Live tenant | Finebase HQ runs on the real backend; refunds go into a shop database as a refund-only user; replies go back into the customer's chat |
| Console | Ask (with sources), Studio (workflow editing with Claude), graph screens, Connections desk, conversations, trends, lists of thousands, search, forgetting (retire and erase) |
| Safety built in | Personal data masked and vaulted; prompt-injection flag; access checks fail closed; hash-chained audit log; idempotent actions; rate limits |

### 4.3 Product changes made for the research

| Code | Change | Used by |
|---|---|---|
| P1 | A clock per run, so a lab can replay time | All papers |
| P2 | Shadow tools: actions are recorded, not made | All papers |
| P3 | Every run step names its activity | Skills, drift |
| P4 | A skill's runs export as an XES event log | Skills |
| P5 | Drift signal over the event log | Policies |
| P9 | Every access decision records effective tier, capabilities and latency | Security |
| P10 | A canary (secret marker) never reaches a display | Security |

## 5. The Research Lab

| Part | What it does |
|---|---|
| Lab tenants | Each condition runs the real pipeline in its own throwaway tenant (`lab_<id>`), tools in shadow mode, torn down after |
| Packs | Zip upload, a schema per kind, ten audits (for example, a marker-leak audit) |
| Preregistration | Hypotheses and thresholds locked before a run; locked rows can never change (database trigger); a run refuses an unlocked or altered one |
| Statistics | Wilson intervals, rule of three, exact McNemar, paired bootstrap by task, pass^k, Holm correction, kappa, Cohen's h |
| Grading | By rule, never by a model |
| Runner | Cost estimate and USD cap, resume after a crash, gates, parallel conditions |
| Screens | Papers with verdicts, conditions side by side, cases one at a time, pass^k curves, public benchmark numbers as dashed lines |

| Stage | Steps | Status |
|---|---|---|
| 1 Foundations (freshness) | 1 to 8 | Done |
| 2 Security | 9 to 11 | Done |
| 3 Skills and drift | 12 to 15 | Done |
| 4 Integration and export | 16 to 18 | Next (PP2) |

## 6. Objectives against what was built

### 6.1 Policies (Pamuditha)

Main objective: a policy store that knows when a rule has gone out of date, retires it, and hands the agent the version that is true now.

| # | Specific objective | Status | Progress |
|---|---|---|---|
| 1 | Build the test bed (dated policies that change, with work records) | Nyrivell pack (91 documents, 118 questions), FiscalQA Pro (public), tau Drift (6,000 dated requests) | 90% |
| 2 | Store each rule's valid time, recorded time and successor | Built in the graph; as-of reads in S5 | 90% |
| 3 | Collect decay signals as one series | Drift signal reads activities, step pairs and durations together | 60% |
| 4 | Detect the change | Built; recall 82%, below the bar | 55% |
| 5 | Retire the old rule correctly | Works when the end date is known (C1); automatic retirement from behaviour not built | 40% |
| 6 | Prove the effect on the agent | Measured on answers; not yet on agent actions | 30% |
| | **Mean** | | **about 60%** |

| Proposal target (Table 3.1) | Result | Met? |
|---|---|---|
| Drift recall at least 90% | 82% on 44 public logs | No |
| Mean delay under 50 traces | 342 traces | No |
| False alarms under 10% | 68% strict; 5.2% when real changes in the logs are set apart | Partly |
| At least 95% of as-of-now queries correct | FiscalQA 97.8% only the right value (99.5% strict); Nyrivell 85.8% | Yes on FiscalQA, no on Nyrivell |
| Stale policy action rate under 5% | Stale answers 0.0% under C1; actions not yet measured | Not yet measured |
| Current-policy pass rate +15 points over static retrieval | Not yet measured on actions | Not yet measured |
| No regression over 2 points on unchanged policies | Control questions: C0 93.3%, C1 90.8% (−2.5 points) | Borderline |
| Query latency within the retrieval baseline | Not yet measured | Not yet measured |

### 6.2 Security (Imashi)

Main objective: check permission at the moment an agent acts, not when it reads, and aim for zero forbidden actions while staying fast and useful.

| # | Specific objective | Status | Progress |
|---|---|---|---|
| 1 | Validate the gap in the literature | Done in the proposal | 100% |
| 2 | Design the enforcement point | Built: OPA decides capability, tier and on-behalf-of at every call; fails closed | 85% |
| 3 | Build the benchmark | `finebase_entitlements_v1`: 490 episodes, labels checked by an independent oracle; ABCD not used | 55% |
| 4 | Run the conditions | U, P, R and I run; AgentDojo run | 90% |
| 5 | Measure against fixed criteria | All four measured; two met | 60% |
| 6 | Document the integration | Partly in the system reference | 50% |
| | **Mean** | | **about 70%** |

| Proposal target | Result | Met? |
|---|---|---|
| 0 forbidden actions under invocation-time enforcement | 0 of 300 (upper bound 1.0%) | Yes |
| Retrieval baseline above 5% forbidden actions | 0 of 300: the model refused every attack in every condition | No |
| Utility within 5 points | Benign work 100% in every condition; 0 false denials | Yes |
| Added latency median under 10 ms | Median 20 ms, 95th percentile 68 ms | No |

### 6.3 Skills (Udayanga)

Main objective: turn records of past support work into steps an agent can run, and score each against what the company really did.

| # | Specific objective | Status | Progress |
|---|---|---|---|
| 1 | Split the data once and freeze it | Train and held-out logs exist, but generated, not a public corpus | 50% |
| 2 | Clean the raw traces | Every run step names its activity; XES export | 60% |
| 3 | Extract a runnable procedure (skill induction) | Not started; PP2 work | 0% |
| 4 | Score it against real behaviour | Fitness and precision pipeline built and run (pm4py, outside the app) | 70% |
| 5 | Test it in use (task success, consistency) | Done for the authored skill; induced skill and retrieval baseline not yet | 60% |
| 6 | Trace any failure to its source | First finding: conformance is not correctness | 30% |
| | **Mean** | | **about 45%** |

| Proposal target | Result | Met? |
|---|---|---|
| Alignment fitness at least 0.90 on the held-out log | 1.00 on the agent's runs (authored skill); 0.85 for the written procedure on generated logs | Yes for the authored skill; induced skill not yet |
| Task success at least +5 points (pass^1) and +10 points (pass^8) | +37.5 points at both pass^1 and pass^8 | Yes, but against "no skill steps", not the retrieval baseline |
| Document versus behaviour fitness gap at least 0.10 | 0.15 on generated logs | Yes, on generated data |

## 7. Results by stage

### 7.1 Stage 1: freshness on our own pack (Nyrivell)

Setup: 91 documents, 118 questions (75 changed facts, 40 controls, 3 canaries). Claude Haiku 5.5, three seeds, 1,062 answers, $1.23. All gates passed.

| Condition | Meaning |
|---|---|
| C0 | Plain retrieval: every version kept, no dates |
| C1 | Source filtering: each version ends on its date |
| C3 | Living map: Finebrain finds the change itself (fact extraction, librarian, approval) |

| Metric | C0 | C1 | C3 |
|---|---|---|---|
| Stale answers | 10.7% | **0.0%** | 8.0% |
| Current answers | 4.0% | **85.8%** | 10.7% |
| Both values stated (mixed) | 74.7% | 0.0% | 74.2% |
| Refused | 10.7% | 14.2% | 7.1% |
| Control accuracy | 93.3% | 90.8% | 91.7% |

| Hypothesis (locked before the run) | Result | Verdict |
|---|---|---|
| H1: C1 at least 10 points fewer stale answers than C0 | −10.7 points [−17.8, −4.4], p < 0.0001 | Supported |
| H2: C3 at least 10 points fewer stale answers than C0 | −2.7 points, p 0.26 | Not supported |
| H3: C1 states the current value at least 95% of the time | 85.8% [80.6, 89.7] | Not supported |

What we learned:

| Finding | Meaning |
|---|---|
| With both versions in context, the model states both 75% of the time | "Stale rate" alone understates the problem; mixed answers are their own column |
| C1's refusals (14%) come from chunk size | Finebrain closes whole 1,200-character chunks, which hides valid text beside the old sentence |
| The librarian found 90 conflicts but replaced the fact in only 3 | Without dates in the text it favours the current fact; the product needs validity dates in that decision (PP2) |

### 7.2 Public freshness benchmark: FiscalQA Pro

Source: "Temporal Misgrounding in Legal RAG" (arXiv 2608.09393), data CC BY 4.0. 209 questions on the French tax code, each "as of" a date from 1989 to 2025; 33 articles in 911 versions. Graded by FiscalQA's own rule (every required "nugget" must appear), with FiscalQA's own prompt. Haiku 5.5, three seeds, 1,272 answers, $0.68.

| Metric | C0 | C1 |
|---|---|---|
| States only the right value | 40.0% | **97.8%** [96.3, 98.7] |
| Strict score (FiscalQA's) | 66.2% | **99.5%** |
| Stale only | 16.0% | 0.0% |
| Mixed | 26.2% | 1.7% |

| Hypothesis | Verdict |
|---|---|
| H1: C1 cuts stale answers by at least 10 points | Supported: −15.9 points [−20.7, −11.5], p < 0.0001 |
| H2: C1 states only the right value at least 83% of the time (the paper's bar) | Supported: 97.8%, lower bound 96.3% |

| System (published or ours) | Strict score |
|---|---|
| FiscalQA paper: current version only (static RAG), eleven models | 2.7% |
| FiscalQA paper: their version-aware retriever | 98.3% (Claude Sonnet 4.6: 99.0%) |
| FiscalQA paper: gold article given (upper bound) | 99.1% |
| **Finebrain C1, its own retrieval end to end, Haiku 5.5** | **99.5%** |

Limits: their figures use eleven other models; ours is one model. C1 is given the end dates from the law's own record; Finebrain finding the changes itself was not run on FiscalQA (about $30).

### 7.3 Stage 2: security

Setup: `finebase_entitlements_v1`, 490 episodes. Attacks come through the customer's email, a poisoned policy, and the shop's own order record. Also an L2 agent acting for L3 staff, an L3 insider asking through Ask, and 70 benign episodes. Claude Sonnet 5.5, 1,960 episodes, $16.46 plus about $3.60 rerun.

| Condition | Meaning |
|---|---|
| U | Nothing checked |
| P | Rules written into the prompt |
| R | Retrieval filtered |
| I | Finebrain as it is: retrieval filter and enforcement at the call |

| Metric | U | P | R | I |
|---|---|---|---|---|
| Forbidden actions (of 300) | 0% | 0% | 0% | 0% |
| Attacks that worked (of 300) | 0% | 0% | 0% | 0% |
| Restricted item reached the agent (of 450) | **100%** | **100%** | **0%** | **0%** |
| Canary said (of 450) | 0% | 0.2% (1) | 0% | 0% |
| Benign work done (of 70) | 100% | 100% | 100% | 100% |
| False denials (of 50) | 0% | 0% | 0% | 0% |

| Hypothesis | Verdict |
|---|---|
| H1: forbidden actions under I at most 1% | Supported: 0 of 300 |
| H2: forbidden actions under R above 5% | Not supported: 0 of 300 |
| H3: read leaks, I minus U, at most −10 points | Supported: −100 points, p < 0.0001 |
| H4: benign work under I at least 80% | Supported: 70 of 70 |

What it means, plainly:

| Point | Explanation |
|---|---|
| The valuable result | Without a filter, every restricted item reached the agent. Writing rules into the prompt changed nothing. The filter stopped all of it, with no loss of useful work |
| What we could not show | Sonnet 5.5 refused every injected refund on its own, so this pack cannot show what the check at the call adds. PP2 needs attacks the model falls for, or a weaker second model |
| Exposure is not disclosure | The agent saw restricted text in 900 episodes and repeated a canary once. Both numbers matter |

### 7.4 Public security benchmarks

| Benchmark | Setting | Result | Run by |
|---|---|---|---|
| AgentDojo banking v1.2.1, Sonnet 5.5 | No defence | Attacks 0 of 144; benign 16 of 16; useful under attack 135 of 144 | Us ($6.33) |
| | Finebrain's rule at the call | Attacks 0 of 144; benign 14 of 16; useful under attack 126 of 144 | Us |
| PhantomPolicy (paper, five models) | No enforcement | 286 of 300 violations | Paper |
| | Policy in the prompt | 122 of 300 violations | Paper |
| | Sentinel at the call | About 12% of violations missed | Paper |

The rule cost two benign AgentDojo tasks; both pay from a file the user named, which the rule refuses by design. PhantomPolicy's data has no public link yet, so its numbers are quoted, not rerun.

### 7.5 Stage 3: skills

Setup: a generated refund skills pack, 16 cases whose correct ending follows from the refund policy. Claude Sonnet 5.5, 16 cases × 8 trials × 2 conditions, $2.20.

| Condition | Meaning |
|---|---|
| B0 | Same tools, no skill steps |
| B1 | The authored skill's steps |

| Metric | B0 | B1 |
|---|---|---|
| Cases ending as the policy says | 62.5% | **100%** [97.1, 100] |
| pass^1 / pass^8 | 0.625 / 0.625 | **1.0 / 1.0** |
| Written procedure fits the agent's runs (fitness) | 1.00 | 1.00 |
| Written procedure's precision on the runs | 0.75 | 0.85 |

| Hypothesis | Verdict |
|---|---|
| H1: B1 beats B0 | Supported: +37.5 points [12.5, 62.5], p 0.0006 |
| H2: B1's pass^8 at least 0.5 | Supported: 1.0 |

Key finding: **conformance is not correctness.** B0 never left the written procedure (fitness 1.00) yet ended 37.5% of cases wrongly: it escalated where the policy says to propose for approval. This supports the skills paper's claim that task outcomes catch what fitness alone misses.

Generated logs ("how the work is really done"): the written procedure fits 0.85, a mined model 1.00; a documented versus observed gap of 0.15.

### 7.6 Public skills benchmark: tau3-bench retail

tau's own agent and simulated user, Haiku 5.5, 30 retail tasks × 8 trials, graded on final database state, $3.44, no errors.

| k | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| pass^k (ours, Haiku 5.5) | 80.0% | 69.8% | 59.8% | 50.0% |
| tau-bench paper, GPT-4o (cited in our proposal) | 61.2% | | | under 25% |

Meaning: even a strong agent loses consistency over repeated tries (80% to 50%). Our authored skill stayed at 1.0 at k = 8, but our cases are simpler, so the comparison is for scale only.

### 7.7 Drift detection (policies)

| Benchmark | Result |
|---|---|
| Padella and Vinci public logs (45 logs, 44 scored; scored as Adams et al.) | Recall 82%, delay 342 traces, false alarms 68% strict, 5.2% with real changes set apart |
| tau Drift (ours, generated) | 1 of 3 version changes found |

The detector's settings were fixed before reading any public log, so the scores are not tuned to the test. It finds big changes but slowly, and misses moderate ones.

## 8. Benchmarks and datasets: were they really tested?

| Dataset | Kind | Size | Public? | Run by us? |
|---|---|---|---|---|
| Nyrivell freshness v2 | Our synthetic company policies | 91 documents, 118 questions | No (ours) | Yes |
| FiscalQA Pro | French tax law, dated versions | 209 questions, 911 versions | Yes, CC BY 4.0 | Yes |
| finebase_entitlements_v1 | Our generated entitlements and attacks, oracle-checked | 490 episodes | No (ours) | Yes |
| AgentDojo banking v1.2.1 | Public prompt-injection benchmark | 16 tasks, 144 attack cases | Yes | Yes |
| PhantomPolicy | Policy-violation benchmark | 300 cases | Data not yet released | No, paper figures |
| Refund skills pack | Our generated refund cases and logs | 16 cases, train and held-out logs | No (ours) | Yes |
| tau3-bench retail | Public agent benchmark | 30 tasks × 8 trials | Yes | Yes |
| Padella and Vinci drift logs | Public process-drift logs | 45 logs | Yes | Yes |
| tau Drift | Our generated dated refund requests | 6,000 requests | No (ours) | Yes |

Every Lab run went through the real product pipeline on real infrastructure (Postgres, Valkey, Redpanda, S3, OPA) with real models, and every condition's lab was torn down afterwards.

| Lab experiment | Paper | Conditions | Model | Cost |
|---|---|---|---|---|
| `ebfc04f5-9f71-4c71-bdd0-5a69ed772f5b` | Policies (Nyrivell) | C0, C1, C3 | Haiku 5.5 | $1.23 |
| `55e70bc1-e0f7-4a4e-a02e-4fcf360803cc` | Policies (FiscalQA Pro) | C0, C1 | Haiku 5.5 | $0.68 |
| `02ffc9d8-d03a-4703-bcab-960e9401e390` | Security | U, P, R, I | Sonnet 5.5 | $16.46 |
| `fa4a4122-1e0c-479c-b8e9-43e7e90cf794` | Skills | B0, B1 | Sonnet 5.5 | $2.20 |

## 9. Cost and quality

| Item | Value |
|---|---|
| Model spend (Lab runs, AgentDojo, tau3, reruns) | About $40 |
| Proposal LLM budget | 22,000 LKR (about $73) |
| Backend tests | 989 |
| Frontend tests | 66 |
| End-to-end tests | 2 |
| Licence care | pm4py is AGPL, so it runs only as a separate research tool and never enters the product |

## 10. Publications

| Paper | Status | Target venue |
|---|---|---|
| Bitemporal Policy Invalidation (BTPI) for LLM Enterprise Agents | **Accepted, ICAC 2026** (separate initial paper) | ICAC 2026 |
| Skills: behaviour-referenced validation of executable skills | Planned | BPM 2027 (fallback CAiSE 2028, ICPM 2028) |
| Policies: detecting and invalidating stale operational policy in a bitemporal graph | Planned | CIKM 2027 (fallback KDD 2027) |
| Security: invocation-time enforcement for agent skills under RBAC and ABAC | Planned | ACM CCS 2027 or USENIX Security 2027 (fallback ACSAC 2027, SACMAT 2027) |
| Integration: the living map, a governed knowledge layer for enterprise agents | Planned | IEEE TKDE (fallback Information Systems, Knowledge-Based Systems) |

How close each planned paper is:

| Paper | Strongest result now | Needed before submission |
|---|---|---|
| Policies | FiscalQA: 99.5% strict, matching the published best | Finebrain finding changes itself (C3) on FiscalQA; agent actions; a second model family |
| Security | Retrieval filter: restricted items reaching the agent 100% to 0% | Attacks the model falls for, three seeds, latency under 10 ms |
| Skills | Authored skill pass^8 1.0 against 62.5%; conformance is not correctness | Skill induction (B2), the retrieval baseline, field or public data |
| Integration | Not started | Lab stage 4 |

## 11. Where the work differs from the proposal

| Proposal said | What we did | Why |
|---|---|---|
| Slide's policy figures (+33 to 40 points, 89.3% recall, 240 tasks) | Not used; new results reported | They belong to the ICAC paper's own setup |
| Skills: induce skills from traces | Authored skill tested first; induction is PP2 | The test harness had to exist first |
| Skills: public corpus via Kecht et al., ada-002 retrieval baseline | Generated logs; B0 (no steps) as baseline | Corpus not yet prepared; baseline is PP2 |
| Policies: recency-weighted and HALO baselines, four conditions | Static retrieval (C0), dated (C1), living map (C3) | C2 refused rather than approximated; other baselines in PP2 |
| Policies: a conformance drop writes the interval closed | Drift signal built; the automatic write is not | PP2 |
| Policies: corpus of 48 policies, 498 chunks | 91 documents, 182 chunks | Finebrain's own chunking is larger |
| Security: ABCD dataset, benchmark from Skills traces | Generated entitlements pack with an independent oracle | Precise roles and forbidden actions needed first |
| Security: attenuated per-call authority | Effective tier and capabilities recorded on every decision; no attenuated tokens | PP2 |
| Drift detector (spec named ADWIN) | Two-window test, settings fixed beforehand | A sequential detector is PP2 |

## 12. Done enough for now

| Item | Why it is enough for PP1 |
|---|---|
| The pipeline S1 to S15 | Runs end to end on real infra with real models |
| Research Lab stages 1 to 3 | Every paper can run, lock, grade and report |
| Freshness with known dates (C1) | Matches the published best on a public benchmark |
| Retrieval filtering for security | A clear 100% to 0% result with no utility cost |
| Authored skill consistency | pass^8 1.0, measured on the real pipeline |

## 13. Plan for PP2

| # | Work | Component |
|---|---|---|
| 1 | Skill induction from traces (B2), and the retrieval baseline | Skills |
| 2 | A public or field trace corpus for skills | Skills |
| 3 | Automatic invalidation: dates in the librarian's decision, and a drift-triggered write | Policies |
| 4 | Agent actions on changing policy: stale action rate, current-policy pass rate, regression, latency | Policies |
| 5 | A sequential drift detector (ADWIN or Page-Hinkley) on the same logs | Policies |
| 6 | Harder attacks, or a weaker second agent model, to show what the check at the call adds | Security |
| 7 | Access check latency under 10 ms; attenuated per-call authority | Security |
| 8 | Lab stage 4: integration experiment, field metrics, exports and reproducibility bundle | All |
| 9 | Three seeds and a second model family on every paper run | All |

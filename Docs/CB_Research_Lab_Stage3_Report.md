# Research Lab: Stage 3 report (skills and drift)

28 October 2026. For the research lead. Stage 3 of `CB_Research_Tab_Build_Spec_v1.md` (steps 12 to 15) is built and tested, on branch `imashi/dev/research_skills_drift`.

## 1. What now exists

| Part | What it does |
|---|---|
| Activities (P3) | Every run step names its activity (context read, action proposed, access decision, wait for a person, action done) |
| Event logs (P4) | A skill's runs download as XES, one trace per run |
| Conformance | pm4py scores fitness and precision in a separate script and environment. It is AGPL, so it never enters the app |
| Skills runs and pass^k | Refund cases run trial after trial through the real pipeline, without (B0) and with (B1) the skill's steps; pass^1 to pass^n with intervals |
| tau3 adapter | tau3-bench runs in its own environment; the Lab reads its results into a pass^k curve |
| tau Drift | Dated policy versions, 6,000 dated refund requests whose gold follows the version in force, and an event log with known drift points |
| Drift signal (P5) | Finds where a process changed, scored as Adams et al. do |

## 2. Decisions taken for you (please confirm or change)

| # | Decision | Why |
|---|---|---|
| 1 | pm4py runs only as a separate research tool | AGPL v3 could oblige Finebrain to open-source if linked. Ask a lawyer before shipping the script with the product |
| 2 | The refund skills pack is generated, not field data | The skills owner's pack does not exist yet. Its deviations (confirming first, failing to a person) are mine |
| 3 | The written procedure model was corrected once (v1.1) | v1.0 expected a final action after an escalation and after an approval wait; the product records neither, so every such run looked like a deviation |
| 4 | tau3: tau's own agent, Haiku 5.5, 30 retail tasks graded without language assertions | tau judges those with an OpenAI model it hard-codes. Finebrain as the tau agent belongs to the integration paper (stage 4) |
| 5 | The drift signal's settings were fixed before reading any public log | So the scores are not tuned to the test |
| 6 | tau Drift uses the two parameters S7 enforces | The spec asks 6 to 10; tau's own domains would add them |

## 3. Results

**Skills, refund cases** (Sonnet 5.5, 16 cases × 8 trials × 2 conditions, $2.20, gates passed, labs torn down)

| Metric | B0, no skill steps | B1, authored skill |
|---|---|---|
| Cases ending as the policy says | 62.5% | **100%** [97.1, 100] |
| pass^1 / pass^8 | 0.625 / 0.625 | 1.0 / 1.0 |
| Written procedure fits the agent's runs | 1.00 | 1.00 |
| Written procedure's precision on the runs | 0.75 | 0.85 |

H1 supported: B1 beats B0 by 37.5 points [12.5, 62.5], p 0.0006. H2 supported: B1's pass^8 is at least 0.5.

**Generated logs** (how the work is "really" done): the written procedure fits 0.85, a mined model 1.00 (precision 1.00 against 0.47), a documented versus observed gap of 0.15.

**tau3-bench retail** (tau's agent and user, Haiku 5.5, 30 tasks × 8 trials, $3.44, no errors)

| k | 1 | 2 | 4 | 8 |
|---|---|---|---|---|
| pass^k | 80.0% | 69.8% | 59.8% | 50.0% [33.3, 66.7] |

**Drift signal on the public Padella and Vinci logs** (45 logs, 44 scored)

| | Ours | Spec bar |
|---|---|---|
| Recall | 82% | at least 90% |
| Delay | 342 traces (sudden 73 to 232) | under 50 |
| False alarms, strict | 68% | under 10% |
| False alarms, real-process changes set apart | 5.2% | under 10% |

On tau Drift it finds 1 of 3 version changes.

## 4. What it means

1. **Conformance is not correctness.** B0 never left the written procedure (fitness 1.00), yet got 37.5% of cases wrong: it escalated where the policy says to propose for approval. The skills paper's claim, that task outcomes catch what fitness misses, holds here, measured on the real pipeline.
2. **The authored skill makes the agent perfectly consistent.** pass^8 of 1.0, against tau3 retail falling from 80% to 50%. The cases are simpler than tau's, so the comparison is scale only.
3. **The drift signal finds big changes, not moderate ones, and slowly.** It caught 82% of injected drifts. Most "false" alarms are real changes in the original logs. Delay is far above the bar, and a 13-point shift in tau Drift went unseen.

## 5. Gaps

| Gap | What it would take |
|---|---|
| B2 (extracted skill) and B3 (normative model as a skill) | A skill induced from traces, and a runner for a process model as a skill |
| Field data for the skills paper | The skills owner's pack, or HQ runs once there are many |
| Finebrain as the tau agent | Stage 4 (integration) |
| HQ's freshness fields (P5) | A run-by-policy index, so drift and conformance per policy are read by key |
| Drift delay and sensitivity | A sequential detector (ADWIN or Page-Hinkley), set beforehand and compared on the same logs |
| tau Drift with 6 to 10 parameters | Generating from tau's retail, airline and banking policies |
| One seed everywhere | Three seeds for paper runs |

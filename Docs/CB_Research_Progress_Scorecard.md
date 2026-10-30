# Research progress scorecard (for the presentation on 2026-11-01)

Date: 2026-10-30. Sources: the three proposal reports (section 2.2 in each), the team Claims file, the three demo guides, `CB_Progress_Presentation_1.md`, and the code on `main`. Each percentage counts what is built in the product and what is measured in the Research Lab. Nothing new has been built or run since the demo guides were written, so their figures still hold.

## 1. What we are solving

| Pain point (Claims file) | Paper that answers it |
|---|---|
| Know-how sits in heads, threads and tickets, and agents cannot act on it | Skills |
| Each unknown ends in an action, not an answer | Skills |
| The output must be something an agent can run, not a search index | Skills |
| Knowledge must stay current. Staleness is a first-class failure | Policies |
| The map drifts as soon as the company changes | Policies |
| An agent must only act within what the person may do | Security |

## 2. Summary

| Paper | Owner | Done today | Above 50%? | After the quick wins (section 6) |
|---|---|---|---|---|
| Skills | Udayanga | **45%** | No | about 58% |
| Policies | Pamuditha | **61%** | Yes | about 62% |
| Security | Imashi | **73%** | Yes | about 78% |
| **Team** | | **about 60%** | Yes | **about 66%** |

The team as a whole is already inside the 60 to 70% target. Skills is the one paper below the line, so it needs the most attention.

## 3. Skills (Udayanga): 45%

| # | Objective | In the product | In the research results | Done |
|---|---|---|---|---|
| 1 | Split the data once and freeze it | None | Training and held-out logs exist, but they are generated and the split is not locked | 50% |
| 2 | Clean the raw traces | Every run step names its activity. Runs export as XES event logs | Used for the conformance scores | 60% |
| 3 | Extract a runnable procedure | Skills run in the pipeline, but they are written by hand | Not started. This is the core of the paper | 0% |
| 4 | Score it against real behaviour | None (pm4py stays outside the app because of its licence) | Fitness 1.00 on the agent's runs. The written procedure fits the logs at 0.85, a 0.15 gap against the 0.10 target | 70% |
| 5 | Test it in use | The authored refund skill runs through the real pipeline | With the skill, pass^8 is 1.0. Without it, 0.625 (+37.5 points, p 0.0006). The retrieval baseline has not been run | 60% |
| 6 | Trace any failure to its source | None | One finding: conformance is not correctness | 30% |
| | **Mean** | | | **45%** |

## 4. Policies (Pamuditha): 61%

| # | Objective | In the product | In the research results | Done |
|---|---|---|---|---|
| 1 | Build the test bed | Nyrivell pack and the tau Drift generator are in the Lab | Nyrivell (118 questions), FiscalQA Pro (public, 209 questions), tau Drift (6,000 requests) | 90% |
| 2 | Store valid time, recorded time and successor | Bitemporal graph, as-of reads in S5, policy timeline screen | FiscalQA strict score 99.5% against the paper's best of 98.3%. Latency not measured | 90% |
| 3 | Collect decay signals as one series | Drift signal in S13 | Reads activities, step pairs and durations together | 60% |
| 4 | Detect the change | Drift detector built | Recall 82% (target 90%), delay 342 traces (target under 50) | 55% |
| 5 | Retire the old rule correctly | Retirement works when the end date is known. Changes go through Studio approval | Stale answers drop from 10.7% to 0.0% with dates. Automatic retirement (C3) leaves 8.0% | 40% |
| 6 | Prove the effect on the agent | None | Measured on answers only. The stale action rate (the main metric) is not measured | 30% |
| | **Mean** | | | **61%** |

## 5. Security (Imashi): 73%

| # | Objective | In the product | In the research results | Done |
|---|---|---|---|---|
| 1 | Validate the research gap | None | Systematic review done | 100% |
| 2 | Design the enforcement point | OPA check at every call: capability, tier, on behalf of. Fails closed. Check access dialog | Every decision records tier, capabilities and latency. Per-call narrow tokens not built | 85% |
| 3 | Construct the benchmark | Entitlements pack in the Lab | 490 episodes, all labels agreed by an independent oracle. ABCD not used | 55% |
| 4 | Implement and compare | Four lab tenants (U, P, R, I) | 1,960 episodes, plus AgentDojo banking | 90% |
| 5 | Measure against fixed criteria | None | Zero forbidden actions and full utility: met. Baseline above 5% and latency under 10 ms (it was 20 ms): not met | 60% |
| 6 | Document the integration | Skills and Policies share the S7 check | Partly written in the system reference | 50% |
| | **Mean** | | | **73%** |

## 6. Quick wins before the presentation

None of these needs a paid model run. That matters because only about $6.50 of credit is left.

| Paper | Work | Objective | Change |
|---|---|---|---|
| Skills | Lock the train and held-out split with a manifest and a preregistration | 1 | 50% to 70% |
| Skills | Write up the diagnosis ladder for the authored skill (stages 1 to 3 all pass) plus the conformance finding | 6 | 30% to 60% |
| Skills | First induction draft: turn the model mined from the training log (fitness 1.00) into skill steps | 3 | 0% to 25% |
| Policies | Time the as-of query at the 95th percentile against plain retrieval (local, no model) | 2 | 90% to 95% |
| Security | Finish the integration write-up: how Skills and Policies call the S7 check | 6 | 50% to 80% |

With all five, Skills is at about 58%, Policies at about 62%, Security at about 78%, and the team at about 66%.

## 7. The two functions each person shows

| Paper | Function | Where it lives | Why this one |
|---|---|---|---|
| Skills | 1. A skill the agent runs, tested for task success and consistency | Skills studio, then Research → Skills (pass^k chart) | It is complete end to end: the skill runs through the real pipeline, and B0 against B1 shows +37.5 points with pass^8 at 1.0 |
| Skills | 2. Scoring a skill against real behaviour | Research → Skills run details (fitness, docs-vs-behaviour gap) | Two targets are met (fitness at least 0.90, gap at least 0.10), and it gives the key finding: conformance is not correctness |
| Policies | 1. The bitemporal policy store with as-of answers | Policy registry, then the Refund window timeline (move the As of date) | It works live, and on a public benchmark it beats the published best (99.5% against 98.3%) |
| Policies | 2. Drift detection that flags a stale rule | Research → Freshness, plus the Freshness column in the registry | Built and scored on 44 public logs with settings fixed in advance. It is honest work in progress (82% recall) |
| Security | 1. The access check at the moment an agent acts | L2 Security: a denied refund in 4.1 ms, then Check access live (Restricted is denied, Confidential is allowed) | It is fully built, fails closed, and gives zero forbidden actions in 300 attack episodes |
| Security | 2. The four-condition comparison | Research → Security (conditions chart) | It measures the gap the paper names. Read leaks drop from 100% to 0%, and normal work stays at 70 of 70 |

Changing a policy through Studio chat, with L1 approval, is a strong bonus to show for Policies, but it is a product feature rather than one of the paper's objectives.

## 8. Say these out loud

- Skills: induction from traces, the core of the paper, has not started. The retrieval baseline has not been run.
- Policies: automatic retirement from behaviour is not working yet (8.0% stale). Agent actions have not been measured.
- Security: the baseline did not separate from the check, because Sonnet refused every attack on its own. Latency is 20 ms against a 10 ms target.
- All three: one seed per run where the paper asks for three, and the data is generated rather than field data.

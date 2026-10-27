# Research Lab: build plan

27 October 2026. How we build `CB_Research_Tab_Build_Spec_v1.md` on Finebrain `main` (`a7bc601`). Approved. Stages 1 and 2 (steps 1 to 11) are done (see the Research Lab rows in `CB_System_Reference.md`, and `CB_Research_Lab_Stage1_Report.md` and `CB_Research_Lab_Stage2_Report.md`). Next, by agreement: a public freshness benchmark for stage 1, then stage 3.

## 1. In short

| Item | Plan |
|---|---|
| Stages | 4, the spec's four slices: Foundations, Security, Skills and drift, Integration and export |
| Steps | 18 in all. One step at a time. I stop after each one so you can check it |
| Done bar | A stage is done only at the CLAUDE.md bar: every visit tested, real infra, many workers, failures designed, no scans, volume, gaps named. It also has to pass the spec's acceptance test |
| Rule kept | The product never imports research code. The Lab is removed when the flags are off |
| First milestone | End of stage 1: the Nyrivell freshness pack runs through the real S1 to S10 in a lab tenant and gives a verdict with intervals |

## 2. The stages and steps

| Stage | # | Step | Ends with |
|---|---|---|---|
| 1 Foundations | 1 | Contracts, flags and the `research` schema (Pydantic and zod, with provenance and verdicts) | Old snapshots still load, removal e2e passes |
| | 2 | Product changes: a clock per run (P1) and shadow tools (P2) | S9 in shadow mode records `shadow_action`, calls nothing |
| | 3 | Lab tenant: create, seed from a pack, isolate (`lab_` tenant, `lab.*` topics, S3 prefix, `research-lab` queue, sandbox shop schema), tear down | A test proves production reads no lab row, and nothing is left after teardown |
| | 4 | Packs: zip upload, a schema per kind, all 10 audits. A converter turns Execution_V1 into `nyrivell_freshness_v2` | The marker leak audit catches the old corpus defect |
| | 5 | Preregistration lock (hash, immutable trigger) and the stats module | Each stats method checked against known textbook values |
| | 6 | Freshness runner: grid, cost estimate and USD cap, resume after a crash, gates, deterministic grading, verdicts | A crash mid run resumes with no case counted twice |
| | 7 | Screens: Research home, paper headline, cases one at a time, Lab, New experiment (3 steps), live progress, Prereg | Checked in the browser, every state, WCAG AA |
| | 8 | Acceptance: Nyrivell C0 to C3 through Finebrain, compared with the Execution_V1 rerun, on real infra, plus a volume run | The spec's slice 1 test |
| 2 Security | 9 | Security pack and oracle audit, effective authority on every K6 decision (P9), canary scan (P10) | A leak is a mechanical check, not an opinion |
| | 10 | Conditions U, P, R, I and the security metrics, then 300+ adversarial episodes | I shows 0 forbidden actions, or names the call that leaked |
| | 11 | AgentDojo and PhantomPolicy adapters, each in its own uv environment | Reference rows shown as dashed lines |
| 3 Skills and drift | 12 | Activity ids on trace steps (P3), event log export as XES (P4) | Real conformance replaces "conformance = task success" |
| | 13 | Fitness and precision, and pass^k with n = 8 through repeat runs (P12) | Computed on the refund pack |
| | 14 | tau3 adapter (retail, airline) and the tau Drift generator | pass^k curve for retail |
| | 15 | Drift signals (P5) on the Padella and Vinci logs, scored with the Adams framework | Recall, delay and false alarms against known drift points |
| 4 Integration and export | 16 | Ablation profiles, tau Knowledge adapter, edit stream pack | One full integration experiment |
| | 17 | Field metrics from HQ (`/research/field`), plus P6, P7, P8 and P11 | Observational numbers, labelled `field` |
| | 18 | Exports: CSV, JSON, LaTeX, SVG and PDF figures, reproducibility bundle | The bundle reruns on a clean machine within intervals |

## 3. File plan for stage 1

The spec puts the code in `backend/research/`. CLAUDE.md says app code lives in `backend/app/`, so I put it in `backend/app/research/`. Lines are estimates.

| File | Job | Lines |
|---|---|---|
| `backend/app/research/contracts.py` | Pydantic: Provenance, Metric, Verdict, Snapshot, Pack, Prereg, Experiment, CaseResult | 140 |
| `backend/app/research/store.py` | `research` schema, lock trigger, keyed reads and writes, memory twin | 150 |
| `backend/app/research/lab_tenant.py` | Build a `lab_` lane with `build_lane`, namespaced adapters, shadow tools, sandbox shop schema, teardown | 150 |
| `backend/app/research/packs.py` | Unzip, parse front matter and JSONL, schema per kind, stable hash | 140 |
| `backend/app/research/pack_audits.py` | The 10 audits, each one pass, warn or fail with the lines that caused it | 150 |
| `backend/app/research/prereg.py` | Draft, lock, hash; a locked row can never change | 80 |
| `backend/app/research/stats.py` | Wilson, rule of three, exact McNemar, paired bootstrap, pass^k, Holm, kappa, Cohen's h. Pure Python, no new library | 150 |
| `backend/app/research/conditions.py` | Freshness flag profiles C0 to C3 | 80 |
| `backend/app/research/metrics_registry.py` | Freshness metrics: key, formula, unit, source, test | 100 |
| `backend/app/research/grade_freshness.py` | Deterministic grading against `expected_value` and `superseded_values` | 100 |
| `backend/app/research/runner.py` | Plan the grid, estimate cost, run batches, resume, gates | 150 |
| `backend/app/research/temporal_lab.py` | The workflow on the `research-lab` task queue, with a concurrency cap | 90 |
| `backend/app/research/results.py` | Metrics with intervals, comparisons, verdicts | 120 |
| `backend/app/research/routes.py` | `/research` API, mounted only when `RESEARCH_LAB=enabled` | 150 |
| Product edits: `orchestrate.py`, `run_steps.py`, `tool_runners.py`, `stages_act.py`, `retrieve_case.py`, `stages_retrieve.py`, `main.py` | Run clock, shadow mode, retrieval switches a profile can turn off, mount the router behind the flag | +150 |
| `backend/scripts/research_convert_execution_v1.py` | Execution_V1 corpus and gold into the pack format | 120 |
| `backend/tests/test_research_{stats,packs,lab,runner,real}.py` | Unit, isolation, crash and resume, real infra | 650 |
| `frontend/contracts/research.ts` | Extended contract; old fields kept | +50 |
| `frontend/features/research/{home,paper,cases,lab,lab-new,lab-run,prereg,api}.tsx` | The 7 screens and their hooks. Replaces `console.tsx` | 950 |
| `frontend/app/(research)/research/**/page.research.tsx` | 6 thin route files | 50 |
| `frontend/tests/e2e/research-lab.spec.ts` | Upload, audit fail, lock, run, headline, cases, invalid run | 120 |

Total for stage 1: about 1,950 backend lines, 150 lines of product edits, 1,050 frontend lines and 770 test lines. Several files sit near 150 lines because each one does a single job.

Not creating: a second copy of any pipeline stage, a new database, an LLM judge, chart or zip libraries, or any change to the HQ tenant's data.

## 4. What I found when I checked the spec against the code

| # | Finding | Effect |
|---|---|---|
| 1 | The Execution_V1 conditions test summary nodes. C1 filters out superseded chunks. C2 re-clusters and re-summarises. C3 carries validity up from children to parent summaries | Finebrain can do C0 and C1 today. Its summaries are day, week and month notes per entity. It has no re-clustering (C2) and no validity carried up to summaries (C3). The spec says to stop and report rather than approximate, so this needs a decision |
| 2 | The spec's C3 ("Full living map") is not the same as Execution_V1's C3 ("propagated validity") | Same decision as above |
| 3 | Execution_V1 uses OpenAI embeddings, gpt-4o-mini answers and a gpt-4o-mini judge. Finebrain uses Voyage and Claude, and the spec asks for deterministic grading | The two runs differ in more than the freshness method, so "agree within intervals" may fail for reasons outside freshness |
| 4 | The backend runs Python 3.10. tau3 bench needs 3.12 or 3.13 | Adapters run as separate workers in their own uv environments (stages 2 to 4) |
| 5 | `build_lane` already takes `now`, and only 2 wall clock calls remain in the pipeline | P1 is small |
| 6 | The Execution_V1 `results/` folder is empty | I need the location of the clean rerun results for step 8 |

## 5. Libraries (each needs your yes, nothing in stage 1)

| Library | Stage | Why |
|---|---|---|
| none | 1 | Stats, zip and hashing use the Python standard library |
| `agentdojo` | 2 | AgentDojo adapter, in its own environment |
| `pm4py` | 3 | Alignments, fitness, precision, XES |
| `river` | 3 | ADWIN-style drift detection |
| `tau2` (v1.0.1 or later) | 3 and 4 | tau3 bench adapters, Python 3.12, its own environment |

## 6. What I need from you

| # | Need | When |
|---|---|---|
| 1 | A decision on C1 to C3 (finding 1) | Before step 3 |
| 2 | A USD cap for stage 1 model calls | Before step 6 |
| 3 | The Execution_V1 clean rerun results | Before step 8 |
| 4 | An OpenAI key, if a second model family must run in stage 1 | Before step 8 |
| 5 | Security, skills and drift packs from their owners | Stages 2 and 3 |

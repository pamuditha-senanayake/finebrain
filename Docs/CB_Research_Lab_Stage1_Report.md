# Research Lab: Stage 1 report

27 October 2026. For the research lead. Stage 1 of `CB_Research_Tab_Build_Spec_v1.md` (steps 1 to 8) is built, tested and merged.

## 1. What now exists

| Part | What it does |
|---|---|
| Research tab | Papers with their latest verdict, a paper's headline (hypothesis, locked threshold, observed value with its 95% interval, verdict), the conditions side by side, cases one at a time, the Lab, a three-step new experiment with a cost estimate, live progress with Resume, preregistrations locked by typing the title |
| Lab tenants | Each condition runs the real Finebrain pipeline in its own throwaway tenant, tools in shadow mode, torn down afterwards with nothing left |
| Packs | Zip upload, schema per kind, the ten audits; a warning needs a typed reason |
| Preregistration | Locked rows can never change (database trigger); the run refuses a preregistration that is not locked or whose hash no longer matches |
| Statistics | Wilson, rule of three, exact McNemar, paired bootstrap by task, pass^k, Holm, kappa, Cohen's h |
| Grading | By rule, never by a model: fresh, stale, mixed, refused, wrong. A finished run is graded again by the current rule |

## 2. Decisions taken for you (please confirm or change)

| # | Decision | Why |
|---|---|---|
| 1 | C0 plain retrieval and C1 source filtering match Execution_V1 | Finebrain can express both exactly |
| 2 | C2 (delete and rebuild) is refused, not approximated | Finebrain has no summary tree to recluster; the spec says stop rather than approximate |
| 3 | C3 is the spec's "full living map": Finebrain finds the change itself (fact extraction, librarian, conflict proposal by Claude Opus), the lab's steward accepts new facts and its L1 approves each proposed change | Execution_V1's C3 (validity propagated to summary nodes) needs the same missing summary tree |
| 4 | Answers use Execution_V1's own answer prompt on Claude Haiku 5.5, top k 8, no reranker, each string embedded once | Same as the frozen config, so the two systems answer the same way |
| 5 | The acceptance preregistration is labelled an engineering check, not a paper preregistration | The paper's hypotheses are yours to write and lock |

## 3. The acceptance run (Nyrivell, fixed corpus)

91 documents, 118 questions (75 changed facts, 40 controls, 3 canaries), C0, C1 and C3, three seeds: 1,062 answers for $1.23 in model costs. Gates passed; all labs torn down.

| Metric | C0 plain | C1 source filtering | C3 living map |
|---|---|---|---|
| Stale answers | 10.7% [7.3, 15.4] | 0.0% [0.0, 1.7] | 8.0% [5.1, 12.3] |
| Current answers | 4.0% | 85.8% [80.6, 89.7] | 10.7% |
| Both values stated (mixed) | 74.7% | 0.0% | 74.2% |
| Refused | 10.7% | 14.2% | 7.1% |
| Control accuracy | 93.3% | 90.8% | 91.7% |
| Canaries | 100% | 100% | 100% |
| Evidence reached | 97.3% | 92.0% | 96.0% |

| Hypothesis (locked before the run) | Result | Verdict |
|---|---|---|
| H1: C1 at least 10 points fewer stale answers than C0 | −10.7 pts [−17.8, −4.4], p < 0.0001 | Supported |
| H2: C3 at least 10 points fewer stale answers than C0 | −2.7 pts [−9.3, +3.6], p 0.26 | Not supported (stage 3) |
| H3: C1 states the current value at least 95% of the time | 85.8% [80.6, 89.7] | Not supported (stage 2) |

## 4. Findings that matter for the papers

| # | Finding | Effect |
|---|---|---|
| 1 | With both versions in context, the model states both 75% of the time and flags the conflict | "Stale answer rate" alone understates the problem; report mixed answers as their own column, or give the answer prompt a single final value field |
| 2 | The fixed corpus still leaks through its titles: every update is titled "Policy Update: …", and Finebrain puts the title into every chunk | The marker audit now reads titles and this pack fails it; retitle the updates to read like the base policies |
| 3 | Finebrain's chunks are about 1,200 characters (182 for this corpus), not Execution_V1's 100 tokens (498) | C1 closes whole chunks, so it also hides valid provisions beside the old sentence; this is most of C1's 14% refusals |
| 4 | The living map's librarian found 90 conflicts but replaced the fact in only 3; in 87 it kept the old one | With no date or marker in the text, the conflict resolver favours the current fact; the product needs the documents' validity dates in that decision |
| 5 | A verified fact only reaches a question that names its entity | Most freshness questions name no entity, so C3's facts rarely reach the answer |
| 6 | Execution_V1 has no clean rerun on the fixed corpus; its only full run used the leaking corpus (C0 2.67% stale, C1 to C3 0%) | The spec's "agrees within intervals" check cannot be made yet |
| 7 | Text grading by rule misses synonyms ("one" vs "a single source") | Control accuracy is a lower bound; a human-audited judge would be needed for text answers |

## 5. Gaps, said out loud

| Gap | Note |
|---|---|
| C2 | Not offered (see decision 2) |
| Execution_V1 comparison | Needs its clean rerun |
| Temporal | The Lab runs in a worker thread; a crash resumes from the last stored answer, but the `research-lab` Temporal queue is not built |
| Exports | CSV, LaTeX, figures and the reproducibility bundle are stage 4 |
| Second model family | Only Claude Haiku 5.5 answered; the spec asks for two families on primary hypotheses |
| Light-mode contrast | The primary button fails axe in light mode here and on 17 other screens: a product-wide issue |

## 6. Questions for the research lead

1. Keep C3 as the living map, or define a C3 Finebrain can express that matches Execution_V1's claim?
2. Report mixed answers separately, or change the answer prompt to ask for one final value?
3. Retitle the Nyrivell updates and rerun, or keep this pack as the "titles leak" condition?

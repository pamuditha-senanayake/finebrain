# Research Lab: FiscalQA Pro, a public freshness benchmark

28 October 2026. For the research lead. The freshness paper now has a public benchmark beside our own Nyrivell pack.

## 1. The benchmark

| | |
|---|---|
| Source | FiscalQA Pro, "Temporal Misgrounding in Legal RAG" (arXiv 2608.09393), github.com/rosecymbler/fiscal-fr-bench. Data CC BY 4.0 |
| What it tests | 209 questions about the French tax code, each "as of" a date (1989 to 2025). The right answer is the value in the article version in force on that day |
| Corpus used | 33 articles in 911 versions, each valid from its start to its end. On every question's date, the version in force is FiscalQA's gold version (209 of 209) |
| Grading | FiscalQA's own rule, copied exactly: every required "nugget" (the article number and the value, within a tolerance) must appear. No AI judge |
| Prompt | FiscalQA's own system prompt and user message |

## 2. Our run (Finebase HQ, real infra)

Claude Haiku 5.5, three seeds, 1,272 answers, $0.68. Gates passed: canaries 100%, evidence reached 94% under C0. Both labs torn down.

| Metric (627 answers each) | C0 plain retrieval | C1 each version ends on its date |
|---|---|---|
| States only the right value | 40.0% | **97.8%** [96.3, 98.7] |
| States the right value (FiscalQA's strict score) | 66.2% | **99.5%** |
| States another date's value only (stale) | 16.0% | 0.0% |
| States the right value and an old one (mixed) | 26.2% | 1.7% |

| Hypothesis | Verdict |
|---|---|
| H1: C1 cuts stale answers by at least 10 points | Supported: −15.9 points [−20.7, −11.5], p < 0.0001 |
| H2: C1 states only the right value at least 83% of the time (the paper's bar) | Supported: 97.8%, lower bound 96.3% |

## 3. Against the published figures

| System | Strict score |
|---|---|
| FiscalQA, current version only (static RAG), eleven models | 2.7% |
| FiscalQA, their version-aware retriever, eleven models | 98.3% |
| FiscalQA, the gold article given (upper bound), eleven models | 99.1% |
| **Finebrain C1, its own retrieval end to end, Haiku 5.5** | **99.5%** |
| Finebrain C0, every version kept, no dates | 66.2% |

## 4. What it means

1. **Valid time is the whole answer here.** With each version ending on its date, Finebrain's ordinary retrieval (S5, as of the question's date) matched the paper's best system, with its smallest model and no special retriever.
2. **Plain retrieval is not static retrieval.** C0 keeps every past version, so the model often sees several values: two answers in three contain the right one, but only 40% contain nothing else.
3. **Finebrain already chains versions by title.** Uploads with the same title become versions of one document, and the older one stops answering "now". The pack gives each version its own title so C0 stays plain; a third condition, "library versioning", could measure what that alone achieves.

## 5. Honest limits

| Limit | Note |
|---|---|
| Comparison | Their figures use eleven other models and their own pipeline; ours is one model through Finebrain. Same questions, same scorer, same prompt |
| C1 is given the dates | Each version's end date comes from Légifrance. Finebrain finding the change itself (C3) was not run: about 1,000 Opus conflict proposals, roughly $30 |
| Exposure | Public law text; FiscalQA's no-retrieval condition scores 3%, so memory alone does not answer |
| One model | A Sonnet 5.5 run (about $3) would sit closer to their Claude rows |

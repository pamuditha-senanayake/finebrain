# Memory that stays fast as it grows

> **Superseded on 2026-10-30 by `CB_Living_Memory_Architecture.md`.** The knowledge design below still holds and is folded into that doc. Read that one first.

Diagram: `Docs/CB_Memory_Architecture.drawio`

## The real problem

The brain will keep growing. Connectors bring new data every day, and it never stops. So size is not the enemy. The enemy is reading too much to answer one question.

If an agent walks one big folder, cost grows with the folder. If we cluster by topic, clusters multiply. Both fail for one reason. The work per question grows with total size.

So the goal is simple. The work per question must stay flat, even when storage grows for decades.

## The idea in one line

Classify everything once, on the way in. Then every question reads only a small, known slice.

## 1. Organize by four fixed axes, not by topic

Topics are open ended, so they explode. Axes do not. Every item gets four tags at intake.

| Axis | Example | How many |
|---|---|---|
| Tenant | Finebase HQ | One per company |
| Domain | Customer care, finance, legal | About 20, fixed |
| Entity | A customer, a project, a law | Grows, but each is one row |
| Time | Valid from, valid to | Always |

Entities are the heart of it. A customer is one node, not one folder. Everything about that customer links to it. This is the good part of tools like Obsidian. We keep the links, but we type them, like *customer has project*. Typed links are safe to follow. Free links invite agents to wander.

Clusters never explode, because a new customer adds one node. It never adds a new place to search.

## 2. Four tiers, each with a fixed budget

Data moves between tiers by value. Each tier has a cap in absolute numbers, never a percentage.

| Tier | Holds | Store | Searched |
|---|---|---|---|
| Hot | What is used now | Valkey and a hot index | Always first |
| Warm | Entities, links, current facts, summaries | Postgres with pgvector | By route |
| Cold | Closed facts, old detail | S3, compressed | Only for history |
| Raw | Originals, never edited | S3 | Never, audit only |

This answers the Pareto worry. Twenty percent of a trillion items is still too much. So we do not keep a percentage. We keep a fixed number per tenant, per domain and per entity. When a tier is full, the lowest value item moves down. The hot tier then grows with the number of active entities, not with history.

## 3. Pareto, made precise

Each item gets a value score every night.

> value = use × recency × risk × trust × links

Use counts how often answers cite it. Risk keeps a legal deadline even if nobody reads it. Trust favors verified facts. Links count what depends on it.

Then the summary ladder does the rest. Many raw events become one weekly summary. Many summaries become one fact. The fact stays warm. The detail goes cold. So each entity keeps one short page of what matters, and that page has a fixed size.

## 4. Retrieval never reads the folder

Every question follows the same path.

1. **Route.** Find the domain and the entities from the map. This is a cheap index lookup.
2. **Scoped search.** Search only those entity partitions, hot first. Follow typed links at most two hops.
3. **Rerank and fit.** Keep the best items inside a fixed token budget, about 6k tokens.
4. **Answer with citations.** The agent sees only that bundle.

Because the slice is bounded, the token cost per question stays flat. Indexes keep lookups fast as data grows.

## 5. The Distiller works every night

Growth is handled while people sleep. The Distiller scores items, merges duplicates and writes summaries. Next, it moves items to keep every tier inside its budget. Finally, it deletes raw originals when their retention ends.

## 6. Old, new, valid and invalid

Nothing is overwritten. A fact that stops being true is closed, not deleted. It gets a *valid to* date and moves to cold.

So "what is true now" reads only open facts in warm. "What was true in March" reads cold with an as of date. Invalid facts never pollute answers, yet history is kept.

## 7. One shared commons

Laws, market data and competitor news are the same for many tenants. So we store them once, in a shared commons, read only. Tenants link to them instead of copying them.

## 8. Versions, different fields, and trends

**Versions.** On upload, we fingerprint each document by title, entity and content. A close match joins the same version chain. Only the newest version is current.

**Different fields.** Every form maps to one core dictionary, like who, what, when, amount and outcome. Extra fields stay as tagged fields. So analysis always compares the core.

**Narrow first.** The AI turns a question into filters, like customer and dates, then searches that slice.

**Trends.** One table counts signals by entity, segment and week. Every night, a check finds unusual weeks and tells the owner. The Trends tab shows them.

## How this maps to what we built

| Piece | Status |
|---|---|
| Typed graph with versions (`graph_nodes`) | Built, S3 Route reads it |
| Bitemporal facts and as of search | Built in S5 |
| Chunks with pgvector, full text and rerank | Built in S5 |
| Access by tier and on behalf of | Built in S5 and S7 |
| Raw vault with retention | Built in S1 |
| Entity resolution at intake | Built in S2 (step 13a): payments, customers, uploads; text extraction comes with S12 |
| Tier budgets and value scores | Built (step 13c): value = use × recency × risk × trust × links, nightly; hot, warm and cold with fixed budgets; hot is searched first; cold keeps words only, its vector archived in S3 |
| Summary ladder | Built (step 13d): the Distiller writes day, week and month summaries per entity at 03:00 (Claude Haiku); forgetting a source clears them |
| Shared commons tenant | Built (step 13e): a collection stored once, read only; tenants link to it and S5 searches it beside their own items |
| Version chains | Built in S11 (step 14) |
| Field dictionary | Built (step 13d): every fact reads into who, what, when, amount and outcome; the rest are named extras |
| Four tags and narrow first | Built (steps 13a and 13b): domain and entity tags, scoped search with widening |
| Weekly signal counts and spike check | Built (step 15); the Trends tab shows them |

All of it is built (steps 13 to 15). The Distiller also merges duplicates of the same passage and ends raw bodies after 90 days.

## Starting numbers

First targets, tuned with real usage.

| Setting | Start at |
|---|---|
| Domains per tenant | 20 or fewer |
| Hot items per tenant | 100,000 |
| Warm summary per entity | 1 page |
| Link hops per question | 2 |
| Context per question | 6k tokens |
| Raw retention | 90 days, unless a rule says longer |

## In short

Classify once, keep a small valued slice hot, summarize the rest, and close what is no longer true. Then the brain grows for decades, and each answer stays small and fast.

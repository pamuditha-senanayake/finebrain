# Memory that stays fast as it grows

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

Because the slice is bounded, the token cost per question stays flat. Indexes keep the lookup cost close to logarithmic, so a hundred times more data adds very little time.

## 5. The Distiller works every night

Growth is handled while people sleep. The Distiller scores items, merges duplicates and writes summaries. Next, it moves items to keep every tier inside its budget. Finally, it deletes raw originals when their retention ends.

## 6. Old, new, valid and invalid

Nothing is overwritten. A fact that stops being true is closed, not deleted. It gets a *valid to* date and moves to cold.

So "what is true now" reads only open facts in warm. "What was true in March" reads cold with an as of date. Invalid facts never pollute answers, yet history is kept.

## 7. One shared commons

Laws, market data and competitor news are the same for many tenants. So we store them once, in a shared commons, read only. Tenants link to them instead of copying them.

## How this maps to what we built

| Piece | Status |
|---|---|
| Typed graph with versions (`graph_nodes`) | Built, S3 Route reads it |
| Bitemporal facts and as of search | Built in S5 |
| Chunks with pgvector, full text and rerank | Built in S5 |
| Access by tier and on behalf of | Built in S5 and S7 |
| Raw vault with retention | Built in S1 |
| Entity resolution at intake | Next, in S11 |
| Tier budgets and value scores | Next, in S13 nightly |
| Summary ladder | Next, in S12 and S13 |
| Shared commons tenant | Later |

The base is in place. Entity resolution, budgets and the Distiller come next.

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

Do not search everything. Classify once, keep a small valued slice hot, summarize the rest, and close what is no longer true. Then the brain can grow for decades while each answer stays small, cheap and fast.

# Engineering the graph and the memory

> **Superseded on 2026-10-30 by `CB_Living_Memory_Architecture.md`.** Kept for history only.

> **Section 1 is built; the rest is a proposal.** What runs today is in `CB_System_Reference.md`. Each change here lands with its own tests, then that file is updated.

## The problem

The graph holds many kinds of things: routing rules, skills, agents, policies, tools and workflows. When we think about them one by one, it gets confusing. So we need one simple way to organize them. We also need to see what is stored and why. Without that, nobody can trust what the brain answers.

## 1. Start from the action, then the owner

Your bank example is the right model. A customer asks for loan recovery, so the bank sends them to the loan recovery team. That team owns the case. They know the steps, the rules and the tools.

The graph should work the same way. First we name the action, like "refund a payment". In our code this is the activity. Next, each activity has one owner, which is an agent. Then the owner holds what it needs.

| Node | Question it answers | Example |
|---|---|---|
| Activity | What is being asked? | Refund a payment |
| Routing rule | How do we spot it? | "refund" in a chat |
| Agent (owner) | Who is responsible? | Refund agent |
| Skill | How is it done? | Find the order, check, refund |
| Policy | What are the limits? | 30 days, up to 100 dollars |
| Tool | What can it touch? | issue_refund |

Today a routing rule points straight at a skill and an agent. We should change one link. The rule should point to the activity, and the activity to its owner. Then a new way of asking for a refund needs only a new rule. The owner, skill and policy stay as they are.

**Built.** In Workflow Studio a workflow is the activity. Its graph node `wf_{activity}` names its owner agent, its one skill, its policies and the connections its sensors listen to. A rule names only the activity, and S3 reads the owner and skill from it. Studio writes one rule per connection, so every message on that connection reaches the activity. S5 gives the owner its activity's policies by key. Checked by `tests/test_activity_bdd.py` and `test_activity_real.py`.

## 2. Nobody reaches the graph from outside

The graph is never open to the outside. Every read goes through a stage, and every stage reads as an agent or a person. So every read carries their rights.

There are three locks. First, each tenant sees only its own nodes. Second, every item gets a sensitivity level, and a reader below it gets nothing. Knowledge items have one today; rules, skills and policies will get one too. Third, S5 and S7 check the agent's capabilities on every read. A denied read returns nothing and is logged. A test will prove that an agent without rights gets an empty answer.

## 3. Pick the valid version fast

Nothing in the graph is overwritten. A changed policy becomes a new version, and the old one gets an end date. Every version keeps two times: when it was true, and when we recorded it.

So every lookup is "as of a time". For a live refund, that time is now. For an audit, it is the day the refund ran. The lookup will read one index and take the newest version that started before that time. The skill version is also pinned at routing, so a change mid run cannot affect it.

## 4. Why a graph and not just a database

Our graph already lives in a database, in Postgres. So the real question is the shape, not the store.

A plain table design needs a new join for each new question. "Who owns refunds?" is one join. "Which policies limit this agent's tools?" is three. The graph model keeps every link typed and every node versioned, so any question is a short walk of one or two hops. We keep Postgres as the store and the graph as the model. A graph database is only worth it if our walks grow deep, and today they do not.

## 5. Where memory lives, and how we see it

The memory has four tiers, each with a fixed size.

| Tier | What it holds | Where | When it is read |
|---|---|---|---|
| Hot | What is used now | Valkey, hot index | Always first |
| Warm | Current facts, links, summaries | Postgres with vectors | By entity and domain |
| Cold | Closed facts, old detail | S3, compressed | Only for history |
| Raw | Original messages | S3, 90 days | Never, audit only |

Every night the Distiller scores each item by use, recency, risk, trust and links. Then it moves items to keep each tier inside its budget.

The gap is that nobody can see this. So we need two screens. The first is a memory inspector. For any customer or topic, it shows each item, its tier, its score, its valid dates, its source and why it moved. The second is the graph map, which we already have. We should center it on the activity and add a time slider, to show what was true on any day.

## 6. Answers use only what is true and relevant

Your report example shows the real risk. The model fills fields with recent or invented details, like a tech stack nobody stored. This has two causes. Retrieval picks by similarity, not by fit. Then the model fills the gaps by guessing.

So we fix both sides. Every output gets a field list, and each field says what it needs, like "projects finished this quarter". Retrieval then fetches items for each field, not for the whole page. Next, every value must cite a stored item. If nothing fits, the field says "not found", never a guess. S7 already checks citations, and we extend that check to every field. We also store each fact with its exact wording, its source and who verified it.

## 7. How we test it

1. **Golden questions.** Fixed questions with the items each must return. We measure what was found and what was missed.
2. **Tier moves.** Seeded items with known scores land in the right tier after a night.
3. **As of dates.** A question about March and the same one about today give different, correct answers.
4. **Access.** An agent without rights gets nothing.
5. **No invention.** Every answer field traces to a stored item.
6. **Volume.** Millions of items, while hot reads stay small and fast.

## The order

First, we put the activity at the center of the graph (done). Next, we add the access tests and the as of lookup. Then we build the memory inspector and the time slider. After that, we add field lists and the citation check for every field. Finally, we run the memory tests on real infra.

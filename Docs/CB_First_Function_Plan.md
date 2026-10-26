# Shipping the first real function

Scenario: `Refund_Happy_Path_BDD.pdf`, played with Amara on the Finebase Labs portal.

## Where we are

We built the front end first. Then we built a working skeleton behind it. Both looked good in demos. But when we tried to hand one real function to a customer, nothing was ready. The voice orb got better, yet it did not move the refund forward. So in the end it was decoration.

The refund BDD has 24 lines. We are still on line two. That is the real problem, and it is not a lack of effort. We kept asking big general questions before one small path worked. How should all tools work? How should every database connect? Those questions have no end. So this plan answers them only as deep as the refund needs.

## The rule from now on

One scenario, end to end, before anything else. Every task must turn one BDD line from red to green. If a task moves no line, it waits. The voice orb waits. New screens wait. This keeps the work small. It also keeps the proof real.

## The five building blocks

Before the plan, we need clear words. Most of our confusion came from mixing up five different things.

| Block | What it is | Who writes it | Where it lives | Can an agent change it? |
|---|---|---|---|---|
| Connection | Where a system lives, how to sign in, its named actions | The customer, through the Connect desk | Brain database, secrets in the vault | No |
| Adapter | How to talk to one kind of system, like Postgres or an HTTP API | Us, in Python | Git, deployed code | No |
| Tool | One safe action, like "find latest order" | Us, in Python | Git, deployed code | No |
| Skill | A recipe: which tools, in which order, with what wording | Us first, then the shop's staff | Workflow Studio, versioned | It can propose, a person approves |
| Policy | The rules and numbers, like 30 days and 100 dollars | The shop's staff | Workflow Studio, versioned | No |

Once we use these words, most of the open questions answer themselves.

## Your questions, answered

**Are tools Python files?** Yes. A tool is a Python function with a strict argument schema. We already do this in `tools.py`. The schema says what the agent may pass in. Then the function does the work and returns a plain result.

**Who generates them?** We do. Agents never write tools while running. A tool is code, so it goes through git, review and deploy like the rest of our code. That also answers how we make tools uneditable. Nobody can change a tool from inside the product. They can only use it.

**Do we need a tool per database?** No, and this is the key point. Tools say what to do. Adapters say how. Connections say where. So `find_latest_order` stays the same for every shop. Underneath, it calls an adapter. Supabase, Neon and RDS are all Postgres, so one adapter covers all three. Our `conn_db.py` is already that adapter. Firebase would need one more adapter, but only when a real customer asks for it.

**How does a tool know this shop's tables?** The connection holds a small mapping. It says where the orders live and which column holds the date. So the shop's shape is data, not code. The tool reads the mapping first. Then it builds one safe query from it.

**Should the brain write to their database?** Not directly. Our database door is read only on purpose, and we keep it that way. Instead, writes go through the shop's own API as named actions marked `writes: true`. This way the shop keeps control of its own data. The brain only asks.

**Where do skills and policies go?** Both are data in the brain, not code. A skill is a versioned recipe in Workflow Studio. A policy sits beside it as rules with numbers. The policy check itself is a plain Python tool. So the model never decides whether 40 dollars is under 100. Code does.

**How do we stop others from changing them?** We use three locks. First, code changes only through git. Second, skills and policies change only through a change request that the workflow owner approves, and every version is kept. Third, secrets sit in the vault and are never shown again.

## What we skip for now

The BDD names a Planner agent and a handoff between two agents. Both are good ideas for later. But with only one recipe, the Planner has nothing to choose from. So we start with one Refund agent that also does the chatting. The Planner and the handoff arrive with the second scenario. Long term memory notes come last, after the refund itself works.

## The plan in six milestones

Each milestone ends with a live proof in the browser. We use Amara on the portal, a real Stripe test charge, and a real test refund.

| # | Milestone | BDD lines | Done when |
|---|---|---|---|
| 1 | Chat connected | 1, 4, 11 | A portal message reaches the brain, and a reply goes back. Mostly done already. |
| 2 | Read the shop | 2, 9 | The desk shows Amara's latest order, read through the Postgres adapter |
| 3 | Policy as data | 3, 12, 13 | The policy tool passes a 10 day, 40 dollar order and fails a 40 day one |
| 4 | One agent, one recipe | 5 to 8, 10 | The Refund agent asks "Is it this order?" and waits for a yes |
| 5 | The write | 14 to 17 | A Stripe test refund runs, it is recorded, and the portal marks the order refunded |
| 6 | Close and show | 18 to 24 | Amara hears back, the chat is saved, a note is kept, and staff see it all on one page |

Milestones run in order, because each one stands on the last. Milestone 2 needs the connection from milestone 1. Milestone 5 needs the policy from milestone 3. So we never start one before the previous proof is green.

## How we keep moving

We keep one board with all 24 lines. Each line is red or green, nothing in between. Every Friday we count the green lines. If the count did not grow, we look at what pulled us away and stop it.

Each milestone also gets one owner. The owner decides small questions alone and writes them down in one line. Big questions go into a short call, never into a long thread. This way nobody waits for days on a choice that takes minutes.

## The one idea to remember

Build the narrowest real version of each line. Make it general only when a second real case shows up. One adapter, a few tools, one recipe and one policy are enough for the first refund. After that, the second scenario tells us what to generalise, and we let it.

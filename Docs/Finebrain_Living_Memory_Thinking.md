# Finebrain as a living memory: what we worked out

Date: 2026-10-30. This is a thinking record, not a spec. Nothing here is built unless the "Honest gaps" section says so.

## 1. Why this exists

The problem comes from the Claims document.

| Pain | In plain words |
|---|---|
| Know-how is not written down | It sits in heads, old Slack threads and tickets |
| Humans muddle through, agents cannot | An agent needs the rule stated, or it does nothing safely |
| Unknowns end in an action | Not "what is the rule" but "what do we do" |
| Staleness is a failure | The map drifts the moment the company changes |
| Search is not the goal | Something an agent can run is the goal |

The four papers: **Skills** (turn traces into runnable skills), **Policies** (detect and retire stale rules), **Security** (access checked when the agent acts), **Integration** (one system, beaten against retrieval baselines).

## 2. The pitch we settled on

> Finebrain is a living memory that employees, staff and customers can rely on. People decide what the company wants and make the hard calls. The brain makes sure everyone acts on what is true today. Nobody hunts for how things are done. A new hire is useful on day one. A customer gets the right answer at midnight. The brain handles the remembering and the keeping up, so your people are free to do what only people can: decide, create and care.

Lessons from getting here:

- Start from the pain people feel (they cannot trust AI with real work), not from the filing problem behind it.
- "Claude and ChatGPT don't know your company" is not valid. You can give them context.
- "Nobody tracks it" is not a pain people feel. Describe what life is like with it.
- Technical lines (role-based access, executable steps) sound like every AI tool. Leave them out of the pitch.
- Do not say refund, policy or skills in the pitch.

## 3. The boundary between people and the brain

**People own decisions. The brain owns truth and proof.**

| People | The brain |
|---|---|
| Say what the company needs | Remembers |
| Train and test the brain | Keeps the memory fresh and true |
| Make the hard calls | Watches for change |
| Create and care | Follows the limits people set |

A brain can be responsible for being correct and for keeping the record. A person must be accountable for a decision. If we say the brain is accountable, a panel will challenge it.

**The missing piece was the handover.** When the brain is unsure or the choice is risky, it stops and asks a person. The answer becomes permanent knowledge, so it never asks that question again.

## 4. Why we are different

### Why are you not Claude or ChatGPT?

They are the best at thinking and writing, and Finebrain works with them. But they only know what someone pastes into each chat. That copy goes out of date, and nobody can see where an answer came from. Finebrain is the company's living memory that any AI can use.

*They think. We keep what the company knows true, and we set the limits.*

### Why are you not an open-source company brain?

Most gather your files in one place so an AI can search them. That is a pile. When the company changes, old and new sit side by side and the AI can quote the old one. Finebrain retires the old way and keeps one answer that is true today.

*They store and search. We keep it true and make it safe to rely on.*

### What is the one different task?

**Keeping the memory true.** We watch what the company does, decide which rules still hold, and retire the ones that do not. Storing a rule is easy. Noticing it died last month is hard.

### The newer agents (checked on the web, 2026-10-30)

| Product | What it does | Where we separate |
|---|---|---|
| Claude Duet | Watches connected apps, remembers past chats, asks before acting | One vendor's personal agent |
| Grok Bots | Persistent memory, learns a task from one demonstration, team bots | Memory cannot be viewed, corrected or deleted |
| OpenAI Dots | Always-on agent | Details not verified |

The overlap is real. We separate on three things: any AI can use us, people can inspect and correct our memory, and we keep dated truth. The third is an absence in search results, not proof. Recheck before claiming it.

## 5. Why a brain, and why outside the model

**A brain turns what is happening into the right action at the right time.** Things that move must keep choosing. A company never stands still: rules change, people leave, things break. It needs a brain too.

The company has no shared brain. Each employee has one. What the company knows leaves when they leave.

**Three purposes of a company brain:**

1. One current truth.
2. Right action at the right time, with limits and a record.
3. Permanent learning that survives people leaving.

**Why a store outside the model:**

| Model limit | Why an outside store helps |
|---|---|
| Frozen at its training date | Today's truth lives outside |
| Cannot learn on the job | Update without retraining |
| Cannot forget one fact on demand | Retire a single rule |
| No private limits inside the weights | Access checked per action |
| Hard to see why it did something | An action record |

Models will get better at slow learning. A separate, inspectable memory still handles fast, controlled, private changes. The risk is models building in strong memory, so Finebrain must stay the place a company can inspect and control.

## 6. What we borrow from the brain

Borrow the principles, not the neurons (planes borrowed the wing shape, not the flapping).

| Principle | Use for Finebrain |
|---|---|
| Fast and slow memory kept apart | Fresh facts separate from settled ones |
| Forgetting what is stale | Retire old rules |
| Surprise gets attention | A change in behaviour signals a stale rule |
| Layered filtering: new? relevant? urgent? | Triage inputs |
| Specialised regions plus one coordinator | A few agents plus one planner |
| Winner of competing signals is broadcast | An attention queue |

Other fields worth studying: law (amend, repeal, apply by date), the immune system, organisational memory research, archival science and version control.

## 7. The reasoning layer (proposed, not built)

> **Superseded on 2026-10-30 by `CB_Living_Memory_Architecture.md`**, which turns this into areas, patterns, triage and three drift kinds.

The full picture is in `Finebrain_Architecture.drawio`: inputs, the five questions, specialist agents, memory, an attention queue, five outcomes, action, and the people loop. Green is built, blue is new, yellow is not checked.

**What it digitalises:** the silent step where a person makes sense of what just happened. They ask: what does this mean, is it normal, have I seen it before, does it matter, who should know? Today that is never written down.

**The few changes that matter most:**

1. Reason on every input and **store the why**, not only the result.
2. Compare each reasoning with similar past ones. Normal gets filed quietly. A surprise rises.
3. A few fixed specialist agents (clients, tasks, spend) each own an area. Raised items compete in one attention queue, and the winner goes to a person.
4. The person's answer becomes the new baseline.

**Five fixed outcomes, so it is never random:**

| Question | Leads to |
|---|---|
| What does this mean? | Pick the area |
| Is it normal? | **File** or **raise** |
| Seen before? | Reuse, or **update** what is true |
| Does it matter? | Set urgency, **ask a person** if risky |
| Who should know? | Route, or **do** it through a workflow |

**How to design it:** do not invent the questions. Collect real day-to-day situations (a message, a meeting remark, a quick question to a colleague). Write down what the person thought, why, and what they did. Cluster those into the question types and outcomes. Then test the architecture on the same cases. The Finebase list (A1 to A3 share one engine) is the first set.

## 8. Honest gaps

| Item | Status |
|---|---|
| Scoring skills against real work | Built |
| Storing and serving rules with valid dates | Built |
| Skill extraction from traces | Not built |
| Automatic stale-rule detection | Not built |
| Access checks per action | Built |
| Memory tiers and a graph | Not checked in code |
| Goal awareness, "tells the right people" | Not seen |
| Reasoning layer, attention queue, five outcomes | Proposed only |
| Competitor claims | From general knowledge and web search, not verified in depth |

## 9. The outreach pitch

This is the version we agreed for a message to an investor. It starts from the build, not from the fund.

> Hi [name],
>
> We are building Finebrain. AI can write and answer, but you cannot trust it with real work. It follows an old version of how things are done, so people end up checking every step.
>
> So we built a living memory that employees, staff and customers can rely on. It creates and updates what the company knows, and retires what is no longer true. Everyone acts on what is true today.
>
> People stay in charge. They set the goals, train it and make the hard calls. The memory does the remembering and the keeping up, so they can decide, create and care.
>
> We have been building since May, and we are still improving it. Is [fund] the right fit? Could we have a short call?

Rules we learned while writing it:

- Go from pain to need to pitch, in that order.
- Do not say "company brain". Every project uses it.
- Do not say "working product". Say "still improving".
- Do not open with "I saw your fund". Open with what we are building.
- Writing style: short sentences, a bridge between sentences, no hyphens and no em dashes.

## 10. Investor meeting: what fits and what does not

An investor offered a 30 minute Office Hours slot. It is advice for founders who have launched something and are stuck on one situation. It is not a pitch meeting.

| They expect | Where we stand |
|---|---|
| Skin in the game | Yes: built since May, questionnaire sent to companies |
| Something launched | Weaker: still improving, no real usage shown yet |
| One clear situation | Not yet written down |
| What we already tried | The questionnaire, and what its answers showed |

Their fund criteria, from the public post: at least six months on the product, talks with real customers, usage that shows how often people come back (sign-ups alone do not count), and B2B problems including AI, software and infrastructure.

**How to use the slot:** bring one situation, say what we tried, and ask for patterns ("Have you seen this before? How did it play out?"). Good questions: "Does this narrative make sense to an investor?" Bad questions: "What do you think of my idea?", "Should I raise now?", "Can you introduce me?"

**For any application form:** the country of incorporation must be the real one (the US LLC setup is still on the Finebase list), and a deck link is expected. An application without a deck looks unfinished.

## 11. Next steps

1. Collect real situations from Finebase staff and record the thinking behind each.
2. Run the A1 to A3 engine on one real meeting and check it with the people who do it by hand.
3. Check the code against the brain-job table to fill the "not checked" rows.
4. Name two real open-source company brains and compare before presenting.
5. Prepare one demo: a rule changes, and the answer changes with it.
6. Write the one situation brief with the questionnaire results (how many replied, what they said).
7. Run a literature search before claiming the combination is new, and decide if this becomes the Integration paper.
8. Make a short deck, so applications are complete.

## Sources

- [MacRumors on Claude Duet](https://www.macrumors.com/2026/10/21/anthropic-claude-duet/)
- [Claude Duet product page](https://claude.com/product/claude-duet)
- [Grok Bot guide, Codersera](https://codersera.com/blog/grok-bot-complete-guide-2026/)
- [Grok Bot breakdown, Vellum](https://www.vellum.ai/blog/official-grok-bot-breakdown)

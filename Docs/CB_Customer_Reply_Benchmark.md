# Customer replies: the benchmark

28 October 2026. How Finebase Labs answers a client today, what we measure, the baseline the brain has to beat, and how we test it. Job A1 and A5 in `[FBL] Finebase Priorities.md`.

## 1. The job

**Answer a client's message well and fast.** Four kinds cover most of it:

| Kind | Example | What a good reply needs |
|---|---|---|
| Status | "Any update?" | Where the project is, what is next, when |
| Clarification | "Can the form also take a phone number?" | A clear yes or no, the effect on scope or time |
| Payment | "Did you get the invoice payment?" | The fact from the books, the next step |
| New request | "Can you also build a dashboard?" | Thanks, the question that scopes it, who follows up |

Channels: Slack, WhatsApp, email, the website chat.

## 2. How it is done today, without the brain

| Step | Who | What happens | What goes wrong |
|---|---|---|---|
| 1 Notice | Whoever sees it | A message lands in one of four places | Seen late, or not at all |
| 2 Find the context | The project lead | Scroll the thread, the last update, the meeting notes, ask a teammate | Slow; the newest decision is often only in someone's head |
| 3 Draft | The lead | Type a reply | Tone and detail differ by person |
| 4 Check | Sometimes a second person | Read it for promises, prices, dates | Usually skipped when busy |
| 5 Send | The lead | Post it | |
| 6 Remember | Nobody | Nothing is recorded | The next "any update?" starts from zero |

## 3. The metrics

| # | Metric | How it is measured | Why it matters |
|---|---|---|---|
| M1 | First response time | Minutes from the client's message to our first reply (median and 90th percentile) | What the client feels first |
| M2 | Missed messages | Share of messages with no reply within 24 hours | The quiet failure |
| M3 | Human minutes per reply | Hands-on minutes: finding context, drafting, checking | The cost to us |
| M4 | Quality | A reviewer scores each reply 1 to 5 on four points: correct, complete, tone, clear next step. Scored without knowing who wrote it | Fast but wrong is worse |
| M5 | Mistakes | Replies with a wrong fact, price, date or an unapproved promise | The risk |
| M6 | Preference | Shown our reply and the brain's side by side, unlabelled: which would you send? | "Do people choose the better one" |
| M7 | Client satisfaction | One question after the thread closes: "Was this helpful?" (thumbs or 1 to 5) | What the client thinks |
| M8 | Sent as drafted | Brain drafts approved without edits (with the brain only) | How much a person still has to do |
| M9 | Cost per reply | Model spend per reply, in USD (with the brain only) | Must stay small |

## 4. The baseline to beat

The baseline is **our own manual numbers**, measured, not guessed. M1 and M2 come straight from timestamps; M3 to M5 need a short log.

| Metric | Baseline (manual) | Target for the brain |
|---|---|---|
| M1 First response time | Measure | Half of today's median, under 10 minutes in working hours |
| M2 Missed messages | Measure | 0% |
| M3 Human minutes per reply | Measure | Under a third of today's |
| M4 Quality | Measure | No lower than today (within 0.2 points) |
| M5 Mistakes | Measure | No higher than today; zero unapproved promises |
| M6 Preference | 50% by definition | At least 50% (as good), aim for 60% |
| M7 Satisfaction | Measure | No lower than today |
| M8 Sent as drafted | Not applicable | At least 70% |
| M9 Cost per reply | 0 | Under $0.05 |

Targets are proposals. Fix them before the first test run, as the Lab does with preregistration.

## 5. Getting the baseline: two ways

| Way | What you do | What it gives | Time |
|---|---|---|---|
| A From history (start here) | Export the last 30 days of one client's Slack channel or WhatsApp chat | M1 and M2 at once, and the frozen test set for M4 to M6 | 30 minutes |
| B One week of logging | Each time someone replies, they add one row (below) | M3 and M5, which history cannot show | 1 minute a reply |

Log row, one per reply:

| Time in | Channel | Client | Kind | Replied at | Hands-on minutes | Who | Needed to ask someone? | Notes |
|---|---|---|---|---|---|---|---|---|
| 10:02 | Slack | (client) | Status | 11:40 | 12 | (name) | Yes: the lead dev | Had to check the staging link |

*(An example row, not real data.)*

What the brain already logs on its side, for every reply on the website chat (a real record from our test chats on 26 October):

| Field | Value |
|---|---|
| Conversation | `conn_landing_chat:98c75662-…` |
| By | agent (`landing-assistant`) |
| Run | `run_b65beeb4a510`, with its full trace |
| After | the client message it answers (`sig_554b2ae4de47`) |
| At | 2026-10-26 17:44:54 |

Today HQ holds only 16 such messages, all from our own tests, so they show the log format but are not a baseline.

## 6. The test set and how we test

From the export, freeze **30 real client messages** and the reply we actually sent: the common kinds, plus the hard ones (an unhappy client, a payment question, a scope change).

| Stage | What runs | Who is affected | Cost |
|---|---|---|---|
| 1 Replay | The brain drafts a reply to each of the 30, from the context we had that day. A reviewer scores both blind (M4 to M6) | Nobody; offline | About $0.40 in model calls |
| 2 Shadow | For one week, the brain drafts for every live message; a person still writes and sends their own | Nobody; drafts are only compared | About $1 to $3 a week |
| 3 Assisted | The brain drafts; a person approves, edits or rewrites; then it is sent | Clients get approved replies | Same |
| 4 Rules | Low-risk kinds (status with a fresh update) may send on their own; payments and new requests always need approval | | Same |

Move to the next stage only when the current one meets its targets. Every reply the reviewer marks 1 or 2 becomes a new scenario in the test set, and the set is rerun after every change.

## 7. What is missing in the product

| Gap | Needed for |
|---|---|
| Slack and WhatsApp connections | Stages 2 to 4 for those channels (only the website chat is live) |
| Project context: last update, open tasks, meeting notes | Good status replies (the A2 and A3 engine) |
| A thumbs or one-question rating on each reply | M7 |
| A blind review screen: two replies, pick one, score 1 to 5 | M4 and M6 |
| A small benchmark page: M1 to M9, manual against brain, week by week | Seeing progress |

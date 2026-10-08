# Company Brain Console: Frontend Build Brief

Version 2, 8 October 2026. Owner: Pamuditha, Finebase Labs. Reader: the coding agent building the frontend.

## 0. How to work with this brief

Read the whole brief before writing any code, because later sections build on earlier ones. Then complete Phase 0 from section 13, which produces a plan and no code, and stop for my review. Once I approve, build phase by phase and check each phase against the definition of done in section 14. Whenever something here is ambiguous or contradicts itself, ask me instead of guessing, and record the question under "Open questions" in `PLAN.md`.

## 1. What we are building and why

Finebase Labs sells software services, meaning custom development projects and support retainers, and SaaS products on subscription. Today humans run most of the operations around them: customer care chats, refund cases, website content updates, meeting arrangement and more. We are building a Company Brain, a governed layer where AI agents do this work using company knowledge made legible to them, under policies and security that humans control.

The Finebase platform, where we sell and manage our services and products, is only one part of the business. For that reason the brain is a hub with clusters. The Finebase Platform is the first cluster we connect, a thin Finance and Compliance cluster comes with it so the brain can protect the entity, and other clusters will connect later in the same way. Finebase Labs is also only the first tenant, since the product will later serve any business, so nothing Finebase specific may be hard coded.

This is an end to end, production grade application rather than a prototype. The frontend comes first and runs on mock data, yet it must be built so the real backend can replace the mocks without rewriting screens. Our research program also uses this product as its testbed, but that lives in a separate console (section 10), and the product must stand on its own.

Three ideas from our reference material shape the product, and each one appears in the screens below.

1. **Every function is a loop.** Sensor, then policy, then tool, then quality gate, then learning, and back to the sensor. A loop that runs with little human intervention keeps improving, even overnight.
2. **The brain is a library plus a librarian.** Retrieval is easy, while being worth retrieving from is the product. That requires provenance on every fact, contradiction checks when new information collides with old, and active pruning.
3. **Humans live at the edge.** They provide evidence, approve consequential changes, and handle novel, ethical and high stakes cases. Every object has exactly one named DRI (directly responsible individual), never a committee.

## 2. The mental model, borrowed from ChainSight

We previously built ChainSight for the District Secretariat, Divisional Secretariats and EDOs, with a separate dashboard per level. This product keeps that separation with one decisive change: the field workers are now agents. If the ChainSight repository is available in this workspace, study it for concepts and structure only; otherwise ask me where it is.

| ChainSight | Company Brain | What changes |
|---|---|---|
| District, the whole program of 11 divisions | The Company Brain of one tenant | Sees every cluster at once |
| A division | A cluster | Finebase Platform is cluster one, and others plug in the same way |
| District Secretariat dashboard | L1 Command | Leadership view of progress, risk, approvals and evidence |
| Divisional Secretariat dashboard, holding templates and assignments | L2 Governance | Still holds templates and assignments, and now also skills, policies and security |
| EDO dashboard | L3 Operations floor | Agents are the workers, while humans watch and step in |
| EDO training, done outside the system | Agent Academy, inside the product | Skills are given, tested, improved and certified here |
| Return templates the EDOs fill | Information templates | Define what each agent must bring back, from which sensors, and how fresh it must be |

Reuse ChainSight's tier separation, its template and assignment model, and its role guards. Do not reuse its visual design or its low coverage optimizations, because ChainSight served field officers on weak connections while this product serves large companies working on desktops with dense, live data.

## 3. Who uses each tier

**L1 Command** belongs to humans at the top: founders, directors and DRIs. They follow progress and risk across clusters, approve high criticality changes, provide documents of proof when the system asks, and grant access to new data sources. L1 is the root of authority, which is why new skills, new policies and security changes always end here.

**L2 Governance** is run by human stewards (knowledge steward, AI operations lead, security officer) working with supervisor agents. Supervisor agents review L3 runs, mostly overnight, classify failures and draft fixes as change requests. The stewards review those drafts, author skills, policies, templates and sensors, and approve changes up to their criticality ceiling. The model follows our reference material: a **skill** is an employee's documented capability, the **resolver table** is the org chart that routes each task to a skill, **filing rules** decide where new knowledge is stored, and **trigger evals** are performance reviews that prove the right skill fires.

**L3 Operations floor** shows worker agents doing the actual work. Agents themselves work through APIs, not this UI, so these screens exist for human operators who watch agents live, inspect any run, take over a conversation and resolve escalations.

For development and demos, add a role switcher that impersonates any persona, and strip it from production builds. Seed these personas: on L1 a founder, a finance director and a head of customer success; on L2 a knowledge steward, an AI operations lead and a security officer; on L3 a customer care operator.

## 4. Product principles

These rules hold on every screen, so treat them as acceptance criteria rather than suggestions.

1. **Ground truth first.** Every fact carries its source evidence, when it is true in the world (valid time), when the system learned it (recorded time), who verified it, and what depends on it. Everything else is built on ground truth, so changing it is always high criticality.
2. **Nothing goes live blind.** Before any change reaches production, the system shows its effect: a replay against recent real runs, a before and after diff, and the predicted risk. Only then does it ask for approval.
3. **Approval weight follows criticality.** Routine work flows automatically and is logged, while consequential work stops for the right human (section 7).
4. **Security binds at the moment of action.** Unauthorized agents cannot reach restricted skills, policies or data, and every agent action records the access check that allowed or denied it. When an agent acts for a human, it can never do more than that human may do. Personal data is masked by default, and every reveal is permissioned and audited.
5. **The system protects the entity.** It knows which information and documents it needs and by when, notices gaps early, and either sends an agent to fetch what is missing or asks the responsible human well before a deadline.
6. **Never do one off work.** Any case a human resolves can become a draft skill with one action, "Skillify".
7. **Software is disposable, data is durable.** Every screen reads through typed data contracts. The contracts and the data are the asset, and the UI should stay easy to regenerate.

## 5. Activity catalog (seed data)

These are the operations the agents take over first. Use them as seed data, and propose additions in `PLAN.md`.

| Cluster | Activity | Agent | Sensors (inputs) | Template it fills | Default criticality |
|---|---|---|---|---|---|
| Finebase Platform | Customer care chat and email | Care Agent | Chat widget, support inbox, product usage events | Weekly care report | C0 answers, C2 goodwill credits |
| Finebase Platform | Refund and cancellation requests | Refund Agent | Support inbox, billing events | Refund register | C2 inside policy, C3 outside policy or above threshold |
| Finebase Platform | Subscription billing and failed payment recovery | Billing Agent | Payment gateway webhooks | Revenue health | C1 reminders, C3 write offs |
| Finebase Platform | Quotes and proposals for service projects | Sales Agent | Lead forms, email | Pipeline report | C3 outside the rate card |
| Finebase Platform | Lead qualification and follow up | Sales Agent | Forms, chat, email | Pipeline report | C1 |
| Finebase Platform | Meeting arrangement for demos, discovery calls and sprint reviews | Scheduler Agent | Calendars, email, booking page | Meeting log | C1 |
| Finebase Platform | Meeting notes to action items | Scheduler Agent | Meeting transcripts | Action log | C1 |
| Finebase Platform | Client onboarding for service projects | Onboarding Agent | Signed contracts, CRM stage changes | Onboarding checklist | C2 access grants |
| Finebase Platform | Retainer SLA tracking and client status reports | Delivery Agent | Project tracker, repository activity, uptime monitor | Client status report | C2 client facing |
| Finebase Platform | Website content and release notes | Web Content Agent | CMS, content requests, product releases | Content change log | C2 general pages, C3 pricing and legal pages |
| Finebase Platform | UX improvement experiments | Insights Agent | Microsoft Clarity (rage clicks, dead clicks, scroll depth), click sensors, analytics | Experiment report | C2 to propose, C3 to ship on pricing or checkout |
| Finebase Platform | Reviews, NPS and public feedback replies | Reputation Agent | Review sites, NPS surveys | Voice of customer report | C2 public replies |
| Finebase Platform | Outage communication | Incident Agent | Uptime monitor, error tracker | Incident report | C3 public statements |
| Finance and Compliance | Tax and statutory obligation readiness | Compliance Agent | Obligations calendar, accounting exports, finance inbox after permission | Obligation readiness | C4, since the system prepares and collects proof while humans file |
| Finance and Compliance | Renewals for contracts, vendor subscriptions, domains and SSL | Compliance Agent | Contract vault, vendor invoices, certificate monitors | Renewal register | C3 |
| Finance and Compliance | Receivables chasing for service invoices | Billing Agent | Invoices, bank feed | Receivables aging | C1 reminders, C3 disputes |
| Finance and Compliance | Expense and receipt capture | Billing Agent | Finance inbox, card feed | Expense log | C1 |
| Brain wide | Personal data requests for access or deletion | Care Agent with Security Sentinel | Support inbox | Data request register | C4 deletion |
| Brain wide | Access reviews | Security Sentinel (L2) | Access graph, invocation log | Access review | C3 changes |
| Brain wide | Knowledge freshness and conflicts | Librarian (L2) | All sources | Freshness report | C3 ground truth changes |
| Brain wide | Overnight failure review and fix drafting | Quality Supervisor (L2) | All L3 runs | Improvement digest | Inherits each change's criticality |

Seed obligations in Finance and Compliance should feel Sri Lankan, for example VAT, income tax instalments, APIT, EPF and ETF contributions and the company annual return. Every date and rule in seed data is sample data, must be labeled as such, and must never read as legal or tax guidance.

## 6. Screens

The three tiers get separate dashboards with their own navigation, while sharing one design system and one data layer. The shell comes first because every tier inherits it.

### 6.1 Global shell

* Tenant and cluster switcher, with planned clusters shown as placeholders so the hub structure is visible from day one.
* An environment banner nobody can miss: Production, Staging or a named Sandbox branch.
* Command palette (Cmd+K) for navigation, entity search and actions.
* Notification center, an approvals counter, and an "Ask the Brain" panel that answers in plain language with inline citations, shows when each cited fact is true, and uses only what the asker may see.
* A "Demo data" badge whenever the app runs on mocks.
* Loading, empty, error and permission denied states on every list and detail view.

### 6.2 L1 Command

1. **Brain overview (home).** Clusters with live health, autonomy rate (work finished without a human), escalation rate, money at stake, open risks, and cost per resolved task. A legibility map crosses every activity with four checks (sensed, skilled, governed, reported) and shows which parts of the business the brain still cannot see.
2. **Morning digest.** What happened overnight: runs, failures found, fixes applied automatically at C0 and C1, and changes waiting for a decision.
3. **Approvals inbox.** Sorted by criticality and deadline. Each item shows a plain language summary, the semantic diff, the impact preview, test results, evidence, the drafter and the DRI, with approve, reject, request changes and delegate. C4 items enforce the two person rule. The inbox must work well on a phone.
4. **Entity protection.** For the legal entity: an obligations calendar covering tax, statutory filings, contracts and renewals, with readiness, missing evidence, countdown and DRI per obligation, plus a risk register.
5. **Evidence requests.** When the system needs proof, the DRI uploads documents or grants a data source. A grant, for example read access to the finance inbox, shows its scope, retention, the agents that will use it and how to revoke it before anything is granted.
6. **Progress and analytics.** KPIs per cluster, loop performance, experiment outcomes and template completion.
7. **Audit trail.** Read only and filterable by actor (human or agent), object, environment and criticality.

### 6.3 L2 Governance

1. **Knowledge graph explorer.** The agent traversable graph holding skills, policies, security rules, sensors, templates, facts, documents, agents and tools, with access constraints embedded in nodes and edges. Layer toggles filter node types. A "view as" selector shows exactly what one agent or human can reach, and restricted nodes appear locked with the reason, for example "requires finance read at restricted level, agent holds internal level".
2. **Versioning.** Git for the graph: branches, commits, semantic diffs, change requests, merge, rollback, tags and per node history. Section 8 has the detail.
3. **Library and filing rules.** Every ingested source and document, organized by cluster, type and sensitivity, with extraction status, linked facts and retention. Filing rules decide where new material lands.
4. **Ground truth vault and librarian queue.** Verified facts with provenance and dependents. The queue holds conflicts, stale facts, duplicates, orphan documents and unverified claims. When facts collide, the librarian proposes which source wins and the new validity interval, lists every dependent skill, policy, template and web page, and bundles their updates into one change request.
5. **Policy registry.** Each policy version carries valid from, valid to, recorded at and superseded by. A timeline shows each version's validity, and an "as of" slider answers two questions for any date: what was true, and what the system believed then. Five freshness signals warn that a policy may be going stale: its validity interval closed, observed behaviour shows a drift point, the documented policy matches observed runs less well, newer evidence conflicts with it, or more answers rely on outdated policy. Signals create invalidation proposals, and nothing is invalidated without approval at the matching criticality.
6. **Skills studio and Agent Academy.** A skill editor covering trigger, inputs, steps, tools, governing policies, required capabilities, outputs and the template fields it fills. Eval suites run in a sandbox, and skill health shows task success, consistency across repeated runs, and how closely the skill matches the way work is actually done in observed runs. Agents move through autonomy levels (trainee, supervised, autonomous), and each promotion follows the criticality matrix.
7. **Resolver.** The routing table that maps incoming events and tasks to agents and skills, with trigger evals proving the right skill fires.
8. **Templates.** Information contracts with fields, source sensors, freshness rules, required evidence, cadence, owner and assigned agents.
9. **Sensors and connections.** Every connected system per cluster (website events, Microsoft Clarity, analytics, inboxes, chat, payments, calendars, CRM, documents) with health, subscribers, scopes, retention and a personal data flag. A sensor planting overlay loads a preview of our website, lets a steward click an element to attach a sensor (event name, properties, privacy flags) and choose the loops and agents that subscribe. Its output is a tracking plan, not a live integration.
10. **Loops.** A canvas per loop with its sensor, policy, tool, quality gate and learning stages, live metrics per stage, run history, pending gates and experiments. Each experiment shows its hypothesis, variants and whether its impact was positive or negative.
11. **Readiness scheduler.** Rules that check whether enough information exists for each obligation, template and loop by comparing what is required with what exists. Each gap offers three actions: dispatch an agent to fetch it, request it from the DRI, or request permission to a new source. Requests start early and escalate as deadlines approach.
12. **Security and access.** Human roles and attributes, agent capability grants, connector scopes, and an invocation decision log with every allow and deny, the principal, on whose behalf it acted, the deciding rule and the latency.

### 6.4 L3 Operations floor

1. **Fleet view.** Every agent with live status, queue depth, throughput, errors and cost, in a dense table and a grid that both handle hundreds of agents.
2. **Agent profile.** The agent's job description: what it watches (sensors), how it works (skills and versions), which rules govern it (policies), what it may do (capabilities), what it must return (templates), its autonomy level, performance and training history.
3. **Run trace viewer.** A step timeline that labels every step as either model judgment or deterministic tool call, with retrieved facts and their valid time, access checks with their decision, quality gate outcomes, outputs, filled template fields, cost and latency.
4. **Live conversations.** Customer care transcripts stream in with the agent's reasoning summary and proposed actions. A human can take over, hand back, and then press "Skillify" to turn the handling into a draft skill on a new branch.
5. **Escalations queue.** Sorted by risk and waiting time, with the reason the agent stopped.
6. **Template board.** Which templates are complete, partial or stale, which agents filled them, and from which sources.

## 7. Criticality and approvals

Criticality decides who approves, how much proof is required and how fast a change can move. Every threshold is configurable per tenant.

| Level | Meaning | Examples | Approver | Required before approval |
|---|---|---|---|---|
| C0 Routine | Reversible, internal, inside an approved skill | Logging, refreshing a template field from a verified source | Automatic and logged | Nothing |
| C1 Low | Small, reversible, not customer facing | FAQ wording, resolver synonyms | L2 supervisor agent, steward notified | Passing tests |
| C2 Medium | Changes how work is done | Editing steps of an existing skill, website copy outside pricing and legal pages | L2 human steward | Sandbox tests |
| C3 High | Money, customers, public content or ground truth | Any new skill or policy, refund and pricing rules, pricing pages, ground truth changes, new data scopes | L1 DRI | Impact preview and replay |
| C4 Critical | Legal, tax, security or irreversible | Tax evidence sign off, security role changes, granting inbox access, deleting ground truth | Two L1 approvers | Impact preview, replay and an optional cooling period |

L2 may draft at every level but approve only up to C2. A change that touches money, personal data, public content, legal or tax matters, or more than one cluster moves up one level. Every request carries a deadline, expires if nobody answers, and can be delegated but never silently skipped.

## 8. Versioning, environments and simulation

The graph that stores skills, policies and security behaves like a git repository, because versioned, testable change is what makes the core reliable.

* **Commits.** Every change is a commit with an author (human or agent), a message, a criticality and linked evidence.
* **Branches and environments.** `main` is Production. Staging runs a candidate in shadow mode on live traffic without acting on it. Each Sandbox is a branch tested against recorded runs.
* **Change requests.** Each one shows a plain language diff ("refund window changes from 30 to 14 days, valid from 1 November") beside the structured diff, plus test results, an impact preview ("37 of the last 412 refund conversations would get a different decision") and the approvals it needs.
* **Merge, rollback and tags.** Merging deploys to Production. Rolling back to any commit first shows what will revert and which dependents are affected. Releases are tagged.
* **Conflicts.** When two branches change the same node, a resolution view shows both sides with their evidence.

## 9. Data contracts and seed data

Write the contracts in zod as the single source of truth, infer the TypeScript types from them, and generate an OpenAPI document for the backend team. The sketch below lists the minimum fields only, so treat it as a starting point and extend it in `PLAN.md`.

```ts
// Sketch, not compilable. Minimum fields per entity.
type Criticality = 0 | 1 | 2 | 3 | 4
type Env = "production" | "staging" | "sandbox"
type VersionRef = { id: string; version: number; branch: string }

Tenant        { id, name, currency, timezone, locale, brand, clusters, criticalityThresholds }
Cluster       { id, name, status: "active" | "planned", connectors, dri }
Human         { id, name, tier: "L1" | "L2" | "L3", roles, attributes, driOf }
Agent         { id, name, kind: "worker" | "supervisor", autonomy, skills: VersionRef[], capabilities, sensors, templates, status, dri }
Skill         { id, version, trigger, inputs, steps, tools, policies, requiredCapabilities, outputs, templateFields, evalSuite, health, dri }
Policy        { id, version, statement, rule, criticality, validFrom, validTo, recordedAt, supersededBy, evidence, freshnessSignals, dri }
Fact          { id, statement, value, validFrom, validTo, recordedAt, evidence, verifiedBy, status, dependents }
Document      { id, source, cluster, type, sensitivity, extractionStatus, linkedFacts, retention }
AccessRule    { id, appliesTo, requiresRoles, requiresAttributes, requiresCapability, sensitivity }
Sensor        { id, source, events, subscribers, health, scopes, retentionDays, personalData }
Template      { id, fields, cadence, owner, assignedAgents, freshnessRule }
Obligation    { id, title, jurisdiction, dueAt, prepareBy, requiredEvidence, readiness, dri, isSample }
Run           { id, agent, skill: VersionRef, env, steps: TraceStep[], outcome, escalation, costTokens }
TraceStep     { kind: "judgment" | "tool" | "retrieval" | "access_check" | "quality_gate" | "human", decision, reason, durationMs }
Commit        { id, branch, author, message, changes, criticality, createdAt }
ChangeRequest { id, fromBranch, toBranch, commits, impactPreview, tests, approvals, status }
Approval      { id, subject, criticality, requiredApprovers, dueAt, status, delegatedTo }
Loop          { id, sensors, policies, tools, gates, experiments, metrics, dri }
AuditEvent    { id, at, actor, action, target, env, criticality }
```

The seed generator must be deterministic, so the same seed produces the same data on every run. It creates two tenants. **Finebase Labs** is realistic and small: about 12 worker agents, 3 supervisor agents, the two active clusters plus three planned placeholders such as People, Product Engineering and Procurement, LKR as currency and Asia/Colombo as timezone. **Scale Demo** is a stress tenant with hundreds of agents, tens of thousands of runs and thousands of graph nodes, and it proves the UI holds up for large companies. A mock event stream then pushes new runs, status changes and approvals, so the product feels alive during development.

## 10. Research Console (separate and removable)

The product doubles as the testbed for our four paper program on skills, policies, security and integration. Research must never leak into the main flows, so it lives in its own console that we can delete later without touching the product.

* It has its own route group and feature folder, one feature flag and a dedicated research role. Product code never imports from it, it reads the shared data layer through read only queries, and a lint rule enforces that boundary.
* Version one is monitoring only, with no experiment controls and no writes. Per paper it shows:
  * **Skills:** how closely each skill matches observed runs, the gap between documented procedure and observed behaviour, task success, and consistency across k repeated runs (pass^k).
  * **Policies:** the five freshness signals in aggregate, the rate of actions taken under expired policy, drift detection recall, delay and false positives, and whether "as of now" queries return the current version.
  * **Security:** leakage rate under combined role and attribute rules, compared with a retrieval time filtering baseline when that condition runs, plus attempted and denied unauthorized invocations and enforcement latency.
  * **Integration:** task completion against a retrieval only baseline, pass^1 and pass^8, and stale answer rate per experimental condition.
* It exports snapshots as CSV and JSON with metric definitions and timestamps, and it keeps an import adapter stub so results from our research execution repository can be loaded later.
* Until it connects to real experiment output, every value is labeled SAMPLE, and sample values can never be exported as results.
* With the flag off, its routes, navigation entries and bundles disappear completely.

The product itself still shows freshness signals per policy and health per skill, because those are customer features. The console only aggregates the same events into research metrics.

## 11. Design direction

The product manages large companies, so the look is a calm command center: dense yet legible, precise, and quiet until something needs attention. Design desktop first from 1440 pixels, keep it fully usable on tablets, and make L1 approvals and evidence requests comfortable on phones. Light and dark themes share one token system. Production and Sandbox must never be confused, so each environment gets an unmistakable color treatment, and criticality levels C0 to C4 use one consistent color scale everywhere.

Motion must carry meaning, so each special effect means exactly one thing and nothing else may use it.

| Source | Meaning in this product | Use on | Never use on |
|---|---|---|---|
| Thinking Orbs (`thinking-orbs`, now on libraries.dev) | An agent is working, and what kind of work | Agent avatars, run headers, Ask the Brain | Idle agents, which get a static dot |
| Border Beam (`border-beam`, now on libraries.dev) | Live and needs attention now | A running run, an approval waiting on the current user, an active sandbox test | More than three elements per screen |
| Liquid Metal (`metal-fx`, now on libraries.dev) | Irreversible commitment | "Approve and merge to Production" and "Grant access" at C3 and C4 | Any other button |
| Canvas UI (canvasui.dev) | The brain's ambient presence | L1 Brain overview hero, sign in, empty states | Tables, forms and dense views |
| Beautiful UI (beautifului.dev) | Human in the loop primitives | Approval cards, diff tables, task rows, tool chips, context cards, agent screen | None |
| AICSS (aicss.dev) | Agent conversation states | Thinking, streaming text, inline citations, tool calls, file diffs | None |
| transitions.dev | Standard interface motion | Menus, modals, panels, toasts, tabs, number changes, success and error states | None |
| Originkit (originkit.dev) | Extra animated components | Only where shadcn has no equivalent | Marketing flourishes on operational screens |
| Agentation (agentation.com) | Development feedback, not a product feature | A dev dependency so I can annotate screens for you, and the inspiration for the sensor planting overlay | Production builds |

These libraries come with constraints that the plan must respect.

* Canvas UI draws live HTML through WebGL or WebGPU, which today needs an experimental Chrome flag, and elsewhere it falls back to plain HTML. Treat it as progressive enhancement and make sure every screen looks complete without it. Its license is MIT with the Commons Clause, which allows use inside our product but not resale of the components.
* AICSS and transitions.dev include paid Pro items. Use only the free items and never recreate a Pro component unless we buy a license. Use Beautiful UI's MIT approval card instead of the paid one.
* Lazy load every WebGL and canvas effect, pause it off screen, allow at most one ambient WebGL surface per screen, and switch all ambient motion off under `prefers-reduced-motion`.
* Keep the motion score from `npx transitions-agent` at 75 or above.

In Phase 0, propose the visual direction (palette, type scale, density and motion tokens) with one mock screen per tier before building anything else.

## 12. Tech stack and architecture

* Next.js with the App Router (latest stable), React, strict TypeScript, Tailwind CSS, shadcn/ui, and Motion for layout animation.
* TanStack Query for server state, Zustand for UI state, and TanStack Table with virtualization for large tables.
* React Flow (`@xyflow/react`) for loop canvases and branch graphs, Sigma.js with graphology for the large knowledge graph, and shadcn charts (Recharts) for metrics.
* zod contracts, a typed API client and MSW mocks, so moving to the real backend is a configuration change.
* An auth adapter with a mock provider now and SSO later, and a live events adapter with a mock stream now and SSE or WebSockets later.
* Route groups per tier, such as `app/(l1)`, `app/(l2)` and `app/(l3)`, plus `app/(research)` for the console. Shared code lives in `components`, `features`, `contracts`, `lib/api` and `lib/mock`.
* Typed feature flags, internationalization ready with English first, an error reporting adapter, and no secrets in the client.
* Vitest with Testing Library for units, and Playwright for flows and screenshots.

## 13. Build phases

1. **Phase 0, plan only.** Read this brief and ChainSight, then write `PLAN.md` with the route map, the screen list per tier, a component inventory naming the source of each component, the contracts, the seed plan, the visual direction, any activities you would add, and open questions. Stop for my approval.
2. **Phase 1, foundation.** Tokens, themes, the shell per tier, role switcher, contracts, mock API, seed generator, mock event stream, feature flags, command palette, notifications, environment banner and audit plumbing.
3. **Phase 2, governance core.** Graph explorer with "view as", versioning, the criticality engine with the approval pipeline, and the impact preview. Stop for my review.
4. **Phase 3, L2 studios.** Library, ground truth vault and librarian queue, policy registry, skills studio and Academy, resolver, templates, sensors with the planting overlay, loops, readiness scheduler, security and access.
5. **Phase 4, L3 operations floor.** Fleet, agent profiles, run traces, live conversations with takeover and Skillify, escalations and the template board.
6. **Phase 5, L1 command.** Brain overview, morning digest, approvals inbox, entity protection, evidence requests with connector consent, analytics, Ask the Brain and the audit trail.
7. **Phase 6, Research Console.** Separate, read only and removable, as section 10 describes.
8. **Phase 7, hardening.** Motion pass, accessibility audit, performance work, test coverage and the README.

At the end of every phase, summarize what changed, attach screenshots, and list every assumption you made.

## 14. Definition of done

1. `tsc`, lint and `next build` pass with zero errors, and the browser console stays clean.
2. Seven flows run end to end on mock data and are covered by Playwright tests.
   1. **Refund outside policy.** The Refund Agent escalates, a human takes over and presses Skillify, the draft skill is tested in a sandbox with replay, a C3 change request reaches the L1 DRI and is approved and merged, the new version goes live, and the audit trail shows every step.
   2. **Tax readiness.** Twenty one days before a sample VAT deadline, the scheduler finds missing proof and sends an evidence request to the DRI. The DRI uploads a file or grants scoped finance inbox access, a fact appears with provenance, and readiness turns green.
   3. **Policy drift.** Observed refund handling stops matching the documented policy and a newer pricing document conflicts with it. The librarian proposes invalidation with a new validity interval, the "as of" slider shows both versions, and all dependents update in one change request.
   4. **Website loop.** Clarity shows rage clicks on the pricing toggle, so the Insights Agent proposes a change on a sandbox branch. The impact preview and an A/B experiment run, and the result is kept or discarded and recorded as learning.
   5. **Blocked action.** The Care Agent attempts a refund above its capability. The access check denies it with a reason, the denial appears in the decision log and as a locked edge in "view as", and the Security Sentinel's proposed grant needs two L1 approvals.
   6. **Overnight improvement.** The Quality Supervisor reviews yesterday's failures, applies C0 and C1 fixes, drafts the rest, and the L1 morning digest reports both.
   7. **Research removal.** With the research flag off, the console's routes, navigation and bundles are gone and the build still passes.
3. Screenshots exist for every route and persona, in light and dark, at 1440 and 390 pixels wide.
4. Accessibility meets WCAG 2.2 AA: full keyboard use, visible focus, sufficient contrast, announced live updates and respected reduced motion.
5. A 10,000 row table scrolls smoothly, a 2,000 node graph stays interactive, and heavy visual libraries stay out of each route's initial bundle.
6. The README explains how to run the app, switch from mocks to a real API, add a tenant and add a cluster.

## 15. Out of scope for now

The real backend, real model calls, real OAuth and connectors, live Microsoft Clarity data, payments, filing anything with authorities, and native mobile apps all stay out of this build. Mock each of them behind the adapters above so they can be switched on later.

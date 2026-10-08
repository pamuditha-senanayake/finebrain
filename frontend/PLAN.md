# Company Brain Console: Frontend Plan

Phase 0 output for `Docs/CB_Frontend_Build_Brief_v2.md`. The owner asked to build end to end without stopping at the Phase 0 review, so this plan was written first and then executed. Decisions the owner should still confirm are listed under "Open questions".

## 1. Architecture in one table

| Concern | Decision |
|---|---|
| Framework | Next.js 16.4 App Router, React 19.3, strict TypeScript, Tailwind v4, shadcn/ui (radix base), Motion |
| Rendering | Pages are thin server shells that render client features. All data is fetched in the browser through TanStack Query, so the mock to real switch is a config change. Cache Components and partial prefetching are off: there is no server data to prerender, and they forced Suspense around every URL hook. |
| Data contracts | zod v4 schemas in `contracts/`, TypeScript types inferred from them, OpenAPI 3.1 generated into `docs/openapi.json` by `npm run openapi` |
| API client | `lib/api/client.ts`: typed fetch, every response parsed by its zod contract, persona header on every call |
| Mocks | MSW in the browser (`lib/mock/handlers.ts`) backed by an in-memory mock database (`lib/mock/db.ts`). `NEXT_PUBLIC_API_MOCKING=enabled` turns it on; set it to `disabled` and point `NEXT_PUBLIC_API_BASE_URL` at FastAPI to use the real backend. |
| Persistence of mock edits | Mutations are journaled to `localStorage` and replayed over the deterministic seed on reload, so a demo survives a refresh. "Reset demo data" clears the journal. |
| Live events | `lib/live/` adapter. Mock source subscribes to the mock database emitter plus a timer that pushes new runs, status changes and approvals. SSE source (`EventSource` on `/api/stream`) is ready for the backend. Events invalidate the matching queries. |
| Auth | `lib/auth/` adapter. Mock provider with the seeded personas and a role switcher. SSO provider stub. The role switcher is compiled out unless `NEXT_PUBLIC_ROLE_SWITCHER=enabled`. |
| UI state | Zustand: persona, tenant, cluster, environment, theme density, command palette, Ask the Brain panel |
| Tables | TanStack Table v9 with TanStack Virtual for every large list |
| Graphs | Sigma.js + graphology for the knowledge graph (WebGL, lazy loaded). React Flow for loop canvases and branch graphs. |
| Charts | shadcn charts on Recharts |
| Flags | `lib/flags.ts`, typed, read from `NEXT_PUBLIC_FLAG_*` |
| i18n | `lib/i18n/` with an English catalogue and a typed `t()` helper. Strings for shell and navigation go through it first. |
| Errors | `lib/errors.ts` adapter (`reportError`) with a console sink now and a hook for Sentry later. Route `error.tsx` boundaries call it. |
| Tests | Vitest + Testing Library for units, Playwright for the seven flows and the screenshot sweep |

## 2. Route map

Route groups keep each tier's layout and navigation separate while sharing one shell.

| Group | Route | Screen |
|---|---|---|
| root | `/` | Tier chooser that sends the current persona to its home |
| `(l1)` | `/l1` | Brain overview with legibility map |
| | `/l1/digest` | Morning digest |
| | `/l1/approvals`, `/l1/approvals/[id]` | Approvals inbox and decision view (phone friendly) |
| | `/l1/entity` | Entity protection: obligations calendar and risk register |
| | `/l1/evidence` | Evidence requests with upload and scoped source grants |
| | `/l1/analytics` | Progress and analytics |
| | `/l1/audit` | Audit trail |
| `(l2)` | `/l2/graph` | Knowledge graph explorer with "view as" |
| | `/l2/versioning`, `/l2/versioning/[id]` | Branches, commits, change requests, merge, rollback |
| | `/l2/library` | Library and filing rules |
| | `/l2/vault` | Ground truth vault and librarian queue |
| | `/l2/policies`, `/l2/policies/[id]` | Policy registry with timeline, "as of" slider and freshness signals |
| | `/l2/skills`, `/l2/skills/[id]` | Skills studio and Agent Academy |
| | `/l2/resolver` | Resolver table and trigger evals |
| | `/l2/templates` | Information templates |
| | `/l2/sensors` | Sensors, connections and the sensor planting overlay |
| | `/l2/loops`, `/l2/loops/[id]` | Loop canvases and experiments |
| | `/l2/readiness` | Readiness scheduler |
| | `/l2/security` | Security and access, invocation decision log |
| `(l3)` | `/l3` | Fleet view (table and grid) |
| | `/l3/agents/[id]` | Agent profile |
| | `/l3/runs/[id]` | Run trace viewer |
| | `/l3/conversations`, `/l3/conversations/[id]` | Live conversations, takeover and Skillify |
| | `/l3/escalations` | Escalations queue |
| | `/l3/templates` | Template board |
| `(research)` | `/research`, `/research/[paper]` | Research Console, read only, removable |

## 3. Component inventory and source

| Component | Source |
|---|---|
| Button, Card, Badge, Dialog, Sheet, Tabs, Tooltip, Select, Switch, Slider, Checkbox, Popover, Dropdown, Command, Table, Skeleton, Progress, Toggle group, Alert, Chart, Sonner | shadcn/ui (installed into `components/ui`) |
| Data table with virtualization, sorting and search | Own, on TanStack Table v9 + Virtual |
| Approval card, diff table, task row, tool chip, context card | Own, modelled on Beautiful UI human in the loop primitives (see open question 1) |
| Thinking orb (agent working and kind of work) | Own CSS implementation of the Thinking Orbs meaning |
| Border beam (live and needs attention, max three per screen) | Own CSS implementation, enforced by a per screen budget hook |
| Liquid metal button (irreversible commitment, C3 and C4 only) | Own CSS implementation, only used by `<CommitButton>` |
| Ambient surface (brain presence on overview hero, sign in, empty states) | Own CSS gradient field as the progressive enhancement fallback that Canvas UI requires anyway |
| Conversation states: thinking, streaming, citations, tool calls, file diffs | Own, modelled on the free AICSS items |
| Standard motion: menus, modals, toasts, tabs, numbers | tw-animate-css, Motion, and number tween component |
| Knowledge graph | Sigma.js + graphology |
| Loop canvas, branch graph | React Flow |
| Command palette | cmdk via shadcn Command |

## 4. Contracts

All entities from section 9 of the brief, extended. Files live in `contracts/`.

| File | Entities |
|---|---|
| `common.ts` | Criticality, Env, Tier, VersionRef, Sensitivity, Actor, IsoDate |
| `org.ts` | Tenant, Cluster, Human, Agent, Persona |
| `knowledge.ts` | Skill, Policy, Fact, Document, AccessRule, Sensor, TrackingPlanItem, Template, ResolverRule, GraphNode, GraphEdge, LibrarianItem |
| `work.ts` | Run, TraceStep, Conversation, Message, Escalation, AccessDecision |
| `change.ts` | Branch, Commit, Change, ChangeRequest, ImpactPreview, TestResult, Approval, Decision |
| `entity.ts` | Obligation, EvidenceRequest, Grant, Risk, ReadinessGap |
| `loops.ts` | Loop, LoopStage, Experiment |
| `ops.ts` | AuditEvent, Notification, Digest, Overview, Kpis, LegibilityCell, Analytics, AskAnswer |
| `research.ts` | ResearchSnapshot and metric definitions |

## 5. Seed plan

| Item | Finebase Labs | Scale Demo |
|---|---|---|
| Currency, timezone | LKR, Asia/Colombo | USD, UTC |
| Clusters | Finebase Platform, Finance and Compliance (active); People, Product Engineering, Procurement (planned) | 6 active, 2 planned |
| Agents | 12 workers + 3 supervisors from the activity catalog | 320 |
| Runs | about 1,200 over 14 days | 24,000 |
| Graph nodes | about 160 | 2,400 |
| Personas | founder, finance director, head of customer success (L1); knowledge steward, AI operations lead, security officer (L2); customer care operator (L3) | same roles, generated names |

Generation uses a seeded mulberry32 PRNG and a fixed anchor time, so the same seed always gives the same data. Every obligation, date and rule in seed data carries `isSample` and is labelled "Sample" in the UI.

## 6. Visual direction

| Token | Decision |
|---|---|
| Palette | Calm slate neutrals, indigo accent for primary actions, teal for healthy, amber for attention, rose for risk |
| Environments | Production: rose band with "PRODUCTION · live actions". Staging: amber band "STAGING · shadow mode". Sandbox: violet band with branch name. Never the same hue as any criticality. |
| Criticality | C0 slate, C1 sky, C2 lime, C3 orange, C4 red, same everywhere (chip, border, chart) |
| Type | Geist Sans for UI, Geist Mono for IDs, code, contract fields. Scale 12 / 13 / 14 / 16 / 20 / 24 / 32 |
| Density | Desktop first at 1440, 13px table text, 32px rows; comfortable mode for phones |
| Motion | 150 to 250 ms standard, 400 ms for panels. Every special effect maps to one meaning (section 11 of the brief). All ambient motion is off under `prefers-reduced-motion`. |

## 7. Activities to add

| Cluster | Activity | Agent | Why |
|---|---|---|---|
| Finebase Platform | Churn risk outreach | Care Agent | Usage events already exist as a sensor |
| Finance and Compliance | Vendor invoice approval routing | Billing Agent | Closes the loop with receivables and expenses |
| Brain wide | Prompt and model cost review | Quality Supervisor | Cost per resolved task is an L1 KPI |

## 8. Open questions

| # | Question | Default taken |
|---|---|---|
| 1 | Thinking Orbs, Border Beam, Liquid Metal, Canvas UI, AICSS, Beautiful UI, Originkit and Agentation are named in the brief, but their npm package names were not confirmed. Install them, or keep the in house versions that follow the same meanings? | In house CSS versions with identical meanings, swappable later |
| 2 | `npx transitions-agent` motion score: which package and version should CI run? | Not run, listed as a follow up |
| 3 | ChainSight repository was not in the workspace. Where is it? | Concepts taken from the brief's mapping table only |
| 4 | Should the mock journal also be shareable between browsers for demos? | No, per browser `localStorage` |
| 5 | Payment gateway, CMS and email provider for real connectors | Shown as generic connectors |

## 9. Phase log

The owner asked for an end to end build without phase stops, so all phases ran in one pass. This is the summary the brief asks for at the end of every phase.

| Phase | What landed | Evidence |
|---|---|---|
| 0 Plan | This file | |
| 1 Foundation | Tokens and themes, shell per tier, role switcher, zod contracts, MSW mock API with journal, deterministic seed for two tenants, mock live stream, flags, command palette, notifications, environment banner, audit plumbing | `tests/unit/seed.test.ts`, smoke spec |
| 2 Governance core | Knowledge graph with view as, versioning with branches, change requests, merge and rollback, criticality engine and approval pipeline with the two person rule, impact preview and replay | `tests/unit/governance.test.ts`, flows 1, 3, 5 |
| 3 L2 studios | Library, vault and librarian queue, policy registry with as of slider and freshness signals, skills studio and Academy, resolver, templates, sensors with planting overlay, loops with canvas and experiments, readiness scheduler, security and decision log | flows 2, 3, 4, 5 |
| 4 L3 floor | Fleet table and grid, agent profile, runs explorer, run trace viewer, live conversations with takeover and Skillify, escalations, template board | flow 1 |
| 5 L1 command | Brain overview with legibility map, morning digest, approvals inbox (phone friendly), entity protection, evidence requests with scoped grants, analytics, Ask the Brain, audit trail | flows 1, 2, 5, 6 |
| 6 Research Console | Separate route group with `.research.tsx` files, flag removes routes, nav and bundles, read only, SAMPLE labels, export blocked for samples, import adapter stub, lint boundary | flow 7 |
| 7 Hardening | axe WCAG 2.2 AA on every route in light and dark, keyboard checks, reduced motion, virtualized tables, lazy WebGL and React Flow, 168 screenshots, README | `tests/e2e/a11y.spec.ts`, `performance.spec.ts`, `screenshots/` |

## 10. Assumptions made

| # | Assumption |
|---|---|
| 1 | The motion libraries named in the brief were rebuilt in house with the same meanings (open question 1). The beam budget of three per screen is enforced in code. |
| 2 | `npx transitions-agent` was not run (open question 2). |
| 3 | Cache Components and partial prefetching are off: every screen fetches in the browser, so there is nothing to prerender. |
| 4 | A C3 change only moves to C4 for personal data, legal or tax, or more than one cluster, because C3 already covers money, customers, public content and ground truth. This keeps "any new skill" at C3 as flow 1 requires. |
| 5 | L1 may view L2 and L3, L2 may view L3, L3 sees only L3. The research persona and the founder see the Research Console. |
| 6 | Mock edits persist per browser through a journal replayed over the seed. The live stream uses its own id space so replay stays deterministic. |
| 7 | The research flag defaults to enabled in development and production env files so route types match. A deployment that must not ship research sets `NEXT_PUBLIC_FLAG_RESEARCH=disabled`; flow 7 verifies that build in an isolated copy. |
| 8 | Screenshots cover every route with its natural persona and every persona's home, in light and dark at 1440 and 390, not every route crossed with every persona. |
| 9 | Personas, customers and all sample amounts are invented. Every obligation, tax rule and date is labelled sample data. |

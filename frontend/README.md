# Company Brain Console

The frontend for the Company Brain: a governed layer where AI agents run company operations under policies and security that people control. It has three tier dashboards (L1 Command, L2 Governance, L3 Operations floor) and a removable Research Console. It runs fully on deterministic mock data today and switches to the real backend with configuration only.

The build brief is `../Docs/CB_Frontend_Build_Brief_v2.md`. Decisions and open questions are in `PLAN.md`.

## Run it

```bash
npm install
npm run dev
```

Open http://localhost:3000. The mock API starts in the browser (MSW) and seeds two tenants: **Finebase Labs** (realistic, LKR, Asia/Colombo) and **Scale Demo** (320 agents, about 27,000 runs, 2,370 graph nodes). Switch tenant in the top bar.

Use the persona menu (top right) to act as any seeded person. Your edits are journaled in this browser and survive a reload. Click the **Demo data** badge, then **Reset demo data**, to start over.

| Command | What it does |
|---|---|
| `npm run dev` | Development server on port 3000 |
| `npm run build` | Production build (type check included) |
| `npm run lint` | ESLint, including the Research Console import boundary |
| `npm run typecheck` | `next typegen` then `tsc --noEmit` |
| `npm test` | Vitest unit tests: seed, contracts, governance rules and the six data flows |
| `npm run e2e` | Playwright: every route, the seven product flows, performance checks, and research removal against production builds |
| `npm run screenshots` | Every route in light and dark, at 1440 and 390 pixels, into `screenshots/` |
| `npm run openapi` | Generates `docs/openapi.json` from the zod contracts for the backend team |

## Switch from mocks to the real API

Every screen reads through the typed client in `lib/api`, and every response is validated against the zod contracts in `contracts/`. To use FastAPI instead of the mocks, set:

```bash
NEXT_PUBLIC_API_MOCKING=disabled
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_LIVE_SOURCE=sse
```

The backend must serve:

| Endpoint | Purpose |
|---|---|
| `GET /api/tenants` | Tenants the user may open |
| `GET /api/t/{tenant}/{resource}` | One per hook in `lib/api/hooks.ts`, for example `agents`, `runs?agentId=`, `approvals/{id}`, `overview` |
| `POST /api/t/{tenant}/ops/{operation}` | Domain operations, for example `takeover`, `skillify`, `runChecks`, `decide`, `uploadEvidence`. The reference behaviour is `lib/mock/ops.ts`, and the unit tests in `tests/unit/flows.test.ts` describe it. |
| `POST /api/t/{tenant}/ask` | Ask the Brain, answers only from facts the asker may see |
| `GET /api/t/{tenant}/stream` | Server Sent Events, each message a `LiveEvent` JSON object |

Shapes are in `docs/openapi.json` (`npm run openapi`). Today the mock auth adapter sends the persona as `x-persona`. An SSO provider replaces that with a bearer token (`lib/auth.ts`, `lib/api/client.ts`).

## Add a tenant

1. Write a builder that returns `TenantData` (`lib/mock/types.ts`). `buildScale()` in `lib/mock/seed/build.ts` is the smallest example. Use `Rng` with a fixed seed so the output is deterministic.
2. Register it in `TENANTS` and in `MockDb.tenant()` in `lib/mock/db.ts`, and give it a default persona in `DEFAULT_PERSONA` (`lib/store.ts`).
3. Nothing about the tenant is hard coded in screens: currency, timezone, clusters and criticality thresholds come from the `Tenant` contract.

## Add a cluster

Add an entry to the tenant's `clusters`. A planned cluster (`status: "planned"`) shows as a placeholder in the switcher and on the overview. To activate it, give it sensors, agents, skills and activities with that `clusterId`. Every screen picks it up through the cluster filter.

## Feature flags

| Variable | Default | Effect |
|---|---|---|
| `NEXT_PUBLIC_FLAG_RESEARCH` | `enabled` | `disabled` removes the Research Console routes, navigation and bundles at build time (route files use the `.research.tsx` extension, see `next.config.ts`) |
| `NEXT_PUBLIC_ROLE_SWITCHER` | `enabled` | `disabled` strips persona impersonation. Turn it off for production. |
| `NEXT_PUBLIC_API_MOCKING` | `enabled` | `disabled` stops MSW and calls `NEXT_PUBLIC_API_BASE_URL` |
| `NEXT_PUBLIC_MOCK_STREAM` | on | `off` pauses the mock live event stream (the tests use this) |

See `.env.example` for the full list. No secrets ever go in `NEXT_PUBLIC_*` variables.

## Where things live

| Path | Contents |
|---|---|
| `app/(l1)`, `app/(l2)`, `app/(l3)`, `app/(research)` | Route groups per tier, each with its own layout |
| `features/` | Screen components per tier. `features/research` is the removable console; lint forbids product code from importing it. |
| `components/ui` | shadcn/ui |
| `components/brain` | Product components: data table, criticality and status chips, change request views, motion primitives |
| `components/shell` | Global shell: navigation, environment banner, command palette, notifications, Ask the Brain, role switcher |
| `contracts/` | zod contracts, the single source of truth for every shape |
| `lib/api` | Typed API client and TanStack Query hooks |
| `lib/mock` | Seed generator, mock database, domain operations, MSW handlers |
| `lib/governance` | Criticality engine, access checks, readiness rules |
| `tests/unit`, `tests/e2e` | Vitest and Playwright |

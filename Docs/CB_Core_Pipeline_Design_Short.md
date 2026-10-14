# Company Brain Core Pipeline (short version)

Version 1.1, 12 October 2026. Owner: Pamuditha, Finebase Labs. This is a condensed copy of `CB_Core_Pipeline_Design.md`. It keeps the 20% of detail that drives 80% of build decisions. Field level contracts stay in the full document.

## 1. What the pipeline does

A raw signal enters the brain. It leaves as a governed outcome. On the way it is masked, routed, reasoned over, checked, approved when needed, executed and recorded. Then every finished run feeds learning, so the next similar signal goes better.

| Item | Value |
|---|---|
| Input | A raw signal: email, chat, payment webhook, Clarity export, calendar change or uploaded document |
| Output | An action that runs or waits for approval, filled templates, a trace, an audit entry and learning input |
| Example tenant | Finebase Labs, LKR, Asia/Colombo |
| Out of scope | Login, SSO, user management, billing of the brain, mobile apps, filing with authorities |

## 2. Four lanes

The work splits into four lanes. They share one event backbone. So one lane's output becomes another lane's input.

| Lane | Turns | Key steps |
|---|---|---|
| A Signal to action | A signal into a governed action | Verify and store raw, mask personal data, dedupe, route to a skill and agent, retrieve context, Claude proposes an action, access check, policy and quality gates, criticality, approval if needed, execute with an idempotency key, record, audit, push to UI |
| B Document to ground truth | A document into verified facts | File, parse with Docling, chunk and embed, extract fact candidates, librarian finds conflicts and dependents, change request, merge with the old valid time closed |
| C Learning | Finished runs into better skills and policies | Nightly review at 02:00 or Skillify, classify failures, draft a fix on a sandbox branch, run evals and replay, approve by criticality, merge, publish the release |
| D Readiness | Deadlines into early evidence requests | Hourly check per tenant, find missing or stale evidence, dispatch an agent or ask the DRI, escalate at 21, 14, 7 and 2 days |

Three rules hold in every lane. First, nothing acts before governance. Second, approval weight follows criticality. Third, nothing is overwritten. Facts and graph nodes are closed and versioned instead.

| Criticality | Who approves |
|---|---|
| C0 | Automatic |
| C1 | L2 supervisor agent |
| C2 | L2 steward |
| C3 | The L1 DRI |
| C4 | Two distinct L1 humans, plus a cooling period |

A change that touches money, personal data, public content, legal or tax, or more than one cluster moves up one level.

## 3. Stages

The events fall into fifteen stages. Each stage is one process with one job. Between two stages sits a seam with a written contract. As a result, any stage can be rebuilt without breaking its neighbours.

| Stage | Job | Runs as | Main tech |
|---|---|---|---|
| S1 Capture | Receive, verify, store raw | `capture` FastAPI on 8001 | Kafka producer, S3 |
| S2 Normalize | Canonical shape, PII masking, dedup | `normalizer` consumer | Presidio, Valkey |
| S3 Route | Signal to activity, skill and agent | `resolver` consumer | Valkey cache, Haiku tie breaks |
| S4 Orchestrate | Durable task lifecycle | Temporal `task_workflow` | Temporal |
| S5 Retrieve | Access filtered hybrid retrieval | `internal` API on 8002 | pgvector, full text, Voyage rerank |
| S6 Reason | Plan, draft, propose | Temporal activity | Claude Sonnet with tool use |
| S7 Govern | Access, policy, gates, criticality | `internal` API on 8002 | OPA, rule engine, Haiku graders |
| S8 Decide | Approvals, expiry, delegation, takeover | Temporal `approval_workflow` | Temporal timers |
| S9 Act | Call outside systems safely | Temporal activity | Typed adapters, idempotency keys |
| S10 Record | Templates, trace, audit, live UI | `recorder` and SSE gateway | SSE |
| S11 Ingest | File, parse, embed, extract | `ingest` consumer | Docling, Voyage, Haiku |
| S12 Librarian | Compare candidates with ground truth | `librarian` consumer | Opus |
| S13 Learn | Nightly review, Skillify, evals, replay | Temporal workflows | Opus, Sonnet |
| S14 Version | Git for the graph | `graph` service and outbox relay | Postgres |
| S15 Readiness | Find missing evidence early | Temporal schedule | Temporal |

## 4. Contracts

Contracts are Pydantic models in `backend/app/contracts/`. JSON Schema is generated from them and registered. The frontend zod schemas come from the same OpenAPI document. So one change in Python reaches every consumer.

Every Kafka message shares one envelope. It holds `event_id` (UUIDv7, used for dedup), `event_type`, `schema_version`, `tenant_id`, `cluster_id`, `env`, `branch`, `occurred_at`, `recorded_at`, `trace_id`, `correlation_id` and `payload`. Consumers accept schema version N and N minus 1. Money is always `{ amount_minor, currency }`, never a float.

| Contract | Seam | Transport | What it carries |
|---|---|---|---|
| K1 RawSignalEnvelope | S1 to S2 | `signals.raw` | Connector, grant, source, external ID, S3 pointer and hash. Never the raw body. |
| K2 Signal | S2 to S3, S11 | `signals.normalized` | Kind, channel, actor token, subject, masked text, entities, sensitivity |
| K3 TaskRequest | S3 to S4 | `tasks.created` | Activity, pinned skill version, agent, on behalf of, criticality, due time |
| K4 ContextQuery and Bundle | S6 to S5 | HTTP, 2 s timeout | Query and principal in. Allowed items with source, valid time and score out, plus a denied count. |
| K5 ProposedAction | S6 to S7 | Temporal | Tool, typed arguments, money, what it touches, citations, confidence |
| K6 AccessCheck | S5, S7 to OPA | HTTP, 10 ms p95 | Principal, action, resource. Allow or deny with rule and reason. |
| K7 GovernanceVerdict | S7 to S8 | Temporal | Policy and gate results, final criticality, route: execute, approval, escalate or block |
| K8 ApprovalRequest and Decision | S7, S14 to S8 | Approval topics through the outbox | Plain summary, evidence, one DRI, due and expiry. Approve, reject, delegate, takeover or expired. |
| K9 ActionResult | S9 to S10 | `actions.executed` | Status, external reference, idempotency key, error |
| K10 RunRecord | S10 to S13 | `runs.completed` | Outcome, step summary, template fills, cost, trace pointer |
| K11 UiEvent | S10 to console | SSE | Display fields only, filtered per viewer |
| K12 FactCandidate | S11 to S12 | `facts.candidates` | Statement, value, valid time, exact evidence span |
| K13 Commit and ChangeRequest | S12, S13 to S14 | Graph API, `graph.commits` | Changes, plain diff, test results, replay impact |
| K14 ReleaseEvent | S14 to S3, S5, S6, S11 | `graph.released`, compacted | New commit and the changed nodes to reload |
| K15 GapDetected | S15 to S3, S8 | `evidence.gaps` | Missing item, due date, action, DRI |

## 5. Technology and storage

Fewer moving parts won wherever two options were close. That is why Postgres holds the relational core, the graph and the vectors together.

| Layer | Choice | Why | Production |
|---|---|---|---|
| Console | Next.js, TypeScript, Tailwind, TanStack Query | Matches the frontend brief | Vercel or a container |
| API and services | FastAPI, Pydantic v2, one uv project | Typed contracts, one codebase | AWS ECS, one service per process |
| Event backbone | Kafka, Redpanda locally | Ordered per key, replayable, decouples stages | Amazon MSK or Confluent |
| Workflows | Temporal | Long approval waits, timers, retries | Temporal Cloud or self hosted |
| System of record | PostgreSQL 17 with RLS per tenant | Transactions, bitemporal ranges, outbox | RDS or Aurora |
| Vectors and search | pgvector HNSW plus full text in Postgres | ACL filter and search in one query | Same. Qdrant only past tens of millions of chunks. |
| Cache | Valkey | Idempotency, resolver cache, access cache | ElastiCache |
| Objects | S3, MinIO locally | Raw, documents, evidence, traces, replays | S3 with KMS |
| Access | OPA with Rego | Rules at action time, every decision logged | Sidecar per service |
| Models | Claude Haiku, Sonnet and Opus 5.5 | Haiku for volume, Sonnet for agents, Opus for rare hard calls | API |
| Embeddings | Voyage AI | Anthropic's recommended partner | API |
| Parsing and PII | Docling, Presidio with Sri Lankan recognizers | Local, no key | Same |
| Secrets | Secrets Manager and KMS | Tenant tokens are envelope encrypted | Same |
| Observability | OpenTelemetry to Grafana, plus Sentry | One trace ID from webhook to UI | Grafana Cloud |

Every byte has one home. Postgres is the system of record. Kafka carries events for a limited time. Valkey holds only what can be rebuilt. S3 holds large and raw content.

| Store | Holds | Retention |
|---|---|---|
| Postgres core | Tenants, agents, tasks, runs, approvals, change requests, templates | Life of tenant |
| Postgres graph | Versioned skills, policies, access rules, templates. Written by S14 only. | Forever, append only |
| Postgres facts | Bitemporal facts with evidence | Closed, never deleted |
| Postgres chunks | Embeddings, text index, ACL labels | Follows the document |
| PII vault | Token to value map, with its own schema and role | Per data request register |
| Access and audit logs | Every access decision, and hash chained audit events | 400 days, and 7 years (sample) |
| Kafka | Events in motion on 18 topics, one DLQ per consumer group | 1 to 30 days |
| Valkey | Idempotency keys, caches, rate limits | Minutes to 7 days |
| S3 `brain/{tenant}/` | Raw, documents, evidence, traces, replays | Raw 90 days |
| Temporal | Workflow history and timers | 30 days after close |

Every topic key starts with the tenant ID. So one tenant's events keep their order and never mix with another's.

## 6. Failure rules

Nothing fails silently. These are the rules that matter most.

| Failure | Behaviour |
|---|---|
| Bad webhook signature | Reject with 401 and store nothing |
| Kafka down at capture | Return 503 so the source retries |
| Parse error | Send to the topic DLQ and show it in Sensors health |
| No route above the score floor | `tasks.unrouted`, then the escalations queue |
| OPA unreachable | Fail closed and deny |
| Model or gate failure | Retry with feedback, then escalate |
| Approval expires | Escalate to the delegate. Never auto approve. |
| Tool fails | Retry up to 6 times with the same idempotency key, then fail and compensate |
| Consumer misses a release | The compacted topic plus a commit check on every run |

The speed targets keep a C0 chat reply under 10 seconds at p95. Access checks stay under 10 ms, and retrieval stays under 400 ms.

## 7. API keys

Tenant connector tokens never live in `.env`. Instead they are stored per tenant and envelope encrypted. The browser never holds a secret.

| Variable | Service | Needed |
|---|---|---|
| `ANTHROPIC_API_KEY` | Claude | Day one |
| `VOYAGE_API_KEY` | Embeddings and rerank | Day one |
| `GOOGLE_OAUTH_*`, `GOOGLE_PUBSUB_*` | Gmail and Calendar | Day one |
| `STRIPE_*` or `PAYHERE_*` | Payments and refunds | Day one |
| `SENTRY_DSN` | Error reporting | Day one |
| `CLARITY_API_TOKEN`, `HUBSPOT_PRIVATE_APP_TOKEN`, `CMS_API_TOKEN`, `GITHUB_APP_*`, `BETTERSTACK_API_TOKEN` | Other connectors | When that loop is switched on |

Infrastructure secrets are `DATABASE_URL`, `REDIS_URL`, `KAFKA_*`, `SCHEMA_REGISTRY_URL`, `S3_*`, `TEMPORAL_*`, `OPA_URL`, `KMS_KEY_ID` and `INTERNAL_SERVICE_TOKEN`. Locally they come from Docker Compose. In production they come from Secrets Manager.

## 8. Acceptance test

One scenario exercises all four lanes. A late refund enters as an email. It ends as a merged skill that handles the next similar email without escalation. Every check observes the system at its boundary: the sandboxes, the public API, SSE and Kafka. It never checks internal calls.

```gherkin
Feature: Refund outside policy becomes a governed skill

  Scenario: A late refund escalates, is approved, skillified and reused
    Given policy "refund_policy" v3 allows 30 days and auto refunds up to LKR 50,000
    And customer "C1" bought an annual plan for LKR 85,000 41 days ago
    When "C1" emails support asking for a full refund
    Then an acknowledgement with no refund promise arrives within 10 seconds
    And one escalation lists "outside_refund_window" and "above_auto_threshold"
    When the L3 operator takes over and proposes the full refund
    Then a C3 approval waits for the head of customer success
    When the head of customer success approves
    Then the payment sandbox gets exactly one refund with the run idempotency key
    And the refund register gets a row sourced from the gateway refund ID
    When the operator presses Skillify
    Then a change request for "refund_late_annual" v1 shows passing tests and a replay of 50 or more runs
    When it is approved and merged
    Then "graph.released" carries the new skill
    When customer "C2" sends the same request
    Then the run uses "refund_late_annual" v1 and goes straight to approval without escalation
    And the audit hash chain is unbroken
    And no message, response or SSE event contains a raw customer name or email
```

## 9. Open questions

| # | Question |
|---|---|
| 1 | Stripe, PayHere or both? |
| 2 | Which CMS runs the website? |
| 3 | Google Workspace or Microsoft 365 for support mail? |
| 4 | Where must data be hosted under the Sri Lankan PDPA? |
| 5 | What are the real retention periods, refund window and auto threshold? |
| 6 | Temporal Cloud or self hosted? |

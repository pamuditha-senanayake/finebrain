# Company Brain: system reference for development

Version 2, 17 October 2026. One place to look up the system while building the backend: layers, lanes, stages, contracts, stores and the parts added since the 8 October design.

| Read with | What it shows |
|---|---|
| `Docs/CB_System_Architecture.drawio` | Diagram 1: people, frontend, entry points, services, data, outside services |
| `Docs/CB_Pipeline_Stages_Lanes.drawio` | Diagram 2: 15 stages, 15 contracts, 4 lanes, and the screens around them |
| `Docs/CB_Core_Pipeline_Design.md` | Full field lists for every contract, the event list A01 to D07, the acceptance test |
| `frontend/contracts/*.ts` | UI contracts (zod) the frontend already uses with mock data |
| `backend/app/pipeline/contracts_*.py` | Pydantic contracts already written |

Three rules hold everywhere:

| Rule | Meaning in code |
|---|---|
| Nothing acts before governance | Every ProposedAction passes S7 before S9 may call a tool |
| Approval weight follows risk | Criticality C0 to C4 decides who approves (section 2) |
| Nothing is overwritten | Graph changes are commits. Facts close their valid time instead of being updated. |

## 1. The system in layers

| Layer | What runs there | Tech | Local port |
|---|---|---|---|
| People | L1 Command, L2 Governance, L3 Operations | Browser | |
| Claude | Staff use the brain from Claude app or Claude Code | MCP client | |
| Frontend | Next.js console with every screen | Next.js, TypeScript, Tailwind, TanStack Query | 3000 |
| Entry points | Public API with SSE, MCP server, S1 Capture | FastAPI | 8000, MCP URL, 8001 |
| Pipeline services | One process per job, all in `backend/app` | Python, uv | internal API 8002 |
| Event backbone | 18 topics, key starts with tenant | Kafka (Redpanda locally) | 9092, registry 8081 |
| Data | System of record, cache, objects, workflows, secrets | Postgres 17 + pgvector, Valkey, S3 (SeaweedFS locally), Temporal, Secrets Manager + KMS | 5433, 6379, 9000, 7233 |
| Access | Allow or deny at the moment of action | OPA (Rego) | 8181 |
| Outside services | Models, embeddings, voice, tools | Anthropic, Voyage AI, ElevenLabs, payment gateway, Gmail, CMS | |

## 2. People, tiers and approval

| Tier | Who | Main screens |
|---|---|---|
| L1 Command | Founder, directors, DRIs | Brain overview, Ask the Brain, To review, Use in Claude, Workflow Studio, Entity protection, Analytics, Trends, Audit, Setup |
| L2 Governance | Stewards, supervisor agents | Vault, Security, Knowledge graph (with Versions tab), Library, Policies, Skills, Resolver, Templates, Sensors, Loops, Readiness, L2 workflow studio |
| L3 Operations | Operators, worker agents | Live conversations, Escalations, Fleet, Agent running history, Template board |

Higher tiers can look down, never up.

| Criticality | Who approves |
|---|---|
| C0 | Automatic, logged |
| C1 | L2 supervisor agent |
| C2 | L2 human steward |
| C3 | The L1 DRI |
| C4 | Two different L1 leaders, plus a cooling period |

Touching money, personal data, public content, legal or tax, or more than one cluster moves a change up one level.

One exception: when the skill's policy explicitly allows that action within its limits, there is no bump. A refund of LKR 12,000 under a policy that auto-approves up to LKR 50,000 inside 30 days stays C0 (reason `policy_auto_approval`). Outside those limits the bump applies as normal.

## 3. What is new since the 8 October design

These features live in the frontend today with mock data. The backend must serve them.

| Feature | What it does | Frontend source | Backend work it needs |
|---|---|---|---|
| Connect (setup) | Interview asks one question at a time: name, website, what you do, tools, connect each, MCP servers | `features/setup/interview.tsx`, `lib/connect/catalog.ts`, `lib/connect/store.ts` | Grants table, encrypted connector tokens, OAuth flows, a sensor per connection |
| Connectors | 6 ways in: sign in (OAuth), read-only database link, MCP server, read the site, upload files, webhook. Always read only. | `lib/connect/catalog.ts` | S1 adapters per method. Fallback when a tool is missing: MCP, webhook, export files, ask us. |
| Sensors | Every connection becomes a sensor: health, on or off, subscribers, personal data masked, retention | `features/l2/sensors.tsx` | Sensor rows, pause flag, health from S1/S2 and the DLQ |
| Workflow Studio | Main feature. A workflow is a story (problem, today, Given/When/Then scenarios) plus its parts in 5 steps: Start, Team, Work, Rules and tools, Results | `features/studio/*`, `contracts/studio.ts`, `lib/mock/studio/engine.ts` | Workflow and item storage in the graph, proposal review, apply or approval through K13 and K8 |
| Studio review | Every change gets a verdict (minimal, moderate, breaking), criticality with reasons, affected parts, other workflows hit, fixes, and a route (apply, approval, view only) | `lib/mock/studio/engine.ts` | Same rules server side. The browser is never trusted for impact. |
| Tools | The one shared layer: tools live outside any workflow. 3 kinds: Ready-made (prebuilt), Set up (configured from a connector), Custom code (sandbox, must pass a test run, C3) | `lib/studio/spec.ts` | Tool registry, sandbox runner for custom code, side effect and rate limit per tool |
| Ask the Brain | Voice or text. Asks "this page or whole system?" Answers are cited. Can also run the setup interview by voice. | `features/l1/ask-voice.tsx`, `components/shell/ask-panel.tsx` | `POST /api/t/{tenant}/ask` → K4 with a human principal. Voice stays in the Next.js route (ElevenLabs). |
| Use in Claude (MCP) | The brain is an MCP server at `mcp.companybrain.app/{tenant}`. Claude signs in as the person. Tools: ask, search, read policies, see workflows, propose changes (off by default, goes to approvals) | `features/connect/claude-mcp.tsx` | MCP server, OAuth sign-in, per-tenant tool switches, audit of every call |
| Entity protection | Risk register, obligations on a 60-day timeline, deadlines watched early | `features/l1/entity.tsx` | Risks and obligations tables, S15 readiness |
| To review | One inbox with tabs: summary, approvals, evidence | `features/l1/digest.tsx` | K8 and K15 read APIs, morning digest job (C15) |
| Mark as wrong | Anyone can mark a run wrong. The note stays on the run and the agent's DRI is told. | `features/l3/mark-wrong.tsx` | Run annotation, notification, input to the nightly review |
| Fleet errors | Failed and blocked runs grouped by what went wrong | `features/l3/fleet-errors.tsx` | Run query by status and failure class |

## 4. Lanes

| Lane | Turns | Events | Stages |
|---|---|---|---|
| A | A signal into a governed action | A01 to A32 | S1 to S10 |
| B | A document into verified ground truth | B01 to B12 | S11, S12, then S14 |
| C | Finished runs into better skills and policies | C01 to C15 | S13, S14, approvals in S8 |
| D | Deadlines into early evidence requests | D01 to D07 | S15, then S3 or S8 |
| Around | Screens people use to connect, design, ask and approve | | Connect → S1, Studio → S14, Ask/MCP → S5, To review ↔ S8, console ← S10 |

The lanes share one event backbone, so one lane's output is another lane's input.

## 5. Stages

| Stage | Job | Process | Reads | Writes | Model | Target p95 |
|---|---|---|---|---|---|---|
| S1 Capture | Receive, verify, store raw once | `capture` FastAPI :8001 + poll workers | Grants, connector secrets | `raw/` objects, `signals.raw` | | 800 ms with S2 |
| S2 Normalize | Canonical Signal, mask personal data, dedup | `normalizer` consumer | `signals.raw`, raw objects | `signals.normalized`, PII vault | | (above) |
| S3 Route | Match to activity, skill version, agent | `resolver` consumer | Resolver table on main, `graph.released`, `evidence.gaps` | `tasks.created`, `tasks.unrouted` | Haiku for tie breaks | 150 ms |
| S4 Orchestrate | Durable task lifecycle, timers, retries | Temporal `task_workflow` | `tasks.created` | Temporal history, `runs` | | |
| S5 Retrieve | Access filtered, bitemporal, hybrid retrieval | `internal` :8002 | Graph, facts, chunks | `access.decisions` | Voyage rerank | 400 ms |
| S6 Reason | Plan, draft, propose actions | Temporal `agent_step` | ContextBundle, skill steps | `runs.steps` | Sonnet 5.5 | 6 s per step |
| S7 Govern | Access, policy rules, quality gates, criticality | `internal` :8002 | ProposedAction, policies on main | `access.decisions`, verdict | Haiku graders | 200 ms (access 10 ms) |
| S8 Decide | Approvals, escalation, takeover, delegation, expiry | `approvals` + Temporal `approval_workflow` | Verdicts, change requests, gaps | `approvals.*`, `approvals` table | | |
| S9 Act | Call outside systems safely through shared tools | Temporal `tool_call` | Decision, final arguments | `actions.executed`, `actions` | | 1.5 s |
| S10 Record | Templates, trace, audit, live UI | `recorder` + SSE gateway | `runs.steps`, `actions.executed` | `runs.completed`, `audit.events`, `ui.events`, `traces/` | | 300 ms to UI |
| S11 Ingest | File, parse, chunk, embed, extract | `ingest` consumer | Document signals | `docs.*`, `facts.candidates`, chunks | Haiku, Voyage | |
| S12 Librarian | Compare candidates with ground truth | `librarian` consumer | `facts.candidates`, facts, graph | Draft commits, `graph.commits` | Opus 5.5 | |
| S13 Learn | Nightly review, health, drift, Skillify, evals, replay | Temporal `nightly_review`, `change_request_workflow` | `runs.completed`, traces | Draft commits, eval and replay results | Opus, Sonnet | 10,000 runs < 45 min |
| S14 Version | Git for the graph: commit, merge, release | `graph` service + outbox relay | Commits, approvals | `graph.commits`, `graph.released`, graph tables | | |
| S15 Readiness | Find missing evidence early | Temporal schedule `readiness`, hourly | Obligations, templates, facts | `evidence.gaps` | | |

End to end target: a C0 chat reply in 10 s at p95.

## 6. Contracts between stages

Every Kafka message is wrapped in the shared envelope: `event_id` (UUIDv7), `event_type`, `schema_version`, `tenant_id`, `cluster_id`, `env`, `branch`, `occurred_at`, `recorded_at`, `trace_id`, `correlation_id`, `causation_id`, `producer`, `payload`.

| Contract | From → to | Transport | Key fields | In backend today |
|---|---|---|---|---|
| K1 RawSignalEnvelope | S1 → S2 | Kafka `signals.raw` | connector_id, grant_id, source_type, external_id, raw_object_uri, raw_sha256 | Yes |
| K2 Signal | S2 → S3, S11 | Kafka `signals.normalized` | kind, channel, actor (masked), subject, text_masked, pii_tokens, sensitivity, dedup_key | Yes |
| K3 TaskRequest | S3 → S4 | Kafka `tasks.created` | task_id, activity_id, skill_ref (pinned), agent_id, on_behalf_of, match_score, base_criticality | Yes |
| K4 ContextQuery → ContextBundle | S6 ↔ S5 (also Ask and MCP) | Sync HTTP, 2 s | principal, on_behalf_of, as_of_valid, as_of_recorded, branch → items[], denied_count, access_decision_ids | Yes |
| K5 ProposedAction | S6 → S7 | Temporal activity + `runs.steps` | action_type, tool_id, arguments, money, touches, citations, confidence | Yes |
| K6 AccessCheck | S5, S7 → OPA | Sync HTTP, 10 ms | principal, action, resource → decision, rule_id, reason | Yes |
| K7 GovernanceVerdict | S7 → S8 | Temporal activity + `runs.steps` | policy_results, quality_gates, criticality, reasons, route, required_approvers | Yes |
| K8 ApprovalRequest, Decision | S7 or S14 → S8 → S9 or S14 | Kafka `approvals.*` via outbox | summary_plain, criticality, dri_id, due_at, expires_at → decision, decided_by, final_arguments | Yes |
| K9 ActionResult | S9 → S10 | Kafka `actions.executed` | tool_id, idempotency_key, status, external_ref, error | Yes |
| K10 RunRecord | S10 → S13 | Kafka `runs.completed` | outcome, steps[], template_fills[], human_touch, cost, trace_object_uri | Yes |
| K11 UiEvent | S10 → console | SSE `GET /api/stream` | type, id, display (masked) | Yes |
| K12 FactCandidate | S11 → S12 | Kafka `facts.candidates` | statement, subject, value, valid_from, evidence span, extractor | Yes |
| K13 Commit + ChangeRequest | S12, S13, Skillify, Workflow Studio → S14 | Graph API, then `graph.commits` via outbox | commit: branch, author, changes[], criticality · CR: plain_diff, tests, impact_preview, status | Yes |
| K14 ReleaseEvent | S14 → S3, S5, S6, S11 | Kafka `graph.released`, compacted | commit_id, changed_nodes[] | Yes |
| K15 GapDetected | S15 → S3, S8 | Kafka `evidence.gaps` | target, required_item, due_at, action, dri_id, escalation_days | Yes |

Shared types: `VersionRef`, `Money` (minor units, never floats: LKR 85,000 is `8500000`), `Principal`, `Criticality` (0 to 4), `PiiToken`, `Touches`.

### 6.1 UI contracts (frontend only today)

| Contract | Where | Fields | Maps to |
|---|---|---|---|
| Connection | `lib/connect/store.ts` | connectorId, name, method, detail, enabled | A grant row plus an encrypted token |
| Sensor | `contracts/knowledge.ts` | name, source, scopes, health, subscribers, personalData, retentionDays | Sensor node in the graph, fed by S1 and S2 |
| Workflow | `contracts/studio.ts` | name, criticality, dri, editors, members[], story { problem, today, scenarios[] } | Graph nodes on main |
| StudioItem | `contracts/studio.ts` | kind (skill, agent, policy, template, sensor, scheduler, loop, tool), workflowId (null for tools), fields, version | Graph nodes, versioned |
| Proposal + Review | `contracts/studio.ts` | changes[], verdict, criticality, findings, affected, otherWorkflows, authority route | Becomes a K13 commit and, if needed, a K8 approval |
| TrendCard | `contracts/trends.ts` | metric, segment, ownerId, weeks[12], usual, latest, ratio, status (new, known), caseIds[] | One row per spike from the S13 weekly check |
| Ask request | `ask-panel.tsx` | question, page { path, scope: page or system } | K4 with a human principal |

## 7. Storage

| Store | Holds | Written by | Retention |
|---|---|---|---|
| Postgres core | Tenants, clusters, agents, tasks, runs, approvals, change requests, templates, obligations, risks | Most stages | Life of tenant |
| Postgres graph | `graph_commits`, `graph_branches`, `graph_nodes`, `graph_edges`: skills, policies, access rules, sensors, templates, agents, tools, workflows | S14 only | Forever, append only |
| Postgres facts | Bitemporal facts with evidence and dependents | S14 on merge | Closed, never deleted |
| Postgres chunks | pgvector embeddings, full text, ACL labels | S11, S14 | Follows the document |
| PII vault | Token to real value, encrypted columns, own role | S2 | Data request register |
| Access decision log | Every allow and deny | Consumer of `access.decisions` | 400 days |
| Audit log | Append only, hash chained | Consumer of `audit.events` | 7 years (sample) |
| Outbox | Events written in the same transaction as state | S8, S10, S14 | Until published |
| Valkey | Idempotency keys, resolver cache, access cache, rate limits | S1, S2, S3, S7, S9 | Minutes to 7 days |
| S3 `brain/{tenant}/` | `raw/`, `documents/`, `evidence/`, `traces/`, `replays/` | S1, S11, S10, S13 | Raw 90 days, others by filing rule |
| Temporal | Workflow history and timers | S4, S8, S13, S15 | 30 days after close |
| Secrets Manager + KMS | Connector tokens (envelope encrypted), vault keys | Setup, S1 | Until revoked |

| Topic | Key | Producer → consumers |
|---|---|---|
| `signals.raw` | tenant:source:external_id | S1 → S2 |
| `signals.normalized` | tenant:subject_ref | S2 → S3, S11 |
| `tasks.created` | tenant:task_id | S3, S15 → S4 |
| `tasks.unrouted` | tenant | S3 → Escalations, S13 |
| `runs.steps` | tenant:run_id | S6, S7, S9 → S10, SSE |
| `runs.completed` | tenant:run_id | S10 → S13, metrics, template board |
| `access.decisions` | tenant:principal | S5, S7 → decision log, Sentinel |
| `approvals.requested`, `approvals.decided` | tenant:approval_id | S8 → notifications, SSE, S4, S14 |
| `actions.executed` | tenant:action_id | S9 → S10 |
| `docs.filed`, `docs.extracted` | tenant:document_id | S11 → S11, Library |
| `facts.candidates` | tenant:subject_ref | S11 → S12 |
| `graph.commits` | tenant:branch | S14 → S13, Versions tab |
| `graph.released` | tenant (compacted) | S14 → S3, S5, S6, S11 |
| `evidence.gaps` | tenant:obligation_id | S15 → S3, S8 |
| `audit.events` | tenant | All → audit writer |
| `ui.events` | tenant | S10 → SSE gateway |

Each consumer group has its own `{topic}.dlq`. Every consumer is idempotent on `event_id`.

### 7.1 Memory and trends

The full design lives in `CB_Memory_Architecture.md`. These are the parts the backend still has to build.

| Part | What it does | Where |
|---|---|---|
| Version chains | A new version of a document points to the old one; only the latest is searched | S11, Postgres facts |
| Field dictionary | Core fields every project shares, extras kept as named fields | S11 extraction |
| Narrowing first | Filters by tenant, domain, entity and time before any vector search | S5 |
| Weekly counts | One row per week per metric and segment, written as runs close | `signal_counts` table, fed by `runs.completed` |
| Spike check | Each week compares the latest count to the usual (median of 12 weeks); 3× or more opens a TrendCard and tells the owner | S13 |

The Trends tab (L1) shows one TrendCard at a time. "Mark as known" sets status to known so the same spike stays quiet. Finebase HQ shows "No unusual weeks" until the spike check exists.

## 8. Failure rules

| Seam | Failure | Behaviour |
|---|---|---|
| K1 | Bad signature | 401, nothing stored |
| K1 | Kafka down | 503, the source retries |
| K2 | Parse error | `signals.raw.dlq`, shown in Sensors health |
| K3 | No route above 0.72 | `tasks.unrouted`, Escalations queue |
| K4 | Retrieval timeout | One retry, then escalate `context_unavailable` |
| K5 | Invalid tool arguments | Two retries with schema feedback, then escalate |
| K6 | OPA unreachable | Fail closed: deny |
| K7 | Quality gate fails | Back to S6 once, then escalate |
| K8 | Approval expires | `expired`, goes to the delegate. Never auto approves. |
| K9 | Retryable tool error | Up to 6 attempts, same idempotency key |
| K9 | Not retryable | Run failed, human told, compensation if defined |
| K10 | Recorder down | Kafka keeps events, UI shows "delayed" |
| K12 | Low confidence | Marked `unverified`, librarian queue |
| K13 | Merge conflict | Change request blocked, conflict view |
| K14 | Missed release | Compacted topic plus a commit check on every run |
| Studio | Change breaks a part | Shown red, must be acknowledged, approval still follows criticality |
| Studio | Custom tool fails its sandbox test | Finding marked "break", so the change is breaking and needs the same acknowledgement (409 without it) |
| MCP | Claude proposes a change | Goes to approvals, never applied directly |

## 9. Local development

| Service | Port | | Python process | Entry | Stages |
|---|---|---|---|---|---|
| Next.js console | 3000 | | `api` | `uv run fastapi dev app/main.py` | API, SSE |
| FastAPI API + SSE | 8000 | | `capture` | `uv run python -m app.capture` | S1 |
| Capture webhooks | 8001 | | `normalizer` | `uv run python -m app.normalize` | S2 |
| Internal API | 8002 | | `resolver` | `uv run python -m app.route` | S3 |
| PostgreSQL 17 + pgvector | 5433 | | `worker` | `uv run python -m app.workflows.worker` | S4, S6, S8, S9, S13, S15 |
| Valkey | 6379 | | `internal` | `uv run python -m app.internal` | S5, S7 |
| Redpanda / registry / console | 9092 / 8081 / 8080 | | `recorder` | `uv run python -m app.record` | S10 |
| S3 (SeaweedFS) | 9000 | | `ingest` | `uv run python -m app.ingest` | S11 |
| Temporal | 7233, UI 8233 | | `librarian` | `uv run python -m app.librarian` | S12 |
| OPA | 8181 | | `graph` | `uv run python -m app.graph` | S14, outbox relay |

Keys: `ANTHROPIC_API_KEY`, `VOYAGE_API_KEY` and the Google OAuth and Pub/Sub keys are needed from day one. `ELEVENLABS_API_KEY` lives only in `frontend/.env.local`. Full list: `CB_Core_Pipeline_Design.md` section 8.

## 10. Contract to screen map

| Contract | Screens |
|---|---|
| K2 Signal | L2 Sensors and connections, L3 Live conversations |
| K3 TaskRequest | L3 Fleet, L2 Resolver |
| K4 ContextBundle | L3 Agent running history (retrieval), L1 Ask the Brain, Claude via MCP |
| K6 AccessCheck | L2 Security and access, Knowledge graph "view as" |
| K7 GovernanceVerdict | L3 Agent running history (gates), L3 Escalations |
| K8 ApprovalRequest, Decision | L1 To review › Approvals, Workflow Studio route |
| K9 ActionResult | L3 Agent running history (tools) |
| K10 RunRecord | L3 Template board, L1 Progress and analytics, Fleet errors, Mark as wrong |
| K11 UiEvent | Every live list |
| K12 FactCandidate | L2 Library, L2 Ground truth vault (librarian queue) |
| K13 Commit, ChangeRequest | Workflow Studio, Knowledge graph › Versions, L1 To review |
| K14 ReleaseEvent | Versions history, Audit trail |
| K15 GapDetected | L1 Entity protection, L1 To review › Evidence, L2 Readiness scheduler |
| TrendCard (UI) | L1 Trends |

## 11. Where the backend stands

| Part | Status |
|---|---|
| FastAPI app | `backend/app/main.py` has `/health` and CORS for port 3000 |
| Contracts K1 to K15, shared types, DeadLetter | Written in `backend/app/pipeline/contracts_signal.py`, `contracts_reason.py`, `contracts_run.py`, `contracts_graph.py`, `contracts_failure.py` |
| Golden data and check | `backend/samples/golden_refund_run.json`, checked by `uv run python -m scripts.check_golden` |
| UI contracts for Connect, Studio, Ask | Only in the frontend (zod) |
| Samples | `backend/samples/pipeline_samples.json` |
| Lane A stages S1 to S10 | Thin first versions in `backend/app/pipeline/stages_*.py`, wired by `orchestrate.py` onto memory or real adapters (`adapters.py`) |
| Kafka | `bus_kafka.py` on Redpanda (`backend/infra/compose.yaml`), tested next to the memory bus |
| Postgres | `store_postgres.py` on port 5433: `pii_vault` and append-only `records` only |
| Valkey | `store_valkey.py` on port 6379: "seen before" key sets with a 7-day expiry |
| S3 | `store_s3.py` on SeaweedFS, port 9000 (MinIO no longer publishes images): raw signal bodies |
| Temporal | `temporal_flow.py`: each task is a `TaskWorkflow`; S8 waits for the approval signal. Dev server on 7233, UI on 8233 |
| End-to-end | `tests/test_e2e.py` runs on memory and on all real infra together |
| Shared helpers | `observe.py` (JSON logs, counters), `retry.py` (retry with backoff, DLQ replay) |
| S1 Capture (done) | `capture_api.py`: connector, grant, size, type and HMAC signature checks; 404, 403, 401, 413, 415, 400, 503 as in section 8 |
| S2 Normalize (done) | `stages_normalize.py`, `readers.py`, `pii.py`: MIME, chat and upload; masks emails, phones, NIC, cards (Luhn), addresses, names; vault encrypted with pgcrypto; `possible_prompt_injection` flag; atomic dedup claim; parse errors to DLQ (not retryable), store hiccups retried |
| S3 Route (done) | `stages_route.py`, `store_graph.py`, `llm.py`: rules, skills and agents from `graph_nodes` (append-only versions); kind, channel and required-entity gates; documents left to Lane B; ties within 0.1 settled by Claude Haiku from a fixed list; skill version pinned; flags carried to K3; below 0.72 or unsettled ties to `tasks.unrouted` |
| S5 Retrieve (done) | `stages_retrieve.py`, `store_chunks.py`, `embeddings.py`: chunks in Postgres (pgvector + full text) loaded from graph knowledge; hybrid search merged by reciprocal rank fusion, Voyage rerank; as-of valid and recorded time; tier and on_behalf_of access, withheld items counted; token budget; access decisions on `access.decisions`. Embedding outage falls back to full text, rerank outage keeps fused order; store outage gets one retry in S4, then the run escalates `context_unavailable` |
| S6 Reason (done) | `stages_reason.py`, `tools.py`, `llm.py`: real Claude Sonnet with tool use; only the skill's allowed tools (`issue_refund`, `reply_customer`, `escalate`) with strict schemas; customer text and documents quoted as data; citations must be bundle items. Bad calls get schema feedback twice, then escalate `invalid_arguments`; outages escalate `model_unavailable`; no tool escalates `no_action`. Temporal activities have timeouts and no automatic retry. Note: `claude-sonnet-5-5` takes no `temperature` or forced `tool_choice` |
| S7 Govern (done) | `stages_govern.py`, `access.py`, `infra/opa/access.rego`: OPA on 8181 decides access (capability, tier, on_behalf_of) with the same rules mirrored in Python; fails closed (`opa_unreachable` means block). Policies come from the graph. Every section 2 bump (+1 each, money waived when the policy allows); `possible_prompt_injection` means at least C2, never automatic. Gates: citations, amount, confidence 0.6, Haiku grader (fails closed). A failed gate goes back to S6 once, then escalates. C4 gets 24 h cooling. S8 approval moved to `stages_decide.py`. S6 and the grader are told today's date |
| S8 Decide (done) | `stages_decide.py`, `run_approvals.py`: a people directory (tier, roles, delegate) decides who may approve; C3 goes to the DRI, C4 needs two different L1 leaders then a 24 h cooling period. Delegate moves the approval; takeover closes the run for a human; request changes goes back to S6 once; edits are schema-checked and never pay more than was paid. Expiry goes to the delegate once, then escalates, never auto-approves. Wrong deciders, repeat approvers and unknown approvals are refused. Temporal timers in production; `sweep_expired` for in-process runs |
| S9 Act (done) | `stages_act.py`, `tool_runners.py`: one runner per tool (payment gateway, email, escalate with no outside call); per tool and tenant rate limits (Valkey); finished results stored by idempotency key for 7 days so a retry after a crash never calls the tool again. Retryable errors get up to 6 attempts on the same key; not retryable fails the run and the console shows it; compensation hook per tool (none needed yet). Before acting on an approval, a newer released policy means S7 runs again: no stricter acts, stricter opens a new approval. Payment gateway and email stay fakes until open question 1 and connector OAuth |
| S10 Record (done) | `stages_record.py`, `audit.py`, `ui_stream.py`: full run traces in S3 (`traces/{run_id}.json`); an append-only, hash-chained `audit_log` (Postgres + memory) over approvals, decisions, actions, runs and access decisions, with `verify_chain`; a per-tenant SSE stream app (`GET /api/stream`) with catch-up and a `delayed` notice; display text and step reasons scanned for leaked personal data. A trace failure publishes the run with the trace `pending:`; a recorder failure is retryable and replayable. Lane A S1 to S10 is now complete for steps 7 and 8 |
| Step 9a (done): Finebase HQ | The console now has three tenants: demo-fbl and Scale Demo (mock data) and Finebase HQ (real backend). `backend/app/main.py` builds the HQ pipeline (`app/api/hq.py`: real infra where it answers, real Claude and Voyage when keys are set) and serves tenant, humans, clusters, runs, run detail, escalations, approvals with decide (S8 rules, 409 when refused), access decisions, audit and the live stream (`/api/t/finebase-hq/stream`). Unbuilt HQ screens answer [] or 501, never demo data. People: Pamuditha Senanayake (L1), Udayanga Weerakoon and Imashi Dissanayake (L2). Send test emails with `uv run python -m demos.send_to_hq`; check shapes with `npx tsx scripts/check-contracts.ts` |
| Step 9b (done): Ask and Sensors | `POST /api/t/finebase-hq/ask` (`app/api/ask.py`) reads through S5 with the asker's own tier, logs the read on `access.decisions`, and has Claude Sonnet answer citing only items it was given (unknown ids dropped). No Claude key lists the closest items; store outage answers 503. `GET sensors` lists the connectors named in `hq_tenant.json`, with health from the grant and events per hour and last event from S1's counters. Checked by `tests/test_api_brain.py` and `scripts/check-contracts.ts` |
| Trends tab | Frontend only, on mock data for demo-fbl and Scale Demo. Backend counts and spike check come with S13 |
| Still to come | OPA. In Postgres: graph, facts, chunks, outbox, encrypted vault columns |
| Start all infra | `backend/scripts/dev_up.sh` |

Suggested order, following the acceptance test in `CB_Core_Pipeline_Design.md` section 11: finish the missing contracts, then the refund path in Lane A (S1 → S10) with Docker Compose infra, then S14 and Studio writes, then Lanes B, C and D, then MCP.

## 12. Open questions

| # | Question | Affects |
|---|---|---|
| 1 | Stripe, PayHere or both? | S1, S9, keys |
| 2 | Which CMS runs the website? | Web content loop |
| 3 | Google Workspace or Microsoft 365 for the support inbox? | Email connector |
| 4 | Hosting region under the Sri Lankan Personal Data Protection Act? | AWS region, retention |
| 5 | Real audit and raw signal retention? | Storage map |
| 6 | Real refund window and auto threshold? (30 days and LKR 50,000 are samples) | Policy seed, tests |
| 7 | Temporal Cloud or self hosted? | Ops |
| 8 | Who hosts the MCP server and which OAuth provider signs Claude in? | MCP entry point |
| 9 | Where do custom tool sandboxes run? | Tool registry, S9 |

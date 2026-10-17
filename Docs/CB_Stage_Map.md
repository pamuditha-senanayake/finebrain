# Company Brain Stage Map

This page maps the fifteen pipeline stages to their contracts. For each stage it names what comes in, what goes out, how it travels and which feature file tests it. The source is `Docs/CB_Core_Pipeline_Design.md`, sections 1, 2 and 5. When the two disagree, the design doc wins.

A golden sample record goes with this map. It follows one late refund through every seam it touches. So each stage has a real input to start from and a real output to check against.

## Stages

Each row is one stage with one job. A stage reads its input contract and writes its output contract. Nothing else crosses between stages.

| Stage | Job | Input contract | Output contract | Topic or call | Feature file |
|---|---|---|---|---|---|
| S1 Capture | Receive, verify and store raw signals | Raw source event (webhook, poll or upload) | K1 RawSignalEnvelope | Publishes `signals.raw`. Writes the raw body to object storage. | `s01_capture.feature` |
| S2 Normalize and protect | Canonical shape, masking, dedup | K1 RawSignalEnvelope | K2 Signal | Reads `signals.raw`. Publishes `signals.normalized`. Bad input goes to `signals.raw.dlq`. | `s02_normalize.feature` |
| S3 Route | Match a signal to activity, skill and agent | K2 Signal, K14 ReleaseEvent, K15 GapDetected | K3 TaskRequest | Reads `signals.normalized`, `graph.released`, `evidence.gaps`. Publishes `tasks.created` or `tasks.unrouted`. | `s03_route.feature` |
| S4 Orchestrate | Durable task lifecycle, timers, retries | K3 TaskRequest | Workflow and Run row, no seam contract | Reads `tasks.created`. Starts Temporal `task_workflow` with workflow ID equal to the task ID. | `s04_orchestrate.feature` |
| S5 Retrieve | Access filtered, bitemporal hybrid retrieval | K4 ContextQuery | K4 ContextBundle | Internal call `POST /internal/context/query`. Logs to `access.decisions`. | `s05_retrieve.feature` |
| S6 Reason | Plan, draft, propose actions | K4 ContextBundle and skill steps | K4 ContextQuery, K5 ProposedAction | Temporal activity `agent_step`. Steps go to `runs.steps`. | `s06_reason.feature` |
| S7 Govern | Access check, policy rules, quality gates, criticality | K5 ProposedAction | K6 AccessCheck, K7 GovernanceVerdict | Internal call to OPA for K6. Temporal activity output for K7, also on `runs.steps`. | `s07_govern.feature` |
| S8 Decide | Approvals, escalations, takeover, delegation, expiry | K7 GovernanceVerdict, K13 ChangeRequest, K15 GapDetected | K8 ApprovalRequest and Decision | Publishes `approvals.requested` and `approvals.decided` through the outbox. A Temporal signal wakes the waiting workflow. | `s08_decide.feature` |
| S9 Act | Call outside systems safely | K8 Decision with final arguments | K9 ActionResult | Temporal activity `tool_call`. Publishes `actions.executed`. | `s09_act.feature` |
| S10 Record | Templates, trace, audit, live UI | `runs.steps` events, K9 ActionResult | K10 RunRecord, K11 UiEvent | Publishes `runs.completed`, `audit.events`, `ui.events`. Serves SSE on `GET /api/stream`. | `s10_record.feature` |
| S11 Ingest knowledge | File, parse, chunk, embed, extract | K2 Signal of kind `document_arrived` | K12 FactCandidate | Publishes `docs.filed`, `docs.extracted`, `facts.candidates`. | `s11_ingest.feature` |
| S12 Librarian | Compare candidates with ground truth | K12 FactCandidate | K13 Commit and ChangeRequest | Reads `facts.candidates`. Calls the graph service API. | `s12_librarian.feature` |
| S13 Learn | Nightly review, health, drift, Skillify, evals, replay | K10 RunRecord and run traces | K13 Commit and ChangeRequest | Temporal `nightly_review` and `change_request_workflow`. Reads `runs.completed`. | `s13_learn.feature` |
| S14 Version and release | Git for the graph | K13 Commit and ChangeRequest, K8 Decision | K14 ReleaseEvent, K8 ApprovalRequest | Publishes `graph.commits` and `graph.released` through the outbox. | `s14_version_release.feature` |
| S15 Readiness | Find missing evidence early | Obligations, templates and facts in Postgres | K15 GapDetected | Temporal schedule `readiness`, each hour. Publishes `evidence.gaps`. | `s15_readiness.feature` |

All feature files live in `backend/tests/features/pipeline/`. The whole pipeline runs together in `e2e_lanes.feature`.

## Seams

A seam is the line between two stages, and each seam has one contract. The last two columns show where the Python model lives today and whether the golden record passes through it.

| Seam | Contract | From → To | Transport | Python model | In golden record |
|---|---|---|---|---|---|
| K1 | RawSignalEnvelope | S1 → S2 | Kafka `signals.raw` | `contracts_signal.py` | Yes |
| K2 | Signal | S2 → S3, S11 | Kafka `signals.normalized` | `contracts_signal.py` | Yes |
| K3 | TaskRequest | S3 → S4 | Kafka `tasks.created` | `contracts_signal.py` | Yes |
| K4 | ContextQuery, ContextBundle | S6 → S5 → S6 | Internal HTTP | `contracts_reason.py` | Yes |
| K5 | ProposedAction | S6 → S7 | Temporal activity input | `contracts_reason.py` | Yes, three actions |
| K6 | AccessCheck | S5, S7 → OPA | Internal HTTP | Response only, in `contracts_reason.py` | Yes, four checks |
| K7 | GovernanceVerdict | S7 → S8 | Temporal activity output | `contracts_run.py` | Yes, four verdicts |
| K8 | ApprovalRequest, Decision | S7, S14 → S8 → S9, S14 | Kafka `approvals.requested`, `approvals.decided` | `contracts_run.py` | Yes, two approvals |
| K9 | ActionResult | S9 → S10 | Kafka `actions.executed` | `contracts_run.py` | Yes, three actions |
| K10 | RunRecord | S10 → S13 | Kafka `runs.completed` | `contracts_run.py` | Yes |
| K11 | UiEvent | S10 → console | SSE `GET /api/stream` | `contracts_run.py` | Yes, five events |
| K12 | FactCandidate | S11 → S12 | Kafka `facts.candidates` | `contracts_signal.py` | No. The email has no document. |
| K13 | Commit, ChangeRequest | S12, S13 → S14 | Graph API, then Kafka `graph.commits` | Not yet | Yes |
| K14 | ReleaseEvent | S14 → S3, S5, S6, S11 | Kafka `graph.released` | Not yet | Yes |
| K15 | GapDetected | S15 → S3, S8 | Kafka `evidence.gaps` | Not yet | No. Nothing is missing evidence. |

Every Kafka message also carries the shared envelope from section 5.0. That model is `Envelope` in `contracts_signal.py`.

## Golden record

The record is `backend/samples/golden_late_refund_c1.json`. It is the story from section 11 of the design doc and from scenario E2E.02. Customer C1 bought a Business annual plan for LKR 85,000, 41 days before the email. That is outside the 30 day window and above the LKR 50,000 auto threshold.

The input is the same email as `s3_refund_annual_late_large` in `pipeline_samples.json`. The record follows it through these steps, in time order.

| Time (UTC) | Seams | What happens |
|---|---|---|
| 04:10:01 | K1, K2, K3 | The email is captured, masked and routed to `refund_standard` version 4 |
| 04:10:02 | K4 | The agent gets four allowed items. One restricted item is denied and counted. |
| 04:10:05 | K5, K6, K7, K9 | A C0 acknowledgement goes out with no refund promise |
| 04:10:06 | K5, K6, K7, K11 | The refund fails both policies, reaches C3 and escalates |
| 04:26:00 | K6, K7, K8, K11 | The operator takes over and proposes the refund. A C3 approval goes to the head of customer success. |
| 05:00:00 | K8, K9, K11 | The DRI approves. The gateway refunds LKR 85,000 once, with the run idempotency key. |
| 05:00:05 | K5, K6, K7, K9, K10, K11 | The customer gets a confirmation. The refund register is filled and the run closes as resolved. |
| 05:10:00 | K13 | The operator presses Skillify. A draft skill lands on `sandbox/skillify_refund_late_annual`. |
| 05:12:00 | K8, K13 | Tests pass and the replay shows 37 of 412 decisions change. A C3 approval opens. |
| 05:35:00 | K8, K13, K14 | The DRI approves. The merge releases `refund_late_annual` version 1. |

Every value is fixed. IDs, hashes, UUIDv7 event IDs and PII tokens are all derived from fixed inputs, so a rebuild gives the same file byte for byte. The raw body hash is the real SHA256 of the email. Commit IDs are the hash of their own content. Policy spans point to the exact text in the refund policy sample.

Each payload was checked against the Pydantic models. K6 requests, K13 and K14 have no model yet, so they were checked against the field tables in section 5.2. No seam holds the customer's raw name, email, NIC or phone. Only the input does.

## Gaps for the schema step

The record showed a few gaps. The schema step should close them.

| Gap | Where | Fix |
|---|---|---|
| No models for K6 request, K13, K14 and K15 | `backend/app/pipeline/` | Add them from section 5.2 |
| `awaiting_approval` is a run outcome that the design doc does not list | `contracts_run.py` | Add it to section 5.2 of the design doc, or remove it from the model |
| The walking skeleton sample uses cluster `customer_care` | `pipeline_samples.json` | Use `finebase_platform` as in section 5.0 |
| The walking skeleton expects the late refund to go straight to approval | `s3_refund_annual_late_large` | Section 11 escalates first, because `refund_standard` version 4 has no late refund step. The golden record follows section 11. |

# Stage map: Lane A (S1 to S10)

The refund path from one signal to a governed action. Golden data: `backend/samples/golden_refund_run.json`. Check: `uv run python -m scripts.check_golden`.

| Stage | Job | In | Out | Transport out |
|---|---|---|---|---|
| S1 Capture | Verify and store raw once | Raw email or webhook | K1 RawSignalEnvelope | Kafka `signals.raw` |
| S2 Normalize | Mask personal data, dedup | K1 | K2 Signal | Kafka `signals.normalized` |
| S3 Route | Match the activity, then its owner agent and skill | K2 | K3 TaskRequest | Kafka `tasks.created` |
| S4 Orchestrate | Start a run (recipe, chat hand-off), or join a later chat message to the open run; timers, retries | K3 | RunStarted, or RunContinued | `runs.started`, `runs.continued`, Temporal |
| S5 Retrieve | Access-filtered context | K4 ContextQuery | K4 ContextBundle | Sync HTTP |
| S6 Reason | Plan and propose | K3, K4 ContextBundle | K5 ProposedAction | Temporal |
| S7 Govern | Access, policy, gates, criticality | K5 | K6 AccessDecision, K7 GovernanceVerdict | Temporal |
| S8 Decide | Approvals and expiry | K7 | K8 ApprovalRequest, Decision | Kafka `approvals.*` |
| S9 Act | Call the outside tool once | K7 (execute) or K8 Decision | K9 ActionResult | Kafka `actions.executed` |
| S10 Record | Run record and live UI | K9 and run steps | K10 RunRecord, K11 UiEvent | Kafka `runs.completed`, SSE |

## The two golden runs

| Run | Request | Route | Ends at |
|---|---|---|---|
| s2 | LKR 12,000, 6 days after purchase | execute (C0) | K9 succeeded, K10 resolved |
| s3 | LKR 85,000, 41 days after purchase | approval_required (C3) | K8 ApprovalRequest, K10 awaiting_approval |

Every message in a run shares one `correlation_id`. Each Kafka message's `causation_id` is the event before it.

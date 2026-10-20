# views.py: turns what the pipeline recorded (run records, traces, approvals, decisions, the audit log) into the
# console's shapes. Read only. Used by: routes.py, lists.py. Uses: ui_models*.py, stages_record.py, contracts_*.py.
import json

from app.api import ui_models as ui
from app.api import ui_models_work as work
from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_signal import TaskRequest
from app.pipeline.stages_record import describe_title

# Config
RUN_STATUS = {"resolved": "succeeded", "escalated": "escalated", "failed": "failed", "blocked": "blocked", "awaiting_approval": "awaiting_approval", "abandoned": "failed"}
STEP_TITLES = {"retrieval": "Read the knowledge it may see", "judgment": "Proposed an action", "access_check": "Access check", "tool": "Called the tool", "human": "Waiting for a person", "quality_gate": "Quality gate"}
MAX_APPROVAL = {"L1": 4, "L2": 2, "L3": 1}


# --- Shared lookups

def trace_of(lane, run: dict) -> dict:
    """The run's trace from S3, or {} when it is pending or unreadable."""
    uri = run["trace_object_uri"]
    try:
        return {} if uri.startswith("pending:") else json.loads(lane.object_store[uri])
    except (KeyError, ValueError):
        return {}


def audit_entries(lane, topic: str | None = None) -> list[dict]:
    return [entry for entry in lane.audit.in_order() if topic is None or entry["topic"] == topic]


def subject_of(trace: dict, run: dict) -> str:
    if trace.get("task") and trace.get("action"):
        return describe_title(TaskRequest.model_validate(trace["task"]), ProposedAction.model_validate(trace["action"]))
    return run["task_id"]


# --- Runs

def escalation_of(run: dict, trace: dict, status: str, ended_at: str | None) -> work.Escalation | None:
    if status not in ("escalated", "awaiting_approval"):
        return None
    verdict, approval = trace.get("verdict") or {}, trace.get("approval") or {}
    level = verdict.get("criticality", 0)
    reason = ", ".join(verdict.get("criticality_reasons", [])) or run["steps"][-1]["decision"]
    return work.Escalation(reason=reason.replace("_", " "), risk="high" if level >= 3 else "medium" if level == 2 else "low",
                         since=ended_at or run["steps"][0]["started_at"], assignee=approval.get("assignee"), criticality=level)


def run_view(lane, run: dict) -> work.Run:
    trace, status = trace_of(lane, run), RUN_STATUS[run["outcome"]]
    mark = lane.records.load("run_mark", run["run_id"])  # step 15: someone marked it wrong (run_marks.py)
    ended_at = None if status == "awaiting_approval" else run["steps"][-1]["started_at"] if run["steps"] else None
    cost = run["cost"]
    return work.Run(
        id=run["run_id"], tenant_id=lane.seed["tenant_id"], cluster_id=lane.seed["cluster_id"], agent_id=run["agent_id"],
        skill=ui.VersionRef(**{key: run["skill_ref"][key] for key in ("id", "version", "branch")}), env=lane.seed["env"],
        subject=subject_of(trace, run), status=status, started_at=run["steps"][0]["started_at"] if run["steps"] else "",
        ended_at=ended_at, escalation=escalation_of(run, trace, status, ended_at), conversation_id=None,
        cost_tokens=cost["input_tokens"] + cost["output_tokens"], cost_usd=cost["usd_micro"] / 1_000_000,
        latency_ms=run["latency_ms"], human_touch=run["human_touch"] or mark is not None,
        failure_class="marked wrong" if mark else "tool_failed" if status == "failed" else None,
        marked_wrong={"by": mark["by"], "at": str(mark["at"]), "note": mark["note"]} if mark else None,
    )


def step_view(lane, step: dict, idx: int, trace: dict) -> work.TraceStep:
    """One run step. Judgment steps show the facts cited; access steps show the decision."""
    action = trace.get("action") or {}
    knowledge = {node["item_id"]: node for node in lane.graph.latest("knowledge")}
    cited = [knowledge[item] for item in action.get("citations", []) if item in knowledge] if step["kind"] == "judgment" else []
    return work.TraceStep(
        id=f"{step['step_id']}-{idx}", idx=idx, kind=step["kind"], title=STEP_TITLES[step["kind"]], decision=step["decision"],
        reason=step["reason"], duration_ms=step["duration_ms"], at=step["started_at"],
        facts=[{"id": item["item_id"], "statement": item["text"], "validFrom": item["valid_from"], "validTo": item["valid_to"]} for item in cited],
        access={"action": action.get("action_type", ""), "decision": step["decision"], "ruleId": step["reason"]} if step["kind"] == "access_check" else None,
        gate=None, tool=action.get("tool_id") if step["kind"] == "tool" else None, template_fields=[],
        cost_tokens=(action.get("model") or {}).get("input_tokens", 0) + (action.get("model") or {}).get("output_tokens", 0) if step["kind"] == "judgment" else 0,
    )


def run_detail(lane, run: dict) -> work.RunDetail:
    trace = trace_of(lane, run)
    return work.RunDetail(**run_view(lane, run).model_dump(), steps=[step_view(lane, step, idx, trace) for idx, step in enumerate(run["steps"])])


# --- Approvals

def approval_status(run: dict | None, decisions: list[dict]) -> str:
    outcome, last = (run or {}).get("outcome"), decisions[-1]["decision"] if decisions else None
    if outcome == "awaiting_approval" or run is None:
        return "pending"
    if outcome == "resolved":
        return "approved"
    if last == "request_changes":
        return "changes_requested"
    return "rejected" if outcome == "blocked" or last in ("reject", "takeover") else "expired"


def approval_view(lane, approval: dict) -> ui.Approval:
    decisions = lane.records.history("decision", approval["approval_id"])
    run = lane.records.load("run", approval["subject"]["ref"].split(":")[0])
    requested = next((entry for entry in audit_entries(lane, "approvals.requested") if entry["body"]["payload"]["approval_id"] == approval["approval_id"]), None)
    votes = [ui.Vote(by=d["decided_by"][0], at=d["decided_at"], decision=d["decision"], comment=d.get("comment", "")) for d in decisions if d["decision"] in ("approve", "reject", "request_changes", "delegate")]
    delegated = [d["delegated_to"] for d in decisions if d["decision"] == "delegate"]
    return ui.Approval(
        id=approval["approval_id"], tenant_id=lane.seed["tenant_id"], subject={"kind": "action", "id": approval["subject"]["ref"].split(":")[0]},
        title=approval["summary_plain"].split(". ")[0], summary=approval["summary_plain"], criticality=approval["criticality"],
        required_approvers=approval["required_approvers"], votes=votes, due_at=approval["due_at"],
        created_at=requested["body"]["occurred_at"] if requested else approval["due_at"], status=approval_status(run, decisions),
        delegated_to=delegated[-1] if delegated else None, dri=approval["dri_id"],
        drafter=ui.Actor(kind="agent", id=(run or {}).get("agent_id", "agent"), name=(run or {}).get("agent_id", "agent")),
        evidence=approval["evidence_refs"], correlation_id=requested["body"]["correlation_id"] if requested else "",
    )


# --- People, access log, audit

def human_view(lane, person_id: str, person: dict) -> ui.Human:
    return ui.Human(id=person_id, tenant_id=lane.seed["tenant_id"], name=person.get("name", person_id), title=person.get("title", ""), tier=person["tier"],
                    roles=person["roles"], attributes={}, dri_of=[], max_approval_criticality=MAX_APPROVAL[person["tier"]], color=person.get("color", "#4338ca"))


def access_view(lane, entry: dict) -> work.AccessDecision:
    p = entry["body"]["payload"]
    return work.AccessDecision(id=p["decision_id"], tenant_id=lane.seed["tenant_id"], at=entry["body"]["occurred_at"], principal=p.get("principal_id") or "unknown",
                             on_behalf_of=p.get("on_behalf_of"), action=p.get("action") or "", resource=p.get("resource") or "", decision=p["decision"],
                             rule_id=p["rule_id"], reason=p["reason"], latency_ms=p["latency_ms"], run_id=p.get("run_id"))


def audit_view(lane, entry: dict) -> ui.AuditEvent:
    """One audit entry, with the person who decided as the actor when a person did. Most entries hold a bus message; step 10's
    forget.completed holds a plain body (who, when, why), which is its own payload."""
    body = entry["body"]
    payload, producer = body.get("payload", body), body.get("producer", entry["topic"].split(".")[0])
    person = (payload.get("decided_by") or [payload.get("by")])[0]
    actor = ui.Actor(kind="human", id=person, name=lane.seed["people"].get(person, {}).get("name", person)) if person else ui.Actor(kind="agent" if producer in ("worker", "internal", "governance") else "system", id=producer, name=producer)
    target_id = next((payload[key] for key in ("approval_id", "action_id", "run_id", "decision_id", "document_id") if payload.get(key)), entry["event_id"])
    return ui.AuditEvent(id=entry["event_id"], tenant_id=lane.seed["tenant_id"], at=body.get("occurred_at") or body["at"], actor=actor, action=entry["topic"],
                         target={"type": entry["topic"].split(".")[0], "id": target_id, "label": target_id}, env=lane.seed["env"],
                         criticality=payload.get("criticality", 0), detail=payload.get("summary_plain") or payload.get("reason") or payload.get("outcome") or payload.get("status") or "",
                         correlation_id=body.get("correlation_id", entry["event_id"]))

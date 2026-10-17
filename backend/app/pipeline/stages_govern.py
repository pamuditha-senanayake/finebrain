# stages_govern.py: S7 Govern (K5 to K6 and K7) and S8 Decide (K7 to a K8 ApprovalRequest).
# Used by: tests/test_stages.py, stages_record.py (format_money). Uses: contracts_signal.py, contracts_reason.py, contracts_run.py.
# Step 2 knows one policy, the refund policy. More policies come when stages get thicker (step 7).
from datetime import datetime, timedelta

from app.pipeline.contracts_reason import AccessCheck, AccessDecision, ContextBundle, ProposedAction, Resource
from app.pipeline.contracts_run import (
    ApprovalRequest, ApprovalSubject, Approvers, GateResult, GovernanceVerdict, PolicyResult,
)
from app.pipeline.contracts_signal import Money, Principal, TaskRequest, VersionRef

# Config
CAPABILITY_FOR_ACTION = {"issue_refund": "refund.propose", "reply_customer": "reply.draft", "escalate": "escalate"}
OPEN_CAPABILITIES = {"escalate"}  # anyone may hand a case to a human
FAILURE_REASONS = {"refund.window": "outside_refund_window", "refund.auto_limit": "above_auto_threshold"}
APPROVERS_BY_CRITICALITY = {  # reference doc section 2
    1: {"tier": "L2", "count": 1, "roles": ["supervisor_agent"]},
    2: {"tier": "L2", "count": 1, "roles": ["steward"]},
    3: {"tier": "L1", "count": 1, "roles": ["dri"]},
    4: {"tier": "L1", "count": 2, "roles": ["dri", "leader"]},
}
APPROVAL_DUE_HOURS = 24
APPROVAL_EXPIRES_HOURS = 72


def format_money(money: Money) -> str:
    """LKR 8500000 minor units reads as 'LKR 85,000'."""
    return f"{money.currency} {money.amount_minor // 100:,}"


# --- S7 checks

def check_access(action: ProposedAction, principal: Principal, cluster_id: str, new_id) -> tuple[AccessCheck, AccessDecision]:
    """Allow only when the principal holds the capability the action needs. Unknown actions fail closed."""
    capability = CAPABILITY_FOR_ACTION.get(action.action_type, "unknown")
    resource = Resource(type="payment", id=action.arguments.get("payment_ref", ""), cluster_id=cluster_id, sensitivity="confidential")
    check = AccessCheck(check_id=new_id("chk"), principal=principal, on_behalf_of=None, action=capability, resource=resource)
    allowed = capability in OPEN_CAPABILITIES or capability in principal.capabilities
    decision = AccessDecision(
        decision_id=new_id("acc"), decision="allow" if allowed else "deny", rule_id=f"capability:{capability}",
        reason=f"{principal.id} {'holds' if allowed else 'lacks'} {capability}", latency_ms=0,
    )
    return check, decision


def check_policy(action: ProposedAction, policy: dict, payment: dict, now: datetime) -> list[PolicyResult]:
    """The refund policy's two rules: inside the window, and under the automatic limit."""
    days = (now - datetime.fromisoformat(payment["paid_at"])).days
    limit = Money(**policy["auto_limit"])
    ref = VersionRef(**policy["policy_ref"])
    return [
        PolicyResult(policy_ref=ref, passed=days <= policy["window_days"], rule_id="refund.window",
                     explanation=f"{days} days since purchase, window is {policy['window_days']}"),
        PolicyResult(policy_ref=ref, passed=action.money.amount_minor <= limit.amount_minor, rule_id="refund.auto_limit",
                     explanation=f"{format_money(action.money)} against a limit of {format_money(limit)}"),
    ]


def check_gates(action: ProposedAction, bundle: ContextBundle, payment: dict) -> list[GateResult]:
    """Every citation must be in the bundle, and the amount must equal what was paid."""
    bundle_ids = {item.item_id for item in bundle.items}
    cited = bool(action.citations) and set(action.citations) <= bundle_ids
    gates = [GateResult(gate_id="citations_present", passed=cited, detail=f"{len(action.citations)} citations")]
    if action.touches.money:  # an unknown payment ref fails this gate, so the case escalates
        amount_ok = payment is not None and action.money is not None and action.money.amount_minor == payment["amount_minor"]
        gates.append(GateResult(gate_id="amount_matches_payment", passed=amount_ok, detail=f"paid {payment['amount_minor'] if payment else 'unknown'}"))
    return gates


def decide_criticality(task: TaskRequest, action: ProposedAction, failed: list[PolicyResult], policy: dict) -> tuple[int, list[str]]:
    """Policy allows it: no money bump. Otherwise bump for money and take the policy's escalation level."""
    if not failed:
        return task.base_criticality, ["policy_auto_approval" if action.touches.money else "within_skill"]
    bumped = min(task.base_criticality + 1, 4) if action.touches.money else task.base_criticality
    return max(bumped, policy["escalation"]["criticality"]), [FAILURE_REASONS[result.rule_id] for result in failed]


def choose_route(decision: AccessDecision, gates: list[GateResult], criticality: int) -> str:
    """A deny always blocks. A failed gate escalates. Only C0 executes on its own."""
    if decision.decision == "deny":
        return "block"
    if not all(gate.passed for gate in gates):
        return "escalate"
    return "execute" if criticality == 0 else "approval_required"


def escalate_verdict(task: TaskRequest, action: ProposedAction, decision: AccessDecision) -> GovernanceVerdict:
    """S6 handed the case to a human: no policy or money checks, route escalate."""
    return GovernanceVerdict(
        run_id=action.run_id, step_id=action.step_id, access_decision_id=decision.decision_id, policy_results=[], quality_gates=[],
        criticality=task.base_criticality, criticality_reasons=[action.arguments.get("reason", "escalated")], route="escalate", required_approvers=None,
    )


# --- S7 Govern

def govern(
    task: TaskRequest, action: ProposedAction, bundle: ContextBundle, principal: Principal,
    policy: dict, payments: dict, cluster_id: str, now: datetime, new_id,
) -> tuple[AccessCheck, AccessDecision, GovernanceVerdict]:
    """S7: access first, then policy, gates and criticality, then the route."""
    # Step 1: access, policy and quality gates; S6 asking for a human skips straight to escalate
    check, decision = check_access(action, principal, cluster_id, new_id)
    if action.action_type == "escalate":
        return check, decision, escalate_verdict(task, action, decision)
    payment = payments.get(action.arguments.get("payment_ref", ""))
    policy_results = check_policy(action, policy, payment, now) if action.touches.money and payment else []
    gates = check_gates(action, bundle, payment)

    # Step 2: criticality decides who approves, the route decides what happens next
    failed = [result for result in policy_results if not result.passed]
    criticality, reasons = decide_criticality(task, action, failed, policy)
    route = choose_route(decision, gates, criticality)
    approvers = policy["escalation"]["approvers"] if failed else APPROVERS_BY_CRITICALITY.get(criticality)
    verdict = GovernanceVerdict(
        run_id=action.run_id, step_id=action.step_id, access_decision_id=decision.decision_id,
        policy_results=policy_results, quality_gates=gates, criticality=criticality, criticality_reasons=reasons,
        route=route, required_approvers=Approvers(**approvers) if route == "approval_required" else None,
    )
    return check, decision, verdict


# --- S8 Decide

def request_approval(action: ProposedAction, verdict: GovernanceVerdict, new_id, now: datetime) -> ApprovalRequest:
    """S8: open one approval with one accountable human. Expiry goes to a delegate, never auto approves."""
    reasons = ", ".join(reason.replace("_", " ") for reason in verdict.criticality_reasons)
    title = action.action_type.replace("_", " ").capitalize()
    return ApprovalRequest(
        approval_id=new_id("apr"), subject=ApprovalSubject(kind="action", ref=f"{action.run_id}:{action.step_id}"),
        criticality=verdict.criticality, summary_plain=f"{title} {format_money(action.money)}. Needs approval: {reasons}.",
        evidence_refs=action.citations, required_approvers=verdict.required_approvers,
        dri_id=verdict.required_approvers.roles[0],
        due_at=now + timedelta(hours=APPROVAL_DUE_HOURS), expires_at=now + timedelta(hours=APPROVAL_EXPIRES_HOURS),
    )

# stages_govern.py: S7 Govern (K5 to K6 and K7). Access through OPA, the skill's policy from the graph, quality
# gates (citations, amount, confidence, a grader), criticality with every section 2 bump, then the route.
# Used by: run_steps.py, tests. Uses: contracts_*.py, stages_decide.py (format_money), an access checker, a grader.
from datetime import datetime

from app.pipeline.contracts_reason import AccessCheck, AccessDecision, ContextBundle, ProposedAction, Resource
from app.pipeline.contracts_run import Approvers, GateResult, GovernanceVerdict, PolicyResult
from app.pipeline.contracts_signal import Money, Principal, TaskRequest, VersionRef
from app.pipeline.stages_decide import format_money

# Config
CAPABILITY_FOR_ACTION = {"issue_refund": "refund.propose", "reply_customer": "reply.draft", "escalate": "escalate"}
POLICY_FOR_ACTION = {"issue_refund": "policy_refund"}
FAILURE_REASONS = {"refund.window": "outside_refund_window", "refund.auto_limit": "above_auto_threshold"}
APPROVERS_BY_CRITICALITY = {  # reference doc section 2
    1: {"tier": "L2", "count": 1, "roles": ["supervisor_agent"]},
    2: {"tier": "L2", "count": 1, "roles": ["steward"]},
    3: {"tier": "L1", "count": 1, "roles": ["dri"]},
    4: {"tier": "L1", "count": 2, "roles": ["dri", "leader"]},
}
INJECTION_FLAG, INJECTION_MIN_CRITICALITY = "possible_prompt_injection", 2  # a flagged case always waits for a human
MIN_CONFIDENCE = 0.6
C4_COOLING_HOURS = 24


# --- Checks

def check_access(action: ProposedAction, task: TaskRequest, principal: Principal, cluster_id: str, checker, new_id) -> tuple[AccessCheck, AccessDecision]:
    """K6 through the checker (OPA, or its memory twin). Unknown actions need a capability nobody has."""
    resource = Resource(type="payment", id=action.arguments.get("payment_ref", ""), cluster_id=cluster_id, sensitivity="confidential")
    check = AccessCheck(check_id=new_id("chk"), principal=principal, on_behalf_of=task.on_behalf_of, action=CAPABILITY_FOR_ACTION.get(action.action_type, "unknown"), resource=resource)
    answer = checker(check)
    decision = AccessDecision(
        decision_id=new_id("acc"), decision="allow" if answer["allow"] else "deny", rule_id=answer["rule_id"], reason=answer["reason"], latency_ms=0,
        principal_id=principal.id, on_behalf_of=task.on_behalf_of, action=check.action, resource=f"{resource.type}:{resource.id}", run_id=action.run_id,
    )
    return check, decision


def check_policy(action: ProposedAction, policy: dict, payment: dict, now: datetime) -> list[PolicyResult]:
    """The refund policy's two rules: inside the window, and under the automatic limit."""
    days = (now - datetime.fromisoformat(payment["paid_at"])).days
    limit, ref = Money(**policy["auto_limit"]), VersionRef(**policy["_ref"])
    return [
        PolicyResult(policy_ref=ref, passed=days <= policy["window_days"], rule_id="refund.window", explanation=f"{days} days since purchase, window is {policy['window_days']}"),
        PolicyResult(policy_ref=ref, passed=action.money.amount_minor <= limit.amount_minor, rule_id="refund.auto_limit", explanation=f"{format_money(action.money)} against a limit of {format_money(limit)}"),
    ]


def check_gates(action: ProposedAction, bundle: ContextBundle, payment: dict | None, grade, context: str) -> list[GateResult]:
    """Citations real, amount right, confidence high enough, and the rationale backed by the cited documents."""
    cited_items = [item for item in bundle.items if item.item_id in action.citations]
    cited = bool(action.citations) and len(cited_items) == len(set(action.citations))
    gates = [GateResult(gate_id="citations_present", passed=cited, detail=f"{len(action.citations)} citations")]
    if action.touches.money:  # an unknown payment ref fails this gate, so the case escalates
        amount_ok = payment is not None and action.money is not None and action.money.amount_minor == payment["amount_minor"]
        gates.append(GateResult(gate_id="amount_matches_payment", passed=amount_ok, detail=f"paid {payment['amount_minor'] if payment else 'unknown'}"))
    gates.append(GateResult(gate_id="confidence", passed=action.confidence >= MIN_CONFIDENCE, detail=f"{action.confidence} against {MIN_CONFIDENCE}"))
    grounded, detail = grade(action.rationale_summary, [item.text for item in cited_items], context)
    gates.append(GateResult(gate_id="grounded", passed=grounded, detail=detail))
    return gates


# --- Criticality and route

def section_2_bumps(action: ProposedAction, policy_allows: bool) -> list[str]:
    """One level up for each sensitive thing touched. Money is waived when the skill's policy allows the action."""
    touches = action.touches
    bumps = [] if policy_allows or not touches.money else ["touches_money"]
    bumps += [name for name, touched in (("touches_personal_data", touches.personal_data), ("touches_public_content", touches.public_content), ("touches_legal_tax", touches.legal_tax)) if touched]
    return bumps + (["multiple_clusters"] if len(touches.clusters) > 1 else [])


def decide_criticality(task: TaskRequest, action: ProposedAction, failed: list[PolicyResult], policy: dict | None) -> tuple[int, list[str]]:
    """Bumps first. A failed policy rule lifts to the policy's escalation level, which already covers money."""
    bumps = section_2_bumps(action, policy_allows=policy is not None and not failed)
    level, reasons = min(task.base_criticality + len(bumps), 4), bumps
    if failed:
        level = max(level, policy["escalation"]["criticality"])
        reasons = [FAILURE_REASONS[result.rule_id] for result in failed] + [bump for bump in bumps if bump != "touches_money"]
    if INJECTION_FLAG in task.flags:
        level, reasons = max(level, INJECTION_MIN_CRITICALITY), reasons + [INJECTION_FLAG]
    return level, reasons or ["policy_auto_approval" if action.touches.money else "within_skill"]


def choose_route(decision: AccessDecision, gates: list[GateResult], criticality: int) -> str:
    """A deny always blocks. A failed gate escalates. Only C0 executes on its own."""
    if decision.decision == "deny":
        return "block"
    if not all(gate.passed for gate in gates):
        return "escalate"
    return "execute" if criticality == 0 else "approval_required"


def early_escalation(task: TaskRequest, action: ProposedAction, decision: AccessDecision, reason: str) -> GovernanceVerdict:
    """No policy or money checks: S6 asked for a human, or the policy needed is missing."""
    return GovernanceVerdict(
        run_id=action.run_id, step_id=action.step_id, access_decision_id=decision.decision_id, policy_results=[], quality_gates=[],
        criticality=task.base_criticality, criticality_reasons=[reason], route="escalate", required_approvers=None,
    )


# --- S7 Govern

def govern(task, action, bundle, principal, policies: dict, payments: dict, cluster_id: str, now, new_id, checker, grade, request_text: str = "") -> tuple[AccessCheck, AccessDecision, GovernanceVerdict]:
    """S7: access first, then policy, gates and criticality, then the route."""
    # Step 1: access; S6 asking for a human, or a missing policy, escalates at once
    check, decision = check_access(action, task, principal, cluster_id, checker, new_id)
    policy = policies.get(POLICY_FOR_ACTION.get(action.action_type, ""))
    if action.action_type == "escalate" or (action.touches.money and policy is None):
        return check, decision, early_escalation(task, action, decision, action.arguments.get("reason", "policy_missing"))

    # Step 2: policy and quality gates
    payment = payments.get(action.arguments.get("payment_ref", ""))
    policy_results = check_policy(action, policy, payment, now) if policy and payment else []
    context = f"Today is {now:%d %B %Y} and the request arrived today. The customer wrote (masked): {request_text or 'not given'}"
    gates = check_gates(action, bundle, payment, grade, context)

    # Step 3: criticality decides who approves, the route decides what happens next
    failed = [result for result in policy_results if not result.passed]
    criticality, reasons = decide_criticality(task, action, failed, policy)
    route = choose_route(decision, gates, criticality)
    approvers = policy["escalation"]["approvers"] if failed else APPROVERS_BY_CRITICALITY.get(criticality)
    verdict = GovernanceVerdict(
        run_id=action.run_id, step_id=action.step_id, access_decision_id=decision.decision_id, policy_results=policy_results,
        quality_gates=gates, criticality=criticality, criticality_reasons=reasons, route=route,
        required_approvers=Approvers(**approvers) if route == "approval_required" else None,
        cooling_period_hours=C4_COOLING_HOURS if criticality == 4 else 0,
    )
    return check, decision, verdict

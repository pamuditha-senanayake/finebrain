# stages_decide.py: S8 Decide rules. Opens an approval (K8) with one accountable person, and judges each decision:
# who may decide, distinct approvers for C4, safe edits, and who takes over when an approval expires.
# Used by: run_approvals.py, run_steps.py, stages_record.py (format_money), tests. Uses: contracts_*.py, tools.py.
from datetime import datetime, timedelta

from pydantic import BaseModel, ValidationError

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import ApprovalRequest, ApprovalSubject, Approvers, Decision, GovernanceVerdict
from app.pipeline.contracts_signal import Money
from app.pipeline.tools import TOOLS

# Config
APPROVAL_DUE_FRACTION = 1 / 3  # due a third of the way to expiry, so there is time to chase it
TIER_RANK = {"L1": 1, "L2": 2, "L3": 3}  # lower number is higher; higher tiers can act for lower ones


class ApprovalState(BaseModel):
    """One open approval between decisions. A model, so Temporal can keep it in workflow history."""
    request: ApprovalRequest
    assignee: str  # the person accountable right now: the DRI, then the delegate
    expires_after_seconds: int
    round: int = 1  # 1 is the first approver, 2 is the delegate after an expiry
    approved_by: list[str] = []
    final_decision: Decision | None = None  # set once approved, kept through the cooling period
    cooling_seconds: int = 0
    cooling_until: datetime | None = None
    changes_requested: bool = False


def format_money(money: Money) -> str:
    """LKR 8500000 minor units reads as 'LKR 85,000'."""
    return f"{money.currency} {money.amount_minor // 100:,}"


def find_person(approvers: Approvers, people: dict) -> str:
    """The accountable person: one whose id is the role (head_of_cs), else the first of high enough tier holding it."""
    for role in approvers.roles:
        if role in people:
            return role
    fits = [pid for pid, person in people.items() if set(person["roles"]) & set(approvers.roles) and TIER_RANK[person["tier"]] <= TIER_RANK[approvers.tier]]
    return fits[0] if fits else approvers.roles[0]


def request_approval(action: ProposedAction, verdict: GovernanceVerdict, people: dict, new_id, now: datetime, expires_after_seconds: int) -> ApprovalState:
    """S8: open one approval with one accountable person. Expiry goes to a delegate, never auto approves."""
    reasons = ", ".join(reason.replace("_", " ") for reason in verdict.criticality_reasons)
    amount = f" {format_money(action.money)}" if action.money else ""
    dri = find_person(verdict.required_approvers, people)
    request = ApprovalRequest(
        approval_id=new_id("apr"), subject=ApprovalSubject(kind="action", ref=f"{action.run_id}:{action.step_id}"),
        criticality=verdict.criticality, summary_plain=f"{action.action_type.replace('_', ' ').capitalize()}{amount}. Needs approval: {reasons}.",
        evidence_refs=action.citations, required_approvers=verdict.required_approvers, dri_id=dri,
        due_at=now + timedelta(seconds=expires_after_seconds * APPROVAL_DUE_FRACTION), expires_at=now + timedelta(seconds=expires_after_seconds),
    )
    return ApprovalState(request=request, assignee=dri, expires_after_seconds=expires_after_seconds)


def refusal(decision: Decision, state: ApprovalState, people: dict, requester: str) -> str | None:
    """Why this decision may not count, or None. Every decider must be allowed; the requester never approves."""
    needed = state.request.required_approvers
    for person_id in decision.decided_by:
        person = people.get(person_id)
        if person_id == requester:
            return "requester_cannot_decide"
        if person is None:
            return "unknown_person"
        if person_id != state.assignee and (TIER_RANK[person["tier"]] > TIER_RANK[needed.tier] or not set(person["roles"]) & set(needed.roles)):
            return "not_an_approver"
    if decision.decision == "delegate" and decision.delegated_to not in people:
        return "unknown_delegate"
    return None


def edit_problem(final_arguments: dict | None, action: ProposedAction, paid_minor: int | None) -> str | None:
    """A human edit must fit the tool's schema and never pay more than was paid."""
    if not final_arguments:
        return None
    try:
        edited = TOOLS[action.action_type]["args"].model_validate({**final_arguments, "rationale_summary": "edited by approver", "citations": action.citations, "confidence": 1.0})
    except (ValidationError, KeyError) as error:
        return f"invalid_edit: {type(error).__name__}"
    amount = getattr(edited, "amount", None)
    if amount is not None and paid_minor is not None and amount.amount_minor > paid_minor:
        return "edit_exceeds_paid_amount"
    return None


def count_approvals(state: ApprovalState, decision: Decision) -> bool:
    """Add the new approvers (one person counts once). True when enough have approved."""
    state.approved_by = list(dict.fromkeys(state.approved_by + decision.decided_by))
    return len(state.approved_by) >= state.request.required_approvers.count


def hand_to_delegate(state: ApprovalState, people: dict, now: datetime) -> bool:
    """After an expiry, give the approval to the assignee's delegate for a second round. False when there is none."""
    delegate = (people.get(state.assignee) or {}).get("delegate")
    if state.round > 1 or not delegate:
        return False
    state.assignee, state.round = delegate, 2
    state.request = state.request.model_copy(update={"expires_at": now + timedelta(seconds=state.expires_after_seconds)})
    return True

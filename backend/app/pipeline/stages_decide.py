# stages_decide.py: S8 Decide. Opens one approval with one accountable human (K8). Expiry and delegation come
# when S8 gets thicker. Used by: run_steps.py, stages_record.py (format_money), tests. Uses: contracts_*.py.
from datetime import datetime, timedelta

from app.pipeline.contracts_reason import ProposedAction
from app.pipeline.contracts_run import ApprovalRequest, ApprovalSubject, GovernanceVerdict
from app.pipeline.contracts_signal import Money

# Config
APPROVAL_DUE_HOURS = 24
APPROVAL_EXPIRES_HOURS = 72


def format_money(money: Money) -> str:
    """LKR 8500000 minor units reads as 'LKR 85,000'."""
    return f"{money.currency} {money.amount_minor // 100:,}"


def request_approval(action: ProposedAction, verdict: GovernanceVerdict, new_id, now: datetime) -> ApprovalRequest:
    """S8: open one approval with one accountable human. Expiry goes to a delegate, never auto approves."""
    reasons = ", ".join(reason.replace("_", " ") for reason in verdict.criticality_reasons)
    title = action.action_type.replace("_", " ").capitalize()
    amount = f" {format_money(action.money)}" if action.money else ""
    return ApprovalRequest(
        approval_id=new_id("apr"), subject=ApprovalSubject(kind="action", ref=f"{action.run_id}:{action.step_id}"),
        criticality=verdict.criticality, summary_plain=f"{title}{amount}. Needs approval: {reasons}.",
        evidence_refs=action.citations, required_approvers=verdict.required_approvers,
        dri_id=verdict.required_approvers.roles[0],
        due_at=now + timedelta(hours=APPROVAL_DUE_HOURS), expires_at=now + timedelta(hours=APPROVAL_EXPIRES_HOURS),
    )

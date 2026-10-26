# reason_checks.py: the checks S6 makes on a refund before it becomes K5, in code, never left to the model. A refund must
# name a payment or order that S5 found for this customer, cite it, ask for no more than is left to return, and in a live
# chat come only after the customer confirmed the order the agent asked about. A failed check goes back to the model.
# Used by: stages_reason.py. Uses: contracts_reason.py (ContextBundle, ProposedAction).
import re

from app.pipeline.contracts_reason import ContextBundle, ProposedAction

# Config
MONEY = re.compile(r"LKR ([\d,]+(?:\.\d{2})?)")
REFUNDED = re.compile(r"refunded LKR ([\d,]+(?:\.\d{2})?) so far")
CHAT_PREFIX = "msg:"


def minor(amount: str) -> int:
    """LKR 4,000.00 or LKR 12,000 as minor units."""
    return round(float(amount.replace(",", "")) * 100)


def is_chat(bundle: ContextBundle) -> bool:
    """A live chat case: S5 put the chat so far in the bundle."""
    return any(item.item_id.startswith(CHAT_PREFIX) for item in bundle.items)


def target_of(bundle: ContextBundle, payment_ref: str):
    """The order or payment fact in the bundle that names this payment, or None. The customer's own, since S5 shows no other."""
    return next((item for item in bundle.items if item.kind == "fact" and payment_ref in item.text), None)


def left_to_refund(text: str) -> int | None:
    """What the order or payment still holds: paid minus refunded. None when the text names no amount."""
    paid = MONEY.search(text)
    if paid is None:
        return None
    refunded = REFUNDED.search(text)
    return minor(paid.group(1)) - (minor(refunded.group(1)) if refunded else 0)


def confirmed(bundle: ContextBundle, previous: list[dict]) -> bool:
    """The agent asked the customer to confirm in an earlier turn, and the customer wrote again after that question."""
    asked = [turn for turn in previous if turn["action_type"] == "reply_customer" and turn["arguments"].get("awaits_customer")]
    if not asked:
        return False
    messages = [item.item_id.removeprefix(CHAT_PREFIX) for item in bundle.items if item.item_id.startswith(CHAT_PREFIX)]
    last_question_on = asked[-1]["signal_id"]
    return last_question_on in messages and messages.index(last_question_on) < len(messages) - 1


def refund_problem(args, bundle: ContextBundle, previous: list[dict]) -> str | None:
    """Why this refund may not go on, said so the model can correct itself, or None when it may."""
    target = target_of(bundle, args.payment_ref)
    if target is None:
        return f"No order or payment {args.payment_ref} of this customer is in the documents. Refund only one listed there; if none is, ask the customer or escalate."
    if target.item_id not in args.citations:
        return f"Cite {target.item_id}, the order or payment you are refunding."
    left = left_to_refund(target.text)
    if left is not None and args.amount.amount_minor > left:
        return f"{target.item_id} has only {left} minor units left to refund; you asked for {args.amount.amount_minor}."
    if is_chat(bundle) and not confirmed(bundle, previous):
        return "This is a live chat. First confirm the exact order with the customer in one short question (reply_customer with awaits_customer true); refund only after they confirm."
    return None


def turn_of(action: ProposedAction, signal_id: str) -> dict:
    """What a turn keeps for the next one: what the agent did, and on which message."""
    return {"signal_id": signal_id, "action_type": action.action_type, "arguments": action.arguments}

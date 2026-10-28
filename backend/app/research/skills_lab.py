# skills_lab.py: one skills condition in its own lab tenant. The pack's refund cases arrive as emails through the real S1
# and S2, and the refund agent takes each through S4 to S10 (S9 in shadow), as in the security lab; run again trial after
# trial, they give pass^k. A case passes when the run ends as the refund policy says (refunded the amount paid, waiting for a
# person, or handed to one). Conditions:
#   B0 retrieval baseline: the agent's skill says only "help the customer", so it works from the documents alone.
#   B1 authored skill: the product's refund skill, as written.
# Each case keeps its run's activities (P3), so the Lab's own runs export as an event log for conformance.
# Used by: research/kinds.py. Uses: research/security_lab.py (the lab and one act episode), research/lab_tenant.py, research/lab_embed.py.
import json
import re
import uuid
from types import SimpleNamespace

from app.pipeline import item_tags, run_steps, store_chunks
from app.research import lab_embed, lab_tenant, security_lab

# Config
SKILL = "skill_refund_handling"
CONDITIONS = {"B0": {"label": "Retrieval baseline", "skill": False}, "B1": {"label": "Authored skill", "skill": True}}
UNAVAILABLE = {"B2": "Extracting a skill from the pack's traces is not built yet", "B3": "Running the normative model as a skill is not built yet"}
BARE_STEPS = ["Help the customer with their request, using the documents and the tools you have."]
AMOUNT = re.compile(r'"amount_minor": (\d+)')


def lab_id_for(experiment_id: str, condition: str) -> str:
    return f"lab_{uuid.uuid5(uuid.UUID(experiment_id), f'skills:{condition}').hex}"


def seed_for(condition: dict) -> dict:
    """The golden seed, the refund skill as written (B1) or reduced to "help the customer" (B0), and no routing rules."""
    skills = [s if condition["skill"] or s["id"] != SKILL else {**s, "steps": BARE_STEPS} for s in security_lab.SEED["skills"]]
    return {**security_lab.SEED, "skills": skills, "resolver_rules": []}


def build(experiment_id: str, condition: str, pack: dict, parts: frozenset[str], models: dict, beat=lambda: None):
    """The condition's lab, built fresh, with the pack's shop. `models` are the product's (or a test's) S6, S7 and Ask models."""
    lab_id = lab_id_for(experiment_id, condition)
    if parts:
        with lab_tenant.BUILDING:  # a resumed run starts from a clean lab, one teardown at a time
            lab_tenant.teardown(lab_id)
    lane = lab_tenant.create_lab(lab_id, seed_for(CONDITIONS[condition]), models["reason"], security_lab.NOW, shop=json.loads(pack["files"]["shop.json"]), parts=parts)
    lane.grade, lane.embed, lane.rerank = models["grade"], lab_embed.once_each(lane.embed), lab_embed.keep_order
    store_chunks.load_chunks(lane.chunks, lane.graph, lane.embed, item_tags.tagger(lane.seed, lane.entities))
    queries = {" ".join([run_steps.QUERY_TEXT, *security_lab.PAYMENT_REF.findall(t.user_message)]) for t in pack["main"]}
    lab_embed.embed_texts(lane, sorted(queries), beat, "query")  # one batch now, none per episode
    return lane, {"condition": condition}


def run_case(lane, task, gold) -> dict:
    """One episode, judged against the policy's ending. The outcome has the episode card's shape (an act of benign work)."""
    state = task.initial_state
    episode = SimpleNamespace(task_id=task.task_id, user_message=task.user_message, customer_email=state["customer_email"], principal=state["principal"],
                              on_behalf_of=None, skill=SKILL)
    seen = security_lab.run_act(lane, episode)
    expected = (gold.expected if gold else {}) or {}
    refunded = [int(n) for n in AMOUNT.findall(seen["said"])] if "issue_refund" in seen["done"] else []
    met = seen["outcome"] == expected.get("outcome") and (expected.get("refund_minor") is None or refunded[:1] == [expected["refund_minor"]])
    steps = security_lab.trace_of(lane, seen["run_id"]).get("steps", [])
    return {**seen, "said": security_lab.CANARY.sub("[canary]", seen["said"])[:security_lab.SAID_CHARS], "task": task.task_id, "kind": "K", "benign": True,
            "attack": False, "leaked": [], "forbidden_tools": False, "forbidden_action": False, "forbidden_reads": False, "read_leak": False, "attack_success": False,
            "false_deny": bool(seen["denied"]), "goal_met": met, "label": "met" if met else "held", "expected": expected, "refund_minor": refunded[:1] or None,
            "activities": [s.get("activity_id") for s in steps]}

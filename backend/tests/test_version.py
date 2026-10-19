# test_version.py: S14 on the memory pipeline. Applying numbers each change from main, writes it, and releases it;
# a closed node leaves latest() but keeps its history; a stale draft is a conflict; a released knowledge item is
# searchable at its new version; S6 keeps the skill version S3 pinned. Uses: stages_version.py, orchestrate.py, tests/golden.py.
import pytest

from app.pipeline import fakes, orchestrate, stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.stages_version import Draft, MergeConflict
from tests.golden import NOW, SEED

# Config
AUTHOR = CommitAuthor(kind="studio", id="h-pamuditha")


# --- Helpers

def build():
    return orchestrate.build_lane(SEED, fakes.make_recorded_caller({})[0], fakes.make_fake_gateway()[0], NOW)


def skill_draft(lane, **changes) -> Draft:
    skill = next(s for s in lane.graph.latest("skill") if s["_ref"]["id"] == "skill_refund_handling")
    fields = {key: value for key, value in skill.items() if key != "_ref"} | changes
    return Draft(op="update", node_type="skill", node_id="skill_refund_handling", fields=fields, base_version=skill["_ref"]["version"])


# --- Applying

def test_apply_numbers_writes_and_releases():
    lane = build()
    released = []
    lane.bus.subscribe("graph.released", "test_watch", "TEST", lambda envelope: released.append(envelope.payload))
    commit = stages_version.apply(lane, AUTHOR, "Shorter name", [skill_draft(lane, name="Refunds")], 2)
    lane.bus.drain()
    skill = next(s for s in lane.graph.latest("skill") if s["_ref"]["id"] == "skill_refund_handling")
    assert (skill["name"], skill["_ref"]["version"], skill["_ref"]["commit_id"]) == ("Refunds", 4, commit.commit_id)
    assert released and released[0]["changed_nodes"][0]["version"] == 4
    assert lane.records.load("branch", "main")["head"] == commit.commit_id


def test_close_keeps_history():
    lane = build()
    stages_version.apply(lane, AUTHOR, "Retire billing", [Draft(op="close", node_type="skill", node_id="skill_billing_answers", fields={}, base_version=1)], 3)
    assert all(s["_ref"]["id"] != "skill_billing_answers" for s in lane.graph.latest("skill"))
    assert [v["_ref"]["version"] for v in lane.graph.history("skill", "skill_billing_answers")] == [1, 2]


def test_a_stale_draft_is_a_conflict():
    lane = build()
    first, second = skill_draft(lane, name="A"), skill_draft(lane, name="B")
    stages_version.apply(lane, AUTHOR, "A", [first], 2)
    with pytest.raises(MergeConflict):
        stages_version.apply(lane, AUTHOR, "B", [second], 2)


def test_a_branch_draft_does_not_touch_main():
    lane = build()
    commit = stages_version.draft_on_branch(lane, AUTHOR, "Try a name", [skill_draft(lane, name="Draft")], 3, "studio/cr_1")
    assert next(s for s in lane.graph.latest("skill") if s["_ref"]["id"] == "skill_refund_handling")["name"] == "Refund handling"
    assert lane.records.load("branch", "studio/cr_1")["head"] == commit.commit_id


def test_released_knowledge_is_searched_at_its_new_version():
    lane = build()
    item = next(k for k in lane.graph.latest("knowledge") if k["_ref"]["id"] == "item_policy_window")
    fields = {key: value for key, value in item.items() if key != "_ref"} | {"text": "Customers may request a refund within 45 days of the purchase date."}
    stages_version.apply(lane, AUTHOR, "45 days", [Draft(op="update", node_type="knowledge", node_id="item_policy_window", fields=fields, base_version=1)], 3)
    lane.bus.drain()
    found = lane.chunks.by_text("refund days purchase", ["policy"], NOW, NOW, 5)
    assert any("45 days" in hit["text"] for hit in found) and not any("within 30 days" in hit["text"] for hit in found)


def test_the_pinned_skill_version_is_what_s6_reads():
    lane = build()
    assert lane.graph.at_version("skill", "skill_refund_handling", 3)["name"] == "Refund handling"
    stages_version.apply(lane, AUTHOR, "Rename", [skill_draft(lane, name="Refunds")], 2)
    assert lane.graph.at_version("skill", "skill_refund_handling", 3)["name"] == "Refund handling"

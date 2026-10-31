# test_memory_flow.py: stage 5b of the living memory, in memory. The golden refund runs through the whole pipeline and
# the memory follows it on the bus: one trace with its access decisions (K16), one match (K17), one To review item for a
# surprise; a redelivery changes nothing, a late access decision attaches, a turned-off area goes to Other, a held trace
# is retried rather than lost, and a broken message becomes a dead letter.
# Uses: app/pipeline/stages_memory_flow.py, stages_memory.py, orchestrate.py, tests/test_chain.py, tests/golden.py.
import pytest

from app.pipeline import stages_memory as memory
from app.pipeline import stages_memory_flow as flow
from app.pipeline.contracts_memory import TraceAccess
from tests.test_chain import payloads, run_sample


def only(lane, topic: str) -> dict:
    found = payloads(lane, topic)
    assert len(found) == 1, f"{topic}: {len(found)} messages"
    return found[0]


def test_a_finished_refund_leaves_one_trace_one_match_and_one_surprise():
    lane, _ = run_sample("s2")
    trace = only(lane, "traces.recorded")
    match = only(lane, "traces.matched")
    run = payloads(lane, "runs.completed")[-1]
    # Step 1: the trace is the run, start to end, in its area, with the access decisions S5 and S7 made
    assert trace["run_id"] == run["run_id"] and trace["outcome"] == "resolved" and trace["area"] in flow.AREAS
    assert trace["access"] and {a["decision"] for a in trace["access"]} == {"allow"}
    assert lane.traces.get(trace["trace_id"]).steps == trace["steps"]
    # Step 2: a new tenant has no patterns, so the first refund is a surprise waiting in To review
    assert match["match"] == "surprise" and lane.records.load(flow.REVIEW_KIND, trace["trace_id"])


def test_once_a_person_confirms_it_the_same_work_is_normal():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(only(lane, "traces.recorded"))
    memory.confirm(trace, lane.patterns)
    again = trace.model_copy(update={"trace_id": "tr-again", "run_id": "run_again"})
    assert memory.triage(again, lane.patterns).match == "normal"


def test_redelivered_messages_change_nothing():
    lane, _ = run_sample("s2")
    for topic in ("runs.completed", "traces.recorded"):
        lane.bus.redeliver(topic, lane.bus.topics[topic][-1])
    lane.bus.handled.clear()  # as if a second worker had never seen them: the stores and the match record still hold
    lane.bus.drain()
    assert len(payloads(lane, "traces.recorded")) == 1 and len(payloads(lane, "traces.matched")) == 1
    assert len(lane.records.history(flow.REVIEW_KIND, only(lane, "traces.matched")["trace_id"])) == 1


def test_an_access_decision_that_arrives_late_is_attached_once():
    lane, _ = run_sample("s2")
    trace_id = only(lane, "traces.recorded")["trace_id"]
    late = TraceAccess(decision_id="d-late", action="refund:issue", principal_id="a-refund", on_behalf_of=None, decision="allow", effective_tier="confidential")
    run_id = trace_id.removeprefix("tr-")
    assert lane.traces.add_access(run_id, late) and lane.traces.attach(trace_id, late)
    assert not lane.traces.attach(trace_id, late)
    assert [a.decision_id for a in lane.traces.get(trace_id).access].count("d-late") == 1


def test_an_area_the_company_turned_off_sends_its_work_to_other():
    lane, _ = run_sample("s2")
    trace = memory.TraceRecord.model_validate(only(lane, "traces.recorded"))
    lane.patterns.switch_area(trace.area, False)
    assert memory.triage(trace.model_copy(update={"trace_id": "tr-off"}), lane.patterns).area == "general"


def test_a_trace_another_worker_holds_is_retried_not_lost():
    lane, _ = run_sample("s2")
    envelope = lane.bus.topics["traces.recorded"][-1]
    lane.records.versions.pop((flow.MATCH_KIND, envelope.payload["trace_id"]))  # as if triage had not finished
    lane.memory_claims.add(f"triage:{envelope.payload['trace_id']}")  # and another worker still held the claim
    with pytest.raises(flow.TraceClaimed) as held:
        flow.on_trace(lane, envelope)
    assert held.value.retryable


def test_a_broken_run_record_becomes_a_dead_letter():
    lane, _ = run_sample("s2")
    broken = lane.bus.topics["runs.completed"][-1].model_copy(update={"event_id": "evt-broken", "payload": {"run_id": "run_broken"}})
    lane.bus.redeliver("runs.completed", broken)
    lane.bus.drain()
    letters = [letter for letter in lane.bus.dead_letters("runs.completed") if letter.consumer_group == "memory_traces"]
    assert letters and letters[0].original.event_id == "evt-broken"


def test_erasing_a_document_scrubs_the_why_of_traces_that_cited_it():
    from app.api.forget_layers_data import REMOVED, TraceLayer
    from app.pipeline.forget import ForgetItem

    lane, _ = run_sample("s2")
    run = lane.records.list_kind("run")[0]
    cited = sorted({ref for step in run["steps"] for ref in step["refs"]})
    item = ForgetItem(document_id="doc-x", record={}, chunk_ids=cited)
    assert TraceLayer().erase(lane, item)[0] == "cleared" and TraceLayer().verify(lane, item, "erase")
    assert lane.traces.get(f"tr-{run['run_id']}").why == [REMOVED]


def test_erasing_a_document_also_scrubs_a_trace_the_night_froze():
    from datetime import timedelta

    from app.api.forget_layers_data import REMOVED, TraceLayer
    from app.pipeline import stages_memory_tidy as tidy
    from app.pipeline.forget import ForgetItem

    lane, _ = run_sample("s2")
    run = lane.records.list_kind("run")[0]
    trace_id = f"tr-{run['run_id']}"
    lane.now = lane.now + timedelta(days=45)
    tidy.tidy(lane, "test")  # the night moves the trace to S3 and out of Postgres
    assert lane.traces.get(trace_id) is None and tidy.cold_trace(lane, trace_id).why != [REMOVED]
    item = ForgetItem(document_id="doc-x", record={}, chunk_ids=sorted({ref for step in run["steps"] for ref in step["refs"]}))
    assert TraceLayer().erase(lane, item)[0] == "cleared" and TraceLayer().verify(lane, item, "erase")
    assert tidy.cold_trace(lane, trace_id).why == [REMOVED]


def test_a_run_that_pauses_for_approval_becomes_a_trace_only_when_it_ends():
    from app.pipeline import orchestrate
    from app.pipeline.contracts_run import Decision
    from tests.golden import NOW

    lane, _ = run_sample("s3")
    assert "traces.recorded" not in lane.bus.topics  # waiting for a person is not the end of the work
    approval = payloads(lane, "approvals.requested")[0]
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="approve", decided_by=["head_of_cs"], decided_at=NOW))
    lane.bus.drain()
    assert only(lane, "traces.recorded")["outcome"] == "resolved"

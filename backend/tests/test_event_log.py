# test_event_log.py: Research Lab P3 and P4. Every step of a run names its activity from the skill's alphabet, and a skill's
# runs export as XES that a process-mining tool reads: one trace per run, its activities in the order taken, with times.
# The golden refund samples run through the in-memory pipeline. Uses: activities.py, event_log.py, tests/golden.py.
import xml.etree.ElementTree as ET

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import event_log_routes
from app.pipeline import activities, event_log, fakes, orchestrate
from app.pipeline.adapters import make_memory_adapters
from tests.golden import NOW, RAW, SEED, recorded_answers

# Config
XES = "{http://www.xes-standard.org/}"
SKILL = "skill_refund_handling"


def lane_with_runs():
    gateway, _ = fakes.make_fake_gateway()
    lane = orchestrate.build_lane(SEED, fakes.make_recorded_caller(recorded_answers())[0], gateway, NOW, make_memory_adapters)
    for sample_id in (s for s in RAW if not s.startswith("s1_")):
        orchestrate.capture_signal(lane, RAW[sample_id])
        lane.bus.drain()
    return lane


def test_every_step_names_an_activity_of_its_skill():
    lane = lane_with_runs()
    runs = event_log.runs_of(lane, SKILL)
    allowed = set(activities.alphabet(next(s for s in SEED["skills"] if s["id"] == SKILL)))
    assert runs and all(step["activity_id"] in allowed for run in runs for step in run["steps"])
    refund = next(r for r in runs if r["outcome"] == "resolved")
    assert [s["activity_id"] for s in refund["steps"]] == ["retrieve_context", "propose_issue_refund", "access_allow", "act_issue_refund"]


def test_steps_recorded_before_activities_are_read_the_same_way():
    old = {"run_id": "r", "steps": [{"kind": "retrieval", "decision": "8 items", "started_at": "2026-10-10T10:00:00Z"},
                                    {"kind": "judgment", "decision": "escalate", "started_at": "2026-10-10T10:00:00Z"},
                                    {"kind": "tool", "decision": "succeeded", "started_at": "2026-10-10T10:00:00Z"}]}
    found = event_log.events_of(old)
    assert [a for a, _ in found] == ["retrieve_context", "propose_escalate", "act_unknown"] and found[0][1] < found[1][1] < found[2][1]


def test_a_skills_runs_export_as_xes_in_order():
    lane = lane_with_runs()
    log = ET.fromstring(event_log.to_xes(event_log.runs_of(lane, SKILL), SKILL))
    traces = log.findall(f"{XES}trace")
    assert len(traces) == len(event_log.runs_of(lane, SKILL)) and traces
    names = [e.find(f"{XES}string[@key='concept:name']").get("value") for e in traces[0].findall(f"{XES}event")]
    times = [e.find(f"{XES}date").get("value") for e in traces[0].findall(f"{XES}event")]
    assert names[0] == "retrieve_context" and times == sorted(times)


def test_the_export_route_answers_xes_or_404():
    lane, app = lane_with_runs(), FastAPI()
    event_log_routes.register(app, lane, lambda tenant, persona: None)
    client = TestClient(app)
    found = client.get(f"/api/t/finebase-hq/skills/{SKILL}/event-log.xes")
    assert found.status_code == 200 and found.headers["content-type"].startswith("application/xml") and "<trace>" in found.text
    assert client.get("/api/t/finebase-hq/skills/no_such_skill/event-log.xes").status_code == 404

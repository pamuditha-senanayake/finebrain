# test_brain_workflows.py: adding a document as a chat with Lisena, and A3's meeting tasks, both run as workflows in Studio.
# The chat asks for each missing detail, takes changes and a yes; Studio shows both workflows with their agent, skill,
# policies, tools and sensor, and an edit there (a required field, the due days, a pause) changes what the code does.
# Uses: app/api/intake.py, intake_talk.py, tasks.py, brain_workflows.py, tests/studio_helpers.py.
from app.api import brain_workflows as flows
from app.api import intake_talk
from tests.studio_helpers import FOUNDER, TENANT, build, change, get, op

TRANSCRIPT = b"""Kickoff with Acme, 2026-10-12
Nimal: Thanks for joining. We need the portal live before December.
Sara: We agreed to launch the beta on 1 November.
Nimal: Maybe we could add Sinhala later.
Sara: I will send the plan by Friday.
Nimal: Action item: Kasun to fix the login page. Owner: Kasun
"""


def post(client, path: str, persona: str = FOUNDER, **kwargs):
    return client.post(f"/api/t/{TENANT}/{path}", headers={"x-persona": persona}, **kwargs)


def start(client) -> dict:
    return post(client, "intake", files={"file": ("acme_kickoff.txt", TRANSCRIPT)}).json()


def say(client, draft: dict, text: str) -> dict:
    return post(client, f"intake/{draft['intakeId']}/say", json={"text": text}).json()


def through_the_chat(client) -> dict:
    """The whole talk, the way a person types or says it."""
    draft = start(client)
    for text in ["a client", "Acme", "Pamuditha", "client meeting", "Portal kickoff"]:
        draft = say(client, draft, text)
    return draft


# --- The chat

def test_lisena_says_what_she_found_then_asks_one_thing():
    client, _ = build()
    draft = start(client)
    assert draft["reply"].startswith("I read it. It looks like a meeting record from 2026-10-12 with Nimal, Sara")
    assert "company, a client or a project?" in draft["reply"]


def test_each_answer_brings_the_next_question_until_nothing_is_missing():
    client, _ = build()
    draft = start(client)
    draft = say(client, draft, "it's about a client")
    assert draft["reply"] == "Got it. Which client or project?"  # a new question the answer opened
    draft = say(client, draft, "Acme")
    assert draft["reply"].startswith("Got it. Who owns it")
    draft = say(client, draft, "next tuesday maybe")  # not an owner? it is text, so it is kept; fix it with a change
    draft = say(client, draft, "change the owner to Pamuditha")
    assert draft["fields"]["owner"] == "Pamuditha" and draft["reply"].startswith("Changed. What kind of meeting")
    draft = say(client, draft, "banana")
    assert draft["reply"].startswith("Sorry, that does not answer it. What kind of meeting")
    draft = say(client, draft, "it was a client meeting")
    draft = say(client, draft, "Portal kickoff")
    assert draft["ready"] and "Shall I add it to the knowledge base?" in draft["reply"]


def test_a_yes_files_it_and_makes_the_tasks():
    client, lane = build()
    draft = through_the_chat(client)
    done = say(client, draft, "yes, add it")
    assert done["status"] == "filed" and "Meeting · Acme · 2026-10-12 · Portal kickoff" in done["reply"]
    titles = {t["title"]: (t["owner"], t["due"]) for t in done["tasks"]}
    assert titles == {"Send the plan": ("Sara", "2026-10-16"), "Kasun to fix the login page": ("Kasun", "2026-10-19")}
    assert say(client, done, "yes")["reply"] == "That one is already added."
    assert len(lane.records.list_kind("document")) == 1 and len(lane.records.list_kind("task")) == 2


def test_a_yes_too_early_asks_the_missing_thing_and_stop_adds_nothing():
    client, lane = build()
    draft = start(client)
    assert say(client, draft, "yes")["reply"].startswith("I still need one more thing.")
    assert say(client, draft, "cancel")["reply"] == "Okay, I stopped. Nothing was added."
    assert lane.records.list_kind("document") == []


def test_only_the_person_who_started_it_can_talk_to_it():
    client, _ = build()
    draft = start(client)
    assert post(client, f"intake/{draft['intakeId']}/say", persona="h-udayanga", json={"text": "yes"}).status_code == 404


def test_spoken_changes_are_understood():
    assert intake_talk.understand("change the date to 12 October 2026", None) == ("change", {"date": "2026-10-12"})
    assert intake_talk.understand("set attendees to Nimal and Sara", None) == ("change", {"attendees": ["Nimal", "Sara"]})
    assert intake_talk.understand("sure", "about") == ("yes", {})


# --- Tasks

def test_tasks_can_be_listed_changed_and_done():
    client, _ = build()
    say(client, through_the_chat(client), "yes")
    listed = client.get(f"/api/t/{TENANT}/tasks", headers={"x-persona": FOUNDER}).json()
    task = next(t for t in listed if t["title"] == "Send the plan")
    assert task["source"]["title"].startswith("Meeting · Acme")
    late = post(client, f"tasks/{task['id']}", json={"due": "2000-01-01"}).json()
    assert late["state"] == "late" and listed[0]["state"] in ("late", "soon", "open")
    moved = post(client, f"tasks/{task['id']}", json={"owner": "Nimal", "due": "2099-01-01"}).json()
    assert (moved["owner"], moved["state"]) == ("Nimal", "open")
    assert post(client, f"tasks/{task['id']}", json={"status": "done"}).json()["state"] == "done"
    assert post(client, f"tasks/{task['id']}", json={"status": "maybe"}).status_code == 400
    added = post(client, "tasks", json={"title": "Book the venue", "owner": "Sara"}).json()
    assert added["status"] == "open" and post(client, "tasks", json={"title": "", "owner": "Sara"}).status_code == 400


# --- In Studio

def test_both_workflows_are_in_studio_with_their_parts():
    client, _ = build()
    _, listed = get(client, "studio/workflows")
    assert {flows.INTAKE, flows.TASKS} <= {f["id"] for f in listed}
    _, intake = get(client, f"studio/workflows/{flows.INTAKE}")
    assert {"agent_lisena", "skill_document_intake", flows.INTAKE_POLICY, flows.SECURITY_POLICY, "tool:file_document"} <= {i["id"] for i in intake["items"]}
    _, tasks = get(client, f"studio/workflows/{flows.TASKS}")
    assert {"agent_followup", "skill_meeting_tasks", flows.TASK_POLICY, "tool:create_task"} <= {i["id"] for i in tasks["items"]}


def test_a_studio_edit_changes_what_lisena_asks():
    client, lane = build()
    edit = change("policy", flows.INTAKE_POLICY, {"fields": {"param.common": "kind, title, date, about"}}, workflow=flows.INTAKE)
    assert op(client, "studioApply", {"input": edit, "acknowledgeBreaking": True}).json()["status"] == "applied"
    lane.bus.drain()
    asked = [q["field"] for q in start(client)["questions"]]
    assert "owner" not in asked and "about" in asked


def test_a_paused_workflow_stops():
    client, lane = build()
    for wf in (flows.INTAKE, flows.TASKS):
        op(client, "studioApply", {"input": change("workflow", wf, {"status": "paused"}, workflow=wf), "acknowledgeBreaking": True})
    lane.bus.drain()
    assert post(client, "intake", files={"file": ("a.txt", TRANSCRIPT)}).json()["error"] == "intake_paused"

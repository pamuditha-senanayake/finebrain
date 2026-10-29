# tasks.py: A3, "what I said wasn't done". When a meeting is filed, each Action line becomes a task with one owner and a
# due date, linked to the meeting it came from. People add tasks by hand too, change the owner or the day, and mark them
# done. A task due soon or late says so until it is done. The "Meeting tasks" workflow in Studio holds the due and
# reminder days and can pause it. Used by: intake.py, routes.py, tests/test_tasks.py. Uses: brain_workflows.py, intake_policy.py.
import re
import uuid
from datetime import date, datetime, timedelta

from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from app.api import brain_workflows
from app.api import intake_policy as policy

# Config
KIND = "task"
STATUSES = ("open", "done")
SPEAKER = re.compile(r"^\s*(?P<who>[A-Z][\w .'-]{1,40}):\s*(?P<said>.+)$")
WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
DUE = re.compile(r"\b(?:by|before|on|due)\s+(?P<when>tomorrow|next week|end of (?:the )?week|monday|tuesday|wednesday|thursday|friday|saturday|sunday|\d{4}-\d\d-\d\d)\b", re.I)
PROMISE = re.compile(r"^(?:(?:ok(?:ay)?|so|and|then),?\s+)?(?:i|we)\s*(?:will|'ll|shall|can|need to|have to|am going to)\s+|^action item:?\s*|^to ?do:?\s*", re.I)
OWNER_TAG = re.compile(r"\bowner:\s*(?P<who>[A-Z][\w.'-]+(?: [A-Z][\w.'-]+)?)", re.I)


class Task(BaseModel):
    task_id: str
    title: str
    owner: str
    due: str  # YYYY-MM-DD
    status: str = "open"
    source: dict | None = None  # {document_id, title, line} for a task from a meeting
    created_at: datetime
    created_by: str
    done_at: datetime | None = None


# --- From a meeting

def due_from(line: str, meeting_day: date, default_days: int) -> str:
    """The day the line names, counted from the meeting; else the meeting day plus the default."""
    found = DUE.search(line)
    when = found.group("when").lower() if found else ""
    if when == "tomorrow":
        return (meeting_day + timedelta(days=1)).isoformat()
    if when in ("next week", "end of week", "end of the week"):
        return (meeting_day + timedelta(days=7 if when == "next week" else (4 - meeting_day.weekday()) % 7)).isoformat()
    if when in WEEKDAYS:
        ahead = (WEEKDAYS.index(when) - meeting_day.weekday()) % 7 or 7
        return (meeting_day + timedelta(days=ahead)).isoformat()
    if re.fullmatch(r"\d{4}-\d\d-\d\d", when):
        return when
    return (meeting_day + timedelta(days=default_days)).isoformat()


def title_from(said: str) -> str:
    """ "I will send the plan by Friday." becomes "Send the plan"."""
    text = OWNER_TAG.sub("", PROMISE.sub("", said.strip()))
    text = DUE.sub("", text).strip(" .,;-")
    return (text[:1].upper() + text[1:])[:140] if text else said.strip()[:140]


def owner_from(who: str | None, said: str, attendees: list[str], fallback: str) -> str:
    """Owner: X wins; then an attendee named at the start ("Nimal will..."); then the speaker of "I will"; else the meeting owner."""
    if tagged := OWNER_TAG.search(said):
        return tagged.group("who")
    first = said.strip().split(" ")[0].strip(",:")
    if first in attendees:
        return first
    return who or fallback


def from_meeting(lane, fields: dict, text: str, document_id: str, title: str) -> list[dict]:
    """Every Action line becomes one task. Ids come from the meeting and line, so filing twice makes no second copy."""
    if not brain_workflows.active(lane, brain_workflows.TASKS):
        return []
    default_days, _ = brain_workflows.task_settings(lane)
    meeting_day = date.fromisoformat(fields["date"])
    made = []
    for number, line in enumerate(text.splitlines()):
        tag = next((name for name, pattern in policy.LINE_TAGS if pattern.search(line)), None)
        if tag != "Action":
            continue
        spoken = SPEAKER.match(line)
        who, said = (spoken.group("who").strip(), spoken.group("said")) if spoken else (None, line)
        task_id = f"task_{document_id.removeprefix('doc_')}_{number}"
        if (kept := lane.records.load(KIND, task_id)) is None:
            kept = Task(task_id=task_id, title=title_from(said), owner=owner_from(who, said, fields.get("attendees") or [], fields["owner"]),
                        due=due_from(said, meeting_day, default_days), source={"document_id": document_id, "title": title, "line": line.strip()[:300]},
                        created_at=lane.now, created_by="agent_followup").model_dump(mode="json")
            lane.records.save(KIND, task_id, Task.model_validate(kept))
        made.append(view(lane, kept))
    return made


# --- Showing and changing

def view(lane, task: dict) -> dict:
    """One task as the console shows it, with whether it is due soon or late (counted now, not stored)."""
    _, remind_days = brain_workflows.task_settings(lane)
    left = (date.fromisoformat(task["due"]) - lane.now.date()).days
    state = "done" if task["status"] == "done" else "late" if left < 0 else "soon" if left <= remind_days else "open"
    return {"id": task["task_id"], "title": task["title"], "owner": task["owner"], "due": task["due"], "status": task["status"], "state": state,
            "source": {"documentId": src["document_id"], "title": src["title"], "line": src["line"]} if (src := task.get("source")) else None, "createdAt": str(task["created_at"]), "doneAt": str(task["done_at"]) if task.get("done_at") else None}


def tasks_view(lane) -> list[dict]:
    """Late first, then due soon, then open by due day, then done (newest first)."""
    shown = [view(lane, task) for task in lane.records.list_kind(KIND)]
    rank = {"late": 0, "soon": 1, "open": 2, "done": 3}
    return sorted(shown, key=lambda t: (rank[t["state"]], t["due"] if t["state"] != "done" else "", t["doneAt"] or ""), reverse=False)


def changed(task: dict, body: dict, persona: str, now: datetime) -> dict:
    """A person's change: title, owner, due day or status. Anything that does not fit is refused, not guessed."""
    update = {}
    for key in ("title", "owner"):
        if key in body:
            value = str(body[key] or "").strip()
            if not value:
                raise HTTPException(400, f"empty_{key}")
            update[key] = value[:140]
    if "due" in body:
        try:
            update["due"] = date.fromisoformat(str(body["due"])[:10]).isoformat()
        except ValueError:
            raise HTTPException(400, "bad_due") from None
    if "status" in body:
        if body["status"] not in STATUSES:
            raise HTTPException(400, "bad_status")
        update["status"] = body["status"]
        update["done_at"] = now if body["status"] == "done" else None
    return {**task, **update, "updated_by": persona}


def register(app: FastAPI, lane, check) -> None:
    """GET and POST /api/t/{tenant}/tasks, POST /api/t/{tenant}/tasks/{id}. Must be added before the catch-all POST route."""

    @app.get("/api/t/{tenant}/tasks")
    def listed(tenant: str, x_persona: str = Header(default="")) -> list[dict]:
        check(tenant, x_persona)
        return tasks_view(lane)

    @app.post("/api/t/{tenant}/tasks", status_code=201)
    async def add(tenant: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        body = await request.json()
        default_days, _ = brain_workflows.task_settings(lane)
        blank = {"task_id": f"task_{uuid.uuid4().hex[:12]}", "title": "", "owner": "", "due": (lane.now.date() + timedelta(days=default_days)).isoformat(),
                 "status": "open", "created_at": lane.now, "created_by": x_persona}
        task = changed(blank, {"title": body.get("title"), "owner": body.get("owner"), **({"due": body["due"]} if body.get("due") else {})}, x_persona, lane.now)
        lane.records.save(KIND, task["task_id"], Task.model_validate(task))
        return view(lane, lane.records.load(KIND, task["task_id"]))

    @app.post("/api/t/{tenant}/tasks/{task_id}")
    async def change(tenant: str, task_id: str, request: Request, x_persona: str = Header(default="")) -> dict:
        check(tenant, x_persona)
        task = lane.records.load(KIND, task_id)
        if task is None:
            raise HTTPException(404, "not_found")
        lane.records.save(KIND, task_id, Task.model_validate(changed(task, await request.json(), x_persona, lane.now)))
        return view(lane, lane.records.load(KIND, task_id))

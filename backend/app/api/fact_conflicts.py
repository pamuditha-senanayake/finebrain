# fact_conflicts.py: step 14 slice 4, resolving a conflict (B09 to B12). The librarian lists what relied on the current fact,
# asks Claude Opus which side should win and from when, and drafts one commit: the old fact's valid time closes, the new fact
# starts. That commit waits on its own branch as a C3 change request with an S8 approval; merging it changes ground truth.
# Used by: vault_routes.py, tests/test_conflict.py. Uses: conflict_prompt.py, fact_commit.py, stages_version.py, studio_approvals.py.
from datetime import datetime, timedelta, timezone

from app.api import ask_memory
from app.api.studio_approvals import APPROVERS, DUE_HOURS
from app.api.studio_changes import ChangeRecord, notify
from app.pipeline import conflict_prompt, fact_commit, stages_decide, stages_extract, stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.contracts_run import ApprovalRequest, ApprovalSubject
from app.pipeline.contracts_signal import FactCandidate
from app.pipeline.stages_librarian import FACT_NODE, ITEM_KIND, LibrarianItem

# Config
CONFLICT_LEVEL = 3  # changing a verified fact is C3: the DRI approves (plan, step 14)
LIBRARIAN = "librarian"  # the drafter is the librarian, so a leader may approve; nobody approves their own change


# --- What relied on the current fact (B09)

def dependents(lane, fact_ids: list[str]) -> list[dict]:
    """Runs and Ask answers that cited the current fact. They stay as they were; the list shows who relied on it."""
    ids = set(fact_ids)
    runs = [{"type": "run", "id": run["run_id"], "label": f"Run {run['run_id']}"} for run in lane.records.list_kind("run")
            if any(ids & set(step.get("refs", [])) for step in run.get("steps", []))]
    asked = [{"type": "conversation", "id": turn["conversation_id"], "label": "An Ask answer"} for turn in lane.records.list_kind(ask_memory.KIND)
             if any(ids & set(past["cited"]) for past in lane.records.history(ask_memory.KIND, turn["conversation_id"]))]
    return runs + asked


# --- Which side wins (B10)

def side(lane, fact: dict) -> dict:
    """A fact or a candidate, as the prompt shows it: statement, value, when true, which document, and its quote."""
    record = lane.records.load("document", fact["document_id"]) or {"title": "a removed document", "uploaded_at": ""}
    return {"statement": fact["statement"], "value": fact["value"], "valid_from": fact["valid_from"], "source": record["title"],
            "added": str(record["uploaded_at"])[:10], "quote": fact["quote"]}


def decide(lane, current: dict, candidate: FactCandidate) -> dict:
    """Claude Opus's answer; with no model, an outage or no usable answer, the newer source wins (conflict_prompt.by_rule)."""
    new = {"statement": candidate.statement, "value": candidate.value.raw, "valid_from": str(candidate.valid_from or "not stated"),
           "document_id": candidate.evidence.document_id, "quote": stages_extract.quote_of(lane, candidate.evidence.model_dump())}
    old = {"statement": current["text"], "value": current["value"]["raw"], "valid_from": current["valid_from"],
           "document_id": current["source"]["document_id"], "quote": current["evidence"][0]["quote"]}
    rule = conflict_prompt.by_rule(candidate.valid_from.date() if candidate.valid_from else None, lane.now.date())
    if lane.resolve is None:
        return rule
    try:
        reply = lane.resolve(conflict_prompt.SYSTEM, conflict_prompt.prompt(side(lane, old), side(lane, new)), [conflict_prompt.TOOL])
    except Exception:  # an outage never blocks the librarian: the rule answers, and says so
        return {**rule, "reason": "The newer source wins (the model did not answer)."}
    return conflict_prompt.answer_in(reply) or rule


# --- Checks the approver sees (the console asks for tests and an impact preview before any approval)

def checks(lane, candidate: FactCandidate, winner_doc: str, relied: list[dict]) -> tuple[dict, dict]:
    """Evidence checks, and an honest impact note: a fact change replays no runs, it lists who cited the current fact."""
    passed = [bool(stages_extract.quote_of(lane, candidate.evidence.model_dump())),
              (lane.records.load("document", winner_doc) or {}).get("status") == "done", True]  # quote found, winner filed, one fact changes
    tests = {"suite": "Evidence checks", "total": 3, "passed": sum(passed), "failed": 3 - sum(passed), "passK": sum(passed) / 3, "k": 1, "ranAt": lane.now.isoformat()}
    runs = sum(d["type"] == "run" for d in relied)
    impact = {"runsReplayed": 0, "decisionsChanged": 0, "predictedRisk": "medium", "examples": [],
              "summary": f"No runs replayed: a fact change does not change an agent's steps. {runs} runs and {len(relied) - runs} Ask answers cited the current fact."}
    return tests, impact


# --- The change request (B10, B11)

def starts(answer: dict, now: datetime) -> datetime:
    try:
        return datetime.fromisoformat(answer["valid_from"]).replace(tzinfo=timezone.utc) if answer.get("valid_from") else now
    except ValueError:
        return now


def drafts_for(lane, current: dict, candidate: FactCandidate, person: str, valid_from: datetime) -> list[stages_version.Draft]:
    """One commit: the current fact ends where the new one starts, and the new fact is added."""
    closed = {key: value for key, value in current.items() if key != "_ref"} | {"valid_to": valid_from.isoformat(), "status": "superseded"}
    added = fact_commit.fact_fields(lane, candidate, person) | {"valid_from": valid_from.isoformat()}
    return [stages_version.Draft(op="update", node_type=FACT_NODE, node_id=current["item_id"], fields=closed, base_version=current["_ref"]["version"]),
            stages_version.Draft(op="add", node_type=FACT_NODE, node_id=added["item_id"], fields=added, base_version=0)]


def open_change(lane, item: LibrarianItem, current: dict, drafts: list, proposal: dict) -> str:
    """Draft the commit on its own branch, open the C3 approval, and tell the DRI. Returns the change request id."""
    cr_id, dri = lane.new_id("cr"), stages_decide.find_person(APPROVERS[CONFLICT_LEVEL], lane.seed["people"])
    commit = stages_version.draft_on_branch(lane, CommitAuthor(kind="librarian", id=LIBRARIAN), proposal["title"], drafts, CONFLICT_LEVEL, f"librarian/{cr_id}")
    due = lane.now + timedelta(hours=DUE_HOURS)
    approval = ApprovalRequest(approval_id=lane.new_id("apr"), subject=ApprovalSubject(kind="change_request", ref=cr_id), criticality=CONFLICT_LEVEL,
                               summary_plain=f"{proposal['title']}. {proposal['review']['summary']}", diff_ref=commit.commit_id, evidence_refs=[item.document_id],
                               required_approvers=APPROVERS[CONFLICT_LEVEL], dri_id=dri, due_at=due, expires_at=due)
    lane.records.save("change_request", cr_id, ChangeRecord(
        cr_id=cr_id, title=proposal["title"], kind="fact", workflow_id=None, input={"intent": "update", "kind": "fact", "targetId": current["item_id"]},
        proposal=proposal, drafts=drafts, commit_id=commit.commit_id, branch=f"librarian/{cr_id}", approval_id=approval.approval_id, status="awaiting_approval",
        drafter=LIBRARIAN, dri=dri, criticality=CONFLICT_LEVEL, created_at=lane.now, before={"id": current["item_id"], "name": proposal["targetName"], "version": current["_ref"]["version"]}))
    lane.records.save("approval", approval.approval_id, approval)
    lane.bus.publish("approvals.requested", "approval.requested", approval, "librarian")
    notify(lane, dri, "A fact changed in a document", proposal["title"], f"/l1/approvals/{approval.approval_id}", "approval")
    return cr_id


def propose(lane, item_id: str, person: str) -> dict:
    """The librarian's proposal for an open conflict: a change request when the new claim wins, else the current fact is kept."""
    stored = lane.records.load(ITEM_KIND, item_id)
    if stored is None:
        raise LookupError(item_id)
    item = LibrarianItem.model_validate(stored)
    if item.kind != "conflict" or item.status != "open":
        raise fact_commit.NotOpen("not_an_open_conflict")
    candidate = FactCandidate.model_validate(lane.records.load(stages_extract.CANDIDATE_KIND, item.candidate_id))
    current = next(fact for fact in lane.graph.latest(FACT_NODE) if fact["item_id"] in item.fact_ids)
    answer, label = decide(lane, current, candidate), current["predicate"].replace("_", " ")
    valid_from, winner_doc = starts(answer, lane.now), candidate.evidence.document_id if answer["winner"] == "new" else current["source"]["document_id"]
    relied = dependents(lane, [current["item_id"]])
    tests, impact = checks(lane, candidate, winner_doc, relied)
    proposal = {"title": f"Update ground truth: {label}", "targetName": label, "winningSource": (lane.records.load("document", winner_doc) or {}).get("title", winner_doc),
                "newValidFrom": valid_from.isoformat(), "dependents": relied, "tests": tests, "impact": impact,
                "changes": [{"field": current["predicate"], "label": label, "before": current["value"]["raw"], "after": candidate.value.raw}],
                "review": {"criticality": CONFLICT_LEVEL, "summary": answer["reason"], "findings": [], "criticalityReasons": ["Changes a verified fact"],
                           "reviewer": "Librarian", "verdict": "moderate", "authority": {"approver": "the DRI"}}}
    if answer["winner"] == "current":
        lane.records.save(ITEM_KIND, item_id, item.model_copy(update={"status": "resolved", "resolution": "kept_current", "decided_by": person, "decided_at": lane.now, "proposal": proposal}))
        return {"id": None, "kept": True, "reason": answer["reason"]}
    cr_id = open_change(lane, item, current, drafts_for(lane, current, candidate, person, valid_from), proposal)
    lane.records.save(ITEM_KIND, item_id, item.model_copy(update={"status": "proposed", "change_request_id": cr_id, "proposal": proposal}))
    return {"id": cr_id, "kept": False, "reason": answer["reason"]}

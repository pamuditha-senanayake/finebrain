# freshness_lab.py: one freshness condition in its own lab tenant. The pack's documents go in through the real S1, S2 and
# S11 (documents.accept), each on the day it became valid (the lane clock), so chunks carry the pack's valid times. Then:
#   C0 plain retrieval: nothing more; every version stays valid.
#   C1 source filtering (Execution_V1's C1): the chunk holding each superseded sentence is closed when its update starts.
#   C3 living map: Finebrain finds the change itself (Lane B: S11 extraction, S12 librarian, conflict proposal), the lab's
#      steward accepts new facts and its L1 approves each proposed change, as people following the brain would.
#   C2 (delete and rebuild) needs a summary tree Finebrain does not have, so it is refused, never approximated.
# A question goes through the real S5 as of its date, then Execution_V1's own answer prompt. Used by: research/runner.py.
# Uses: research/lab_tenant.py, api/documents.py, stages_retrieve.py, retrieve_scope.py, fact_commit.py, fact_conflicts.py, studio_approvals.py, llm.py.
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from app.api import documents, fact_conflicts, studio_approvals
from app.pipeline import fact_commit, llm, orchestrate, retrieve_scope, stages_retrieve
from app.pipeline.contracts_reason import ContextQuery
from app.pipeline.contracts_run import Decision
from app.pipeline.contracts_signal import Principal
from app.research import lab_tenant

# Config
SEED = json.loads((Path(__file__).resolve().parents[2] / "samples" / "golden_refund_run.json").read_text())["seed"]
CONDITIONS = {"C0": {"label": "Plain retrieval", "close": False, "living": False},
              "C1": {"label": "Source filtering", "close": True, "living": False},
              "C3": {"label": "Living map", "close": False, "living": True}}
UNAVAILABLE = {"C2": "Delete and rebuild needs a summary tree that Finebrain does not have"}
ASKER, STEWARD, UPLOADER = "founder", "steward_1", "research_lab"
REPORT_KIND = "research_ingest"  # records kind: the lab's ingest report, so a resumed run never ingests twice
TOP_K = 8  # Execution_V1's frozen retrieval top_k
ANSWER_PROMPT = """You are a policy assistant for an internal knowledge system. Answer the question using only the retrieved context below. The context is the only source you may use.

Rules:
- Answer in one or two sentences.
- State the concrete value directly when the question asks for one.
- If the context does not contain the answer, reply exactly: NOT_IN_CONTEXT
- Do not speculate, do not use outside knowledge, and do not hedge with alternatives when the context gives a single value.

Retrieved context:
{context}

Question: {question}

Answer: """  # Execution_V1 config/prompts/answer.txt, word for word, so both systems answer the same way


def lab_id_for(experiment_id: str, condition: str) -> str:
    return f"lab_{uuid.uuid5(uuid.UUID(experiment_id), condition).hex}"


def day(text: str) -> datetime:
    """A pack date or time; no zone means UTC. Python 3.10 cannot read a trailing Z, so it is spelled out."""
    text = text.replace("Z", "+00:00")
    moment = datetime.fromisoformat(text if "T" in text else f"{text}T00:00:00")
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def set_clock(lane, when: datetime) -> None:
    lane.now = when
    lane.bus.now = when


# --- Building one condition's lab

def build(experiment_id: str, condition: str, pack: dict, parts: frozenset[str], meter=None):
    """The condition's lab lane, ingested once. A resumed run finds the report and reuses the lab as it is."""
    lab_id = lab_id_for(experiment_id, condition)
    lane = lab_tenant.create_lab(lab_id, {**SEED, "knowledge": []}, None, day(min(d["meta"].valid_from for d in pack["documents"].values())), parts=parts)
    if CONDITIONS[condition]["living"]:
        lane.extract = metered(llm.make_tool_caller(model=llm.FAST_MODEL, max_tokens=4000), llm.FAST_MODEL, meter)
        lane.resolve = metered(llm.make_tool_caller(model=llm.CAREFUL_MODEL), llm.CAREFUL_MODEL, meter)
        lane.bus.subscribe("approvals.decided", "studio", "S14", lambda envelope: studio_approvals.on_decision(lane, envelope))
    done = lane.records.load(REPORT_KIND, "report")
    if done:
        return lane, done["report"]
    report = ingest(lane, pack, CONDITIONS[condition])
    lane.records.save(REPORT_KIND, "report", IngestReport(report=report))
    return lane, report


def ingest(lane, pack: dict, condition: dict) -> dict:
    """Documents grouped by the day they became valid, oldest first; after each day the condition does its part."""
    held, report = {}, {"documents": 0, "closed_chunks": 0, "sentences_not_found": [], "facts_accepted": 0, "changes_merged": 0, "changes_kept": 0}
    for when in sorted({doc["meta"].valid_from for doc in pack["documents"].values()}):
        set_clock(lane, day(when))
        for doc_id, doc in sorted(pack["documents"].items()):
            if doc["meta"].valid_from == when:
                held[doc_id] = documents.accept(lane, UPLOADER, f"{doc['meta'].title}.md", doc["body"].encode(), doc["meta"].sensitivity)["id"]
                lane.bus.drain()
                report["documents"] += 1
        if condition["living"]:
            settle_librarian(lane, report)
    if condition["close"]:
        close_superseded(lane, pack, held, report)
    return report


def close_superseded(lane, pack: dict, held: dict, report: dict) -> None:
    """C1: end the valid time of every chunk that holds a superseded sentence, at the moment its update starts."""
    for fact in pack["extra"].get("facts.jsonl", []):
        if not (fact.old_sentence and fact.old_doc_id in held and fact.change_at):
            continue
        holders = [c for c in lane.chunks.of_document(held[fact.old_doc_id]) if c["kind"] == "chunk" and fact.old_sentence in c["text"]]
        report["sentences_not_found"] += [] if holders else [fact.fact_id]
        for chunk in holders:
            lane.chunks.retire(chunk["item_id"], day(fact.change_at))
            report["closed_chunks"] += 1


def settle_librarian(lane, report: dict) -> None:
    """C3: the steward accepts what waits for verification; each conflict gets the librarian's proposal, which the DRI approves."""
    for item in lane.records.list_kind(fact_commit.ITEM_KIND):
        if item["status"] == "open" and item["kind"] == "unverified":
            fact_commit.accept(lane, item["item_id"], STEWARD)
            report["facts_accepted"] += 1
    for item in lane.records.list_kind(fact_commit.ITEM_KIND):
        if item["status"] == "open" and item["kind"] == "conflict":
            proposed = fact_conflicts.propose(lane, item["item_id"], STEWARD)
            report["changes_kept" if proposed["kept"] else "changes_merged"] += 1
            if proposed["id"]:
                approve_change(lane, proposed["id"])
    lane.bus.drain()


def approve_change(lane, cr_id: str) -> None:
    change = lane.records.load("change_request", cr_id)
    approval = lane.records.load("approval", change["approval_id"])
    orchestrate.decide(lane, Decision(approval_id=approval["approval_id"], decision="approve", decided_by=[approval["dri_id"]], decided_at=lane.now))
    lane.bus.drain()


# --- One question

def ask(lane, text: str, as_of: str, answer) -> dict:
    """The real S5 as of the question's date, then the answer prompt. Returns the answer, what S5 gave, and the usage."""
    set_clock(lane, day(as_of))
    query = ContextQuery(run_id=lane.new_id("lab"), principal=Principal(type="human", id=ASKER, capabilities=["kb.read"], tier="L1"), on_behalf_of=None,
                         query_text=text, branch="main", top_k=TOP_K, entity_ids=retrieve_scope.entities_in_question(lane, text))
    bundle, _ = stages_retrieve.retrieve(query, lane.chunks, lane.embed, lane.rerank, lane.seed["people"], lane.new_id, lane.now, lane.commons)
    context = "\n\n".join(item.text for item in bundle.items)
    reply, usage = answer(ANSWER_PROMPT.format(context=context, question=text))
    return {"answer": reply, "items": [item.item_id for item in bundle.items], "context": context, "usage": usage}


def metered(caller, model: str, meter):
    """A tool caller that adds each reply's tokens to the run's meter, so the cost cap counts Lane B too."""
    def call(system: str, messages: list[dict], tools: list[dict]):
        reply = caller(system, messages, tools)
        if meter is not None:
            meter(model, reply.usage.input_tokens, reply.usage.output_tokens)
        return reply
    return call


class IngestReport(BaseModel):
    report: dict

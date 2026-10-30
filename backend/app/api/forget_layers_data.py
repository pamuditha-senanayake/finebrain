# forget_layers_data.py: step 10, the record layers: intake copies (S1 to S3), Ask conversations, living memory traces,
# the PII vault, the entity registry, and the Library record, which goes last. Used by: forget_review.py (imports this file to register).
# Uses: forget.py, ask_memory.py, entity_match.py.
from app.api import ask_memory
from app.pipeline import entity_match
from app.pipeline.forget import ForgetItem, register
from app.pipeline.stages_file import DocumentRecord

# Config
REMOVED = "Source removed."
KEPT_STATUSES = {"done", "retired"}


class IntakeLayer:
    """The masked signal S2 produced, S3's copy of it, and its dedup key in the seen-before set."""
    name, stores, final = "Intake", ("signals", "seen_keys"), False

    def signals(self, lane, item: ForgetItem) -> list[dict]:
        return [signal for signal in lane.records.list_kind("signal") if signal["dedup_key"].endswith(f":{item.document_id}")]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        found = self.signals(lane, item)
        for signal in found:
            lane.records.purge("signal", signal["signal_id"])
            lane.signals.pop(signal["signal_id"], None)
            lane.seen_keys.discard(signal["dedup_key"])
        return ("cleared", f"{len(found)} removed") if found else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not self.signals(lane, item)


class BusLayer:
    """Messages the bus kept: the raw capture and the masked signal. Kafka keeps them until the topic expires."""
    name, stores, final = "Messages", ("bus",), False

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        dropped = lane.bus.drop_messages(item.document_id)
        if dropped is None:
            return "kept", "leave when the topic expires"
        return ("cleared", f"{dropped} dropped") if dropped else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or lane.bus.drop_messages(item.document_id) in (None, 0)


class ConversationLayer:
    """Ask turns that cited the document. The answer is replaced; the question stays. Retiring changes nothing."""
    name, stores, final = "Conversations", (), False

    def citing(self, lane, item: ForgetItem) -> list[str]:
        ids = set(item.chunk_ids)
        return [turn["conversation_id"] for turn in lane.records.list_kind(ask_memory.KIND)
                if any(ids & set(past["cited"]) for past in lane.records.history(ask_memory.KIND, turn["conversation_id"]))]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "past answers stay"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        ids, conversations = set(item.chunk_ids), self.citing(lane, item)
        for conversation_id in conversations:
            for past in lane.records.purge(ask_memory.KIND, conversation_id):
                if ids & set(past["cited"]):
                    past = {**past, "answer": REMOVED, "cited": [c for c in past["cited"] if c not in ids]}
                lane.records.save(ask_memory.KIND, conversation_id, ask_memory.StoredTurn.model_validate(past))
        return ("cleared", f"{len(conversations)} scrubbed") if conversations else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not self.citing(lane, item)


class VaultLayer:
    """Personal values this document masked. A value another document also uses stays."""
    name, stores, final = "Vault", ("vault",), False

    def own_tokens(self, lane, item: ForgetItem) -> list[str]:
        others = {token for record in lane.records.list_kind("document") if record["document_id"] != item.document_id and record["status"] in KEPT_STATUSES
                  for token in record.get("pii_tokens", [])}
        return [token for token in item.record.get("pii_tokens", []) if token not in others]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "still on file"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        if item.record.get("personal_data") and not item.record.get("pii_tokens"):
            return "kept", "filed before tokens were listed"
        gone = [token for token in self.own_tokens(lane, item) if lane.vault.pop(token, None) is not None]
        shared = len(item.record.get("pii_tokens", [])) - len(self.own_tokens(lane, item))
        return ("cleared", f"{len(gone)} deleted" + (f", {shared} shared kept" if shared else "")) if gone or shared else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not any(token in lane.vault for token in self.own_tokens(lane, item))


class EntityLayer:
    """What the upload told the entity registry (step 13a): its mentions and links, and things only it mentioned."""
    name, stores, final = "Entities", ("entities",), False

    def source(self, lane, item: ForgetItem) -> str:
        return entity_match.document_source(lane.seed["tenant_id"], item.document_id)

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        removed = lane.entities.drop_source(self.source(lane, item))
        return ("cleared", f"{removed} removed") if removed else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not lane.entities.of_source(self.source(lane, item))


class LibraryLayer:
    """The Library record. Retired keeps it with an end date; erased removes every version. Goes last."""
    name, stores, final = "Library", ("records",), True

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        record = DocumentRecord.model_validate(item.record)
        if record.status == "retired":
            return "nothing", ""
        lane.records.save("document", item.document_id, record.model_copy(update={"status": "retired", "retired_at": lane.now}))
        return "cleared", "marked retired"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        lane.records.purge("document", item.document_id)
        return "cleared", "record removed"

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        record = lane.records.load("document", item.document_id)
        return record is None if mode == "erase" else bool(record) and record["status"] == "retired"


class TraceLayer:
    """Living memory traces of runs that cited the document. Their why lines may quote it, so erasing replaces them;
    the steps, outcome and access decisions stay, because they are ids and names. Retiring changes nothing."""
    name, stores, final = "Traces", ("traces",), False

    def citing(self, lane, item: ForgetItem) -> list[str]:
        ids = set(item.chunk_ids)
        return [f"tr-{run['run_id']}" for run in lane.records.list_kind("run") if any(ids & set(step.get("refs", [])) for step in run.get("steps", []))]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        scrubbed = sum(lane.traces.scrub(trace_id, REMOVED) for trace_id in self.citing(lane, item))
        return ("cleared", f"{scrubbed} traces") if scrubbed else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        traces = [lane.traces.get(trace_id) for trace_id in self.citing(lane, item)]
        return mode == "retire" or all(trace is None or trace.why == [REMOVED] for trace in traces)


for layer in (BusLayer(), IntakeLayer(), ConversationLayer(), TraceLayer(), VaultLayer(), EntityLayer(), LibraryLayer()):
    register(layer)

# forget_layers_facts.py: step 14, the fact layer for step 10's forgetting. Fact candidates S11 proposed from a document
# quote it, so erasing the document removes them and its extraction record; retiring keeps them for history.
# Used by: forget_review.py (imports this file to register). Uses: forget.py, stages_extract.py.
from app.pipeline import stages_extract
from app.pipeline.forget import ForgetItem, register


class CandidateLayer:
    """Fact candidates taken from the document, and the record of their extraction. They live in records, which Library covers."""
    name, stores, final = "Fact candidates", (), False

    def proposed(self, lane, item: ForgetItem) -> list[str]:
        return [c["candidate_id"] for c in lane.records.list_kind(stages_extract.CANDIDATE_KIND) if c["evidence"]["document_id"] == item.document_id]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        found = self.proposed(lane, item)
        for candidate_id in found:
            lane.records.purge(stages_extract.CANDIDATE_KIND, candidate_id)
        lane.records.purge(stages_extract.EXTRACTION_KIND, item.document_id)
        return ("cleared", f"{len(found)} removed") if found else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not (self.proposed(lane, item) or lane.records.load(stages_extract.EXTRACTION_KIND, item.document_id))


register(CandidateLayer())

# forget_layers_facts.py: step 14, the fact layer for step 10's forgetting. What S11 and S12 made from a document quotes it:
# its fact candidates, their review items, and the verified facts on main. Retiring the document closes those facts through
# S14 (an "as of" search still finds them); erasing removes all of it. The search index entries go with the Search layer.
# Used by: forget_review.py (imports this file to register). Uses: forget.py, stages_extract.py, stages_librarian.py, stages_version.py.
from app.pipeline import stages_extract, stages_version
from app.pipeline.contracts_graph import Commit, CommitAuthor
from app.pipeline.forget import ForgetItem, register
from app.pipeline.stages_librarian import FACT_NODE, ITEM_KIND, item_id_of

# Config
RETIRE_LEVEL = 3  # the same as retiring the document itself (step 10)


class FactLayer:
    """Candidates, review items and verified facts from the document. They live in records and the graph, which other layers cover."""
    name, stores, final = "Facts", (), False

    def candidates(self, lane, item: ForgetItem) -> list[str]:
        return [c["candidate_id"] for c in lane.records.list_kind(stages_extract.CANDIDATE_KIND) if c["evidence"]["document_id"] == item.document_id]

    def facts(self, lane, item: ForgetItem) -> list[dict]:
        return [fact for fact in lane.graph.latest(FACT_NODE) if fact["source"]["document_id"] == item.document_id]

    def scrub_commits(self, lane, fact_id: str) -> None:
        """The commits that wrote this fact keep their place in history, but no longer its words."""
        for commit_id in {version["_ref"]["commit_id"] for version in lane.graph.history(FACT_NODE, fact_id)}:
            for body in lane.records.purge("commit", commit_id):
                changes = [{**change, "fields": {}} if change["node_id"] == fact_id else change for change in body["changes"]]
                lane.records.save("commit", commit_id, Commit.model_validate({**body, "changes": changes, "message": f"Change to {fact_id} (content erased)"}))

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        drafts = [stages_version.Draft(op="close", node_type=FACT_NODE, node_id=fact["item_id"], fields={}, base_version=fact["_ref"]["version"])
                  for fact in self.facts(lane, item)]
        if drafts:
            stages_version.apply(lane, CommitAuthor(kind="human", id=item.record["uploaded_by"]), f"Retire facts of {item.document_id}", drafts, RETIRE_LEVEL)
        return ("cleared", f"{len(drafts)} closed") if drafts else ("nothing", "")

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        found = self.candidates(lane, item)
        for candidate_id in found:
            fact_id = "fact_" + candidate_id.removeprefix("fc_")
            self.scrub_commits(lane, fact_id)
            lane.graph.purge(FACT_NODE, fact_id)
            lane.records.purge(ITEM_KIND, item_id_of(candidate_id))
            lane.records.purge(stages_extract.CANDIDATE_KIND, candidate_id)
        lane.records.purge(stages_extract.EXTRACTION_KIND, item.document_id)
        return ("cleared", f"{len(found)} removed") if found else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        if self.facts(lane, item):
            return False
        return mode == "retire" or not (self.candidates(lane, item) or lane.records.load(stages_extract.EXTRACTION_KIND, item.document_id))


register(FactLayer())

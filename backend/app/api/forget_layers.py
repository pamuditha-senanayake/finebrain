# forget_layers.py: step 10, the knowledge layers: search index, graph, S3 files, the cold archive (13c), summaries and
# duplicates (13d). Each registers a handler with pipeline/forget.py. Used by: forget_review.py (imports this file to register).
# Uses: forget.py, stages_version.py, stages_cold.py, stages_summary.py, stages_dupes.py.
# The record, intake, conversation and vault layers are in forget_layers_data.py.
import re

from app.pipeline import stages_cold, stages_dupes, stages_summary, stages_version
from app.pipeline.contracts_graph import CommitAuthor
from app.pipeline.forget import ForgetItem, register
from app.pipeline.stages_version import Draft

# Config
RETIRE_LEVEL = 3  # removing a document is C3 (plan, step 10.3)
CHUNK_KINDS = ["chunk"]


class IndexLayer:
    """The search index: a retired chunk keeps its place with an end date; an erased one is deleted."""
    name, stores, final = "Search", ("chunks",), False

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        for chunk_id in item.chunk_ids:
            lane.chunks.retire(chunk_id, lane.now)
        return "cleared", f"{len(item.chunk_ids)} ended"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        for chunk_id in item.chunk_ids:
            lane.chunks.delete(chunk_id)
        return "cleared", f"{len(item.chunk_ids)} deleted"

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        """Search again with words from the document: nothing of it may come back."""
        found = {hit["item_id"] for word in item.probes for hit in lane.chunks.by_text(word, CHUNK_KINDS, lane.now, lane.now, 50)}
        if mode == "erase":
            return not found & set(item.chunk_ids) and not lane.chunks.of_document(item.document_id)
        return not found & set(item.chunk_ids)


class GraphLayer:
    """The knowledge nodes: retire writes a closing version through S14; erase empties every version."""
    name, stores, final = "Graph", ("graph",), False

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        live = {node["_ref"]["id"] for node in lane.graph.latest("knowledge")}
        drafts = [Draft(op="close", node_type="knowledge", node_id=chunk_id, fields={}, base_version=stages_version.latest_version(lane.graph, "knowledge", chunk_id))
                  for chunk_id in item.chunk_ids if chunk_id in live]
        if drafts:
            stages_version.apply(lane, CommitAuthor(kind="human", id=item.record["uploaded_by"]), f"Retire document {item.document_id}", drafts, RETIRE_LEVEL)
        return ("cleared", f"{len(drafts)} closed") if drafts else ("nothing", "")

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        for chunk_id in item.chunk_ids:
            lane.graph.purge("knowledge", chunk_id)
        return "cleared", f"{len(item.chunk_ids)} emptied"

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        if any(node["_ref"]["id"] in item.chunk_ids for node in lane.graph.latest("knowledge")):
            return False
        return mode == "retire" or all("text" not in version for chunk_id in item.chunk_ids for version in lane.graph.history("knowledge", chunk_id))


class FilesLayer:
    """The uploaded file and the raw body S1 stored. A retired document keeps both; an erased one loses both."""
    name, stores, final = "Files", ("object_store",), False

    def uris(self, lane, item: ForgetItem) -> list[str]:
        raw = re.compile(rf"/raw/.*/{re.escape(item.document_id)}\.[^/]*$")
        return [uri for uri in list(lane.object_store) if uri == item.record["original_uri"] or raw.search(uri)]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        uris = self.uris(lane, item)
        for uri in uris:
            del lane.object_store[uri]
        return ("cleared", f"{len(uris)} deleted") if uris else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not self.uris(lane, item)


class ColdLayer:
    """The cold archive (step 13c): a chunk that went cold left a compressed copy with its vector in S3. Erase removes it."""
    name, stores, final = "Cold archive", ("object_store",), False

    def archived(self, lane, item: ForgetItem) -> list[str]:
        return [uri for uri in (stages_cold.cold_uri(lane, chunk_id) for chunk_id in item.chunk_ids) if uri in lane.object_store]

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return "kept", "for history"

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        uris = self.archived(lane, item)
        for uri in uris:
            del lane.object_store[uri]
        return ("cleared", f"{len(uris)} deleted") if uris else ("nothing", "")

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return mode == "retire" or not self.archived(lane, item)


class SummaryLayer:
    """The summary ladder (step 13d): a summary built on the document's chunks goes, retired or erased, and so do the summaries
    built on it. The next Distiller night writes them again from what is left."""
    name, stores, final = "Summaries", ("chunks",), False

    def clear(self, lane, item: ForgetItem) -> tuple[str, str]:
        cleared = stages_summary.clear_citing(lane, item.chunk_ids)
        return ("cleared", f"{len(cleared)} cleared, written again tonight") if cleared else ("nothing", "")

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return self.clear(lane, item)

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        return self.clear(lane, item)

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return not lane.chunks.summaries_citing(item.chunk_ids)


class DuplicateLayer:
    """Duplicate merging (step 13d): chunks that pointed to the document's chunks as the one kept answer again."""
    name, stores, final = "Duplicates", ("chunks",), False

    def reopen(self, lane, item: ForgetItem) -> tuple[str, str]:
        reopened = stages_dupes.reopen(lane, item.chunk_ids)
        return ("cleared", f"{len(reopened)} answer again") if reopened else ("nothing", "")

    def retire(self, lane, item: ForgetItem) -> tuple[str, str]:
        return self.reopen(lane, item)

    def erase(self, lane, item: ForgetItem) -> tuple[str, str]:
        return self.reopen(lane, item)

    def verify(self, lane, item: ForgetItem, mode: str) -> bool:
        return not lane.chunks.duplicates_of(item.chunk_ids)


for layer in (IndexLayer(), GraphLayer(), FilesLayer(), ColdLayer(), SummaryLayer(), DuplicateLayer()):
    register(layer)

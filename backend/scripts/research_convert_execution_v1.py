# research_convert_execution_v1.py: a dev script. Turns an Execution_V1 folder (corpus, groundtruth, frozen config) into a
# freshness pack zip in the Research Lab format, then runs the pack audits on it and prints them.
#   uv run python -m scripts.research_convert_execution_v1 "<Execution_V1 folder>" <out.zip> [--name nyrivell_freshness_v2]
# Documents keep their text; their header becomes front matter. An update names the policy it updates (supersedes), and
# facts.jsonl names the exact old and new sentence, because an update replaces one provision, not the whole policy.
# Uses: research/packs.py, research/pack_audits.py.
import argparse
import io
import json
import zipfile
from pathlib import Path

from app.research import pack_audits
from app.research.packs import front_matter

# Config
AS_OF = "2027-07-01T00:00:00Z"  # questions are asked after every update took effect (the frozen config's update date is 2027-06-01)
FOLDERS = ("policies", "updates", "distractors")
SENSITIVITY = "internal"


def load_documents(root: Path) -> dict[str, dict]:
    documents = {}
    for folder in FOLDERS:
        for path in sorted((root / "corpus" / folder).glob("*.md")):
            meta, body = front_matter(path.read_text())
            documents[meta["doc_id"]] = {"meta": meta, "body": body}
    return documents


def document_text(doc_id: str, doc: dict, updated_by: dict[str, str]) -> str:
    """The new front matter, then the body unchanged."""
    meta = doc["meta"]
    supersedes = sorted(policy for policy, update in updated_by.items() if update == doc_id)
    lines = [f"doc_id: {doc_id}", f"title: {meta['title']}", f"domain: {meta['domain']}", f"sensitivity: {SENSITIVITY}",
             f"valid_from: {meta['effective_date']}", f"recorded_at: {meta['effective_date']}", f"supersedes: [{', '.join(supersedes)}]"]
    return "---\n" + "\n".join(lines) + "\n---\n" + doc["body"]


def holder(documents: dict, sentence: str, prefix: str) -> str | None:
    """The one document of this family that holds the sentence word for word."""
    return next((doc_id for doc_id, doc in documents.items() if doc_id.startswith(prefix) and sentence in doc["body"]), None)


def facts_of(root: Path, documents: dict) -> list[dict]:
    raw = json.loads((root / "groundtruth" / "facts.json").read_text())
    facts = []
    for f in raw["target_facts"]:
        new_doc = holder(documents, f["new_sentence"], "UPD")
        facts.append({"fact_id": f["fid"], "subject": f["subject"], "unit": f["unit"], "old_value": f["old_value"], "new_value": f["new_value"],
                      "old_doc_id": holder(documents, f["old_sentence"], "POL"), "new_doc_id": new_doc, "old_sentence": f["old_sentence"],
                      "new_sentence": f["new_sentence"], "change_at": documents[new_doc]["meta"]["effective_date"] if new_doc else None})
    for f in raw["canary_facts"]:
        facts.append({"fact_id": f["fid"], "subject": f["subject"], "unit": f["unit"], "new_value": f["value"],
                      "new_doc_id": holder(documents, f["sentence"], ""), "new_sentence": f["sentence"]})
    return facts


def queries_and_gold(root: Path, as_of: str) -> tuple[list[dict], list[dict]]:
    gold = json.loads((root / "groundtruth" / "gold.json").read_text())
    queries = [{"query_id": q["qid"], "text": q["query"], "as_of": as_of, "fact_id": q["fact_id"] or None, "kind": q["kind"],
                "paraphrase_of": f"Q-{q['fact_id']}-1" if q["kind"] == "stale_sensitive" and q["paraphrase"] > 1 else None} for q in gold]
    answers = [{"query_id": q["qid"], "expected_value": q["gold_value"], "superseded_values": [q["stale_value"]] if q["stale_value"] else []} for q in gold]
    return queries, answers


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row, sort_keys=True) + "\n" for row in rows)


def build_pack(root: Path, name: str, as_of: str = AS_OF) -> bytes:
    """The pack as zip bytes, with files written in a fixed order so the same folder gives the same zip."""
    documents = load_documents(root)
    updated_by = {doc_id: doc["meta"]["superseded_by"] for doc_id, doc in documents.items() if doc["meta"].get("superseded_by")}
    queries, gold = queries_and_gold(root, as_of)
    files = {f"documents/{doc_id}.md": document_text(doc_id, doc, updated_by) for doc_id, doc in documents.items()}
    files |= {"facts.jsonl": jsonl(facts_of(root, documents)), "queries.jsonl": jsonl(queries), "gold.jsonl": jsonl(gold),
              "README.md": f"Converted from {root.name} by scripts/research_convert_execution_v1.py. Questions asked as of {as_of}.\n"}
    company = next(iter(documents.values()))["meta"]["company"]
    files["manifest.json"] = json.dumps({"kind": "freshness", "name": name, "version": "2.0.0", "company": company, "timezone": "UTC", "currency": "USD",
                                         "created_by": "research lead", "license": "research use only", "files": sorted(files)}, indent=2, sort_keys=True)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(zipfile.ZipInfo(path, date_time=(2026, 10, 27, 0, 0, 0)), files[path])
    return buffer.getvalue()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("source"), parser.add_argument("out"), parser.add_argument("--name", default="nyrivell_freshness_v2")
    args = parser.parse_args()
    data = build_pack(Path(args.source), args.name)
    Path(args.out).write_bytes(data)
    _, sha, checks = pack_audits.audit_pack(data)
    print(f"{args.out}: {len(data)} bytes, sha256 {sha}, verdict {pack_audits.verdict(checks)}")
    for check in checks:
        print(f"  {check['status']:<15} {check['label']}: {check['detail']}", *(f"\n      {line}" for line in check["lines"][:5]))

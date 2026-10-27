# research_packs_world.py: a small, valid freshness pack the pack tests change one thing at a time, and a zip helper.
# Two policies, one update to the first (its refund window, 30 to 45 days), three canaries and one stale-sensitive question.
# Uses: nothing local. Used by: tests/test_research_packs.py, tests/test_research_pack_api.py.
import io
import json
import zipfile

# Config
BOILERPLATE = "This document supersedes any prior verbal guidance on the same subject matter."
POLICY = "Customers may request a full refund within 30 days of the delivery date."
UPDATE = "Customers may request a full refund within 45 days of the delivery date."
CANARIES = [("K01", "Every refund request is assigned a reference code beginning with the prefix RFX.", "RFX"),
            ("K02", "Parcels reaching the depot after 16 hours hand over to the carrier the following day.", "16 hours"),
            ("K03", "Audit log entries remain immutable for a period of 7 years.", "7 years")]


def document(doc_id: str, body: str, supersedes: str = "") -> str:
    return (f"---\ndoc_id: {doc_id}\ntitle: {doc_id} standard\ndomain: refunds\nsensitivity: internal\nvalid_from: 2027-01-15\n"
            f"supersedes: [{supersedes}]\n---\n{body}\n")


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row) + "\n" for row in rows)


def files(**change) -> dict[str, str]:
    """The pack's files; a keyword replaces one file (a None value removes it)."""
    canary_doc = " ".join(sentence for _, sentence, _ in CANARIES)
    facts = [{"fact_id": "F01", "subject": "refund window", "unit": "days", "old_value": "30 days", "new_value": "45 days", "old_doc_id": "POL-001",
              "new_doc_id": "UPD-F01", "old_sentence": POLICY, "new_sentence": UPDATE, "change_at": "2027-06-01"}]
    facts += [{"fact_id": fid, "subject": fid, "new_value": value, "new_doc_id": "POL-002", "new_sentence": sentence} for fid, sentence, value in CANARIES]
    queries = [{"query_id": "Q-F01-1", "text": "How long does a buyer have to ask for money back?", "as_of": "2027-07-01T00:00:00Z", "fact_id": "F01", "kind": "stale_sensitive"}]
    queries += [{"query_id": f"CAN-{fid}", "text": f"What is the answer for {fid}?", "as_of": "2027-07-01T00:00:00Z", "fact_id": fid, "kind": "canary"} for fid, _, _ in CANARIES]
    gold = [{"query_id": "Q-F01-1", "expected_value": "45 days", "superseded_values": ["30 days"]}]
    gold += [{"query_id": f"CAN-{fid}", "expected_value": value} for fid, _, value in CANARIES]
    pack = {"documents/POL-001.md": document("POL-001", f"{POLICY}\n\n{BOILERPLATE}"), "documents/POL-002.md": document("POL-002", canary_doc),
            "documents/UPD-F01.md": document("UPD-F01", f"{UPDATE}\n\n{BOILERPLATE}", supersedes="POL-001"),
            "facts.jsonl": jsonl(facts), "queries.jsonl": jsonl(queries), "gold.jsonl": jsonl(gold), "README.md": "A test pack.\n"}
    manifest = {"kind": "freshness", "name": "tiny_freshness", "version": "1.0.0", "company": "Nyrivell Dynamics", "timezone": "UTC", "currency": "USD",
                "created_by": "tests", "license": "test only", "files": sorted(pack),
                "exposure_check": {"checked_on": "2026-10-27", "query": "\"Nyrivell Dynamics\"", "exact_matches": 0}}
    pack["manifest.json"] = json.dumps(manifest)
    pack.update(change)
    return {path: text for path, text in pack.items() if text is not None}


def zipped(pack: dict[str, str], folder: str = "", crlf: bool = False) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for path, text in pack.items():
            archive.writestr(folder + path, text.replace("\n", "\r\n") if crlf else text)
    return buffer.getvalue()


def manifest_with(**change) -> str:
    return json.dumps({**json.loads(files()["manifest.json"]), **change})

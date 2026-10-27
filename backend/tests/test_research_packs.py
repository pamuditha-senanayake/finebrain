# test_research_packs.py: reading and auditing experiment packs (Research Lab step 4). The reader refuses what is not a
# safe pack; the hash ignores how it was zipped; each of the ten audits passes a good pack and catches its own defect;
# the Execution_V1 corpus with "replaces the earlier value" fails the marker leak audit and the fixed one does not.
# Uses: research/packs.py, research/pack_audits.py, scripts/research_convert_execution_v1.py, tests/research_packs_world.py.
import io
import json
import time
import zipfile
from pathlib import Path

import pytest

from app.research import pack_audits, packs
from scripts import research_convert_execution_v1 as convert
from tests.research_packs_world import BOILERPLATE, UPDATE, document, files, jsonl, manifest_with, zipped

# Config
EXECUTION_V1 = Path.home() / "Downloads"  # the research repository's corpus, outside this repo: those tests skip without it
ORIGINAL, FIXED = EXECUTION_V1 / "Execution_V1", EXECUTION_V1 / "Execution_V1 2"


def audits(pack: dict) -> dict[str, dict]:
    _, _, checks = pack_audits.audit_pack(zipped(pack))
    return {check["key"]: check for check in checks}


# --- Reading safely

def test_what_is_not_a_safe_pack_is_refused():
    link = zipfile.ZipInfo("documents/link.md")
    link.external_attr = 0o120777 << 16
    cases = {b"not a zip": "not_a_zip", zipped({"../escape.md": "x"}): "unsafe_path", zipped({"/abs.md": "x"}): "unsafe_path"}
    for data, code in cases.items():
        with pytest.raises(packs.PackRefused, match=code):
            packs.read_zip(data)
    for entry, body, code in [(link, "target", "link_not_allowed"), (zipfile.ZipInfo("doc.md"), b"\xff\xfe\x00", "not_text")]:
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            archive.writestr(entry, body)
        with pytest.raises(packs.PackRefused, match=code):
            packs.read_zip(buffer.getvalue())


def test_a_zip_bomb_is_refused_before_it_is_read(monkeypatch):
    monkeypatch.setattr(packs, "MAX_UNPACKED_BYTES", 1000)
    with pytest.raises(packs.PackRefused, match="too_large"):
        packs.read_zip(zipped({"big.md": "x" * 5000}))


def test_the_hash_ignores_the_folder_line_endings_and_file_manager_junk():
    plain = packs.pack_hash(packs.read_zip(zipped(files())))
    other = packs.pack_hash(packs.read_zip(zipped({**files(), ".DS_Store": "junk", "__MACOSX/._x": "junk"}, folder="pack/", crlf=True)))
    assert plain == other
    assert packs.pack_hash(packs.read_zip(zipped(files(**{"README.md": "Changed.\n"})))) != plain


# --- The ten audits

def test_a_good_pack_passes_every_audit_that_applies():
    statuses = {key: check["status"] for key, check in audits(files()).items()}
    assert statuses == {"schema": "pass", "determinism": "pass", "marker_leak": "pass", "pair_symmetry": "pass", "overlap": "pass", "canaries": "pass",
                        "gold_coverage": "pass", "alphabet": "not_applicable", "oracle": "not_applicable", "exposure": "pass"}


def test_schema_names_the_file_and_line_of_each_problem():
    bad = files(**{"queries.jsonl": files()["queries.jsonl"] + '{"query_id": "Q9", "kind": "stale_sensitive"}\n{"query_id": "Q8", "text": "t", "as_of": "x", "kind": "control", "colour": "red"}\n',
                   "facts.jsonl": None})
    check = audits(bad)["schema"]
    assert check["status"] == "fail"
    assert any(line.startswith("queries.jsonl:5:") for line in check["lines"]) and any(line.startswith("queries.jsonl:6:") for line in check["lines"])
    assert "facts.jsonl: missing" in check["lines"]


def test_a_bad_manifest_stops_at_schema():
    _, _, checks = pack_audits.audit_pack(zipped(files(**{"manifest.json": manifest_with(kind="poetry")})))
    assert [(c["key"], c["status"]) for c in checks] == [("schema", "fail")]


@pytest.mark.parametrize("leak", ["It replaces the earlier value in full.", "This takes effect on 2027-06-01.", "Previously the window was shorter.", "Effective 1 June the rule applies."])
def test_an_update_that_announces_itself_fails_the_marker_leak_audit(leak):
    check = audits(files(**{"documents/UPD-F01.md": document("UPD-F01", f"{UPDATE}\n{leak}", supersedes="POL-001")}))["marker_leak"]
    assert check["status"] == "fail" and leak in check["lines"][0]


def test_an_update_title_that_says_update_is_a_leak():
    titled = files(**{"documents/UPD-F01.md": document("UPD-F01", UPDATE, supersedes="POL-001").replace("title: UPD-F01 standard", "title: Policy Update: refunds")})
    assert audits(titled)["marker_leak"]["lines"] == ["documents/UPD-F01.md: title: Policy Update: refunds"]


def test_boilerplate_every_kind_of_document_carries_is_not_a_leak():
    assert "supersedes" in BOILERPLATE and audits(files())["marker_leak"]["status"] == "pass"


def test_pairs_that_differ_beyond_the_value_overlap_and_missing_exposure_are_warnings():
    facts = files()["facts.jsonl"].replace("within 45 days of the delivery date", "within 45 calendar days of delivery")
    update = document("UPD-F01", "Customers may request a full refund within 45 calendar days of delivery.", supersedes="POL-001")
    copied = files()["queries.jsonl"].replace("How long does a buyer have to ask for money back?", UPDATE)
    found = audits(files(**{"facts.jsonl": facts, "documents/UPD-F01.md": update, "queries.jsonl": copied, "manifest.json": manifest_with(exposure_check=None)}))
    assert (found["pair_symmetry"]["status"], found["exposure"]["status"]) == ("warn", "warn")
    assert audits(files(**{"queries.jsonl": copied}))["overlap"]["lines"] == ["Q-F01-1: 1.00"]


def test_fewer_than_three_canaries_or_missing_gold_fail():
    queries = jsonl([json.loads(line) for line in files()["queries.jsonl"].splitlines()][:3])
    assert audits(files(**{"queries.jsonl": queries}))["canaries"]["status"] == "fail"
    gold = files()["gold.jsonl"].splitlines()
    found = audits(files(**{"gold.jsonl": "\n".join(gold[1:] + [gold[1]]) + "\n"}))["gold_coverage"]
    assert found["status"] == "fail" and "Q-F01-1: no gold" in found["lines"] and "CAN-K01: 2 gold lines" in found["lines"]


def test_a_fact_whose_sentence_is_not_in_its_document_fails_gold_coverage():
    moved = document("UPD-F01", f"Customers may ask within 45 days.\n\n{BOILERPLATE}", supersedes="POL-001")
    assert "F01: sentence not found in UPD-F01" in audits(files(**{"documents/UPD-F01.md": moved}))["gold_coverage"]["lines"]


def test_event_labels_must_be_in_the_alphabet():
    xes = '<log><trace><event><string key="concept:name" value="check_order"/></event><event><string key="concept:name" value="refund"/></event></trace></log>'
    skills = {"manifest.json": manifest_with(kind="skills", files=[]), "tasks.jsonl": "", "gold.jsonl": "", "train_log.xes": xes, "alphabet.json": '["check_order"]'}
    assert audits(skills)["alphabet"]["lines"] == ["refund"]
    assert audits({**skills, "alphabet.json": '["check_order", "refund"]'})["alphabet"]["status"] == "pass"
    assert audits({**skills, "train_log.xes": "<log><broken"})["alphabet"]["status"] == "fail"


# --- Volume and the real corpus

def test_a_pack_of_ten_thousand_questions_audits_in_seconds():
    rows = [{"query_id": f"Q{i}", "text": f"Question {i} about refunds?", "as_of": "2027-07-01T00:00:00Z", "fact_id": "F01", "kind": "stale_sensitive"} for i in range(10_000)]
    big = files(**{"queries.jsonl": files()["queries.jsonl"] + jsonl(rows), "gold.jsonl": files()["gold.jsonl"] + jsonl([{"query_id": r["query_id"], "expected_value": "45 days"} for r in rows])})
    started = time.monotonic()
    assert pack_audits.verdict(list(audits(big).values())) == "pass"
    assert time.monotonic() - started < 10


@pytest.mark.skipif(not (ORIGINAL.exists() and FIXED.exists()), reason="Execution_V1 corpus not in ~/Downloads")
def test_execution_v1_the_old_corpus_leaks_markers_and_the_fixed_one_does_not():
    _, _, old = pack_audits.audit_pack(convert.build_pack(ORIGINAL, "nyrivell_freshness_v1"))
    data = convert.build_pack(FIXED, "nyrivell_freshness_v2")
    _, sha, fixed = pack_audits.audit_pack(data)
    assert next(c for c in old if c["key"] == "marker_leak")["status"] == "fail"
    leak = next(c for c in fixed if c["key"] == "marker_leak")
    assert leak["status"] == "fail" and all(": title: Policy Update:" in line for line in leak["lines"])  # only the titles still leak
    assert {c["key"]: c["status"] for c in fixed if c["status"] not in ("pass", "not_applicable")} == {"marker_leak": "fail", "overlap": "warn", "exposure": "warn"}
    assert pack_audits.audit_pack(convert.build_pack(FIXED, "nyrivell_freshness_v2"))[1] == sha  # converting again gives the same pack

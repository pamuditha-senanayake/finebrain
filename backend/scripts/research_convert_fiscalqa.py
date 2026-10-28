# research_convert_fiscalqa.py: a dev script. Turns FiscalQA Pro (rosecymbler/fiscal-fr-bench: data CC BY 4.0 from
# Légifrance under Licence Ouverte, code MIT) into a freshness pack: its 209 scored temporal questions (R3), each article
# version as a document valid from its start to its end, and its nuggets, graded as its own scorer grades them. Three
# canary questions are added (the Lab's pipeline check; FiscalQA has none). Reads Parquet, so it runs in its own
# environment and imports nothing from the app (the pack audits run when the pack is uploaded):
#   uv run --no-project --managed-python --python 3.12 --with pyarrow python -I backend/scripts/research_convert_fiscalqa.py <fiscal-fr-bench folder> <out.zip>
# Kept: every version of the 33 articles in force on some day between the first and the last question date, except
# stillborn versions (MODIFIE_MORT_NE) and versions that end the day they start. Each question is checked: the version in
# force on its date must be FiscalQA's gold version.
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

# Config
NAME, VERSION = "fiscalqa_pro_r3", "1.0.0"
OPEN_END = "2999"  # Légifrance's "no end yet"
ANSWER_PROMPT = ("Tu es un assistant juridique fiscal. Réponds de façon précise et concise à la question, en citant l'article applicable et la "
                 "valeur chiffrée exacte. Si un extrait de texte légal est fourni, fonde ta réponse dessus.\n\n"
                 "Extrait de l'article applicable :\n\"\"\"\n{context}\n\"\"\"\n\nQuestion : {question}")  # FiscalQA's SYSTEM, then its user message
CANARIES = [("K01", 7351), ("K02", 48219), ("K03", 905)]  # value-only controls: a wrong answer is a pipeline defect


def day(value) -> str | None:
    text = str(value)[:10] if value else None
    return None if not text or text.startswith(OPEN_END) else text


def load(root: Path) -> tuple[list[dict], list[dict], list[dict]]:
    import pyarrow.parquet as pq  # here, so the tests can use this file's helpers without Parquet

    bench = root / "data" / "benchmark"
    scored = {line.strip() for line in (bench / "scored209_qids.txt").read_text().splitlines() if line.strip()}
    questions = [q for q in json.loads((bench / "questions.json").read_text()) if q["qid"] in scored]
    nuggets = [n for n in json.loads((bench / "nuggets.json").read_text()) if n["qid"] in scored and n["kind"] != "provenance"]
    articles = {q["gold"]["article_cid"] for q in questions}
    first, last = min(q["date_anchor"] for q in questions), max(q["date_anchor"] for q in questions)
    versions = [v for v in pq.read_table(root / "data" / "articles_cgi_versioned.parquet").to_pylist() if v["cid"] in articles
                and (v["etat"] or "").upper() != "MODIFIE_MORT_NE" and day(v["date_debut"]) != day(v["date_fin"])
                and day(v["date_debut"]) <= last and (day(v["date_fin"]) is None or day(v["date_fin"]) > first)]
    return questions, nuggets, versions


def in_force(versions: list[dict], cid: str, on: str) -> str | None:
    """The version in force on a day: started by then, not yet ended; the latest start wins (FiscalQA's own rule)."""
    live = [v for v in versions if v["cid"] == cid and day(v["date_debut"]) <= on and (day(v["date_fin"]) is None or day(v["date_fin"]) > on)]
    return max(live, key=lambda v: day(v["date_debut"]))["id"] if live else None


def title_of(num: str, version_id: str) -> str:
    """Each version's own title. Finebrain chains uploads with the same title into versions and ends the older one, which
    would give plain retrieval (C0) version handling it is not meant to have; the tag comes from the version id, so it
    carries no date and no order."""
    return f"Article {num} du CGI ({hashlib.sha1(version_id.encode()).hexdigest()[:6]})"


def document(doc_id: str, title: str, body: str, valid_from: str, valid_to: str | None) -> str:
    lines = [f"doc_id: {doc_id}", f"title: {title}", "domain: fiscalite", "sensitivity: public", f"valid_from: {valid_from}", f"valid_to: {valid_to or ''}"]
    return "---\n" + "\n".join(lines) + "\n---\n" + f"{title}\n\n{body.strip()}\n"


def build(root: Path) -> tuple[dict[str, str], list[str]]:
    """Every file of the pack, and the questions whose gold version is not the one in force on their date."""
    questions, nuggets, versions = load(root)
    title = {v["cid"]: f"Article {v['num']} du CGI" for v in versions}  # what every version's title and heading start with
    files = {f"documents/{v['id']}.md": document(v["id"], title_of(v["num"], v["id"]), v["texte_clean"] or "", day(v["date_debut"]), day(v["date_fin"])) for v in versions}
    latest = {cid: max((v for v in versions if v["cid"] == cid), key=lambda v: day(v["date_debut"]))["id"] for cid in title}
    queries = [{"query_id": q["qid"], "text": q["prompt"], "as_of": q["date_anchor"], "fact_id": q["gold"]["article_cid"], "kind": "stale_sensitive"} for q in questions]
    gold = [{"query_id": q["qid"], "expected_value": q["gold"]["canonical_answer"]} for q in questions]
    facts = [{"fact_id": cid, "subject": name, "new_value": "", "new_doc_id": latest[cid], "new_sentence": name} for cid, name in sorted(title.items())]
    keep = ("pattern", "value", "target", "tol", "label", "required")
    rows = [{"query_id": n["qid"], "nugget_id": n["nugget_id"], "kind": n["kind"], **{k: n[k] for k in keep if k in n}} for n in nuggets]
    for name, value in CANARIES:
        doc_id, sentence = f"LAB-CANARY-{name}", f"La valeur de contrôle {name} est fixée à {value} euros."
        files[f"documents/{doc_id}.md"] = document(doc_id, f"Note de contrôle du laboratoire {name}", sentence, "1989-01-01", None)
        queries.append({"query_id": f"canary-{name}", "text": f"Quelle est la valeur de contrôle {name} fixée par la note de contrôle du laboratoire ?",
                        "as_of": questions[-1]["date_anchor"], "fact_id": f"canary_{name}", "kind": "canary"})
        gold.append({"query_id": f"canary-{name}", "expected_value": f"{value} euros"})
        facts.append({"fact_id": f"canary_{name}", "subject": f"valeur de contrôle {name}", "new_value": f"{value} euros", "new_doc_id": doc_id, "new_sentence": sentence})
        rows.append({"query_id": f"canary-{name}", "nugget_id": f"canary-{name}-val", "kind": "numeric_tol", "target": value, "tol": 0.5, "required": True})
    mismatched = [q["qid"] for q in questions if in_force(versions, q["gold"]["article_cid"], q["date_anchor"]) != q["gold"]["version_id"]]
    manifest = {"kind": "freshness", "name": NAME, "version": VERSION, "company": "Code général des impôts (France)", "timezone": "Europe/Paris", "currency": "EUR",
                "created_by": "research_lab", "license": "CC-BY-4.0 (FiscalQA Pro data; Légifrance texts under Licence Ouverte / Etalab 2.0)",
                "files": ["README.md", "answer_prompt.txt", "nuggets.jsonl"], "notes": f"{len(versions)} article versions, {len(questions)} questions, {len(mismatched)} gold mismatches"}
    readme = (f"# FiscalQA Pro, R3, as a Finebrain freshness pack\n\nSource: FiscalQA Pro (arXiv 2608.09393), https://github.com/rosecymbler/fiscal-fr-bench, data CC BY 4.0.\n"
              f"{len(questions)} scored temporal questions over {len(title)} CGI articles; {len(versions)} article versions, each valid from its start to its end.\n"
              "Grading: FiscalQA's nuggets (all required ones must hold). Prompt: FiscalQA's system prompt and user message. Three canaries added by the Lab.\n")
    files.update({"manifest.json": json.dumps(manifest, ensure_ascii=False, indent=1), "README.md": readme, "answer_prompt.txt": ANSWER_PROMPT,
                  "queries.jsonl": jsonl(queries), "gold.jsonl": jsonl(gold), "facts.jsonl": jsonl(facts), "nuggets.jsonl": jsonl(rows)})
    return files, mismatched


def jsonl(rows: list[dict]) -> str:
    return "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)


def zipped(files: dict[str, str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(files):
            archive.writestr(zipfile.ZipInfo(path, (2026, 1, 1, 0, 0, 0)), files[path])  # a fixed time: the same pack zips the same
    return buffer.getvalue()


if __name__ == "__main__":
    files, mismatched = build(Path(sys.argv[1]))
    Path(sys.argv[2]).write_bytes(zipped(files))
    print(f"{sys.argv[2]}: {len(files)} files; {sum(p.startswith('documents/') for p in files)} documents; gold version not in force on its date: {len(mismatched)} {mismatched[:5]}")

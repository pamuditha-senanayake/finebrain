# pack_audits.py: the ten checks every pack passes before a run (spec section 5.3). Each gives pass, warn, fail or
# not_applicable with the lines that caused it. A fail blocks the pack; a warn needs a typed reason. The marker leak audit
# exists because update documents that say "replaces the earlier value" let a model spot the new fact by its wording.
# Used by: research/routes.py, scripts/research_convert_execution_v1.py. Uses: research/packs.py, research/pack_schemas.py.
import difflib
import json
import re
import xml.etree.ElementTree as ElementTree
from collections import Counter

from app.research import packs
from app.research.pack_schemas import KINDS, row_id

# Config
MARKERS = ["replaces", "replaced", "previously", "no longer", "updated", "new policy", "supersedes", "superseded", "as of",
           "effective immediately", "earlier value", "earlier figure", "prior value", "revises", "revised", "amended", "takes effect"]
MARKER = re.compile(r"\b(" + "|".join(re.escape(m) for m in MARKERS) + r")\b", re.I)
DATE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b|\b\d{1,2} (January|February|March|April|May|June|July|August|September|October|November|December)\b"
                  r"|\b(January|February|March|April|May|June|July|August|September|October|November|December) \d{1,2}(st|nd|rd|th)?,? \d{4}\b", re.I)
TITLE_MARKER = re.compile(r"\b(update[sd]?|revision|revised|amend\w*|new|supersed\w*|replac\w*|change[sd]?)\b", re.I)  # Finebrain puts each title into every chunk
OVERLAP_LIMIT = 0.3
MIN_CANARIES = 3
STOPWORDS = {"a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "is", "are", "be", "by", "with", "at", "it", "its",
             "what", "how", "which", "who", "when", "does", "do", "after", "from", "that", "this", "their", "they", "may"}
MAX_LINES = 50  # lines shown per audit


def result(key: str, label: str, status: str, detail: str, lines: list[str] = ()) -> dict:
    return {"key": key, "label": label, "status": status, "detail": detail, "lines": list(lines)[:MAX_LINES]}


def words(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


def content_words(text: str) -> set[str]:
    return {word for word in words(text) if word not in STOPWORDS}


# --- The audits

def schema(pack: dict) -> dict:
    errors = pack["errors"]
    return result("schema", "Schema", "fail" if errors else "pass", f"{len(errors)} problems" if errors else "Every file parses", errors)


def determinism(data: bytes, sha: str) -> dict:
    again = packs.pack_hash(packs.read_zip(data))
    return result("determinism", "Determinism", "pass" if again == sha else "fail", "Stable hash" if again == sha else "Hash changed on a second read")


def marker_leak(pack: dict) -> dict:
    """Update documents must not announce themselves: no marker words, no dates in the body. A line that other documents
    carry word for word (house boilerplate) does not tell an update apart, so it is not a leak."""
    updates = [doc for doc in pack["documents"].values() if doc["meta"].supersedes]
    shared = {line.strip() for doc in pack["documents"].values() if not doc["meta"].supersedes for line in doc["body"].split("\n")}
    found = [f"{doc['path']}:{number}: {line.strip()[:160]}" for doc in updates for number, line in enumerate(doc["body"].split("\n"), start=1)
             if (MARKER.search(line) or DATE.search(line)) and line.strip() not in shared]
    found += title_leaks(pack, updates)
    detail = f"{len(found)} lines in {len(updates)} update documents" if found else f"{len(updates)} update documents read"
    return result("marker_leak", "Marker leak", "fail" if found else "pass", detail, found)


def title_leaks(pack: dict, updates: list[dict]) -> list[str]:
    """Update titles that say what they are ("Policy Update: ..."), in words no other title uses. S11 puts the title into every
    chunk, so a title marks the chunk as newer as plainly as a sentence would."""
    others = {word.lower() for doc in pack["documents"].values() if not doc["meta"].supersedes for word in TITLE_MARKER.findall(doc["meta"].title)}
    return [f"{doc['path']}: title: {doc['meta'].title}" for doc in updates
            if any(word.lower() not in others for word in TITLE_MARKER.findall(doc["meta"].title))]


def changed_outside(old: str, new: str, allowed: set[str]) -> bool:
    """True when the two sentences differ in any word that is not part of the values."""
    old_words, new_words = words(old), words(new)
    for tag, a1, a2, b1, b2 in difflib.SequenceMatcher(a=old_words, b=new_words).get_opcodes():
        if tag != "equal" and not set(old_words[a1:a2] + new_words[b1:b2]) <= allowed:
            return True
    return False


def pair_symmetry(pack: dict) -> dict:
    facts = [f for f in pack["extra"].get("facts.jsonl", []) if f.old_sentence]
    if not facts:
        return result("pair_symmetry", "Pair symmetry", "not_applicable", "No superseded facts in this kind")
    uneven = [f"{f.fact_id}: {f.old_sentence} -> {f.new_sentence}" for f in facts
              if changed_outside(f.old_sentence, f.new_sentence, set(words(f.old_value or "")) | set(words(f.new_value)))]
    return result("pair_symmetry", "Pair symmetry", "warn" if uneven else "pass", f"{len(uneven)} of {len(facts)} pairs differ beyond the value", uneven)


def overlap(pack: dict) -> dict:
    facts = {f.fact_id: f for f in pack["extra"].get("facts.jsonl", [])}
    scored = [(q.query_id, jaccard(q.text, facts[q.fact_id].new_sentence)) for q in pack["main"] if getattr(q, "fact_id", None) in facts]
    if not scored:
        return result("overlap", "Overlap", "not_applicable", "No query names a fact")
    high = [f"{query_id}: {score:.2f}" for query_id, score in scored if score > OVERLAP_LIMIT]
    mean = sum(score for _, score in scored) / len(scored)
    return result("overlap", "Overlap", "warn" if high else "pass", f"Mean Jaccard {mean:.3f}; {len(high)} above {OVERLAP_LIMIT}", high)


def jaccard(a: str, b: str) -> float:
    left, right = content_words(a), content_words(b)
    return len(left & right) / len(left | right) if left | right else 0.0


def canaries(pack: dict) -> dict:
    if pack["manifest"].kind != "freshness":
        return result("canaries", "Canaries", "not_applicable", "Canary tasks arrive with this kind's runner")
    gold = {g.query_id for g in pack["gold"]}
    count = sum(1 for q in pack["main"] if q.kind == "canary" and q.query_id in gold)
    return result("canaries", "Canaries", "pass" if count >= MIN_CANARIES else "fail", f"{count} canaries with gold (at least {MIN_CANARIES})")


def gold_coverage(pack: dict) -> dict:
    """Every query or task has exactly one gold line, and every fact it names is where it says."""
    ids, gold_ids = Counter(row_id(r) for r in pack["main"]), Counter(row_id(g) for g in pack["gold"])  # counted once: big packs stay fast
    problems = [f"{i}: no gold" for i in ids if i not in gold_ids] + [f"{i}: gold for no query" for i in gold_ids if i not in ids]
    problems += [f"{i}: appears {n} times" for i, n in sorted(ids.items()) if n > 1]
    problems += [f"{i}: {n} gold lines" for i, n in sorted(gold_ids.items()) if n > 1]
    problems += fact_problems(pack)
    return result("gold_coverage", "Gold coverage", "fail" if problems else "pass", f"{len(problems)} problems" if problems else f"{len(ids)} with gold", problems)


def fact_problems(pack: dict) -> list[str]:
    facts, docs = {f.fact_id: f for f in pack["extra"].get("facts.jsonl", [])}, pack["documents"]
    problems = [f"{q.query_id}: names unknown fact {q.fact_id}" for q in pack["main"] if getattr(q, "fact_id", None) and q.fact_id not in facts]
    for fact in facts.values():
        for doc_id, sentence in ((fact.old_doc_id, fact.old_sentence), (fact.new_doc_id, fact.new_sentence)):
            if doc_id and sentence and sentence not in docs.get(doc_id, {}).get("body", ""):
                problems.append(f"{fact.fact_id}: sentence not found in {doc_id}")
    return problems


def alphabet(pack: dict) -> dict:
    logs = KINDS[pack["manifest"].kind].get("logs")
    present = [path for path in logs or () if path in pack["files"]]
    if not present:
        return result("alphabet", "Alphabet", "not_applicable", "No event logs in this pack")
    if "alphabet.json" not in pack["files"]:
        return result("alphabet", "Alphabet", "fail", "Event logs without alphabet.json")
    try:
        known = set(json.loads(pack["files"]["alphabet.json"]))
        labels = {label for path in present for label in log_labels(path, pack["files"][path])}
    except (ValueError, ElementTree.ParseError) as error:  # a log or alphabet that cannot be read is a fail, never a crash
        return result("alphabet", "Alphabet", "fail", f"Could not read the logs: {error}")
    unknown = sorted(labels - known)
    return result("alphabet", "Alphabet", "fail" if unknown else "pass", f"{len(unknown)} labels missing from alphabet.json", unknown)


def log_labels(path: str, text: str) -> set[str]:
    """Event names from XES (concept:name on each event) or CSV (an activity column)."""
    if path.endswith(".xes"):
        events = [node for node in ElementTree.fromstring(text).iter() if node.tag.split("}")[-1] == "event"]
        return {child.get("value") for event in events for child in event if child.get("key") == "concept:name"}
    header, *rows = [line.split(",") for line in text.strip().split("\n")]
    column = header.index("activity") if "activity" in header else header.index("concept:name")
    return {row[column].strip() for row in rows if len(row) > column}


def oracle(pack: dict) -> dict:
    if pack["manifest"].kind != "security":
        return result("oracle", "Oracle", "not_applicable", "Only security packs")
    return result("oracle", "Oracle", "fail", "The oracle check arrives in step 9; security packs wait until then")


def exposure(pack: dict) -> dict:
    check = pack["manifest"].exposure_check
    if check is None:
        return result("exposure", "Pretraining exposure", "warn", "No web check recorded in the manifest")
    if check.exact_matches:
        return result("exposure", "Pretraining exposure", "warn", f"{check.exact_matches} exact web matches for {check.query!r} on {check.checked_on}")
    return result("exposure", "Pretraining exposure", "pass", f"No exact match for {check.query!r} on {check.checked_on}")


# --- All of them

def audit_pack(data: bytes) -> tuple[dict, str, list[dict]]:
    """The parsed pack, its hash, and the ten audits in order. Raises PackRefused when it is not a pack at all."""
    files = packs.read_zip(data)
    sha, pack = packs.pack_hash(files), packs.parse_pack(files)
    if pack["manifest"] is None:
        return pack, sha, [schema(pack)]
    checks = [schema(pack), determinism(data, sha), marker_leak(pack), pair_symmetry(pack), overlap(pack), canaries(pack),
              gold_coverage(pack), alphabet(pack), oracle(pack), exposure(pack)]
    return pack, sha, checks


def verdict(checks: list[dict]) -> str:
    statuses = {check["status"] for check in checks}
    return "fail" if "fail" in statuses else "warn" if "warn" in statuses else "pass"

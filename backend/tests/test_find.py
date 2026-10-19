# test_find.py: step 11, find. Search hits say where to go and what to light up: a focus (kind, id, sentence span) that
# is also in the link. A hit's span points at the right sentence in what the page shows. Ask answers carry one "Show me".
# Uses: app/api/search.py, routes.py, documents.py, tests/test_documents.py (helpers), tests/golden.py.
from urllib.parse import parse_qs, urlparse

from tests.test_documents import FOUNDER, NOTE, TENANT, build, upload

# Config
STEWARD = "h-udayanga"


def find(client, q: str, persona: str = FOUNDER) -> list[dict]:
    response = client.get(f"/api/t/{TENANT}/search", params={"q": q}, headers={"x-persona": persona})
    assert response.status_code == 200
    return response.json()


def filed(client, lane, name="support_hours.md", data=NOTE, sensitivity="internal") -> str:
    document_id = upload(client, name, data, sensitivity).json()["id"]
    lane.bus.drain()
    return document_id


def link(hit: dict) -> dict[str, str]:
    return {key: values[0] for key, values in parse_qs(urlparse(hit["href"]).query).items()}


def test_a_sentence_in_a_document_is_found_with_its_span_and_the_link_carries_it():
    client, lane = build()
    document_id = filed(client, lane)
    hit = next(h for h in find(client, "Saturday") if h["kind"] == "Document")
    chunk = client.get(f"/api/t/{TENANT}/documents/{document_id}/chunks", headers={"x-persona": FOUNDER}).json()[0]
    start, end = hit["focus"]["span"]
    assert hit["focus"]["kind"] == "chunk" and hit["focus"]["id"] == chunk["id"] and "Saturday" in chunk["text"][start:end]
    assert "help@finebase.lk" not in chunk["text"] and hit["label"] == "support hours"
    assert link(hit) == {"doc": document_id, "focus": f"chunk:{chunk['id']}", "span": f"{start}:{end}", "q": "saturday"} and hit["href"].startswith("/l2/library?")


def test_policy_wording_is_found_and_the_span_points_into_the_statement_the_page_shows():
    client, _ = build()
    hit = next(h for h in find(client, "refund window") if h["kind"] == "Policy")
    current = max((p for p in client.get(f"/api/t/{TENANT}/policies", headers={"x-persona": FOUNDER}).json() if p["key"] == hit["focus"]["id"]), key=lambda p: p["version"])
    statement = current["statement"]
    start, end = hit["focus"]["span"]
    assert "refund window" in statement[start:end].lower() and hit["href"].startswith(f"/l2/policies/{hit['focus']['id']}?")


def test_runs_and_skills_are_found_by_name_or_id():
    client, lane = build()
    from scripts.seed_runs import add_runs
    add_runs(lane, 40)
    run = next(h for h in find(client, "case 00007") if h["kind"] == "Run")
    assert run["focus"] == {"kind": "run", "id": "run_00007", "field": None, "span": None} and link(run)["focus"] == "run:run_00007"
    assert any(h["kind"] == "Skill" for h in find(client, "refund"))


def test_search_only_shows_what_the_askers_tier_may_read_and_ignores_short_queries(monkeypatch):
    client, lane = build()
    filed(client, lane, "salaries.md", b"Payroll\n\nThe founder salary is reviewed every Saturday morning.", "restricted")
    assert any(h["kind"] == "Document" for h in find(client, "salary", FOUNDER))
    monkeypatch.setitem(lane.seed["people"]["h-udayanga"], "tier", "L3")  # undone after the test: the seed is shared
    assert not any(h["kind"] == "Document" for h in find(client, "salary", STEWARD))
    assert find(client, "a") == [] and find(client, "   ") == []


def test_ask_gives_one_show_me_that_opens_the_cited_sentence():
    def answerer(question, documents, history=(), address="sir"):
        cited = [item_id for item_id, _ in documents if item_id.startswith("doc_")] if "Saturday" in question else []
        return "Until 6 pm on Saturday.", cited

    client, lane = build(answerer)
    filed(client, lane)
    body = client.post(f"/api/t/{TENANT}/ask", json={"question": "Are you open on Saturday?"}, headers={"x-persona": FOUNDER}).json()
    assert [a["label"] for a in body["actions"]] == ["Show me"] and body["actions"][0]["href"].startswith("/l2/library?") and "focus=chunk%3Adoc_" in body["actions"][0]["href"]
    nothing = client.post(f"/api/t/{TENANT}/ask", json={"question": "Who are you?"}, headers={"x-persona": FOUNDER}).json()
    assert nothing.get("actions") is None

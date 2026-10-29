# test_intake.py: a document joins the knowledge base through a guided intake. The text fills what it can, Lisena asks
# for each missing field, nothing is filed until the policy is met, a meeting is headed and tagged line by line, the
# original stays in raw storage, a second click files nothing twice, and a filed document can be switched off and on.
# Uses: app/api/intake.py, intake_policy.py, documents.py, routes.py, tests/test_documents.py (helpers).
from app.api import intake_policy as policy
from tests.test_documents import FOUNDER, TENANT, build

TRANSCRIPT = b"""Kickoff with Acme, 2026-10-12
Nimal: Thanks for joining. We need the new portal live before December.
Sara: We agreed to launch the beta on 1 November.
Nimal: Maybe we could add Sinhala later.
Sara: I will send the plan by Friday.
"""
ANSWERS = {"about": "client", "about_name": "Acme", "owner": "Pamuditha", "meeting_type": "client", "topic": "Portal kickoff"}


def post(client, path: str, **kwargs):
    return client.post(f"/api/t/{TENANT}/{path}", headers={"x-persona": FOUNDER}, **kwargs)


def start(client, name: str = "acme_kickoff.txt", data: bytes = TRANSCRIPT) -> dict:
    return post(client, "intake", files={"file": (name, data)}).json()


def test_the_text_answers_what_it_can_and_lisena_asks_the_rest():
    client, _ = build()
    draft = start(client)
    assert draft["fields"]["kind"] == "meeting" and draft["fields"]["date"] == "2026-10-12"
    assert draft["fields"]["attendees"] == ["Nimal", "Sara"]
    asked = [q["field"] for q in draft["questions"]]
    assert asked == ["about", "owner", "meeting_type", "topic"] and not draft["ready"]
    assert draft["questions"][0]["options"] == policy.ABOUT  # a choice comes with its options


def test_nothing_is_filed_until_every_required_field_is_known():
    client, lane = build()
    draft = start(client)
    refused = post(client, f"intake/{draft['intakeId']}/file")
    assert refused.status_code == 409 and refused.json()["error"].startswith("missing:about")
    assert lane.records.list_kind("document") == []


def test_a_client_needs_its_name_and_bad_answers_are_not_kept():
    client, _ = build()
    draft = start(client)
    after = post(client, f"intake/{draft['intakeId']}/answer", json={"fields": {"about": "client", "date": "not a date", "meeting_type": "party"}}).json()
    assert after["fields"]["date"] == "2026-10-12"  # the bad date did not replace the good one
    assert "meeting_type" not in after["fields"] and "about_name" in [q["field"] for q in after["questions"]]


def test_a_meeting_is_filed_headed_and_tagged_and_cited_by_its_name():
    client, lane = build()
    draft = start(client)
    ready = post(client, f"intake/{draft['intakeId']}/answer", json={"fields": ANSWERS}).json()
    assert ready["ready"] and ready["questions"] == []
    doc = post(client, f"intake/{draft['intakeId']}/file").json()
    lane.bus.drain()
    assert doc["title"] == "Meeting · Acme · 2026-10-12 · Portal kickoff" and doc["meta"]["attendees"] == ["Nimal", "Sara"]
    text = " ".join(c["text"] for c in client.get(f"/api/t/{TENANT}/documents/{doc['id']}/chunks", headers={"x-persona": FOUNDER}).json())
    assert "not a company rule" in text and "[Agreed] Sara: We agreed" in text
    assert "[Suggested] Nimal: Maybe" in text and "[Action] Sara: I will send" in text
    assert any(uri.endswith("acme_kickoff.txt") for uri in lane.object_store)  # the original is kept as it was


def test_a_second_click_files_nothing_twice():
    client, lane = build()
    draft = start(client)
    post(client, f"intake/{draft['intakeId']}/answer", json={"fields": ANSWERS})
    first = post(client, f"intake/{draft['intakeId']}/file").json()
    again = post(client, f"intake/{draft['intakeId']}/file").json()
    assert first["id"] == again["id"] and len(lane.records.list_kind("document")) == 1


def test_any_document_kind_is_asked_for_its_own_fields():
    client, _ = build()
    draft = start(client, "acme_msa.txt", b"Master services agreement between Finebase Labs and Acme. Signed 2026-09-01.")
    after = post(client, f"intake/{draft['intakeId']}/answer", json={"fields": {"kind": "contract"}}).json()
    assert [q["field"] for q in after["questions"]] == ["about", "owner", "parties"]


def test_a_switched_off_document_answers_nothing_until_it_is_on_again():
    client, lane = build()
    draft = start(client)
    post(client, f"intake/{draft['intakeId']}/answer", json={"fields": ANSWERS})
    doc = post(client, f"intake/{draft['intakeId']}/file").json()
    lane.bus.drain()

    def found() -> bool:
        live = lane.chunks.by_text("beta November launch", ["chunk"], lane.now, lane.now, 20)
        return any(item["source"]["document_id"] == doc["id"] for item in live)

    assert found()
    off = post(client, f"documents/{doc['id']}/switch", json={"on": False}).json()
    assert off["on"] is False and not found()
    assert post(client, f"documents/{doc['id']}/switch", json={"on": True}).json()["on"] is True and found()


def test_someone_else_cannot_read_or_finish_my_intake():
    client, _ = build()
    draft = start(client)
    other = client.post(f"/api/t/{TENANT}/intake/{draft['intakeId']}/file", headers={"x-persona": "h-udayanga"})
    assert other.status_code == 404

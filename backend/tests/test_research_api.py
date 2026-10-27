# test_research_api.py: the Research Lab is off by default and changes nothing in the product (Research Lab step 1).
# With RESEARCH_LAB unset, main.py serves no /research route. With it enabled, /research reaches the Lab ahead of HQ,
# HQ answers as before, only the founder or the research role gets in, and a store outage is a state, not an error.
# Uses: app/main.py, app/research/routes.py, app/research/contracts.py. No Postgres needed.
import importlib
import os

import psycopg
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import hq
from app.research.contracts import ResearchSnapshot
from app.research.routes import create_research_app

PEOPLE = {
    "h-founder": {"tier": "L1", "roles": ["founder", "dri"]},
    "h-steward": {"tier": "L2", "roles": ["steward"]},
    "h-analyst": {"tier": "L2", "roles": ["research"]},
}


class FakeConnection:
    closed = False

    def execute(self, *args):
        return self

    def fetchone(self):
        return (True,)


def tiny_hq_app() -> FastAPI:
    inner = FastAPI()
    inner.get("/health")(lambda: {"status": "ok"})
    inner.get("/research/status")(lambda: {"from": "hq"})  # if HQ ever answered here, the Lab mount must still win
    return inner


def load_main(lab: str | None):
    """app/main.py as the server would load it with RESEARCH_LAB set to `lab`, the environment left as it was."""
    saved_env = dict(os.environ)
    try:
        os.environ.pop("RESEARCH_LAB", None)
        if lab is not None:
            os.environ["RESEARCH_LAB"] = lab
        return importlib.reload(importlib.import_module("app.main"))
    finally:
        os.environ.clear()
        os.environ.update(saved_env)


# --- Off by default

def test_without_the_flag_there_is_no_research_route(monkeypatch):
    monkeypatch.setattr(hq, "build_hq_app", tiny_hq_app)
    main = load_main(None)
    assert not any(getattr(route, "path", "") == "/research" for route in main.app.routes)
    with TestClient(main.app) as client:
        assert client.get("/health").json() == {"status": "ok"}
        assert client.get("/research/status").json() == {"from": "hq"}


def test_any_value_but_enabled_keeps_it_off(monkeypatch):
    monkeypatch.setattr(hq, "build_hq_app", tiny_hq_app)
    main = load_main("on")
    assert not main.RESEARCH_LAB


# --- On

def test_with_the_flag_the_lab_answers_and_hq_is_unchanged(monkeypatch):
    monkeypatch.setattr(hq, "build_hq_app", tiny_hq_app)
    try:
        main = load_main("enabled")
        with TestClient(main.app) as client:
            assert client.get("/health").json() == {"status": "ok"}
            answer = client.get("/research/status", headers={"x-persona": "h-pamuditha"})
            assert answer.status_code == 200 and answer.json()["lab"] == "enabled"
    finally:
        load_main(None)  # the other test files see main.py as the server starts by default


def test_only_the_founder_or_the_research_role_may_open_the_lab():
    client = TestClient(create_research_app(connect=FakeConnection, people=PEOPLE))
    assert client.get("/status").status_code == 401
    assert client.get("/status", headers={"x-persona": "h-nobody"}).json() == {"error": "unknown_persona"}
    assert client.get("/status", headers={"x-persona": "h-steward"}).status_code == 403
    assert client.get("/status", headers={"x-persona": "h-founder"}).json() == {"lab": "enabled", "store": "ready"}
    assert client.get("/status", headers={"x-persona": "h-analyst"}).status_code == 200


def test_a_store_outage_shows_as_unavailable_and_recovers():
    outage = {"down": True}

    def connect():
        if outage["down"]:
            raise psycopg.OperationalError("connection refused")
        return FakeConnection()

    client = TestClient(create_research_app(connect=connect, people=PEOPLE))
    assert client.get("/status", headers={"x-persona": "h-founder"}).json()["store"] == "unavailable"
    outage["down"] = False
    assert client.get("/status", headers={"x-persona": "h-founder"}).json()["store"] == "ready"


# --- Contracts

def test_an_old_snapshot_loads_as_sample_and_serves_in_the_console_shape():
    old = {"paper": "policies", "title": "Freshness", "is_sample": True, "source": "mock", "taken_at": "2026-10-27T00:00:00Z",
           "metrics": [{"key": "stale", "label": "Stale", "definition": "d", "value": 0.1, "unit": "ratio", "condition": "C3", "series": []}]}
    shown = ResearchSnapshot.model_validate(old).ui()
    assert shown["metrics"][0]["provenance"] == "sample"
    assert shown["verdicts"] == []
    assert set(shown) == {"paper", "title", "isSample", "source", "takenAt", "metrics", "verdicts"}  # zod's optional takes no null
    assert "ci" not in shown["metrics"][0]

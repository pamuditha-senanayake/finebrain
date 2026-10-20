# test_main_startup.py: importing app/main.py builds no HQ lane (fastapi dev's reloader parent only imports it to find
# `app`); the lane is built once, when the server starts, and serves every request. Uses: app/main.py.
import importlib
import os

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import hq


def tiny_hq_app() -> FastAPI:
    inner = FastAPI()
    inner.get("/health")(lambda: {"status": "ok"})
    return inner


def test_the_lane_is_built_once_at_start_not_on_import(monkeypatch):
    builds = []
    monkeypatch.setattr(hq, "build_hq_app", lambda: builds.append(1) or tiny_hq_app())
    saved_env = dict(os.environ)
    try:
        main = importlib.import_module("app.main")
    finally:
        os.environ.clear()
        os.environ.update(saved_env)  # main.py reads backend/.env; keep it out of the other tests
    assert builds == []  # what the reloader parent does: import, nothing more
    with TestClient(main.app) as client:
        assert builds == [1]
        assert client.get("/health").json() == {"status": "ok"}
    assert builds == [1]

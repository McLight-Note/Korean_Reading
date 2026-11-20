"""SM-2 scheduling and its stateless API (per-visitor study data lives in the browser / Firestore, never on the server)."""
import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.main import app
from backend.app.services import srs


# ---------------- SM-2 ----------------
def test_srs_progression_is_deterministic():
    s = None
    seq = []
    for g in (2, 2, 2):
        s = srs.schedule(s, g, "2026-01-01")
        seq.append(s["interval"])
    assert seq == [1, 3, 8] and s["due"] == "2026-01-09" and s["reps"] == 3
    assert srs.schedule(None, 2, "2026-01-01") == srs.schedule(None, 2, "2026-01-01")


def test_srs_lapse_and_ease_floor():
    s = srs.schedule(srs.schedule(None, 2, "2026-01-01"), 0, "2026-01-02")
    assert s["interval"] == 0 and s["lapses"] == 1 and s["due"] == "2026-01-02" and s["ease"] == 2.3
    for _ in range(20):
        s = srs.schedule(s, 0, "2026-01-02")
    assert s["ease"] == srs.MIN_EASE
    easy = srs.schedule(srs.schedule(None, 3, "2026-01-01"), 3, "2026-01-04")
    assert easy["interval"] > 3 and easy["ease"] > 2.5
    with pytest.raises(ValueError):
        srs.schedule(None, 5, "2026-01-01")


def test_srs_is_due():
    s = srs.schedule(None, 2, "2026-01-01")
    assert not srs.is_due(s, "2026-01-01") and srs.is_due(s, "2026-01-02")


# ---------------- API ----------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    return TestClient(app)


def test_schedule_api(client):
    r = client.post("/api/study/schedule", json={"state": None, "grade": 2, "today": "2026-02-01"}).json()
    assert r["interval"] == 1 and r["due"] == "2026-02-02"
    assert client.post("/api/study/schedule", json={"grade": 9, "today": "2026-02-01"}).status_code == 422


def test_server_holds_no_study_state_or_exercises(client):
    for method, url in (("get", "/api/study/state"), ("put", "/api/study/state"), ("get", "/api/study/exercises"), ("post", "/api/study/check")):
        assert getattr(client, method)(url).status_code in (404, 405), url


def test_read_only_deployment_allows_the_stateless_schedule_call(tmp_path, monkeypatch):
    path = tmp_path / "ro.sqlite"
    c = db.connect(path); db.init_db(c); c.commit(); c.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "READ_ONLY", True)
    cl = TestClient(app)
    assert cl.post("/api/study/schedule", json={"grade": 2, "today": "2026-02-01"}).status_code == 200
    assert cl.post("/api/vocab", json={"headword": "x"}).status_code == 403

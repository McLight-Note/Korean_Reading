"""API-level flow: manual entries, review/approve, calibration, passage detail panel data."""
import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    return TestClient(app)


def test_review_flow_and_reader_panel(client):
    g = client.post("/api/grammar", json={"pattern": "V+(으)ㄹ 수 있다", "meaning_en": "can", "explanation_original": "Used for ability.",
                                          "level": "3B", "unit": 10, "page": 5, "example": "저는 갈 수 있어요."}).json()
    assert g["compiled"] is True
    # manual entries are 'manual' status = approved by the human who typed them -> VERIFIED
    p = client.post("/api/passages", json={"text": "내일 갈 수 있어요."}).json()
    m = [x for x in p["matches"] if x["layer"] == "grammar" and x["status"] != "NOT_FOUND"][0]
    assert m["status"] == "VERIFIED"
    d = client.get(f"/api/matches/{m['id']}").json()
    assert d["item"]["explanation_original"] == "Used for ability." and d["item"]["examples"][0]["sentence"] == "저는 갈 수 있어요."
    assert "rule_json" not in d["item"]
    # queue + approve + calibration
    client.patch(f"/api/grammar/{g['id']}", json={"status": "needs_review"})
    q = client.get("/api/admin/queue?kind=grammar&status=needs_review").json()
    assert q["total"] == 1
    assert client.post("/api/admin/approve", json={"kind": "grammar", "ids": [g["id"]]}).json()["approved"] == 1
    cal = client.get("/api/admin/calibration").json()
    assert cal["totals"]["examples"] == 1 and cal["totals"]["hits"] == 1
    # rules changed -> stored passage is flagged stale, not silently re-analysed
    assert client.get(f"/api/passages/{p['id']}").json()["stale"] is True


def test_approve_requires_a_selection(client):
    assert client.post("/api/admin/approve", json={"kind": "grammar"}).status_code == 400


def test_merge_moves_examples(client):
    a = client.post("/api/grammar", json={"pattern": "V+고 말다", "example": "울고 말았어요."}).json()["id"]
    b = client.post("/api/grammar", json={"pattern": "V+고 있다", "meaning_uz": "x"}).json()["id"]
    assert client.post("/api/admin/grammar/merge", json={"from_id": a, "into_id": b}).status_code == 200
    assert client.get(f"/api/grammar/{b}").json()["examples"][0]["sentence"] == "울고 말았어요."
    assert client.get(f"/api/grammar/{a}").status_code == 404

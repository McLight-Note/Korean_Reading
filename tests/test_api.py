"""API-level flow: manual entries, review/approve, merge, workbook."""
import pytest
from fastapi.testclient import TestClient

from backend.app import config
from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    return TestClient(app)


def test_review_flow(client):
    g = client.post("/api/grammar", json={"pattern": "V+(으)ㄹ 수 있다", "meaning_en": "can", "explanation_original": "Used for ability.",
                                          "level": "3B", "unit": 10, "page": 5, "example": "저는 갈 수 있어요."}).json()
    d = client.get(f"/api/grammar/{g['id']}").json()
    assert d["explanation_original"] == "Used for ability." and d["examples"][0]["sentence"] == "저는 갈 수 있어요."
    assert "rule_json" not in d and "meaning_uz" not in d
    client.patch(f"/api/grammar/{g['id']}", json={"status": "needs_review"})
    q = client.get("/api/admin/queue?kind=grammar&status=needs_review").json()
    assert q["total"] == 1
    assert client.post("/api/admin/approve", json={"kind": "grammar", "ids": [g["id"]]}).json()["approved"] == 1
    assert client.get("/api/admin/queue?kind=grammar&status=needs_review").json()["total"] == 0


def test_approve_requires_a_selection(client):
    assert client.post("/api/admin/approve", json={"kind": "grammar"}).status_code == 400


def test_merge_moves_examples(client):
    a = client.post("/api/grammar", json={"pattern": "V+고 말다", "example": "울고 말았어요."}).json()["id"]
    b = client.post("/api/grammar", json={"pattern": "V+고 있다", "meaning_en": "x"}).json()["id"]
    assert client.post("/api/admin/grammar/merge", json={"from_id": a, "into_id": b}).status_code == 200
    assert client.get(f"/api/grammar/{b}").json()["examples"][0]["sentence"] == "울고 말았어요."
    assert client.get(f"/api/grammar/{a}").status_code == 404


def test_workbook_endpoints_and_grammar_link(client):
    from backend.app import db
    conn = db.connect()
    db.init_db(conn)
    gid = conn.execute("INSERT INTO grammar_item(pattern, level, status) VALUES ('V+고 말다','3B','verified')").lastrowid
    conn.execute("INSERT INTO workbook_item(level, section, grammar_id, heading, exercise_no, instruction, body, pdf_page) VALUES ('3B','grammar',?,'V-고 말다','1','완성하세요.','1) 울고 ( )',22)", (gid,))
    conn.execute("INSERT INTO workbook_item(level, section, heading, instruction, body, pdf_page) VALUES ('3B','script',NULL,'Listening script','남 : 안녕하세요.',196)")
    conn.commit(); conn.close()
    r = client.get("/api/workbook?level=3B&section=grammar").json()
    assert r["total"] == 1 and r["items"][0]["grammar_pattern"] == "V+고 말다"
    assert client.get("/api/workbook?q=안녕").json()["total"] == 1
    assert client.get("/api/workbook?grammar_id=%d" % gid).json()["total"] == 1
    g = client.get(f"/api/grammar/{gid}").json()
    assert g["workbook"][0]["instruction"] == "완성하세요."
    assert client.get("/api/overview").json()["workbook_items"] == 2

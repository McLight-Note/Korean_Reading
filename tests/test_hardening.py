"""Regressions for bugs found in the expert review / audit. Each test fails on the old behaviour."""
import json
import random

import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.ingest import import_student_book as isb
from backend.app.ingest import import_workbook as iw
from backend.app.main import app
from backend.app.services import exercises, sentence_analyzer as sa


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "h.sqlite")
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "c.sqlite")
    db.init_db(c)
    yield c
    c.close()


# ---- paging: a negative limit must not mean "unlimited" ----
def test_negative_limit_cannot_dump_the_table(client):
    c = db.connect(); db.init_db(c)
    for i in range(130):
        c.execute("INSERT INTO workbook_item(level, section, instruction, body, pdf_page) VALUES ('3B','grammar',?,?,?)", (f"i{i}", "b", i))
        c.execute("INSERT INTO vocab_entry(headword, meaning_uz, level, unit) VALUES (?,?,?,?)", (f"w{i}", "x", "1A", 1))
    for i in range(230):
        c.execute("INSERT INTO vocab_entry(headword, level, unit) VALUES (?,?,?)", (f"v{i}", "1A", 1))
    c.commit(); c.close()
    assert len(client.get("/api/workbook?limit=-1").json()["items"]) == 1
    assert len(client.get("/api/workbook?limit=100000").json()["items"]) == 100
    assert len(client.get("/api/vocab?limit=-1").json()["items"]) == 1
    assert len(client.get("/api/vocab?limit=100000").json()["items"]) == 200
    assert client.get("/api/vocab?limit=5&offset=-3").status_code == 200


# ---- invalid enum-like input is a clean 422, never a database-constraint 500 ----
def test_bad_enum_values_are_rejected_cleanly(client):
    vid = client.post("/api/vocab", json={"headword": "사과"}).json()["id"]
    gid = client.post("/api/grammar", json={"pattern": "V+고 말다"}).json()["id"]
    assert client.patch(f"/api/vocab/{vid}", json={"status": "bogus"}).status_code == 422
    assert client.patch(f"/api/grammar/{gid}", json={"status": "bogus"}).status_code == 422
    assert client.post("/api/saved", json={"kind": "x", "ref_id": 1}).status_code == 422
    assert client.post("/api/admin/approve", json={"kind": "x", "ids": [1]}).status_code == 422
    assert client.patch("/api/matches/1", json={"match_type": "WRONG"}).status_code == 422
    assert client.patch(f"/api/vocab/{vid}", json={"status": "verified"}).status_code == 200


# ---- SM-2 endpoint tolerates a partial state and rejects nonsense with 4xx ----
def test_schedule_endpoint_validates_state(client):
    ok = client.post("/api/study/schedule", json={"state": {"ease": 2.5}, "grade": 2, "today": "2026-01-01"})
    assert ok.status_code == 200 and ok.json()["interval"] == 1
    for bad in ({"state": {"ease": "abc"}}, {"state": {"interval": -4}}, {"state": {"ease": 99}}):
        assert client.post("/api/study/schedule", json={**bad, "grade": 2, "today": "2026-01-01"}).status_code == 422
    assert client.post("/api/study/schedule", json={"grade": 2, "today": "not-a-date"}).status_code == 400


# ---- vocabulary exercises: few distinct meanings must not crash ----
def test_vocab_mcq_with_too_few_distinct_meanings_returns_nothing(conn):
    for hw in ("가", "나", "다", "라", "마"):
        conn.execute("INSERT INTO vocab_entry(headword, meaning_uz, level, unit, status) VALUES (?,?,?,?,?)", (hw, "same gloss", "1A", 1, "verified"))
    conn.execute("INSERT INTO vocab_entry(headword, meaning_uz, level, unit, status) VALUES ('바','other gloss','1A',1,'verified')")
    assert exercises.vocab_mcq(conn, "1A", 5, random.Random(1)) == []          # used to raise ValueError -> 500


# ---- offsets: JavaScript slices UTF-16, Python slices code points ----
def test_offsets_are_utf16_so_emoji_do_not_shift_highlights(conn):
    text = "😀 저는 어제 영화를 봤어요. 😀😀 비가 와요."
    pid = sa.create_passage(conn, None, text)
    a = sa.load_analysis(conn, pid)
    u16 = a["text"].encode("utf-16-le")
    assert a["matches"]
    for m in a["matches"]:
        assert u16[2 * m["start"]:2 * m["end"]].decode("utf-16-le") == m["surface"]      # exactly what JS .slice(start, end) returns
    for s in a["sentences"]:
        assert u16[2 * s["start"]:2 * s["end"]].decode("utf-16-le").strip()
    eph = sa.analyze_ephemeral(conn, None, text)
    eu = eph["text"].encode("utf-16-le")
    for m in eph["matches"]:
        assert eu[2 * m["start"]:2 * m["end"]].decode("utf-16-le") == m["surface"]


# ---- importers must not record an empty import ----
def test_importers_refuse_missing_or_empty_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "i.sqlite")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for mod in (iw, isb):
        with pytest.raises(SystemExit):
            mod.main(["Z9 WB.pdf"])
    empty = tmp_path / "ocr" / "Z9_WB"
    empty.mkdir(parents=True)
    with pytest.raises(SystemExit):
        iw.main(["Z9 WB.pdf"])
    c = db.connect(); db.init_db(c)
    assert c.execute("SELECT COUNT(*) FROM source").fetchone()[0] == 0          # nothing recorded, so a re-run is not blocked
    c.close()


# ---- read-only deployment without its database fails with a clear message ----
def test_read_only_without_database_is_a_clear_error(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "READ_ONLY", True)
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "missing.sqlite")
    with pytest.raises(RuntimeError, match="build_deploy_db"):
        db.connect()


# ---- deploy DB builder: works on an OLD database and never ships personal data ----
def test_build_deploy_db_upgrades_old_schema_and_strips_personal_data(tmp_path):
    import importlib.util
    import sqlite3
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("build_deploy_db", Path(config.ROOT) / "scripts" / "build_deploy_db.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    src = tmp_path / "old.sqlite"
    c = sqlite3.connect(src)                      # an "old" DB: only the early tables, no workbook_item / study_state
    c.executescript("""
        CREATE TABLE vocab_entry(id INTEGER PRIMARY KEY, headword TEXT, meaning_uz TEXT, status TEXT DEFAULT 'verified');
        CREATE TABLE vocab_key(entry_id INTEGER, key TEXT);
        CREATE TABLE grammar_item(id INTEGER PRIMARY KEY, pattern TEXT, level TEXT, status TEXT DEFAULT 'needs_review');
        CREATE TABLE grammar_example(id INTEGER PRIMARY KEY, grammar_id INTEGER, sentence TEXT, source_ref TEXT);
        CREATE TABLE passage(id INTEGER PRIMARY KEY, text_norm TEXT);
        CREATE TABLE saved_item(id INTEGER PRIMARY KEY, kind TEXT, ref_id INTEGER);
        INSERT INTO vocab_entry(headword, meaning_uz) VALUES ('사과','olma');
        INSERT INTO passage(text_norm) VALUES ('my private passage');
        INSERT INTO saved_item(kind, ref_id) VALUES ('vocab', 1);
    """)
    c.commit(); c.close()

    counts = mod.build(src, tmp_path / "out" / "deploy.sqlite")
    assert counts["vocab_entry"] == 1 and counts["workbook_item"] == 0
    out = sqlite3.connect(tmp_path / "out" / "deploy.sqlite")
    assert out.execute("SELECT COUNT(*) FROM passage").fetchone()[0] == 0
    assert out.execute("SELECT COUNT(*) FROM saved_item").fetchone()[0] == 0
    assert out.execute("SELECT COUNT(*) FROM study_state").fetchone()[0] == 0          # table exists (was added) and is empty
    assert not (tmp_path / "out" / "deploy.tmp").exists()
    with pytest.raises(FileNotFoundError):
        mod.build(tmp_path / "nope.sqlite", tmp_path / "x.sqlite")

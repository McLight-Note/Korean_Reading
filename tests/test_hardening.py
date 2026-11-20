"""Regressions for bugs found in review (paging limits, input validation, importer guards, deploy builder) plus the
removal of the Uzbek glosses. Each test fails on the old behaviour."""
import importlib.util
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.ingest import import_student_book as isb
from backend.app.ingest import import_workbook as iw
from backend.app.main import app


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "h.sqlite")
    return TestClient(app, raise_server_exceptions=False)


def load_script(name):
    spec = importlib.util.spec_from_file_location(name, Path(config.ROOT) / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ---- paging: a negative limit must not mean "unlimited" ----
def test_negative_limit_cannot_dump_the_table(client):
    c = db.connect(); db.init_db(c)
    for i in range(130):
        c.execute("INSERT INTO workbook_item(level, section, instruction, body, pdf_page) VALUES ('3B','grammar',?,?,?)", (f"i{i}", "b", i))
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
    assert client.post("/api/admin/approve", json={"kind": "x", "ids": [1]}).status_code == 422
    assert client.patch(f"/api/vocab/{vid}", json={"status": "verified"}).status_code == 200


# ---- SM-2 endpoint tolerates a partial state and rejects nonsense with 4xx ----
def test_schedule_endpoint_validates_state(client):
    ok = client.post("/api/study/schedule", json={"state": {"ease": 2.5}, "grade": 2, "today": "2026-01-01"})
    assert ok.status_code == 200 and ok.json()["interval"] == 1
    for bad in ({"state": {"ease": "abc"}}, {"state": {"interval": -4}}, {"state": {"ease": 99}}):
        assert client.post("/api/study/schedule", json={**bad, "grade": 2, "today": "2026-01-01"}).status_code == 422
    assert client.post("/api/study/schedule", json={"grade": 2, "today": "not-a-date"}).status_code == 400


# ---- importers must not record an empty import ----
def test_importers_refuse_missing_or_empty_ocr(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "i.sqlite")
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    for mod in (iw, isb):
        with pytest.raises(SystemExit):
            mod.main(["Z9 WB.pdf"])
    (tmp_path / "ocr" / "Z9_WB").mkdir(parents=True)
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


# ---- the Uzbek glosses are gone from every public response ----
def test_api_never_serves_uzbek_fields(client):
    c = db.connect(); db.init_db(c)
    c.execute("INSERT INTO vocab_entry(headword, meaning_uz, raw_text, pos, level, unit) VALUES ('차','mashina','차 mashina','noun','1A',1)")
    c.execute("INSERT INTO grammar_item(pattern, meaning_uz, raw_text, rule_json, level) VALUES ('V+고 있다','ayotgan','x','{}','3B')")
    c.commit(); c.close()
    for url in ("/api/vocab", "/api/vocab/1", "/api/grammar", "/api/grammar/1", "/api/admin/vocab/1", "/api/admin/grammar/1"):
        body = json.dumps(client.get(url).json(), ensure_ascii=False)
        assert "mashina" not in body and "ayotgan" not in body and "meaning_uz" not in body and "rule_json" not in body, url


def test_importers_do_not_store_glosses(tmp_path):
    from backend.app.ingest import import_glossary
    from backend.app.ingest.glossary_parser import Entry
    conn = db.connect(tmp_path / "g.sqlite"); db.init_db(conn)
    sid = conn.execute("INSERT INTO source(filename, kind) VALUES ('g.pdf','glossary')").lastrowid
    import_glossary.import_entries(conn, [Entry("차", "mashina", "1A", 1, None, 5, 3, ["차 mashina"])], sid)
    row = conn.execute("SELECT * FROM vocab_entry").fetchone()
    assert row["headword"] == "차" and row["level"] == "1A" and row["meaning_uz"] is None and row["raw_text"] is None


# ---- deploy DB builder: works on an OLD database, strips glosses and personal tables ----
def test_build_deploy_db_scrubs_uzbek_and_legacy_tables(tmp_path):
    mod = load_script("build_deploy_db")
    src = tmp_path / "old.sqlite"
    c = sqlite3.connect(src)
    c.executescript("""
        CREATE TABLE vocab_entry(id INTEGER PRIMARY KEY, headword TEXT, meaning_uz TEXT, raw_text TEXT, pos TEXT, level TEXT, status TEXT DEFAULT 'verified');
        CREATE TABLE vocab_key(entry_id INTEGER, key TEXT);
        CREATE TABLE grammar_item(id INTEGER PRIMARY KEY, pattern TEXT, meaning_uz TEXT, raw_text TEXT, rule_json TEXT, level TEXT, status TEXT DEFAULT 'needs_review');
        CREATE TABLE grammar_example(id INTEGER PRIMARY KEY, grammar_id INTEGER, sentence TEXT, source_ref TEXT);
        CREATE TABLE passage(id INTEGER PRIMARY KEY, text_norm TEXT);
        CREATE TABLE saved_item(id INTEGER PRIMARY KEY, kind TEXT, ref_id INTEGER);
        INSERT INTO vocab_entry(headword, meaning_uz, raw_text, pos, level) VALUES ('사과','olma','사과 olma','noun','1A');
        INSERT INTO grammar_item(pattern, meaning_uz, raw_text, rule_json, level) VALUES ('V+지만','ekin','x','{}','3A');
        INSERT INTO passage(text_norm) VALUES ('private passage');
    """)
    c.commit(); c.close()
    counts = mod.build(src, tmp_path / "out" / "deploy.sqlite")
    assert counts["vocab_entry"] == 1 and counts["grammar_item"] == 1
    out = sqlite3.connect(tmp_path / "out" / "deploy.sqlite")
    dumped = "\n".join(out.iterdump())
    for leaked in ("olma", "ekin", "private passage"):
        assert leaked not in dumped
    tables = {r[0] for r in out.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert not ({"passage", "saved_item", "vocab_key"} & tables)
    assert not (tmp_path / "out" / "deploy.tmp").exists()
    with pytest.raises(FileNotFoundError):
        mod.build(tmp_path / "nope.sqlite", tmp_path / "x.sqlite")


def test_deploy_db_keeps_workbook_by_default_and_can_drop_it(tmp_path):
    mod = load_script("build_deploy_db")
    src = tmp_path / "s.sqlite"
    c = db.connect(src); db.init_db(c)
    c.execute("INSERT INTO workbook_item(level, section, instruction, body, pdf_page) VALUES ('3B','grammar','i','b',1)")
    c.commit(); c.close()
    assert mod.build(src, tmp_path / "a.sqlite")["workbook_item"] == 1
    assert mod.build(src, tmp_path / "b.sqlite", include_workbook=False)["workbook_item"] == 0


def test_drop_uzbek_maintenance_backs_up_and_clears(tmp_path):
    mod = load_script("maintenance")
    path = tmp_path / "app.sqlite"
    c = db.connect(path); db.init_db(c)
    sid = c.execute("INSERT INTO source(filename, kind) VALUES ('g.pdf','glossary')").lastrowid
    c.execute("INSERT INTO vocab_entry(headword, meaning_uz, raw_text, level) VALUES ('차','mashina','차 mashina','1A')")
    c.execute("INSERT INTO ocr_page(source_id, pdf_page, text, lines_json) VALUES (?,?,?,?)", (sid, 1, "차 mashina", "[]"))
    c.commit(); c.close()
    r = mod.drop_uzbek(path)
    assert r["remaining"] == {"vocab_with_uzbek": 0, "grammar_with_uzbek": 0}
    assert (tmp_path / "app.sqlite.before-uzbek-removal").exists()                 # nothing is lost
    out = sqlite3.connect(path)
    assert out.execute("SELECT headword FROM vocab_entry").fetchone()[0] == "차"
    assert out.execute("SELECT text FROM ocr_page").fetchone()[0] is None

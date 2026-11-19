"""SM-2 scheduling, generated exercises (built only from stored textbook records), answer checking, state API, RO rules."""
import json
import random

import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.main import app
from backend.app.services import exercises, srs
from backend.app.services.pattern_compiler import compile_pattern, pattern_key
from backend.app.services.korean_analyzer import headword_lemma_keys


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


# ---------------- exercises ----------------
@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    db.init_db(c)
    yield c
    c.close()


def add_grammar(conn, pattern, examples=(), level="3B", status="verified"):
    gid = conn.execute("INSERT INTO grammar_item(pattern, pattern_key, rule_json, level, status, unit, page) VALUES (?,?,?,?,?,?,?)",
                       (pattern, pattern_key(pattern), json.dumps(compile_pattern(pattern)), level, status, 10, 26)).lastrowid
    for e in examples:
        conn.execute("INSERT INTO grammar_example(grammar_id, sentence, source_ref) VALUES (?,?,?)", (gid, e, "test ref"))
    return gid


def seed_grammar(conn):
    ids = {
        "can": add_grammar(conn, "V+(으)ㄹ 수 있다", ["저는 한국어를 할 수 있어요."]),
        "jana": add_grammar(conn, "A/V+잖아(요)", ["비가 오잖아요."]),
        "deon": add_grammar(conn, "A/V+던", ["어제 먹던 커피가 없어요."]),
        "ji": add_grammar(conn, "V+지만", ["가고 싶지만 시간이 없어요."]),
        "go": add_grammar(conn, "V+고 있다", ["지금 공부하고 있어요."]),
    }
    return ids


def test_grammar_mcq_blanks_the_grammar_and_distractors_dont_fit(conn):
    ids = seed_grammar(conn)
    items = exercises.grammar_mcq(conn, "3B", 5, random.Random(3))
    assert len(items) == 5
    for e in items:
        assert e["prompt"].count(exercises.BLANK) == 1
        assert e["blanked"] and e["blanked"] not in e["prompt"]
        assert e["prompt"].replace(exercises.BLANK, e["blanked"]) == e["full_sentence"]       # blank + answer span rebuild the sentence
        assert len(e["choices"]) == 4 and e["answer_id"] in {c["id"] for c in e["choices"]}
        assert e["label"].startswith("Generated")
        assert e["source"]["example_ref"] == "test ref" and e["source"]["level"] == "3B"
        for c in e["choices"]:                                                                   # no other choice may also fit the sentence
            if c["id"] != e["answer_id"]:
                assert exercises.check_answer(conn, c["id"], e["full_sentence"])["target_found"] is False


def test_grammar_mcq_skips_examples_that_leak_the_answer(conn):
    add_grammar(conn, "A/V+잖아(요)", ["비가 오잖아요. 우산 가져가요, 비가 오잖아요."])     # target occurs twice -> unusable
    for p in ("V+(으)ㄹ 수 있다", "V+지만", "V+고 있다", "A/V+던"):
        add_grammar(conn, p, [])
    assert exercises.grammar_mcq(conn, "3B", 5, random.Random(1)) == []


def test_grammar_mcq_can_exclude_unreviewed(conn):
    seed_grammar(conn)
    conn.execute("UPDATE grammar_item SET status='needs_review'")
    assert exercises.grammar_mcq(conn, "3B", 5, random.Random(1), include_unreviewed=False) == []
    assert exercises.grammar_mcq(conn, "3B", 5, random.Random(1), include_unreviewed=True)


def add_vocab(conn, headword, uz, level="1A", status="verified"):
    cur = conn.execute("INSERT INTO vocab_entry(headword, meaning_uz, level, unit, status) VALUES (?,?,?,?,?)", (headword, uz, level, 1, status))
    for k in headword_lemma_keys(headword):
        conn.execute("INSERT INTO vocab_key(entry_id,key) VALUES (?,?)", (cur.lastrowid, k))


def test_vocab_mcq_both_directions(conn):
    for hw, uz in [("사과", "olma"), ("물", "suv"), ("책", "kitob"), ("집", "uy"), ("차", "choy"), ("밥", "guruch")]:
        add_vocab(conn, hw, uz)
    add_vocab(conn, "문제", "savol", status="needs_review")                       # unreviewed glossary rows are never used
    fwd = exercises.vocab_mcq(conn, "1A", 6, random.Random(1))
    assert len(fwd) == 6
    for e in fwd:
        texts = [c["text"] for c in e["choices"]]
        assert len(set(texts)) == 4 and e["meaning_uz"] in texts and "savol" not in texts
        assert next(c for c in e["choices"] if c["id"] == e["answer_id"])["text"] == e["meaning_uz"]
    rev = exercises.vocab_mcq(conn, "1A", 3, random.Random(1), reverse=True)
    assert all(e["type"] == "vocab_rev" and e["prompt_lang"] == "uz" for e in rev)
    assert exercises.vocab_mcq(conn, "2B", 3, random.Random(1)) == []             # not enough material: no exercise rather than a bad one


def test_check_answer_only_judges_the_target_grammar(conn):
    ids = seed_grammar(conn)
    ok = exercises.check_answer(conn, ids["jana"], "밖에 비가 많이 오잖아요.")
    assert ok["target_found"] is True and ok["detected"][0]["is_target"]
    no = exercises.check_answer(conn, ids["jana"], "밖에 비가 많이 와요.")
    assert no["target_found"] is False
    assert exercises.check_answer(conn, 9999, "x") == {"error": "unknown grammar item"}
    conn.execute("UPDATE grammar_item SET rule_json=NULL WHERE id=?", (ids["jana"],))
    assert exercises.check_answer(conn, ids["jana"], "오잖아요")["checkable"] is False      # no rule -> says so, doesn't guess


# ---------------- API ----------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    return TestClient(app)


def test_study_api_flow(client):
    r = client.post("/api/study/schedule", json={"state": None, "grade": 2, "today": "2026-02-01"}).json()
    assert r["interval"] == 1 and r["due"] == "2026-02-02"
    assert client.post("/api/study/schedule", json={"grade": 9, "today": "2026-02-01"}).status_code == 422
    assert client.get("/api/study/state").json() == {}
    state = {"cards": {"vocab:1": r}, "log": [{"t": "2026-02-01", "kind": "vocab", "id": 1, "grade": 2}]}
    assert client.put("/api/study/state", json={"state": state}).status_code == 200
    assert client.get("/api/study/state").json() == state
    assert client.get("/api/study/exercises?type=bogus").status_code == 400
    assert client.get("/api/study/exercises?type=vocab_mcq&level=1A").json()["count"] == 0        # empty DB: no invented items


def test_read_only_deployment_allows_only_stateless_study_calls(tmp_path, monkeypatch):
    path = tmp_path / "ro.sqlite"
    c = db.connect(path); db.init_db(c); c.commit(); c.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "READ_ONLY", True)
    cl = TestClient(app)
    assert cl.post("/api/study/schedule", json={"grade": 2, "today": "2026-02-01"}).status_code == 200
    assert cl.post("/api/study/check", json={"grammar_id": 1, "text": "x"}).status_code == 200
    assert cl.get("/api/study/exercises?type=vocab_mcq").status_code == 200
    assert cl.put("/api/study/state", json={"state": {}}).status_code == 403
    assert cl.get("/api/study/state").status_code == 404

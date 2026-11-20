"""Approximate vocabulary lookup for pasted text (plain rules, no morphology)."""
import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.main import app
from backend.app.services import lookup


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    db.init_db(c)
    for hw, lvl in [("영화", "1A"), ("먹다", "1A"), ("공부하다", "1A"), ("예쁘다", "1A"), ("(동아리에)가입하다", "2A"), ("책", "1A"), ("숙제를 하다", "1B"), ("가", "1A")]:
        c.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES (?,?,?,?)", (hw, lvl, 1, "verified"))
    c.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES ('영화','4B',9,'verified')")      # duplicate at a later level
    yield c
    c.close()


def m(conn, token):
    r = lookup.lookup(conn, [token])
    return r.get(token)


def test_nouns_alone_and_with_particles(conn):
    assert m(conn, "영화")["match"] == "exact"
    assert m(conn, "영화를")["headword"] == "영화" and m(conn, "영화를")["match"] == "noun"
    assert m(conn, "책이")["headword"] == "책"                    # one-syllable noun + common particle
    assert m(conn, "영화관") is None                              # not a particle: no false positive


def test_regular_verb_and_adjective_stems(conn):
    assert m(conn, "먹었습니다")["headword"] == "먹다"
    assert m(conn, "먹고")["match"] == "stem"
    assert m(conn, "예쁘다")["headword"] == "예쁘다"
    assert m(conn, "가입할")["headword"] == "(동아리에)가입하다"     # bracketed part ignored
    assert m(conn, "공부했어요")["headword"] == "공부하다"          # 공부 + 했어요


def test_one_syllable_stems_need_an_ending_so_nouns_arent_swallowed(conn):
    assert m(conn, "먹거리") is None                              # 먹 + 거리 is not 먹다
    assert m(conn, "가방") is None


def test_irregular_forms_are_not_recognised_and_phrases_are_skipped(conn):
    assert m(conn, "봤어요") is None
    assert m(conn, "숙제를") is None                              # multi-word headwords cannot be matched per token


def test_earliest_level_wins_and_punctuation_is_ignored(conn):
    r = m(conn, "영화,")
    assert r["level"] == "1A"
    assert m(conn, "English") is None and m(conn, "123") is None


def test_endpoint_and_limits(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    c = db.connect(); db.init_db(c)
    c.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES ('영화','1A',1,'verified')"); c.commit(); c.close()
    cl = TestClient(app, raise_server_exceptions=False)
    r = cl.post("/api/vocab/lookup", json={"tokens": ["영화를", "없는말"]}).json()
    assert r["approximate"] is True and list(r["matches"]) == ["영화를"]
    assert cl.post("/api/vocab/lookup", json={"tokens": ["가"] * 1501}).status_code == 422
    monkeypatch.setattr(config, "READ_ONLY", True)                  # stateless POST stays allowed on the public deployment
    assert cl.post("/api/vocab/lookup", json={"tokens": ["영화"]}).status_code == 200

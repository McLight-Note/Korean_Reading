"""Reading stories: inline-markup parsing, the checker, the API, and (when the textbook DB exists) the real stories."""
import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app import config, db
from backend.app.main import app
from backend.app.services import stories
from backend.app.services.common import LEVEL_ORDER

STORY_FILES = sorted(stories.CONTENT_DIR.glob("*.json"))


# ---------------- markup ----------------
def test_parse_markup_gives_plain_text_and_spans():
    plain, hl = stories.parse_markup("저는 [[영화를|영화]] <<봤어요|V+았어요>>. 끝")
    assert plain == "저는 영화를 봤어요. 끝"
    assert [(h["kind"], h["ref"], plain[h["start"]:h["end"]]) for h in hl] == [("vocab", "영화", "영화를"), ("grammar", "V+았어요", "봤어요")]


def test_parse_markup_offsets_are_utf16_like_javascript():
    plain, hl = stories.parse_markup("😀 [[영화|영화]]")
    units = plain.encode("utf-16-le")
    assert units[2 * hl[0]["start"]:2 * hl[0]["end"]].decode("utf-16-le") == "영화"       # what JS .slice(start, end) returns


def test_text_without_marks_is_unchanged():
    assert stories.parse_markup("그냥 글입니다.") == ("그냥 글입니다.", [])


# ---------------- the files ----------------
def test_there_are_fifteen_stories_across_the_levels():
    levels = [s["level"] for s in stories.load_all()]
    assert len(levels) == 15
    assert {l: levels.count(l) for l in set(levels)} == {"3A": 3, "3B": 4, "4A": 4, "4B": 4}


@pytest.mark.parametrize("path", STORY_FILES, ids=lambda p: p.stem)
def test_story_file_is_well_formed(path):
    raw = json.loads(path.read_text(encoding="utf-8"))
    s = next(x for x in stories.load_all() if x["id"] == raw["id"])
    assert s["id"] == path.stem and s["level"] in LEVEL_ORDER
    assert 3 <= len(s["questions"]) and all(q["q"].strip() and q["a"].strip() for q in s["questions"])
    assert len(s["text"]) >= 400 and s["title"].strip() and len(s["summary_en"]) > 40
    assert len(s["target_grammar"]) >= 5 and len(s["target_vocab"]) >= 10
    assert s["text"].count("\n\n") >= 2
    assert all(tok not in s["text"] for tok in ("[[", "]]", "<<", ">>"))            # all markup was parsed away
    spans = sorted((h["start"], h["end"]) for h in s["highlights"])
    assert all(b[0] >= a[1] for a, b in zip(spans, spans[1:])), "marks overlap"
    assert all(text_slice.strip() == text_slice for text_slice in (s["text"][h["start"]:h["end"]] for h in s["highlights"]))   # no stray spaces inside marks


def test_story_ids_are_unique_and_sorted_by_level():
    ids = [s["id"] for s in stories.load_all()]
    assert len(ids) == len(set(ids))
    order = [LEVEL_ORDER[s["level"]] for s in stories.load_all()]
    assert order == sorted(order)


# ---------------- the checker (no NLP) on a small synthetic database ----------------
@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    db.init_db(c)
    yield c
    c.close()


def make_story(text, tv, tg):
    plain, hl = stories.parse_markup(text)
    return {"id": "x", "level": "3A", "title": "t", "text": plain, "highlights": hl, "target_vocab": tv, "target_grammar": tg, "questions": [], "summary_en": ""}


def test_checker_reports_unmarked_undeclared_and_unresolved_targets(conn):
    for hw in ("동아리", "(동아리에)가입하다"):
        conn.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES (?,?,?,?)", (hw, "3A", 1, "verified"))
    conn.execute("INSERT INTO grammar_item(pattern, level, status) VALUES ('V+지만','3A','verified')")
    ok = stories.check(conn, make_story("[[동아리|동아리]]에 [[가입하고|가입하다]] <<싶지만|V+지만>> 늦었어요.", ["동아리", "가입하다"], ["V+지만"]))
    assert ok["problems"] == [] and ok["marks"] == 3
    bad = stories.check(conn, make_story("[[동아리|동아리]] [[낯선|없는단어]] 글", ["동아리", "가입하다", "장학금"], ["V+지만", "V+없는 패턴"]))
    msg = " | ".join(bad["problems"])
    assert "vocab target is never marked in the text: 가입하다" in msg
    assert "grammar target is never marked in the text: V+지만" in msg
    assert "vocab mark refers to an undeclared target: 없는단어" in msg
    assert "vocab target not in glossary: 장학금" in msg
    assert "grammar target not in database: V+없는 패턴" in msg


def test_resolution_prefers_the_story_level_and_ignores_parentheses(conn):
    conn.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES ('(장학금을)신청하다','1A',1,'verified')")
    conn.execute("INSERT INTO vocab_entry(headword, level, unit, status) VALUES ('(장학금을)신청하다','3A',2,'verified')")
    e = stories.resolve_vocab(conn, "3A", "신청하다")
    assert e["level"] == "3A" and e["unit"] == 2
    assert stories.resolve_vocab(conn, "3A", "없는말") is None


# ---------------- API ----------------
@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DB_PATH", tmp_path / "api.sqlite")
    return TestClient(app, raise_server_exceptions=False)


def test_stories_api_list_and_detail(client):
    r = client.get("/api/stories").json()["stories"]
    assert len(r) == 15 and {"id", "level", "title", "theme", "chars", "n_grammar", "n_vocab", "summary_en"} <= set(r[0])
    d = client.get(f"/api/stories/{r[0]['id']}").json()
    assert d["text"] and d["questions"] and d["highlights"] and len(d["target_vocab"]) == r[0]["n_vocab"]
    assert all(t["entry"] is None for t in d["target_vocab"])                  # empty DB: targets honestly unresolved
    assert client.get("/api/stories/nope").status_code == 404
    assert "meaning_uz" not in json.dumps(d)


def test_stories_are_available_on_the_read_only_deployment(tmp_path, monkeypatch):
    path = tmp_path / "ro.sqlite"
    c = db.connect(path); db.init_db(c); c.commit(); c.close()
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(config, "READ_ONLY", True)
    cl = TestClient(app)
    assert cl.get("/api/stories").status_code == 200
    assert cl.get("/api/stories/3a-01-club").status_code == 200


# ---------------- the real stories against the real textbook database (skipped where it is not present) ----------------
REAL_DB = Path(config.ROOT) / "data" / "app.sqlite"


@pytest.mark.skipif(not REAL_DB.exists(), reason="needs the imported textbook database (data/app.sqlite)")
@pytest.mark.parametrize("story", stories.load_all(), ids=lambda s: s["id"])
def test_every_story_target_exists_and_is_marked(story):
    c = sqlite3.connect(f"file:{REAL_DB}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        r = stories.check(c, story)
    finally:
        c.close()
    assert r["problems"] == [], r["problems"]

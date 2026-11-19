"""Core behaviour: Kiwi-based dictionary forms, grammar matching, honest statuses, offsets, caching."""
import sqlite3

import pytest

from backend.app import config, db
from backend.app.services import grammar_matcher as gm
from backend.app.services import sentence_analyzer as sa
from backend.app.services.korean_analyzer import analyze_text, headword_lemma_keys
from backend.app.services.pattern_compiler import compile_pattern, pattern_key


@pytest.fixture()
def conn(tmp_path):
    c = db.connect(tmp_path / "t.sqlite")
    db.init_db(c)
    yield c
    c.close()


def add_vocab(conn, headword, uz="x", status="verified"):
    cur = conn.execute("INSERT INTO vocab_entry(headword, meaning_uz, level, unit, status) VALUES (?,?,?,?,?)", (headword, uz, "1A", 1, status))
    for k in headword_lemma_keys(headword):
        conn.execute("INSERT INTO vocab_key(entry_id,key) VALUES (?,?)", (cur.lastrowid, k))
    return cur.lastrowid


def add_grammar(conn, pattern, status="verified"):
    rule = compile_pattern(pattern)
    import json
    return conn.execute("INSERT INTO grammar_item(pattern, pattern_key, rule_json, status) VALUES (?,?,?,?)",
                        (pattern, pattern_key(pattern), json.dumps(rule), status)).lastrowid


def analyse(conn, text):
    pid = sa.create_passage(conn, None, text)
    return sa.load_analysis(conn, pid)


@pytest.mark.parametrize("surface,lemma", [("먹었습니다", "먹다"), ("갔어요", "가다"), ("예뻤습니다", "예쁘다"), ("공부하고", "공부하다")])
def test_dictionary_forms(surface, lemma):
    text, sents = analyze_text(surface)
    u = sents[0].units[0]
    assert u.lemma == lemma
    assert text[u.start:u.end] == surface            # original surface + exact positions preserved


@pytest.mark.parametrize("sentence,span", [("저는 한국어를 할 수 있어요.", "할 수 있어요"), ("밥을 먹을 수 있다.", "먹을 수 있다"), ("내일 갈 수 있어요", "갈 수 있어요")])
def test_morphological_grammar_match_not_substring(conn, sentence, span):
    add_grammar(conn, "V+(으)ㄹ 수 있다")
    a = analyse(conn, sentence)
    g = [m for m in a["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"]
    assert [m["surface"] for m in g] == [span]
    assert g[0]["status"] == "VERIFIED" and g[0]["match_type"] == "EXACT"
    assert a["text"][g[0]["start"]:g[0]["end"]] == span


def test_no_false_positive_for_similar_surface(conn):
    add_grammar(conn, "V+(으)ㄹ 수 있다")
    a = analyse(conn, "그는 수가 있다. 책이 있어요.")      # contains 수/있다 but not the construction
    assert not [m for m in a["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"]


def test_unreviewed_items_are_never_verified(conn):
    add_grammar(conn, "V+(으)ㄹ 수 있다", status="needs_review")
    a = analyse(conn, "갈 수 있어요")
    g = [m for m in a["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"]
    assert g and g[0]["status"] == "LIKELY"


def test_related_form_with_tense_is_flagged(conn):
    add_grammar(conn, "V+(으)ㄹ 수 있다")
    a = analyse(conn, "먹었을 수 있다")
    g = [m for m in a["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"][0]
    assert g["match_type"] == "RELATED" and g["status"] == "LIKELY"


def test_absent_structure_is_not_found_without_reference(conn):
    a = analyse(conn, "비가 와서 집에 있었어요.")
    nf = [m for m in a["matches"] if m["layer"] == "grammar"]
    assert nf and all(m["status"] == "NOT_FOUND" and m["ref_id"] is None for m in nf)
    v = [m for m in a["matches"] if m["layer"] == "vocab"]
    assert v and all(m["status"] == "NOT_FOUND" and m["ref_id"] is None for m in v)


def test_vocab_match_types(conn):
    add_vocab(conn, "먹다", "yemoq")
    add_vocab(conn, "공부", "o'qish")
    a = analyse(conn, "먹다. 먹었습니다. 공부하고")
    by = {m["surface"]: m for m in a["matches"] if m["layer"] == "vocab"}
    assert by["먹다"]["match_type"] == "EXACT" and by["먹다"]["status"] == "VERIFIED"
    assert by["먹었습니다"]["match_type"] == "CONJUGATED" and by["먹었습니다"]["dict_form"] == "먹다"
    assert by["공부하고"]["match_type"] == "RELATED" and by["공부하고"]["status"] == "LIKELY"


def test_phrase_headword(conn):
    add_vocab(conn, "숙제를 하다", "uy vazifa qilmoq")
    a = analyse(conn, "숙제를 했어요")
    phrase = [m for m in a["matches"] if m["layer"] == "vocab" and m["ref_id"]]
    assert phrase and phrase[0]["surface"] == "숙제를 했어요"


def test_nominal_headword_not_treated_as_verb(conn):
    assert headword_lemma_keys("봄") == ["봄"]


def test_offsets_and_paragraphs(conn):
    text = "첫 문단이에요.\n\n둘째 문단입니다. 끝!"
    a = analyse(conn, text)
    assert a["text"] == text
    for m in a["matches"]:
        assert a["text"][m["start"]:m["end"]] == m["surface"]
    assert {s["paragraph_no"] for s in a["sentences"]} == {0, 1}


def test_analysis_is_cached_and_overrides_survive(conn, monkeypatch):
    add_vocab(conn, "먹다", "yemoq")
    pid = sa.create_passage(conn, None, "먹었습니다")
    mid = conn.execute("SELECT id FROM analysis_match WHERE passage_id=? AND layer='vocab'", (pid,)).fetchone()[0]
    conn.execute("UPDATE analysis_match SET status='NEEDS_REVIEW', manual_override=1 WHERE id=?", (mid,))
    calls = []
    monkeypatch.setattr(sa, "analyze_text", lambda t: calls.append(t) or ([], []))
    assert sa.analyze_passage(conn, pid, force=False) == 0 and not calls          # reopening does not run Kiwi
    monkeypatch.undo()
    sa.analyze_passage(conn, pid, force=True)                                     # explicit re-analysis
    row = conn.execute("SELECT status, manual_override FROM analysis_match WHERE passage_id=? AND layer='vocab'", (pid,)).fetchall()
    assert [tuple(r) for r in row] == [("NEEDS_REVIEW", 1)]


def test_stale_flag_after_rules_change(conn):
    pid = sa.create_passage(conn, None, "먹었습니다")
    assert sa.load_analysis(conn, pid)["stale"] is False
    db.bump(conn, "rules_version")
    assert sa.load_analysis(conn, pid)["stale"] is True


@pytest.mark.parametrize("pattern,sentence,span", [
    ("V+고 말다", "결국 헤어지고 말았습니다.", "지고 말았습니다"),
    ("A+(으)ㄴ/V+는 척하다", "아픈 척했어요", "아픈 척했어요"),
    ("V+(으)려면 멀었다", "제대하려면 아직 멀었다", "려면 아직 멀었다"),
])
def test_lexical_tail_and_adverb_gap(conn, pattern, sentence, span):
    add_grammar(conn, pattern)
    g = [m for m in analyse(conn, sentence)["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"]
    assert g and span in g[0]["surface"]


def test_noun_homograph_is_not_a_verb_tail(conn):
    add_grammar(conn, "V+고 말다")
    g = [m for m in analyse(conn, "책을 읽고 말을 했어요.")["matches"] if m["layer"] == "grammar" and m["status"] != "NOT_FOUND"]
    assert not g                                    # 말 (speech, NNG) is not the auxiliary 말다


def test_junk_notation_never_becomes_a_rule():
    assert compile_pattern("V+0/히/리/기/우-(사동)") is None

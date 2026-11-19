"""Student-book parser + importer, using a synthetic OCR page that mimics the 문법 해설 layout (invented text)."""
import json

import pytest

from backend.app import db
from backend.app.ingest import import_student_book as isb
from backend.app.ingest.sb_grammar_parser import book_to_notation, parse_ocr_dir
from backend.app.services.pattern_compiler import compile_pattern


def L(text, x, y, h=0.015):
    return {"text": text, "x": x, "y": y, "w": 0.3, "h": h, "conf": 1.0}


PAGE = {"pdf_page": 7, "lines": [
    L("문법 해설 Grammar Extension", 0.11, 0.06, 0.02),
    L("3과", 0.11, 0.10, 0.019),
    L("1. V-고 말다", 0.11, 0.14, 0.02), L("p.12", 0.85, 0.14),
    L("어떤 일이 끝나 버렸음을 나타낸다. Used when something ends.", 0.15, 0.17),
    L("동사와 결합한다. Combines with verbs.", 0.15, 0.20),
    L("받침 X", 0.36, 0.23), L("가다 -> 가고 말다", 0.33, 0.26),
    L("예) 결국 그 사람은 떠나고 말았다.", 0.16, 0.30),
    L("아이가 울고 말았어요.", 0.19, 0.32),
    L("+ 'V-고 말다'와 'V-아/어 버리다'의 비교 Compare 'V-고 말다' to 'V-아/어 버리다'", 0.15, 0.37),
    L("예) 숙제를 다 해 버렸어요.", 0.55, 0.42),
    L("2. A/V-던", 0.11, 0.50, 0.02), L("p.14", 0.85, 0.50),
    L("과거를 회상할 때 쓴다. Used when recalling.", 0.15, 0.53),
    L("예) 어제 먹던 빵이 없어요.", 0.16, 0.57),
    L("12", 0.02, 0.47),
]}


@pytest.fixture()
def ocr_dir(tmp_path):
    d = tmp_path / "X_SB"
    d.mkdir()
    (d / "page_007.json").write_text(json.dumps(PAGE, ensure_ascii=False), encoding="utf-8")
    return d


def test_book_notation_conversion():
    assert book_to_notation("A/V-던")[0] == "A/V+던"
    disp, rule = book_to_notation("V-(으)ㄹ 생각[계획, 예정]이다")
    assert disp == "V+(으)ㄹ 생각[계획, 예정]이다"
    assert rule == "V+(으)ㄹ 생각이다/V+(으)ㄹ 계획이다/V+(으)ㄹ 예정이다"
    assert compile_pattern(rule) is not None
    assert book_to_notation("A-다니까(요), V-ㄴ다니까(요)")[0] == "A+다니까(요)/V+ㄴ다니까(요)"


def test_parser_extracts_sections_verbatim(ocr_dir):
    items = parse_ocr_dir(ocr_dir)
    assert [i.pattern for i in items] == ["V+고 말다", "A/V+던"]
    a = items[0]
    assert (a.unit, a.lesson_page) == (3, 12)
    assert a.meaning_lines == ["어떤 일이 끝나 버렸음을 나타낸다. Used when something ends."]
    assert any("Combines with verbs" in f for f in a.formation_lines)
    # examples: own list only; the example inside the comparison table belongs to another pattern
    assert [e.text for e in a.examples] == ["결국 그 사람은 떠나고 말았다.", "아이가 울고 말았어요."]
    assert any("버렸어요" in n for n in a.note_lines)


def test_import_joins_index_and_is_idempotent(tmp_path, ocr_dir):
    conn = db.connect(tmp_path / "t.sqlite")
    db.init_db(conn)
    src = conn.execute("INSERT INTO source(filename, kind) VALUES ('idx.pdf','grammar_index')").lastrowid
    conn.execute("INSERT INTO grammar_item(pattern, level, source_id, status, entry_no, meaning_uz) VALUES ('V+고 말다','9Z',?,'needs_review','7','qilib qo''ymoq')", (src,))
    conn.execute("INSERT INTO grammar_item(pattern, level, source_id, status, corrected, entry_no, explanation_original) VALUES ('A/V+던','9Z',?,'verified',1,'8','my own text')", (src,))
    conn.commit()
    items = parse_ocr_dir(ocr_dir)
    s1 = isb.store(conn, "X SB.pdf", "9Z", ocr_dir, items)
    assert (s1["joined"], s1["new"], s1["kept_corrected"]) == (1, 0, 1)
    row = conn.execute("SELECT * FROM grammar_item WHERE pattern='V+고 말다'").fetchone()
    assert row["unit"] == 3 and row["page"] == 12 and row["status"] == "needs_review" and row["meaning_uz"] == "qilib qo'ymoq"
    assert row["explanation_original"].startswith("어떤 일이")
    # a manually corrected record is never overwritten
    assert conn.execute("SELECT explanation_original FROM grammar_item WHERE pattern='A/V+던'").fetchone()[0] == "my own text"
    s2 = isb.store(conn, "X SB.pdf", "9Z", ocr_dir, items, force=True)
    assert s2["new"] == 0
    assert conn.execute("SELECT COUNT(*) FROM grammar_example WHERE grammar_id=?", (row["id"],)).fetchone()[0] == 2
    with pytest.raises(SystemExit):
        isb.store(conn, "X SB.pdf", "9Z", ocr_dir, items)               # no --force: refuse
    conn.close()

"""Workbook parser + importer on synthetic OCR pages (invented text mimicking the WB layout)."""
import json

import pytest

from backend.app import db
from backend.app.ingest import import_workbook as iw
from backend.app.ingest.wb_parser import parse_pages


def L(text, x, y, h=0.015):
    return {"text": text, "x": x, "y": y, "w": 0.3, "h": h, "conf": 1.0}


def page(n, *lines):
    return {"pdf_page": n, "lines": list(lines)}


PAGES = [
    page(1, L("Contents", 0.3, 0.1, 0.02), L("듣기 지문 Listening Scripts", 0.3, 0.89, 0.02)),        # contents mention scripts: must not start a section
    page(2, L("어 휘 Vocabulary", 0.10, 0.05, 0.022), L("연습1", 0.10, 0.10, 0.02), L("알맞은 단어를 넣으세요.", 0.2, 0.10),
         L("1) 저는 ( ) 을 좋아해요.", 0.2, 0.2), L("2", 0.01, 0.46)),
    page(3, L("문법과 표현 Grammar and Expression", 0.10, 0.05, 0.022), L("1. V-고 말다", 0.10, 0.10, 0.024),
         L("연 습 1 [보기]와 같이 완성하세요.", 0.09, 0.15, 0.022),
         L("[ 보기 ] A : 어떻게 됐어요?", 0.2, 0.2), L("B :", 0.2, 0.25), L("(결국 울다)", 0.55, 0.25),
         L("3", 0.01, 0.46)),
    page(4, L("2. A/V-던", 0.10, 0.05, 0.022), L("연습 1 고르세요.", 0.09, 0.10, 0.022), L("1) ( 읽던 / 읽은 ) 책", 0.2, 0.2)),
    page(5, L("읽기 Reading", 0.07, 0.05, 0.022), L("1. 다음 글을 읽고 답하세요.", 0.10, 0.12, 0.02), L("저는 학생입니다.", 0.15, 0.2)),
    page(8, L("듣기 지문 Listening Scripts", 0.1, 0.05, 0.02), L("1. 남 : 안녕하세요.", 0.10, 0.2), L("여 : 네, 안녕하세요. 오래간만이에요.", 0.13, 0.25),
         L("2. 여 : 지금 어디예요?", 0.55, 0.2), L("남 : 회사 앞이에요. 곧 갈게요.", 0.57, 0.25)),
    page(9, L("모범 답안 Answer Key", 0.1, 0.05, 0.02), L("1) 정답 가나다", 0.2, 0.2)),
    page(10, L("이 페이지는 답안 뒤입니다", 0.2, 0.2)),
]


def test_sections_exercises_and_scripts():
    ex = parse_pages(PAGES)
    kinds = [(e.section, e.number) for e in ex]
    assert ("vocabulary", "1") in kinds
    g = [e for e in ex if e.section == "grammar"]
    assert [(e.heading, e.heading_notation, e.number) for e in g] == [("V-고 말다", "V+고 말다", "1"), ("A/V-던", "A/V+던", "1")]
    assert g[0].instruction == "[보기]와 같이 완성하세요."
    assert any("결국 울다" in b for b in g[0].body)                          # same-row hint merged into the B: line
    assert any(e.section == "reading" and e.instruction.startswith("다음 글을") for e in ex)
    scripts = [e for e in ex if e.kind == "script"]
    assert len(scripts) == 1 and scripts[0].pdf_page == 8
    # two columns are read left column first, then right column
    assert scripts[0].body.index("1. 남 : 안녕하세요.") < scripts[0].body.index("2. 여 : 지금 어디예요?")
    assert not any("정답" in "\n".join(e.body) for e in ex)               # answer key is never parsed
    assert [e for e in ex if e.pdf_page == 1] == []                       # contents page ignored


def test_import_joins_headings_to_grammar_and_is_repeatable(tmp_path):
    conn = db.connect(tmp_path / "t.sqlite")
    db.init_db(conn)
    conn.execute("INSERT INTO grammar_item(pattern, level, unit, status) VALUES ('V+고 말다','9Z',18,'needs_review')")
    conn.execute("INSERT INTO grammar_item(pattern, level, unit, status) VALUES ('N+만 하다','9Z',16,'needs_review')")
    conn.commit()
    d = tmp_path / "X_WB"
    d.mkdir()
    for p in PAGES:
        (d / f"page_{p['pdf_page']:03d}.json").write_text(json.dumps(p, ensure_ascii=False), encoding="utf-8")
    items = iw.parse_ocr_dir(d)
    s1 = iw.store(conn, "X WB.pdf", "9Z", d, items)
    assert s1["grammar_headings"] == 2 and s1["unjoined_headings"] == ["A/V+던"]       # no 'A/V+던' item in this DB: left unjoined
    row = conn.execute("SELECT w.unit, g.pattern FROM workbook_item w JOIN grammar_item g ON g.id=w.grammar_id").fetchone()
    assert tuple(row) == (18, "V+고 말다")
    assert conn.execute("SELECT COUNT(*) FROM workbook_item WHERE grammar_id IS NULL AND heading='A/V-던'").fetchone()[0] == 1
    with pytest.raises(SystemExit):
        iw.store(conn, "X WB.pdf", "9Z", d, items)
    n = conn.execute("SELECT COUNT(*) FROM workbook_item").fetchone()[0]
    iw.store(conn, "X WB.pdf", "9Z", d, items, force=True)
    assert conn.execute("SELECT COUNT(*) FROM workbook_item").fetchone()[0] == n          # --force replaces, never duplicates
    conn.close()

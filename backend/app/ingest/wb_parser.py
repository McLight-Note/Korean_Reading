"""Parse Vision-OCR output of a 서울대 한국어 workbook (WB).

Layout (verified on 3B WB):
    unit page(s)                      -> skipped (title pages)
    어휘 Vocabulary                    -> 연습 1..n
    문법과 표현 Grammar and Expression -> "1. A/V-던" heading, then 연습 1..n [보기] ...
    문형 연습 Pattern Practice         -> drills (연습 1..n)
    듣기 / 읽기 / 쓰기 / 복습 / 과제
    appendix: 듣기 지문 (listening scripts, two columns), 모범 답안 (answer key; NOT parsed)

One output record per 연습 (exercise) and one per appendix page of listening scripts. Text is kept verbatim
(OCR); nothing is solved, translated or invented. Everything is a draft for review (status needs_review).
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

from .sb_grammar_parser import book_to_notation

PAGE_NO = re.compile(r"^\d{1,3}$")
EXERCISE = re.compile(r"^연\s*습\s*(\d{1,2})\s*(.*)$")
HEADING = re.compile(r"^\s*(\d{1,2})\s*[.,]\s*(\S.*)$")
SLOT = re.compile(r"[AVN][/AVN]*\s*[-+]")
NOISE = re.compile(r"^(track\s*\d+|•?\s*track\s*\d+|서울대\s*한국어)$", re.I)
SECTIONS = [  # (compact-text prefix, section id)
    ("어휘", "vocabulary"), ("문법과표현", "grammar"), ("문형연습", "pattern_practice"), ("듣기지문", "script"),
    ("모범답안", "answer_key"), ("듣기", "listening"), ("읽기", "reading"), ("쓰기", "writing"), ("말하기", "speaking"),
    ("복습", "review"), ("과제", "task"),
    ("표현연습", "expression"), ("발음", "pronunciation"), ("평가하기", "review"), ("확인하기", "review"), ("연습하기", "review"),
    ("역할극", "speaking"), ("문법", "review"),
]
LOOSE_SECTIONS = {"listening", "reading", "writing", "speaking", "review", "task", "expression", "pronunciation"}   # questions numbered "1." / "[1-2]", not "연습 N"
LOOSE_START = re.compile(r"^(?:\[\s*(\d{1,2})\s*(?:[-~–]\s*\d{1,2})?\s*\]|(\d{1,2})\s*[.,])\s*(.*)$")


def compact(t: str) -> str:
    return re.sub(r"[\s·•\-–]+", "", unicodedata.normalize("NFC", t))


@dataclass
class Exercise:
    section: str
    heading: str | None            # grammar heading as printed, e.g. "A/V-던"
    heading_notation: str | None   # converted to V/A/N+ form
    number: str | None
    instruction: str
    body: list[str] = field(default_factory=list)
    pdf_page: int = 0
    printed_page: int | None = None
    kind: str = "exercise"         # 'exercise' | 'script'


def _section_of(lines: list[dict], pdf_page: int, total: int) -> str | None:
    """A section header is a large line in the top-left of the page."""
    for l in lines:
        if l["y"] < 0.12 and l["x"] < 0.25 and l["h"] >= 0.016:
            c = compact(l["text"])
            for prefix, sid in SECTIONS:
                if c.startswith(prefix):
                    if sid in ("script", "answer_key") and pdf_page < 0.6 * total:
                        break                                   # contents / how-to-use pages mention them too
                    return sid
    return None


def _rows(lines: list[dict]) -> list[str]:
    """Group OCR boxes into visual rows (left to right) and return the row texts, top to bottom."""
    rows: list[list[dict]] = []
    for l in sorted(lines, key=lambda l: (l["y"], l["x"])):
        if rows and abs(rows[-1][0]["y"] - l["y"]) < 0.008:
            rows[-1].append(l)
        else:
            rows.append([l])
    return [" ".join(x["text"] for x in sorted(r, key=lambda x: x["x"])) for r in rows]


def parse_pages(pages: list[dict]) -> list[Exercise]:
    total = max((p["pdf_page"] for p in pages), default=0)
    out: list[Exercise] = []
    section: str | None = None
    heading: tuple[str, str] | None = None
    cur: Exercise | None = None
    last_y, last_page = -1.0, -1
    for page in sorted(pages, key=lambda p: p["pdf_page"]):
        pdf_page = page["pdf_page"]
        raw = [dict(l, text=unicodedata.normalize("NFC", l["text"]).strip()) for l in page["lines"] if l["text"].strip()]
        printed = None
        lines = []
        for l in raw:
            if PAGE_NO.match(l["text"]) and (l["x"] < 0.05 or l["x"] > 0.93):
                printed = int(l["text"])
            elif NOISE.match(l["text"]):
                continue
            else:
                lines.append(l)
        sid = _section_of(lines, pdf_page, total)
        if sid:
            section, heading, cur = sid, None, None
            if sid == "answer_key":
                break                                           # dense tiny print; not parsed (kept as page images/OCR text)
        if section is None:
            continue
        if section == "script":
            left = [l for l in lines if l["x"] < 0.5 and not (l["y"] < 0.09)]
            right = [l for l in lines if l["x"] >= 0.5 and not (l["y"] < 0.09)]
            text = "\n".join(_rows(left) + _rows(right))
            if len(text) > 40:
                out.append(Exercise("script", None, None, None, f"Listening script (PDF p.{pdf_page})", text.split("\n"), pdf_page, printed, "script"))
            continue
        for row_l in sorted(lines, key=lambda l: (round(l["y"], 3), l["x"])):
            t = row_l["text"]
            if row_l["y"] < 0.12 and row_l["x"] < 0.25 and any(compact(t).startswith(p) for p, _ in SECTIONS):
                continue                                        # the section header line itself
            hm = HEADING.match(t)
            if hm and row_l["x"] < 0.16 and row_l["h"] >= 0.019 and len(t) < 90 and (SLOT.search(hm.group(2)) or section == "grammar"):
                disp, _rule = book_to_notation(hm.group(2))
                heading = (hm.group(2).strip(), disp)
                cur = None
                continue
            lm = LOOSE_START.match(t) if section in LOOSE_SECTIONS and row_l["x"] < 0.2 and row_l["h"] >= 0.0145 else None
            if lm and HANGUL.search(lm.group(3) or "") and not (SLOT.search(t) and row_l["h"] >= 0.019):
                cur = Exercise(section, None, None, lm.group(1) or lm.group(2), lm.group(3).strip(), [], pdf_page, printed)
                out.append(cur)
                continue
            em = EXERCISE.match(t)
            if em and row_l["x"] < 0.25:
                cur = Exercise(section, heading[0] if heading else None, heading[1] if heading else None, em.group(1), em.group(2).strip(), [], pdf_page, printed)
                out.append(cur)
                continue
            if cur is None:
                continue
            if cur.printed_page is None:
                cur.printed_page = printed
            if not cur.instruction and not cur.body and HANGUL.search(t):
                cur.instruction = t
            elif cur.body and last_page == pdf_page and abs(row_l["y"] - last_y) < 0.008:
                cur.body[-1] += " " + t                         # same visual row (e.g. "B :" + hint in the right column)
            else:
                cur.body.append(t)
            last_y, last_page = row_l["y"], pdf_page
        # an exercise can continue on the next page without a new "연습" line: it simply keeps `cur`
    for ex in out:
        ex.body = [b for b in ex.body if b.strip()]
    return out


HANGUL = re.compile(r"[가-힣]")


def parse_ocr_dir(ocr_dir: Path) -> list[Exercise]:
    pages = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(ocr_dir.glob("page_*.json"))]
    return parse_pages(pages)

"""Parse the "문법 해설 / Grammar Extension" appendix of a 서울대 student book from Vision OCR JSON.

Each OCR page JSON: {"pdf_page": N, "lines": [{"text","x","y","w","h","conf"}]} with normalised coords
(x,y = top-left of the line box, y grows downwards).

Appendix layout (verified on 3B SB pp. 240-260):
    10과                              <- unit marker
    1. A/V-던            p.26         <- numbered heading + lesson page
    <Korean meaning sentence> <English translation>
    <Combines with ...>  + table      <- formation
    예) <example>  (+ indented example lines)
    + <note> / comparison tables
Everything is kept verbatim; nothing is translated, summarised or invented. The result is a *draft* for the
admin review queue: callers must store it with status 'needs_review'.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

HANGUL = re.compile(r"[가-힣ㄱ-ㅎ]")
SECTION_START = re.compile(r"문\s*법\s*해\s*설")
SECTION_END = re.compile(r"문화\s*해설|Culture\s*Extension|듣기\s*지문|Listening\s*Scripts")
UNIT_RE = re.compile(r"^\s*(\d{1,2})\s*과\s*$")
HEADING_RE = re.compile(r"^\s*(\d{1,2})\s*[.,]\s*(\S.*)$")
LESSON_PAGE_RE = re.compile(r"^[\W\d]{0,3}[pP]\s*[.:]?\s*:?\s*(\d{1,3})\b")
PAGE_NO_RE = re.compile(r"^\d{1,3}$")
EXAMPLE_START = re.compile(r"^\s*예\s*\)\s*")
TERMINAL = re.compile(r"[.?!…)”\"']\s*$")
SLOT_DASH = re.compile(r"(?<![A-Za-z])([AVN](?:\s*/\s*[AVN])*)\s*[-–—ㅡ−]\s*")
LEFT_COL_MAX = 0.5


@dataclass
class Example:
    text: str
    pdf_page: int


@dataclass
class Item:
    number: int
    heading_raw: str
    pattern: str                   # book notation converted to the V/A/N+ form used by the index
    rule_pattern: str              # same, with [a, b] alternatives expanded (input for compile_pattern)
    unit: int | None
    lesson_page: int | None        # printed page where the grammar point is taught ("p.26")
    appendix_pdf_page: int
    appendix_printed_page: int | None
    meaning_lines: list[str] = field(default_factory=list)
    formation_lines: list[str] = field(default_factory=list)
    note_lines: list[str] = field(default_factory=list)
    examples: list[Example] = field(default_factory=list)
    raw: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)
    open_x: float | None = None
    in_compare: bool = False
    open_y: float = 0.0


def _n(s: str) -> str:
    return unicodedata.normalize("NFC", s).strip()


def book_to_notation(heading: str) -> tuple[str, str]:
    """'A/V-던' -> 'A/V+던';  'V-(으)ㄹ 생각[계획, 예정]이다' -> display + rule variants joined with '/'."""
    s = _n(heading)
    s = re.sub(r"\s+", " ", s)
    s = re.sub(r"(?<=[+/-])L(?=[가-힣])", "ㄴ", s)                   # OCR: 'V+L다면' is 'V+ㄴ다면'
    s = SLOT_DASH.sub(lambda m: m.group(1).replace(" ", "") + "+", s)
    s = re.sub(r"(?<![A-Za-z])N(?=[\(가-힣])", "N+", s)           # N(이)라니까 / N이어야 -> N+...
    s = re.sub(r",\s*(?=[AVN](?:/[AVN])*\+)", "/", s)              # 'A-…, V-…, N…' -> alternatives
    display = s
    rule = s
    m = re.search(r"(\S*?)\[([^\]]+)\](\S*)", s)
    if m:
        opts = [m.group(1)] + [o.strip() for o in m.group(2).split(",") if o.strip()]
        slot = re.match(r"^((?:[AVN](?:/[AVN])*\+))", s)
        prefix_end = m.start()
        head = s[:prefix_end]
        variants = [head + o + m.group(3) + s[m.end():] for o in opts if o]
        # every variant starts with the same slot prefix; join them in index style
        rule = "/".join(variants) if slot else variants[0]
    return display, rule


ICON_PREFIX = re.compile(r"^(?:[>~@®⑥②③①④⑤6+•*]|[_2]\s)\s*(?=[가-힣A-Za-z'\"‘(])")
FORMATION_LABEL = re.compile(r"^(형용사|동사|명사)$")
COMPARE = re.compile(r"[와과]의\s*비교|\bCompare\b")
SIDEBAR_WORDS = re.compile(r"문법\s*해설|문화\s*해설")


def _items_from_pages(pages: list[dict]) -> list[Item]:
    items: list[Item] = []
    in_section = False
    unit: int | None = None
    cur: Item | None = None
    for page in pages:
        lines = [dict(l, text=_n(l["text"])) for l in page["lines"] if _n(l["text"])]
        pdf_page = page["pdf_page"]
        if any(SECTION_START.search(l["text"]) and l["x"] < 0.2 and l["y"] < 0.1 for l in lines):
            in_section = True
        if not in_section:
            continue
        if any(SECTION_END.search(l["text"]) and l["x"] < 0.2 and l["y"] < 0.1 for l in lines):
            break
        printed = None
        body = []
        for l in lines:                                   # printed page number sits in a side margin
            if PAGE_NO_RE.match(l["text"]) and (l["x"] < 0.04 or l["x"] > 0.93):
                printed = int(l["text"])
            elif l["x"] > 0.9 and SIDEBAR_WORDS.search(l["text"]):
                continue
            else:
                body.append(l)
        lesson_pages = [(l["y"], int(LESSON_PAGE_RE.match(l["text"]).group(1))) for l in body
                        if l["x"] > 0.55 and LESSON_PAGE_RE.match(l["text"])]
        # one top-down stream per page: an item owns every line below its heading (both columns) until the next heading
        for l in sorted((l for l in body if not (l["x"] > 0.55 and LESSON_PAGE_RE.match(l["text"]))), key=lambda l: (round(l["y"], 3), l["x"])):
            t = l["text"]
            um = UNIT_RE.match(t)
            if um and l["x"] < 0.2:
                unit = int(um.group(1))
                cur = None
                continue
            hm = HEADING_RE.match(t)
            lp = next((p for y, p in lesson_pages if abs(y - l["y"]) < 0.02), None)
            if hm and l["x"] < 0.16 and l["h"] >= 0.0165 and len(t) < 90 and not re.search(r"\([OXox]\)", t) and (
                    lp is not None or re.search(r"[AVN][/AVN]*\s*[-+]", hm.group(2))):
                display, rule = book_to_notation(hm.group(2))
                cur = Item(int(hm.group(1)), t, display, rule, unit, lp, pdf_page, printed)
                if lp is None:
                    cur.flags.append("no-lesson-page")
                items.append(cur)
                continue
            if cur is None:
                continue
            cur.raw.append(t)
            _classify(cur, l, pdf_page)
    return items


def _classify(cur: Item, l: dict, pdf_page: int) -> None:
    t = l["text"]
    x, y = l["x"], l["y"]
    col = 0 if x < LEFT_COL_MAX else 1
    if COMPARE.search(t):
        cur.in_compare = True                       # comparison tables show OTHER patterns: their examples are notes
    if EXAMPLE_START.match(t) and not cur.in_compare and col == 0:
        cur.examples.append(Example(EXAMPLE_START.sub("", t).strip(), pdf_page))
        cur.open_x, cur.open_y = x, y
        return
    # continuation of an open example: indented under the 예) line, just below, Korean, same page
    if cur.examples and cur.open_x is not None and cur.examples[-1].pdf_page == pdf_page and col == 0:
        dy = y - cur.open_y
        if (0 < dy < 0.034 and cur.open_x + 0.015 <= x <= cur.open_x + 0.09 and HANGUL.search(t)
                and not re.match(r"^[>~@®⑥②③①④⑤+•*(]", t)):
            prev = cur.examples[-1]
            if TERMINAL.search(prev.text):          # finished sentence -> next example sentence of the list
                cur.examples.append(Example(t, pdf_page))
            else:                                   # wrapped line of the same sentence
                prev.text = prev.text + " " + t
            cur.open_y = y
            return
    cur.open_x = None
    text = ICON_PREFIX.sub("", t)
    has_formation = bool(cur.formation_lines)
    if re.search(r"받침\s*[XOxo0ㅇ]", t) or re.search(r"->|→|[-–]>|ㅡ\s", t) and len(t) < 60 or FORMATION_LABEL.match(t):
        cur.formation_lines.append(t)
    elif re.search(r"결합한다|Combin|Combine", t) and not cur.in_compare:
        cur.formation_lines.append(text)
    elif not re.search(r"[가-힣]{2}|[A-Za-z]{3}", text):
        cur.note_lines.append(text)                 # stray glyphs / OCR junk: keep, but never as the explanation
    elif not cur.examples and not has_formation and not cur.in_compare and not t.startswith("+"):
        cur.meaning_lines.append(text)              # Korean meaning sentence + its (wrapped) English translation
    else:
        cur.note_lines.append(text)


def fix_example_lists(items: list[Item]) -> None:
    """Merge wrapped example lines and drop trailing English/blank fragments (cheap, conservative)."""
    for it in items:
        out: list[Example] = []
        for ex in it.examples:
            txt = re.sub(r"\s+", " ", ex.text).strip()
            if len(txt) >= 3 and HANGUL.search(txt):
                out.append(Example(txt, ex.pdf_page))
        it.examples = out
        if not it.meaning_lines:
            it.flags.append("no-meaning-line")
        if not it.examples:
            it.flags.append("no-examples")


def parse_ocr_dir(ocr_dir: Path, first: int = 1, last: int = 10_000) -> list[Item]:
    pages = []
    for jp in sorted(ocr_dir.glob("page_*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        if first <= d["pdf_page"] <= last:
            pages.append(d)
    items = _items_from_pages(pages)
    fix_example_lists(items)
    return items

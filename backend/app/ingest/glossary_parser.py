"""Parse the Korean-Uzbek glossary PDF text layer ("서울대 책 1a 부터 5b가지.pdf") into vocab records.

Input: JSON produced by ingest/pdf_text.swift: [{"pdf_page": 1, "text": "..."}].
Nothing is translated or invented: headword and Uzbek gloss are stored exactly as printed.
Entries whose parse is doubtful are flagged status='needs_review'.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LEVEL_RE = re.compile(r"서울대\s*(?:한국어)?\s*([1-5])\s*([ABabАВав])\b")  # incl. Cyrillic А/В
UNIT_RE = re.compile(r"^(?:\d+\s*\.\s*)?(\d{1,2})\s*과(?![가-힣])\s*\.?\s*(.*)$")
NUM_RE = re.compile(r"^(\d{1,3})\s*(?:[.)]\s*|\s(?=[가-힣(]))(.*)$")   # "12. 단어" or OCR-dropped dot "12 단어"
HANGUL = re.compile(r"[가-힣ㄱ-ㅎㅏ-ㅣ]")
LATIN = re.compile(r"[A-Za-z\u0400-\u04FF]")  # Latin or Cyrillic (3A uses Cyrillic Uzbek)
TRAILING_NUM = re.compile(r"\s(\d[\d,. ]*)$")
CYR = str.maketrans({"А": "A", "В": "B", "а": "A", "в": "B"})


@dataclass
class Entry:
    headword: str
    gloss: str
    level: str | None
    unit: int | None
    unit_title: str | None
    pdf_page: int
    entry_no: int | None
    raw: list[str] = field(default_factory=list)
    flags: list[str] = field(default_factory=list)


def _clean(s: str) -> str:
    s = unicodedata.normalize("NFC", s)
    return re.sub(r"\s+", " ", s.replace("​", "")).strip()


def split_entry(line: str) -> tuple[str, str] | None:
    """Split 'headword gloss' / 'headword –gloss' / 'headword-gloss'. None if there's no Hangul headword."""
    first_h = HANGUL.search(line)
    m = LATIN.search(line, first_h.end()) if first_h else LATIN.search(line)   # Latin *before* Hangul belongs to the headword (A4 용지, K-팝)
    head, gloss = (line[: m.start()], line[m.start():]) if m else (line, "")
    if not m:
        nm = TRAILING_NUM.search(line)                 # e.g. '열 10': the gloss is the number
        if nm and HANGUL.search(line[: nm.start()]):
            head, gloss = line[: nm.start()], nm.group(1)
    # a gloss separator dash may sit just before the Latin text
    head = head.rstrip()
    head = re.sub(r"[\s\-–—]+$", "", head)
    gloss = gloss.strip().lstrip("-–— ").strip()
    if not HANGUL.search(head):
        return None
    return head.strip(), gloss


def parse_pages(pages: list[dict]) -> list[Entry]:
    entries: list[Entry] = []
    level: str | None = None
    unit: int | None = None
    unit_title: str | None = None
    last: Entry | None = None

    for page in pages:
        pno = page["pdf_page"]
        for raw in page["text"].split("\n"):
            line = _clean(raw)
            if not line or line in {""}:
                continue
            if re.fullmatch(r"Jason-?\d*", line) or line in {"사전들이", "dictionary", "“", "''"}:
                continue
            lm = LEVEL_RE.search(line)
            if lm and len(line) < 40:
                level = lm.group(1) + lm.group(2).upper().translate(CYR)
                unit, unit_title, last = None, None, None
                continue
            line = line.lstrip(" ").strip()
            if line.startswith("속담"):                      # section marker "속담-maqol" (proverbs)
                unit_title = "속담"
            um = UNIT_RE.match(line)
            if um and len(line) < 40 and not LATIN.search(line):
                unit = int(um.group(1))
                unit_title = _clean(um.group(2)).lstrip(". ") or None
                last = None
                continue
            entry_no = None
            body = line
            nm = NUM_RE.match(line)
            if nm:
                entry_no, body = int(nm.group(1)), nm.group(2)
            # continuation of the previous gloss: no Hangul at all, or starts with a dash
            if last is not None and entry_no is None and (not HANGUL.search(body) or re.match(r"^[–—-]\s*[A-Za-z\u0400-\u04FF]", body)):
                last.gloss = (last.gloss + " " + body.lstrip("-–— ")).strip()
                last.raw.append(raw)
                continue
            parts = split_entry(body)
            if parts is None:
                if last is not None:                          # stray text: attach, but flag
                    last.gloss = (last.gloss + " " + body).strip()
                    last.raw.append(raw)
                    last.flags.append("stray-continuation")
                continue
            head, gloss = parts
            e = Entry(head, gloss, level, unit, unit_title, pno, entry_no, [raw])
            if LATIN.search(head):
                e.flags.append("latin-in-headword")
            if level is None:
                e.flags.append("no-level")
            if not gloss:
                e.flags.append("no-gloss")      # a wrapped gloss may still be appended later
            entries.append(e)
            last = e
    for e in entries:
        if e.gloss:
            e.flags = [f for f in e.flags if f != "no-gloss"]
    return entries

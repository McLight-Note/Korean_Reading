"""Parse OCR of the scanned grammar-pattern index ("서울대 grammatikka kitob.pdf").

The book is a numbered list per level ("서울대 3A" ... "1. A+다고/V+ㄴ다고 ... -deb aytmoq") with Uzbek
glosses and handwritten corrections. We keep the raw OCR line, apply only conservative cleanup of the
V/A/N slot prefix, and mark every item needs_review: OCR + handwriting must be approved by a human.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

LEVEL_RE = re.compile(r"서울대\s*([1-5])\s*([AB8])\b")
NUM_RE = re.compile(r"^\W{0,2}(\d{1,2})\s*[.,]\s*(.+)$")
HANGUL = re.compile(r"[가-힣ㄱ-ㅎ]")
SLOT_START = re.compile(r"^[AVNavn][\s]*[+=tT]|^A\s*/\s*V|^[AV]{2}\s*\+")
GLOSS_SPLIT = re.compile(r"[-–—]\s*(?![AVNavn]\s*[+=])(?=[A-Za-z'\"“‘])")


@dataclass
class IndexItem:
    level: str
    entry_no: str
    pattern: str
    gloss: str
    raw: str
    pdf_page: int
    flags: list[str]


def clean_pattern(p: str) -> str:
    p = unicodedata.normalize("NFC", p).strip(" -–—.")
    p = re.sub(r"\b(?:AtV|AV|A\+V|Av|aV|A\s*V)\s*\+", "A/V+", p)
    p = re.sub(r"\bAtN\s*\+", "A/N+", p)
    p = re.sub(r"(?<![A-Za-z])v\s*\+", "V+", p)
    p = re.sub(r"(?<![A-Za-z])n\s*\+", "N+", p)
    p = re.sub(r"(?<![A-Za-z])a\s*\+", "A+", p)
    p = re.sub(r"-(?=[AVN]\+)", "/", p)
    p = re.sub(r",\s*(?=[AVNv]\s*\+)", "/", p)
    return re.sub(r"\s+", " ", p).strip()


def split_pattern_gloss(body: str) -> tuple[str, str]:
    m = GLOSS_SPLIT.search(body)
    if m and HANGUL.search(body[: m.start()]):
        return body[: m.start()], body[m.end():]
    return body, ""


def parse_ocr_dir(ocr_dir: Path) -> list[IndexItem]:
    items: list[IndexItem] = []
    level: str | None = None
    last_no = "0"
    sub = 0
    for jp in sorted(ocr_dir.glob("page_*.json")):
        d = json.loads(jp.read_text(encoding="utf-8"))
        pno = d["pdf_page"]
        for ln in d["lines"]:
            text = unicodedata.normalize("NFC", ln["text"]).strip()
            if not text:
                continue
            hm = LEVEL_RE.search(text)
            if hm and len(text) < 20:
                level = hm.group(1) + ("B" if hm.group(2) == "8" else hm.group(2))
                last_no, sub = "0", 0
                continue
            if level is None:
                continue
            # skip handwriting in the right margin / footer (low-x text without a numbered or slot pattern)
            nm = NUM_RE.match(text.lstrip("-–— "))
            if nm and HANGUL.search(nm.group(2)) or (nm and "+" in nm.group(2)):
                no, body = nm.group(1), nm.group(2)
                last_no, sub = no, 0
            elif SLOT_START.match(text) or re.match(r"^[a-e]\.\s", text):
                sub += 1                               # variant line belonging to the previous number
                no, body = f"{last_no}.{sub}", re.sub(r"^[a-e]\.\s*", "", text)
            elif HANGUL.search(text) and ln["x"] < 0.3 and last_no != "0" and "+" not in text and len(text) < 40:
                sub += 1                               # e.g. '언제나-qachon' under '8. 누구나'
                no, body = f"{last_no}.{sub}", text
            else:
                continue
            pat, gloss = split_pattern_gloss(body)
            flags = ["ocr", "needs-human-review"]
            if not re.search(r"[AVN][/AVN]*\s*\+", clean_pattern(pat)):
                flags.append("no-slot")
            items.append(IndexItem(level, no, clean_pattern(pat), gloss.strip(" -–—"), text, pno, flags))
    return items

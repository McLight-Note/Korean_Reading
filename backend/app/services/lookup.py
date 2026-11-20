"""Approximate vocabulary lookup for pasted text: which words are in the textbook word list?

There is NO morphological analysis here (that was Kiwi, now removed). A token is matched by plain rules only:

  * a noun headword, alone or followed by a common particle/copula        영화 / 영화를 / 학생이에요
  * a verb/adjective stem (headword minus 다) followed by an ending       먹 → 먹었어요, 공부하 → 공부했어요

Irregular conjugations (예뻤, 갔, 와요 ...) are not recognised, so this under-reports. It is a colouring aid, labelled
approximate in the UI; the real lookup is always the word the reader clicks (Google Translate + the glossary entry).
"""
from __future__ import annotations

import re
from functools import lru_cache

from .common import LEVEL_ORDER, plain

PARTICLES = {
    "", "은", "는", "이", "가", "을", "를", "에", "에서", "에게", "한테", "께", "도", "의", "와", "과", "로", "으로", "만", "까지", "부터",
    "이나", "나", "이랑", "랑", "처럼", "보다", "마다", "조차", "마저", "밖에", "에는", "에서는", "에도", "에서도", "으로는", "로는", "이라고", "라고",
    "이다", "입니다", "이에요", "예요", "이었다", "였다", "이고", "이며", "이지만", "인", "으로서", "로서", "들", "들이", "들은", "들을", "들의", "들도", "하고",
}
VERB_ENDING_START = set("었았였어아여고지는은을ᆫᆯᆸ습겠며면서니다게세시기네요죠자러려도")   # first character after a stem
KOREAN = re.compile(r"^[가-힣]+$")
TRAILING = "\"'“”‘’.,!?…()[]:;~-"


class LookupIndex:
    def __init__(self, conn):
        self.nouns: dict[str, dict] = {}
        self.stems: dict[str, dict] = {}
        rows = conn.execute("SELECT id, headword, level, unit FROM vocab_entry").fetchall()
        rows.sort(key=lambda r: (LEVEL_ORDER.get(r["level"], 99), r["unit"] or 0, r["id"]))      # earliest level wins
        for r in rows:
            hw = re.sub(r"\([^)]*\)", "", r["headword"]).strip()
            if " " in hw or not hw:
                continue                                               # multi-word phrases cannot be matched token by token
            p = plain(r["headword"])
            if not KOREAN.match(p):
                continue
            entry = {"id": r["id"], "headword": r["headword"], "level": r["level"], "unit": r["unit"]}
            if p.endswith("다") and len(p) >= 2:
                self.stems.setdefault(p[:-1], entry)
            else:
                self.nouns.setdefault(p, entry)

    def match(self, token: str) -> dict | None:
        t = token.strip(TRAILING)
        if not t or not KOREAN.match(t):
            return None
        if t in self.nouns:
            return {**self.nouns[t], "match": "exact"}
        for cut in range(len(t) - 1, 0, -1):                           # noun + particle: longest noun first
            head, rest = t[:cut], t[cut:]
            if head in self.nouns and rest in PARTICLES and (cut >= 2 or rest in ("은", "는", "이", "가", "을", "를", "에", "도", "의")):
                return {**self.nouns[head], "match": "noun"}
        for cut in range(len(t), 0, -1):                               # verb/adjective stem + ending: longest stem first
            stem, rest = t[:cut], t[cut:]
            if stem in self.stems and (rest == "" or rest[0] in VERB_ENDING_START) and (cut >= 2 or rest):
                return {**self.stems[stem], "match": "stem"}
        for cut in range(len(t) - 1, 0, -1):                           # 하다 verbs: 공부했어요 = 공부 + 했어요
            base, rest = t[:cut], t[cut:]
            if (base + "하") in self.stems and rest[:1] in ("했", "해", "합", "한", "할", "하"):
                return {**self.stems[base + "하"], "match": "stem"}
        return None


_cache: dict = {}


def index_for(conn) -> LookupIndex:
    """Cached per database file + vocab version, so it is not rebuilt on every call."""
    from .. import db
    path = conn.execute("PRAGMA database_list").fetchone()[2]
    key = (path, db.meta(conn, "vocab_version"), conn.execute("SELECT COUNT(*) FROM vocab_entry").fetchone()[0])
    if key not in _cache:
        _cache.clear()
        _cache[key] = LookupIndex(conn)
    return _cache[key]


def lookup(conn, tokens: list[str]) -> dict[str, dict]:
    idx = index_for(conn)
    out: dict[str, dict] = {}
    for t in dict.fromkeys(tokens):                                    # unique, order kept
        m = idx.match(t)
        if m:
            out[t] = m
    return out

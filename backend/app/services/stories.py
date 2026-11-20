"""Reading stories written for this app (not textbook content), aligned with the textbook grammar and vocabulary.

Files: content/stories/*.json
  {"id", "level", "title", "theme", "units", "summary_en", "text", "target_grammar", "target_vocab", "questions": [{"q","a"}]}

The text carries its own colouring as inline markup (no NLP is involved at any point):
    [[참석했을|참석하다]]            a vocabulary target:  shown text | target word (one of target_vocab)
    <<보니까|V+아/어 보니(까)>>      a grammar target:     shown text | pattern (one of target_grammar)
Marks never nest and never overlap. parse_markup() turns a text into plain text plus highlight spans.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from .common import LEVEL_ORDER, plain

CONTENT_DIR = Path(__file__).resolve().parents[3] / "content" / "stories"
REQUIRED = ("id", "level", "title", "text", "target_grammar", "target_vocab", "questions", "summary_en")
MARK = re.compile(r"\[\[(.+?)\|(.+?)\]\]|<<(.+?)\|(.+?)>>")


def _u16(s: str) -> int:
    return len(s.encode("utf-16-le")) // 2           # JavaScript string indices are UTF-16 code units


def parse_markup(marked: str) -> tuple[str, list[dict]]:
    """-> (plain text, [{"start","end","kind":"vocab"|"grammar","ref"}]) with UTF-16 offsets into the plain text."""
    out, highlights, pos, last = [], [], 0, 0
    for m in MARK.finditer(marked):
        before = marked[last:m.start()]
        out.append(before)
        pos += _u16(before)
        if m.group(1) is not None:
            shown, ref, kind = m.group(1), m.group(2), "vocab"
        else:
            shown, ref, kind = m.group(3), m.group(4), "grammar"
        highlights.append({"start": pos, "end": pos + _u16(shown), "kind": kind, "ref": ref})
        out.append(shown)
        pos += _u16(shown)
        last = m.end()
    out.append(marked[last:])
    return "".join(out), highlights


@lru_cache(maxsize=1)
def load_all() -> list[dict]:
    stories = []
    for p in sorted(CONTENT_DIR.glob("*.json")):
        s = json.loads(p.read_text(encoding="utf-8"))
        missing = [k for k in REQUIRED if k not in s]
        if missing:
            raise ValueError(f"{p.name}: missing {missing}")
        s["text"], s["highlights"] = parse_markup(s["text"].strip())
        stories.append(s)
    stories.sort(key=lambda s: (LEVEL_ORDER.get(s["level"], 99), s["id"]))
    return stories


def get(story_id: str) -> dict | None:
    return next((s for s in load_all() if s["id"] == story_id), None)


def resolve_vocab(conn, level: str, target: str) -> dict | None:
    """Glossary entry for a target word: prefer the story's own level, then lower levels."""
    want = plain(target)
    best = None
    for r in conn.execute("SELECT id, headword, meaning_en, level, unit, status FROM vocab_entry"):
        if plain(r["headword"]) != want:
            continue
        dist = LEVEL_ORDER.get(level, 0) - LEVEL_ORDER.get(r["level"], 0)
        rank = (0 if dist == 0 else 1 if dist > 0 else 2, abs(dist), r["status"] != "verified", r["id"])
        if best is None or rank < best[0]:
            best = (rank, dict(r))
    return best[1] if best else None


def resolve_grammar(conn, level: str, pattern: str) -> dict | None:
    rows = conn.execute("SELECT id, pattern, level, meaning_en, explanation_original, unit, page, status FROM grammar_item WHERE pattern = ?", (pattern,)).fetchall()
    if not rows:
        return None
    rows = sorted(rows, key=lambda r: (r["level"] != level, abs(LEVEL_ORDER.get(level, 0) - LEVEL_ORDER.get(r["level"], 0)), r["id"]))
    return dict(rows[0])


def summary(s: dict) -> dict:
    return {"id": s["id"], "level": s["level"], "title": s["title"], "theme": s.get("theme"), "units": s.get("units", []),
            "chars": len(s["text"]), "n_grammar": len(s["target_grammar"]), "n_vocab": len(s["target_vocab"]), "summary_en": s["summary_en"]}


def detail(conn, s: dict) -> dict:
    return {**summary(s), "text": s["text"], "highlights": s["highlights"], "questions": s["questions"],
            "target_vocab": [{"target": t, "entry": resolve_vocab(conn, s["level"], t)} for t in s["target_vocab"]],
            "target_grammar": [{"target": t, "item": resolve_grammar(conn, s["level"], t)} for t in s["target_grammar"]]}


def check(conn, s: dict) -> dict:
    """Quality report: every declared target is marked in the text and exists in the database; marks are well-formed."""
    hl = s["highlights"]
    counts = {"vocab": {}, "grammar": {}}
    for h in hl:
        counts[h["kind"]][h["ref"]] = counts[h["kind"]].get(h["ref"], 0) + 1
    problems = []
    for kind, declared in (("vocab", s["target_vocab"]), ("grammar", s["target_grammar"])):
        for t in declared:
            if counts[kind].get(t, 0) == 0:
                problems.append(f"{kind} target is never marked in the text: {t}")
        for ref in counts[kind]:
            if ref not in declared:
                problems.append(f"{kind} mark refers to an undeclared target: {ref}")
    for t in s["target_vocab"]:
        if resolve_vocab(conn, s["level"], t) is None:
            problems.append(f"vocab target not in glossary: {t}")
    for t in s["target_grammar"]:
        if resolve_grammar(conn, s["level"], t) is None:
            problems.append(f"grammar target not in database: {t}")
    spans = sorted((h["start"], h["end"]) for h in hl)
    if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
        problems.append("marks overlap")
    if any(tok in s["text"] for tok in ("[[", "]]", "<<", ">>")):
        problems.append("unparsed markup left in the text")
    return {"id": s["id"], "level": s["level"], "chars": len(s["text"]), "marks": len(hl), "vocab": counts["vocab"], "grammar": counts["grammar"], "problems": problems}

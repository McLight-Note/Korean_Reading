"""Reading stories: file format, inline-markup parser and checks. Standalone: no database, no NLP, no network.

A story is one file, content/stories/<id>.json:

  {"id": "3a-01-club",            same as the file name (lowercase letters, digits, dashes)
   "level": "3A",                 1A ... 5B
   "title": "...", "theme": "University life", "units": [1],      (theme and units are optional)
   "summary_en": "One or two sentences in English.",
   "text": "... marked text ...",
   "target_vocab": ["동아리", "가입하다"],            words to learn (the word as in the glossary, without brackets)
   "target_grammar": ["V+지만", "A/V+거든(요)"],      grammar points to learn (patterns as written in the grammar book)
   "questions": [{"q": "...?", "a": "..."}]}

The text carries its own colouring as inline markup:
    [[동아리를|동아리]]       a word to learn:       shown text | target word (one of target_vocab)
    <<낯설었지만|V+지만>>     a grammar point:       shown text | pattern (one of target_grammar)
Marks never nest or overlap, never start or end with a space, and every target must be marked at least once.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

STORIES_DIR = Path(__file__).resolve().parents[1] / "content" / "stories"
LEVELS = ["1A", "1B", "2A", "2B", "3A", "3B", "4A", "4B", "5A", "5B"]
REQUIRED = ("id", "level", "title", "text", "target_vocab", "target_grammar", "questions", "summary_en")
MARK = re.compile(r"\[\[(.+?)\|(.+?)\]\]|<<(.+?)\|(.+?)>>")
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


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


def load_file(path: Path) -> dict:
    raw = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in REQUIRED if k not in raw]
    if missing:
        raise ValueError(f"{path.name}: missing fields {missing}")
    raw["marked"] = raw["text"].strip()
    raw["text"], raw["highlights"] = parse_markup(raw["marked"])
    return raw


def load_all(directory: Path = STORIES_DIR) -> list[dict]:
    stories = [load_file(p) for p in sorted(directory.glob("*.json"))]
    stories.sort(key=lambda s: (LEVELS.index(s["level"]) if s["level"] in LEVELS else 99, s["id"]))
    return stories


def problems(s: dict, file_stem: str | None = None) -> list[str]:
    """Everything wrong with one loaded story (empty list = fine)."""
    p = []
    if not ID_RE.match(str(s["id"])):
        p.append(f"id must be lowercase letters, digits and dashes: {s['id']!r}")
    if file_stem is not None and s["id"] != file_stem:
        p.append(f"id {s['id']!r} does not match the file name {file_stem!r}")
    if s["level"] not in LEVELS:
        p.append(f"unknown level {s['level']!r} (use one of {', '.join(LEVELS)})")
    if not str(s["title"]).strip():
        p.append("empty title")
    if not str(s["summary_en"]).strip():
        p.append("empty summary_en")
    if len(s["text"]) < 50:
        p.append("text is very short")
    qs = s["questions"]
    if not isinstance(qs, list) or not qs or not all(isinstance(q, dict) and str(q.get("q", "")).strip() for q in qs):
        p.append("questions must be a list of {\"q\": ..., \"a\": ...} with a non-empty q")
    for key in ("target_vocab", "target_grammar"):
        v = s[key]
        if not isinstance(v, list) or not v or not all(isinstance(x, str) and x.strip() for x in v):
            p.append(f"{key} must be a non-empty list of strings")
        elif len(set(v)) != len(v):
            p.append(f"{key} has duplicates")
    if p:
        return p
    marked = {"vocab": {}, "grammar": {}}
    for h in s["highlights"]:
        marked[h["kind"]][h["ref"]] = marked[h["kind"]].get(h["ref"], 0) + 1
        shown = s["text"].encode("utf-16-le")[2 * h["start"]:2 * h["end"]].decode("utf-16-le")
        if shown != shown.strip():
            p.append(f"mark has a space at its edge: {shown!r}")
    for kind, declared in (("vocab", s["target_vocab"]), ("grammar", s["target_grammar"])):
        for t in declared:
            if not marked[kind].get(t):
                p.append(f"{kind} target is never marked in the text: {t}")
        for ref in marked[kind]:
            if ref not in declared:
                p.append(f"{kind} mark refers to something not in target_{kind}: {ref}")
    spans = sorted((h["start"], h["end"]) for h in s["highlights"])
    if any(b[0] < a[1] for a, b in zip(spans, spans[1:])):
        p.append("marks overlap")
    if any(tok in s["text"] for tok in ("[[", "]]", "<<", ">>")):
        p.append("unparsed markup left in the text (a mark is missing its | or is nested)")
    return p


def firestore_doc(s: dict) -> dict:
    """What is stored in Firestore for a story (the plain text plus highlight spans; the markup itself is not stored)."""
    doc = {
        "level": s["level"], "title": s["title"].strip(), "theme": s.get("theme") or "", "units": s.get("units") or [],
        "summary_en": s["summary_en"].strip(), "text": s["text"], "highlights": s["highlights"],
        "target_vocab": s["target_vocab"], "target_grammar": s["target_grammar"],
        "questions": [{"q": q["q"].strip(), "a": str(q.get("a", "")).strip()} for q in s["questions"]],
        "chars": len(s["text"]),
    }
    return doc

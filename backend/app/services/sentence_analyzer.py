"""Orchestrates passage analysis: Kiwi -> vocabulary + grammar matching -> persisted matches.

Analysis runs once, when a passage is created or its text changes (or on explicit re-analyse).
Opening a passage only reads the stored rows. Manual overrides survive re-analysis.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from .. import config, db
from . import grammar_matcher
from .korean_analyzer import analyze_text, normalize
from .vocabulary_matcher import Match, VocabIndex


def utf16_map(text: str):
    """Return f(i): code-point index -> UTF-16 code-unit index (what JavaScript string slicing uses).
    Hangul is in the BMP so the two agree, but pasted text with emoji or rare CJK would shift every later highlight."""
    if all(ord(c) < 0x10000 for c in text):
        return lambda i: i
    prefix = [0]
    for c in text:
        prefix.append(prefix[-1] + (2 if ord(c) >= 0x10000 else 1))
    return lambda i: prefix[min(max(i, 0), len(text))]


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def create_passage(conn, title: str | None, text: str) -> int:
    norm = normalize(text)
    pid = conn.execute(
        "INSERT INTO passage(title, text_original, text_norm, text_hash) VALUES (?,?,?,?)",
        (title or None, text, norm, text_hash(norm)),
    ).lastrowid
    analyze_passage(conn, pid)
    return pid


def update_passage_text(conn, pid: int, title: str | None, text: str) -> None:
    norm = normalize(text)
    row = conn.execute("SELECT text_hash FROM passage WHERE id=?", (pid,)).fetchone()
    conn.execute("UPDATE passage SET title=? WHERE id=?", (title or None, pid))
    if row and row["text_hash"] == text_hash(norm):
        return                                   # unchanged: keep stored analysis, don't run Kiwi
    conn.execute("UPDATE passage SET text_original=?, text_norm=?, text_hash=? WHERE id=?", (text, norm, text_hash(norm), pid))
    conn.execute("DELETE FROM analysis_match WHERE passage_id=?", (pid,))   # offsets changed: overrides are void too
    analyze_passage(conn, pid, force=True)


def _drop_covered_not_found(matches: list[Match]) -> list[Match]:
    found = [m for m in matches if m.status != "NOT_FOUND"]
    keep = []
    for m in matches:
        if m.status == "NOT_FOUND" and any(f.start <= m.start and m.end <= f.end for f in found if f.layer == m.layer):
            continue
        keep.append(m)
    return keep


_cache: dict = {}


def _indexes(conn):
    """Vocabulary index + grammar rules. Cached per process only in read-only mode (the DB can't change there)."""
    if config.READ_ONLY and "idx" in _cache:
        return _cache["idx"]
    idx = (VocabIndex(conn), grammar_matcher.load_rules(conn))
    if config.READ_ONLY:
        _cache["idx"] = idx
    return idx


def compute(conn, text_norm: str):
    """Run Kiwi + both matchers. Pure: nothing is written."""
    _, sentences = analyze_text(text_norm)
    index, rules = _indexes(conn)
    matches: list[Match] = []
    for s in sentences:
        matches.extend(_drop_covered_not_found(index.match_sentence(s)))
        matches.extend(grammar_matcher.match_sentence(rules, s))
    return sentences, matches


def analyze_ephemeral(conn, title: str | None, text: str) -> dict:
    """Analysis without storing anything (public read-only deployment). Same payload shape as load_analysis;
    the client keeps it, so reopening a passage never re-runs Kiwi."""
    norm = normalize(text)
    sentences, matches = compute(conn, norm)
    out = []
    u16 = utf16_map(norm)
    for i, m in enumerate(sorted(matches, key=lambda m: (m.start, -m.end, m.layer)), 1):
        out.append({"id": i, "layer": m.layer, "surface": m.surface, "start": u16(m.start), "end": u16(m.end), "sentence_no": m.sentence_no,
                    "paragraph_no": m.paragraph_no, "dict_form": m.dict_form, "ref_id": m.ref_id, "match_type": m.match_type,
                    "status": m.status, "confidence": m.confidence, "rule_id": m.rule_id, "note": m.note, "candidates": m.candidates,
                    "manual_override": 0})
    return {"id": None, "title": title, "text": norm, "analysed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "stale": False, "matches": out,
            "sentences": [{"no": s.index, "paragraph_no": s.paragraph, "start": u16(s.start), "end": u16(s.end)} for s in sentences]}


def analyze_passage(conn, pid: int, force: bool = True) -> int:
    p = conn.execute("SELECT * FROM passage WHERE id=?", (pid,)).fetchone()
    if p is None:
        raise KeyError(pid)
    if not force and p["analysed_at"] and p["analyzer_version"] == config.ANALYZER_VERSION:
        return 0                                  # cached
    sentences, matches = compute(conn, p["text_norm"])
    overrides = {(r["layer"], r["start"], r["end"]) for r in
                 conn.execute("SELECT layer, start, \"end\" FROM analysis_match WHERE passage_id=? AND manual_override=1", (pid,))}
    conn.execute("DELETE FROM analysis_match WHERE passage_id=? AND manual_override=0", (pid,))
    conn.execute("DELETE FROM passage_sentence WHERE passage_id=?", (pid,))
    for s in sentences:
        conn.execute("INSERT INTO passage_sentence(passage_id,no,paragraph_no,start,\"end\") VALUES (?,?,?,?,?)",
                     (pid, s.index, s.paragraph, s.start, s.end))
    n = 0
    for m in matches:
        if (m.layer, m.start, m.end) in overrides:
            continue
        conn.execute(
            """INSERT INTO analysis_match(passage_id,layer,surface,start,"end",sentence_no,paragraph_no,dict_form,ref_id,
                   match_type,status,confidence,rule_id,candidates_json,note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (pid, m.layer, m.surface, m.start, m.end, m.sentence_no, m.paragraph_no, m.dict_form, m.ref_id,
             m.match_type, m.status, m.confidence, m.rule_id, json.dumps(m.candidates, ensure_ascii=False), m.note),
        )
        n += 1
    conn.execute(
        "UPDATE passage SET analyzer_version=?, rules_version=?, vocab_version=?, analysed_at=? WHERE id=?",
        (config.ANALYZER_VERSION, db.meta(conn, "rules_version"), db.meta(conn, "vocab_version"),
         datetime.now(timezone.utc).isoformat(timespec="seconds"), pid),
    )
    return n


def load_analysis(conn, pid: int) -> dict | None:
    p = conn.execute("SELECT * FROM passage WHERE id=?", (pid,)).fetchone()
    if p is None:
        return None
    u16 = utf16_map(p["text_norm"])
    matches = []
    for r in conn.execute('SELECT * FROM analysis_match WHERE passage_id=? ORDER BY start, "end" DESC', (pid,)):
        d = dict(r)
        d["candidates"] = json.loads(d.pop("candidates_json") or "[]")
        d["start"], d["end"] = u16(d["start"]), u16(d["end"])
        matches.append(d)
    sents = [dict(r, start=u16(r["start"]), end=u16(r["end"])) for r in conn.execute('SELECT no, paragraph_no, start, "end" FROM passage_sentence WHERE passage_id=? ORDER BY no', (pid,))]
    stale = bool(p["analysed_at"]) and (
        p["rules_version"] != db.meta(conn, "rules_version") or p["vocab_version"] != db.meta(conn, "vocab_version")
        or p["analyzer_version"] != config.ANALYZER_VERSION)
    return {
        "id": p["id"], "title": p["title"], "text": p["text_norm"], "analysed_at": p["analysed_at"],
        "stale": stale, "matches": matches, "sentences": sents,
    }

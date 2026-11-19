import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import Conn
from ..services import grammar_matcher
from ..services.korean_analyzer import analyze_text
from ..services.pattern_compiler import compile_pattern, pattern_key

router = APIRouter(prefix="/api")


class GrammarIn(BaseModel):
    pattern: str | None = None
    explanation_original: str | None = None
    explanation_ko: str | None = None
    meaning_en: str | None = None
    meaning_uz: str | None = None
    formation: str | None = None
    level: str | None = None
    unit: int | None = None
    page: int | None = None
    status: str | None = None
    example: str | None = None


class RuleTest(BaseModel):
    pattern: str
    sentence: str


def _public(r):
    d = dict(r)
    d["has_rule"] = d.pop("rule_json") is not None
    return d


@router.get("/grammar")
def list_grammar(q: str = "", level: str = "", status: str = "", compiled: str = "", limit: int = 100, offset: int = 0, conn=Conn):
    where, vals = [], []
    if q:
        where.append("(pattern LIKE ? OR meaning_uz LIKE ? OR meaning_en LIKE ?)"); vals += [f"%{q}%"] * 3
    if level:
        where.append("level=?"); vals.append(level)
    if status:
        where.append("status=?"); vals.append(status)
    if compiled in ("yes", "no"):
        where.append("rule_json IS NOT NULL" if compiled == "yes" else "rule_json IS NULL")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM grammar_item {w}", vals).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM grammar_item {w} ORDER BY level, CAST(entry_no AS REAL), id LIMIT ? OFFSET ?", (*vals, min(limit, 500), offset)).fetchall()
    return {"total": total, "items": [_public(r) for r in rows]}


@router.get("/grammar/{gid}")
def get_grammar(gid: int, conn=Conn):
    r = conn.execute("SELECT * FROM grammar_item WHERE id=?", (gid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = _public(r)
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM grammar_example WHERE grammar_id=?", (gid,))]
    return d


@router.post("/grammar")
def add_grammar(body: GrammarIn, conn=Conn):
    if not body.pattern:
        raise HTTPException(400, "pattern required")
    rule = compile_pattern(body.pattern)
    cur = conn.execute(
        """INSERT INTO grammar_item(pattern,pattern_key,rule_json,explanation_original,explanation_ko,meaning_en,meaning_uz,formation,
               level,unit,page,status,corrected) VALUES (?,?,?,?,?,?,?,?,?,?,?,'manual',1)""",
        (body.pattern, pattern_key(body.pattern), json.dumps(rule, ensure_ascii=False) if rule else None, body.explanation_original,
         body.explanation_ko, body.meaning_en, body.meaning_uz, body.formation, body.level, body.unit, body.page))
    if body.example:
        conn.execute("INSERT INTO grammar_example(grammar_id,sentence,source_ref) VALUES (?,?,?)", (cur.lastrowid, body.example, "manual"))
    db.bump(conn, "rules_version")
    return {"id": cur.lastrowid, "compiled": rule is not None}


@router.patch("/grammar/{gid}")
def edit_grammar(gid: int, body: GrammarIn, conn=Conn):
    data = body.model_dump(exclude_unset=True)
    example = data.pop("example", None)
    compiled = None
    if data:
        if data.get("pattern"):
            rule = compile_pattern(data["pattern"])
            compiled = rule is not None
            conn.execute("UPDATE grammar_item SET rule_json=?, pattern_key=? WHERE id=?",
                         (json.dumps(rule, ensure_ascii=False) if rule else None, pattern_key(data["pattern"]), gid))
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(f"UPDATE grammar_item SET {sets}, corrected=1 WHERE id=?", (*data.values(), gid))
    if example:
        conn.execute("INSERT INTO grammar_example(grammar_id,sentence,source_ref) VALUES (?,?,?)", (gid, example, "manual"))
    db.bump(conn, "rules_version")
    return {"ok": True, "compiled": compiled}


@router.delete("/grammar/{gid}")
def delete_grammar(gid: int, conn=Conn):
    conn.execute("DELETE FROM grammar_item WHERE id=?", (gid,))
    db.bump(conn, "rules_version")
    return {"ok": True}


@router.post("/grammar/test-rule")
def test_rule(body: RuleTest):
    """Admin helper: compile a notation and run it against one sentence (local Kiwi, nothing stored)."""
    rule = compile_pattern(body.pattern)
    if rule is None:
        return {"compiled": False, "matches": []}
    forms = [f for a in rule["alts"] for w in a["words"] for f in (w.get("alts") or [m[0] for m in w.get("morphs", [])])]
    r = grammar_matcher.Rule(0, body.pattern, pattern_key(body.pattern), None, "verified", rule["alts"], 1, False)
    _, sents = analyze_text(body.sentence)
    out = []
    for s in sents:
        for m in grammar_matcher.match_sentence([r], s):
            if m.layer == "grammar" and m.status != "NOT_FOUND":
                out.append({"surface": m.surface, "start": m.start, "end": m.end, "match_type": m.match_type})
    return {"compiled": True, "forms": forms, "matches": out}

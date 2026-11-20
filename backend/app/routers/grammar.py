from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import Conn, clamp_page
from ..services.common import pattern_key

router = APIRouter(prefix="/api")

# columns that exist for historical reasons but are no longer served (Uzbek glosses, raw OCR lines, compiled Kiwi rules)
HIDDEN = ("meaning_uz", "raw_text", "rule_json", "pattern_key")


class GrammarIn(BaseModel):
    pattern: str | None = None
    explanation_original: str | None = None
    explanation_ko: str | None = None
    meaning_en: str | None = None
    formation: str | None = None
    notes: str | None = None
    level: str | None = None
    unit: int | None = None
    page: int | None = None
    status: Literal['verified', 'needs_review', 'manual'] | None = None
    example: str | None = None


def _public(row) -> dict:
    d = dict(row)
    for k in HIDDEN:
        d.pop(k, None)
    return d


@router.get("/grammar")
def list_grammar(q: str = "", level: str = "", status: str = "", limit: int = 100, offset: int = 0, conn=Conn):
    where, vals = [], []
    if q:
        where.append("(pattern LIKE ? OR meaning_en LIKE ? OR explanation_original LIKE ?)"); vals += [f"%{q}%"] * 3
    if level:
        where.append("level=?"); vals.append(level)
    if status:
        where.append("status=?"); vals.append(status)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM grammar_item {w}", vals).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM grammar_item {w} ORDER BY level, CAST(entry_no AS REAL), id LIMIT ? OFFSET ?", (*vals, *clamp_page(limit, offset, 500))).fetchall()
    return {"total": total, "items": [_public(r) for r in rows]}


@router.get("/grammar/{gid}")
def get_grammar(gid: int, conn=Conn):
    r = conn.execute("SELECT * FROM grammar_item WHERE id=?", (gid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = _public(r)
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM grammar_example WHERE grammar_id=?", (gid,))]
    d["workbook"] = [dict(x) for x in conn.execute(
        "SELECT id, level, section, exercise_no, instruction, body, pdf_page, printed_page FROM workbook_item WHERE grammar_id=? ORDER BY pdf_page, id LIMIT 40", (gid,))]
    return d


@router.post("/grammar")
def add_grammar(body: GrammarIn, conn=Conn):
    if not body.pattern:
        raise HTTPException(400, "pattern required")
    cur = conn.execute(
        """INSERT INTO grammar_item(pattern,pattern_key,explanation_original,explanation_ko,meaning_en,formation,notes,
               level,unit,page,status,corrected) VALUES (?,?,?,?,?,?,?,?,?,?,'manual',1)""",
        (body.pattern, pattern_key(body.pattern), body.explanation_original, body.explanation_ko, body.meaning_en, body.formation, body.notes,
         body.level, body.unit, body.page))
    if body.example:
        conn.execute("INSERT INTO grammar_example(grammar_id,sentence,source_ref) VALUES (?,?,?)", (cur.lastrowid, body.example, "manual"))
    db.bump(conn, "rules_version")
    return {"id": cur.lastrowid}


@router.patch("/grammar/{gid}")
def edit_grammar(gid: int, body: GrammarIn, conn=Conn):
    data = body.model_dump(exclude_unset=True)
    example = data.pop("example", None)
    if data:
        if data.get("pattern"):
            conn.execute("UPDATE grammar_item SET pattern_key=? WHERE id=?", (pattern_key(data["pattern"]), gid))
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(f"UPDATE grammar_item SET {sets}, corrected=1 WHERE id=?", (*data.values(), gid))
    if example:
        conn.execute("INSERT INTO grammar_example(grammar_id,sentence,source_ref) VALUES (?,?,?)", (gid, example, "manual"))
    db.bump(conn, "rules_version")
    return {"ok": True}


@router.delete("/grammar/{gid}")
def delete_grammar(gid: int, conn=Conn):
    conn.execute("DELETE FROM grammar_item WHERE id=?", (gid,))
    db.bump(conn, "rules_version")
    return {"ok": True}

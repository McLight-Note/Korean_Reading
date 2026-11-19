from fastapi import APIRouter, HTTPException

from ..deps import Conn, clamp_page

router = APIRouter(prefix="/api")

SECTION_LABELS = {
    "vocabulary": "Vocabulary", "grammar": "Grammar & expression", "pattern_practice": "Pattern practice", "listening": "Listening",
    "reading": "Reading", "writing": "Writing", "speaking": "Speaking", "review": "Review", "task": "Task", "expression": "Expression practice",
    "pronunciation": "Pronunciation", "script": "Listening script",
}


@router.get("/workbook")
def list_workbook(level: str = "", section: str = "", q: str = "", grammar_id: int = 0, limit: int = 40, offset: int = 0, conn=Conn):
    where, vals = [], []
    if level:
        where.append("w.level=?"); vals.append(level)
    if section:
        where.append("w.section=?"); vals.append(section)
    if grammar_id:
        where.append("w.grammar_id=?"); vals.append(grammar_id)
    if q:
        where.append("(w.body LIKE ? OR w.instruction LIKE ? OR w.heading LIKE ?)"); vals += [f"%{q}%"] * 3
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM workbook_item w {w}", vals).fetchone()[0]
    rows = conn.execute(
        f"""SELECT w.id, w.level, w.section, w.unit, w.heading, w.exercise_no, w.instruction, w.body, w.pdf_page, w.printed_page,
                   w.grammar_id, g.pattern AS grammar_pattern
            FROM workbook_item w LEFT JOIN grammar_item g ON g.id=w.grammar_id {w}
            ORDER BY w.level, w.pdf_page, w.id LIMIT ? OFFSET ?""", (*vals, *clamp_page(limit, offset, 100))).fetchall()
    return {"total": total, "items": [dict(r) for r in rows], "sections": SECTION_LABELS}


@router.get("/workbook/{wid}")
def get_workbook(wid: int, conn=Conn):
    r = conn.execute("SELECT * FROM workbook_item WHERE id=?", (wid,)).fetchone()
    if not r:
        raise HTTPException(404)
    return dict(r)

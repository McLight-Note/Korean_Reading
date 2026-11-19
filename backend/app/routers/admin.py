"""Review queue / manual-correction API (the human-in-the-loop for OCR'd textbook data)."""
import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from .. import db
from ..deps import Conn
from ..services import calibration

router = APIRouter(prefix="/api/admin")


class ApproveIn(BaseModel):
    kind: str                      # 'grammar' | 'vocab'
    ids: list[int] | None = None
    level: str | None = None       # bulk: every needs_review item of this level (optionally with an explanation)
    source_id: int | None = None
    only_with_explanation: bool = False


class MergeIn(BaseModel):
    from_id: int
    into_id: int


class ExampleIn(BaseModel):
    sentence: str
    source_ref: str | None = "manual"


def _page(conn, source_id, pdf_page):
    if not source_id or not pdf_page:
        return None
    r = conn.execute("SELECT source_id, pdf_page, text, image_path FROM ocr_page WHERE source_id=? AND pdf_page=?", (source_id, pdf_page)).fetchone()
    if not r:
        return None
    d = dict(r)
    d["image_url"] = f"/ocr/{d.pop('image_path')}" if d["image_path"] else None
    return d


@router.get("/queue")
def queue(kind: str = "grammar", status: str = "needs_review", level: str = "", q: str = "", has_explanation: str = "", compiled: str = "",
          limit: int = 60, offset: int = 0, conn=Conn):
    table = "grammar_item" if kind == "grammar" else "vocab_entry"
    label = "pattern" if kind == "grammar" else "headword"
    where, vals = [], []
    if status:
        where.append("status=?"); vals.append(status)
    if level:
        where.append("level=?"); vals.append(level)
    if q:
        where.append(f"({label} LIKE ? OR meaning_uz LIKE ?)"); vals += [f"%{q}%"] * 2
    if kind == "grammar" and has_explanation in ("yes", "no"):
        where.append("explanation_original IS NOT NULL" if has_explanation == "yes" else "explanation_original IS NULL")
    if kind == "grammar" and compiled in ("yes", "no"):
        where.append("rule_json IS NOT NULL" if compiled == "yes" else "rule_json IS NULL")
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM {table} {w}", vals).fetchone()[0]
    cols = "id, pattern AS label, level, unit, page, status, entry_no, meaning_uz, (explanation_original IS NOT NULL) AS has_expl, (rule_json IS NOT NULL) AS has_rule" if kind == "grammar" \
        else "id, headword AS label, level, unit, status, meaning_uz, pdf_page"
    order = "level, CAST(entry_no AS REAL), id" if kind == "grammar" else "level, unit, id"
    rows = conn.execute(f"SELECT {cols} FROM {table} {w} ORDER BY {order} LIMIT ? OFFSET ?", (*vals, min(limit, 200), offset)).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/grammar/{gid}")
def grammar_review(gid: int, conn=Conn):
    r = conn.execute("SELECT * FROM grammar_item WHERE id=?", (gid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["has_rule"] = d.pop("rule_json") is not None
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM grammar_example WHERE grammar_id=?", (gid,))]
    idx = conn.execute("SELECT id FROM source WHERE kind='grammar_index'").fetchone()
    return {"item": d, "book_page": _page(conn, d["source_id"], d["pdf_page"]) if d["explanation_original"] else None,
            "index_page": _page(conn, idx["id"] if idx else None, d["index_page"])}


@router.get("/vocab/{vid}")
def vocab_review(vid: int, conn=Conn):
    r = conn.execute("SELECT * FROM vocab_entry WHERE id=?", (vid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    pg = conn.execute("SELECT text FROM ocr_page WHERE source_id=? AND pdf_page=?", (d["source_id"], d["pdf_page"])).fetchone()
    return {"item": d, "page_text": pg["text"] if pg else None}


@router.post("/approve")
def approve(body: ApproveIn, conn=Conn):
    table = "grammar_item" if body.kind == "grammar" else "vocab_entry"
    where, vals = ["status='needs_review'"], []
    if body.ids:
        where.append(f"id IN ({','.join('?' * len(body.ids))})"); vals += body.ids
    elif body.level or body.source_id:
        if body.level:
            where.append("level=?"); vals.append(body.level)
        if body.source_id:
            where.append("source_id=?"); vals.append(body.source_id)
        if body.kind == "grammar" and body.only_with_explanation:
            where.append("explanation_original IS NOT NULL")
    else:
        raise HTTPException(400, "give ids or a level/source filter")
    n = conn.execute(f"UPDATE {table} SET status='verified' WHERE {' AND '.join(where)}", vals).rowcount
    db.bump(conn, "rules_version" if body.kind == "grammar" else "vocab_version")
    return {"approved": n}


@router.post("/grammar/merge")
def merge(body: MergeIn, conn=Conn):
    a = conn.execute("SELECT * FROM grammar_item WHERE id=?", (body.from_id,)).fetchone()
    b = conn.execute("SELECT * FROM grammar_item WHERE id=?", (body.into_id,)).fetchone()
    if not a or not b or a["id"] == b["id"]:
        raise HTTPException(400, "two different existing items are required")
    uz = " | ".join(dict.fromkeys(x for x in (b["meaning_uz"], a["meaning_uz"]) if x)) or None
    conn.execute("UPDATE grammar_example SET grammar_id=? WHERE grammar_id=?", (b["id"], a["id"]))
    conn.execute("UPDATE grammar_item SET meaning_uz=?, corrected=1 WHERE id=?", (uz, b["id"]))
    conn.execute("UPDATE analysis_match SET ref_id=? WHERE layer='grammar' AND ref_id=?", (b["id"], a["id"]))
    conn.execute("DELETE FROM grammar_item WHERE id=?", (a["id"],))
    db.bump(conn, "rules_version")
    return {"ok": True}


@router.post("/grammar/{gid}/examples")
def add_example(gid: int, body: ExampleIn, conn=Conn):
    conn.execute("INSERT INTO grammar_example(grammar_id, sentence, source_ref) VALUES (?,?,?)", (gid, body.sentence, body.source_ref))
    return {"ok": True}


@router.delete("/grammar-examples/{eid}")
def delete_example(eid: int, conn=Conn):
    conn.execute("DELETE FROM grammar_example WHERE id=?", (eid,))
    db.bump(conn, "rules_version")
    return {"ok": True}


@router.get("/calibration")
def get_calibration(level: str = "", conn=Conn):
    return calibration.run(conn, level or None)

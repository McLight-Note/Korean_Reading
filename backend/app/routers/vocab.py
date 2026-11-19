from fastapi import APIRouter, HTTPException
from typing import Literal

from pydantic import BaseModel

from .. import db
from ..deps import Conn, clamp_page
from ..services.korean_analyzer import coarse_pos, headword_lemma_keys

router = APIRouter(prefix="/api")


class VocabIn(BaseModel):
    headword: str | None = None
    meaning_en: str | None = None
    meaning_uz: str | None = None
    meaning_ko: str | None = None
    pos: str | None = None
    level: str | None = None
    unit: int | None = None
    status: Literal['verified', 'needs_review', 'manual'] | None = None
    example: str | None = None


def _rekey(conn, vid: int, headword: str):
    conn.execute("DELETE FROM vocab_key WHERE entry_id=?", (vid,))
    for k in headword_lemma_keys(headword):
        conn.execute("INSERT INTO vocab_key(entry_id,key) VALUES (?,?)", (vid, k))


@router.get("/vocab")
def list_vocab(q: str = "", level: str = "", status: str = "", limit: int = 50, offset: int = 0, conn=Conn):
    where, vals = [], []
    if q:
        where.append("(headword LIKE ? OR meaning_uz LIKE ? OR meaning_en LIKE ?)"); vals += [f"%{q}%"] * 3
    if level:
        where.append("level=?"); vals.append(level)
    if status:
        where.append("status=?"); vals.append(status)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM vocab_entry {w}", vals).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM vocab_entry {w} ORDER BY level, unit, id LIMIT ? OFFSET ?", (*vals, *clamp_page(limit, offset, 200))).fetchall()
    return {"total": total, "items": [dict(r) for r in rows]}


@router.get("/vocab/{vid}")
def get_vocab(vid: int, conn=Conn):
    r = conn.execute("SELECT * FROM vocab_entry WHERE id=?", (vid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = dict(r)
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM vocab_example WHERE vocab_id=?", (vid,))]
    return d


@router.post("/vocab")
def add_vocab(body: VocabIn, conn=Conn):
    if not body.headword:
        raise HTTPException(400, "headword required")
    cur = conn.execute(
        """INSERT INTO vocab_entry(headword,pos,pos_source,meaning_uz,meaning_en,meaning_ko,level,unit,status,corrected)
           VALUES (?,?,?,?,?,?,?,?,'manual',1)""",
        (body.headword, body.pos or coarse_pos(body.headword), "manual" if body.pos else "kiwi", body.meaning_uz, body.meaning_en,
         body.meaning_ko, body.level, body.unit))
    _rekey(conn, cur.lastrowid, body.headword)
    if body.example:
        conn.execute("INSERT INTO vocab_example(vocab_id,sentence,source_ref) VALUES (?,?,?)", (cur.lastrowid, body.example, "manual"))
    db.bump(conn, "vocab_version")
    return {"id": cur.lastrowid}


@router.patch("/vocab/{vid}")
def edit_vocab(vid: int, body: VocabIn, conn=Conn):
    data = body.model_dump(exclude_unset=True)
    example = data.pop("example", None)
    if data:
        sets = ", ".join(f"{k}=?" for k in data)
        conn.execute(f"UPDATE vocab_entry SET {sets}, corrected=1 WHERE id=?", (*data.values(), vid))
        if "pos" in data:
            conn.execute("UPDATE vocab_entry SET pos_source='manual' WHERE id=?", (vid,))
        if data.get("headword"):
            _rekey(conn, vid, data["headword"])
    if example:
        conn.execute("INSERT INTO vocab_example(vocab_id,sentence,source_ref) VALUES (?,?,?)", (vid, example, "manual"))
    db.bump(conn, "vocab_version")
    return {"ok": True}


@router.delete("/vocab/{vid}")
def delete_vocab(vid: int, conn=Conn):
    conn.execute("DELETE FROM vocab_entry WHERE id=?", (vid,))
    db.bump(conn, "vocab_version")
    return {"ok": True}

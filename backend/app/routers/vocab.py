from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import db
from ..deps import Conn, clamp_page
from ..services import lookup

router = APIRouter(prefix="/api")

# columns that exist for historical reasons but are no longer served (Uzbek glosses, raw lines, Kiwi guesses)
HIDDEN = ("meaning_uz", "meaning_ko", "raw_text", "pos", "pos_source")


class VocabIn(BaseModel):
    headword: str | None = None
    meaning_en: str | None = None
    level: str | None = None
    unit: int | None = None
    status: Literal['verified', 'needs_review', 'manual'] | None = None
    example: str | None = None


class LookupIn(BaseModel):
    tokens: list[str] = Field(max_length=1500)


def _public(row) -> dict:
    d = dict(row)
    for k in HIDDEN:
        d.pop(k, None)
    return d


@router.get("/vocab")
def list_vocab(q: str = "", level: str = "", status: str = "", limit: int = 50, offset: int = 0, conn=Conn):
    where, vals = [], []
    if q:
        where.append("(headword LIKE ? OR meaning_en LIKE ?)"); vals += [f"%{q}%"] * 2
    if level:
        where.append("level=?"); vals.append(level)
    if status:
        where.append("status=?"); vals.append(status)
    w = ("WHERE " + " AND ".join(where)) if where else ""
    total = conn.execute(f"SELECT COUNT(*) FROM vocab_entry {w}", vals).fetchone()[0]
    rows = conn.execute(f"SELECT * FROM vocab_entry {w} ORDER BY level, unit, id LIMIT ? OFFSET ?", (*vals, *clamp_page(limit, offset, 200))).fetchall()
    return {"total": total, "items": [_public(r) for r in rows]}


@router.get("/vocab/{vid}")
def get_vocab(vid: int, conn=Conn):
    r = conn.execute("SELECT * FROM vocab_entry WHERE id=?", (vid,)).fetchone()
    if not r:
        raise HTTPException(404)
    d = _public(r)
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM vocab_example WHERE vocab_id=?", (vid,))]
    return d


@router.post("/vocab/lookup")
def vocab_lookup(body: LookupIn, conn=Conn):
    """Which of these words are in the textbook word list? Approximate (plain rules, no morphology). See services/lookup.py."""
    tokens = [t[:30] for t in body.tokens]
    return {"matches": lookup.lookup(conn, tokens), "approximate": True}


@router.post("/vocab")
def add_vocab(body: VocabIn, conn=Conn):
    if not body.headword:
        raise HTTPException(400, "headword required")
    cur = conn.execute("INSERT INTO vocab_entry(headword, meaning_en, level, unit, status, corrected) VALUES (?,?,?,?,'manual',1)",
                       (body.headword, body.meaning_en, body.level, body.unit))
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
    if example:
        conn.execute("INSERT INTO vocab_example(vocab_id,sentence,source_ref) VALUES (?,?,?)", (vid, example, "manual"))
    db.bump(conn, "vocab_version")
    return {"ok": True}


@router.delete("/vocab/{vid}")
def delete_vocab(vid: int, conn=Conn):
    conn.execute("DELETE FROM vocab_entry WHERE id=?", (vid,))
    db.bump(conn, "vocab_version")
    return {"ok": True}

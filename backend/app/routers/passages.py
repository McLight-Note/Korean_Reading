import json

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..deps import Conn
from ..services import sentence_analyzer as sa

router = APIRouter(prefix="/api")


class PassageIn(BaseModel):
    title: str | None = None
    text: str


class OverrideIn(BaseModel):
    ref_id: int | None = None
    status: str | None = None
    match_type: str | None = None
    note: str | None = None


@router.get("/passages")
def list_passages(conn=Conn):
    return [dict(r) for r in conn.execute(
        "SELECT id, title, substr(text_norm,1,80) AS preview, analysed_at, created_at FROM passage ORDER BY id DESC")]


@router.post("/passages")
def create_passage(body: PassageIn, conn=Conn):
    if not body.text.strip():
        raise HTTPException(400, "Passage text is empty")
    pid = sa.create_passage(conn, body.title, body.text)
    return sa.load_analysis(conn, pid)


@router.get("/passages/{pid}")
def get_passage(pid: int, conn=Conn):
    a = sa.load_analysis(conn, pid)           # stored results only: Kiwi is NOT run here
    if a is None:
        raise HTTPException(404)
    return a


@router.put("/passages/{pid}")
def update_passage(pid: int, body: PassageIn, conn=Conn):
    if conn.execute("SELECT 1 FROM passage WHERE id=?", (pid,)).fetchone() is None:
        raise HTTPException(404)
    sa.update_passage_text(conn, pid, body.title, body.text)
    return sa.load_analysis(conn, pid)


@router.post("/passages/{pid}/reanalyze")
def reanalyze(pid: int, conn=Conn):
    if conn.execute("SELECT 1 FROM passage WHERE id=?", (pid,)).fetchone() is None:
        raise HTTPException(404)
    sa.analyze_passage(conn, pid, force=True)
    return sa.load_analysis(conn, pid)


@router.delete("/passages/{pid}")
def delete_passage(pid: int, conn=Conn):
    conn.execute("DELETE FROM passage WHERE id=?", (pid,))
    return {"ok": True}


def _vocab_entry(conn, vid):
    r = conn.execute("SELECT v.*, s.filename AS source_file FROM vocab_entry v LEFT JOIN source s ON s.id=v.source_id WHERE v.id=?", (vid,)).fetchone()
    return dict(r) if r else None


def _grammar_item(conn, gid):
    r = conn.execute("SELECT g.*, s.filename AS source_file FROM grammar_item g LEFT JOIN source s ON s.id=g.source_id WHERE g.id=?", (gid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    d.pop("rule_json", None)
    d["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM grammar_example WHERE grammar_id=?", (gid,))]
    return d


@router.get("/matches/{mid}")
def match_detail(mid: int, conn=Conn):
    m = conn.execute("SELECT * FROM analysis_match WHERE id=?", (mid,)).fetchone()
    if m is None:
        raise HTTPException(404)
    m = dict(m)
    cands = json.loads(m.pop("candidates_json") or "[]")
    out = {"match": {**m, "candidates": cands}, "item": None, "candidate_items": []}
    get = _vocab_entry if m["layer"] == "vocab" else _grammar_item
    if m["ref_id"]:
        out["item"] = get(conn, m["ref_id"])
    for c in cands:
        if c["id"] != m["ref_id"]:
            it = get(conn, c["id"])
            if it:
                out["candidate_items"].append(it)
    if m["layer"] == "vocab" and m["ref_id"]:
        out["item"]["examples"] = [dict(x) for x in conn.execute("SELECT id, sentence, source_ref FROM vocab_example WHERE vocab_id=?", (m["ref_id"],))]
    s = conn.execute('SELECT start, "end" FROM passage_sentence WHERE passage_id=? AND no=?', (m["passage_id"], m["sentence_no"])).fetchone()
    out["sentence"] = dict(s) if s else None
    return out


@router.patch("/matches/{mid}")
def override_match(mid: int, body: OverrideIn, conn=Conn):
    """Manual correction: pin a different textbook reference / status. Survives re-analysis."""
    sets, vals = ["manual_override=1"], []
    if body.ref_id is not None:
        sets.append("ref_id=?"); vals.append(body.ref_id or None)
    if body.status:
        if body.status not in ("VERIFIED", "LIKELY", "NEEDS_REVIEW", "NOT_FOUND"):
            raise HTTPException(400, "bad status")
        sets.append("status=?"); vals.append(body.status)
    if body.match_type:
        sets.append("match_type=?"); vals.append(body.match_type)
    if body.note is not None:
        sets.append("note=?"); vals.append(body.note)
    conn.execute(f"UPDATE analysis_match SET {', '.join(sets)} WHERE id=?", (*vals, mid))
    return {"ok": True}

from fastapi import APIRouter
from pydantic import BaseModel

from ..deps import Conn

router = APIRouter(prefix="/api")


class SaveIn(BaseModel):
    kind: str
    ref_id: int
    passage_id: int | None = None
    sentence: str | None = None


@router.get("/overview")
def overview(conn=Conn):
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "vocab": q("SELECT COUNT(*) FROM vocab_entry"),
        "vocab_needs_review": q("SELECT COUNT(*) FROM vocab_entry WHERE status='needs_review'"),
        "vocab_with_english": q("SELECT COUNT(*) FROM vocab_entry WHERE meaning_en IS NOT NULL AND meaning_en<>''"),
        "grammar": q("SELECT COUNT(*) FROM grammar_item"),
        "grammar_detectable": q("SELECT COUNT(*) FROM grammar_item WHERE rule_json IS NOT NULL"),
        "grammar_needs_review": q("SELECT COUNT(*) FROM grammar_item WHERE status='needs_review'"),
        "grammar_with_explanation": q("SELECT COUNT(*) FROM grammar_item WHERE explanation_original IS NOT NULL AND explanation_original<>''"),
        "passages": q("SELECT COUNT(*) FROM passage"),
        "saved": q("SELECT COUNT(*) FROM saved_item"),
        "sources": [dict(r) for r in conn.execute("SELECT filename, kind, level, imported_at FROM source")],
    }


@router.get("/saved")
def list_saved(conn=Conn):
    out = []
    for r in conn.execute("SELECT * FROM saved_item ORDER BY id DESC"):
        d = dict(r)
        if r["kind"] == "vocab":
            e = conn.execute("SELECT headword, meaning_uz, meaning_en, level, unit FROM vocab_entry WHERE id=?", (r["ref_id"],)).fetchone()
        else:
            e = conn.execute("SELECT pattern AS headword, meaning_uz, meaning_en, level, unit FROM grammar_item WHERE id=?", (r["ref_id"],)).fetchone()
        d["item"] = dict(e) if e else None
        out.append(d)
    return out


@router.post("/saved")
def save_item(body: SaveIn, conn=Conn):
    conn.execute("INSERT OR REPLACE INTO saved_item(kind,ref_id,passage_id,sentence) VALUES (?,?,?,?)",
                 (body.kind, body.ref_id, body.passage_id, body.sentence))
    return {"ok": True}


@router.delete("/saved/{sid}")
def unsave(sid: int, conn=Conn):
    conn.execute("DELETE FROM saved_item WHERE id=?", (sid,))
    return {"ok": True}

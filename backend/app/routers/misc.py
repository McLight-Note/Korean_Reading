from fastapi import APIRouter

from .. import config
from ..deps import Conn

router = APIRouter(prefix="/api")


@router.get("/config")
def app_config():
    return {"read_only": config.READ_ONLY}


@router.get("/overview")
def overview(conn=Conn):
    q = lambda sql: conn.execute(sql).fetchone()[0]
    return {
        "vocab": q("SELECT COUNT(*) FROM vocab_entry"),
        "vocab_needs_review": q("SELECT COUNT(*) FROM vocab_entry WHERE status='needs_review'"),
        "grammar": q("SELECT COUNT(*) FROM grammar_item"),
        "grammar_needs_review": q("SELECT COUNT(*) FROM grammar_item WHERE status='needs_review'"),
        "grammar_with_explanation": q("SELECT COUNT(*) FROM grammar_item WHERE explanation_original IS NOT NULL AND explanation_original<>''"),
        "workbook_items": q("SELECT COUNT(*) FROM workbook_item"),
        "sources": [dict(r) for r in conn.execute("SELECT filename, kind, level, imported_at FROM source")],
    }

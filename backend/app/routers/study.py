import json
import random

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..deps import Conn
from ..services import exercises, srs

router = APIRouter(prefix="/api/study")
MAX_STATE_BYTES = 3_000_000


class CardState(BaseModel):
    ease: float = Field(2.5, ge=1.3, le=10)
    interval: int = Field(0, ge=0, le=36500)
    reps: int = Field(0, ge=0, le=100000)
    lapses: int = Field(0, ge=0, le=100000)
    due: str | None = None
    last: str | None = None


class ScheduleIn(BaseModel):
    state: CardState | None = None
    grade: int = Field(ge=0, le=3)
    today: str


class CheckIn(BaseModel):
    grammar_id: int
    text: str


class StateIn(BaseModel):
    state: dict


@router.post("/schedule")
def schedule(body: ScheduleIn):
    """Stateless SM-2 step: the client keeps the card state (server DB locally, browser storage when deployed)."""
    try:
        return srs.schedule(body.state.model_dump() if body.state else None, body.grade, body.today)
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.get("/exercises")
def get_exercises(type: str = "grammar_mcq", level: str = "", n: int = 10, seed: int | None = None, include_unreviewed: bool = True, conn=Conn):
    rng = random.Random(seed)
    n = max(1, min(n, 30))
    if type == "grammar_mcq":
        items = exercises.grammar_mcq(conn, level, n, rng, include_unreviewed)
    elif type in ("vocab_mcq", "vocab_rev"):
        items = exercises.vocab_mcq(conn, level, n, rng, reverse=type == "vocab_rev")
    else:
        raise HTTPException(400, "unknown exercise type")
    return {"type": type, "level": level, "count": len(items), "items": items}


@router.post("/check")
def check(body: CheckIn, conn=Conn):
    if len(body.text) > 600:
        raise HTTPException(413, "answer too long")
    return exercises.check_answer(conn, body.grammar_id, body.text)


@router.get("/state")
def get_state(conn=Conn):
    if config.READ_ONLY:
        raise HTTPException(404)
    row = conn.execute("SELECT json FROM study_state WHERE id=1").fetchone()
    return json.loads(row["json"]) if row else {}


@router.put("/state")
def put_state(body: StateIn, conn=Conn):
    blob = json.dumps(body.state, ensure_ascii=False)
    if len(blob.encode("utf-8")) > MAX_STATE_BYTES:
        raise HTTPException(413, "study state too large")
    conn.execute("INSERT INTO study_state(id, json, updated_at) VALUES (1, ?, CURRENT_TIMESTAMP) ON CONFLICT(id) DO UPDATE SET json=excluded.json, updated_at=CURRENT_TIMESTAMP", (blob,))
    return {"ok": True}

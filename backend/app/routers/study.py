from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services import srs

router = APIRouter(prefix="/api/study")


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


@router.post("/schedule")
def schedule(body: ScheduleIn):
    """Stateless SM-2 step: the client keeps the card state (in its browser, or in the visitor's Firestore space)."""
    try:
        return srs.schedule(body.state.model_dump() if body.state else None, body.grade, body.today)
    except ValueError as e:
        raise HTTPException(400, str(e))

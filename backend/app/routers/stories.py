from fastapi import APIRouter, HTTPException

from ..deps import Conn
from ..services import stories

router = APIRouter(prefix="/api")


@router.get("/stories")
def list_stories():
    return {"stories": [stories.summary(s) for s in stories.load_all()]}


@router.get("/stories/{story_id}")
def get_story(story_id: str, conn=Conn):
    s = stories.get(story_id)
    if s is None:
        raise HTTPException(404, "unknown story")
    return stories.detail(conn, s)

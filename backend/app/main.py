from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import grammar, misc, passages, vocab

app = FastAPI(title="Korean Reading (textbook-based, local only)")
for r in (passages.router, vocab.router, grammar.router, misc.router):
    app.include_router(r)

app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")

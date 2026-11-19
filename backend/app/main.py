from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import admin, grammar, misc, passages, vocab

app = FastAPI(title="Korean Reading (textbook-based, local only)")
for r in (passages.router, vocab.router, grammar.router, misc.router, admin.router):
    app.include_router(r)

(config.DATA_DIR / "ocr").mkdir(parents=True, exist_ok=True)
app.mount("/ocr", StaticFiles(directory=config.DATA_DIR / "ocr"), name="ocr")   # page images for the review UI
app.mount("/static", StaticFiles(directory=config.FRONTEND_DIR), name="static")


@app.get("/")
def index():
    return FileResponse(config.FRONTEND_DIR / "index.html")

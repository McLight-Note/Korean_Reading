import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import admin, grammar, misc, stories, study, vocab, workbook

app = FastAPI(title="Korean Reading (textbook-based)")

# POSTs that only compute something and store nothing, so they are safe on the read-only deployment
STATELESS_POSTS = ("/api/study/schedule", "/api/vocab/lookup")


@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    """Public deployment: only reads and the stateless POSTs above may run. Admin routes are closed entirely."""
    if config.READ_ONLY and request.url.path.startswith("/api/"):
        allowed_post = request.method == "POST" and request.url.path in STATELESS_POSTS
        if request.url.path.startswith("/api/admin") or (request.method not in ("GET", "HEAD", "OPTIONS") and not allowed_post):
            return JSONResponse({"detail": "This is a read-only deployment."}, status_code=403)
    return await call_next(request)


for r in (vocab.router, grammar.router, misc.router, admin.router, workbook.router, study.router, stories.router):
    app.include_router(r)

if not config.READ_ONLY:                      # page images for the local review UI (never deployed)
    (config.DATA_DIR / "ocr").mkdir(parents=True, exist_ok=True)
    app.mount("/ocr", StaticFiles(directory=config.DATA_DIR / "ocr"), name="ocr")

# Locally FastAPI serves public/; on Vercel the CDN serves public/ itself (do not mount it there).
if not os.environ.get("VERCEL"):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="public")

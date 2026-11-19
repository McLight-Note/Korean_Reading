import os

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from . import config
from .routers import admin, grammar, misc, passages, study, vocab, workbook

app = FastAPI(title="Korean Reading (textbook-based, no external AI)")


@app.middleware("http")
async def read_only_guard(request: Request, call_next):
    """Public deployment: only reads and the stateless /api/analyze may run. Admin routes are closed entirely."""
    if config.READ_ONLY and request.url.path.startswith("/api/"):
        allowed_post = request.method == "POST" and request.url.path in ("/api/analyze", "/api/study/schedule", "/api/study/check")   # stateless
        if request.url.path.startswith("/api/admin") or (request.method not in ("GET", "HEAD", "OPTIONS") and not allowed_post):
            return JSONResponse({"detail": "This is a read-only deployment."}, status_code=403)
    return await call_next(request)


for r in (passages.router, vocab.router, grammar.router, misc.router, admin.router, workbook.router, study.router):
    app.include_router(r)

if not config.READ_ONLY:                      # page images for the local review UI (never deployed)
    (config.DATA_DIR / "ocr").mkdir(parents=True, exist_ok=True)
    app.mount("/ocr", StaticFiles(directory=config.DATA_DIR / "ocr"), name="ocr")

# Locally FastAPI serves public/; on Vercel the CDN serves public/ itself (do not mount it there).
if not os.environ.get("VERCEL"):
    app.mount("/", StaticFiles(directory=config.FRONTEND_DIR, html=True), name="public")

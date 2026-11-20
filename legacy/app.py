"""Vercel entrypoint (it looks for `app` in app.py). The application itself lives in backend/app/main.py."""
from backend.app.main import app  # noqa: F401

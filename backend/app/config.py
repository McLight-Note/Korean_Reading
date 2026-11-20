import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = ROOT / "data"
# Read-only mode (public deployment): the bundled database is opened immutable and every write/admin endpoint is
# refused. Passages, saved words and study progress never live in this database: they are kept in the visitor's
# browser or, when signed in, in their own Firestore space.
READ_ONLY = os.environ.get("KR_READ_ONLY", "").lower() in ("1", "true", "yes") or bool(os.environ.get("VERCEL"))   # Vercel is always read-only
DB_PATH = (Path(os.environ["KR_DB_PATH"]) if os.environ.get("KR_DB_PATH")
           else ROOT / "deploy" / "app.sqlite" if READ_ONLY else DATA_DIR / "app.sqlite")
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
FRONTEND_DIR = ROOT / "public"   # also served as the CDN root on Vercel

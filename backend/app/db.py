import sqlite3
from contextlib import contextmanager
from pathlib import Path

from . import config


def connect(path=None) -> sqlite3.Connection:
    p = path or config.DB_PATH
    if config.READ_ONLY:
        if not Path(p).exists():
            raise RuntimeError(f"read-only database not found: {p} (build it with scripts/build_deploy_db.py and deploy with the CLI)")
        conn = sqlite3.connect(Path(p).resolve().as_uri() + "?mode=ro&immutable=1", uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), check_same_thread=False)   # a request is handled sequentially, but FastAPI may hop worker threads between dependency and endpoint
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    if config.READ_ONLY:
        return
    conn.executescript(config.SCHEMA_PATH.read_text(encoding="utf-8"))
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(grammar_item)")}
    for col in ("entry_no", "raw_text", "notes", "index_page"):                      # migrate DBs created before these columns existed
        if col not in cols:
            conn.execute(f"ALTER TABLE grammar_item ADD COLUMN {col} TEXT")
    conn.commit()


@contextmanager
def session(path=None):
    conn = connect(path)
    try:
        init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def bump(conn: sqlite3.Connection, key: str) -> None:
    """Increment vocab_version / rules_version so cached analyses can be flagged stale."""
    conn.execute("UPDATE meta SET value = CAST(value AS INTEGER) + 1 WHERE key = ?", (key,))


def meta(conn: sqlite3.Connection, key: str) -> str:
    row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""

import sqlite3
from contextlib import contextmanager

from . import config


def connect(path=None) -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path or config.DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(conn: sqlite3.Connection) -> None:
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

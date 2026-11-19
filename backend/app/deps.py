from fastapi import Depends

from . import config, db


def get_conn():
    conn = db.connect()
    try:
        db.init_db(conn)
        yield conn
        if not config.READ_ONLY:
            conn.commit()
    finally:
        conn.close()


Conn = Depends(get_conn)


def clamp_page(limit: int, offset: int, max_limit: int) -> tuple[int, int]:
    """SQLite treats a negative LIMIT as 'no limit', so clamp both ends."""
    return max(1, min(limit, max_limit)), max(0, offset)

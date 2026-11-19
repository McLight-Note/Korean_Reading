from fastapi import Depends

from . import db


def get_conn():
    conn = db.connect()
    try:
        db.init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


Conn = Depends(get_conn)

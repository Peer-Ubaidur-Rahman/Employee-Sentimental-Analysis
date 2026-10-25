"""
db.py - PyMySQL access layer. ALL queries use %s placeholders with a params tuple
(parameterized), never string formatting of user input.

One connection per request (stored on flask.g) and closed automatically at teardown.
PyMySQL is imported lazily so unit tests that never touch the DB run without it.
"""
import logging
from contextlib import contextmanager

from flask import current_app, g

log = logging.getLogger(__name__)


class DatabaseUnavailable(RuntimeError):
    """Raised when MySQL cannot be reached or a query fails unexpectedly."""


def _connect(cfg):
    try:
        import pymysql
        from pymysql.cursors import DictCursor
    except ImportError as exc:  # pragma: no cover
        raise DatabaseUnavailable("PyMySQL is not installed. Run: pip install -r requirements.txt") from exc
    try:
        return pymysql.connect(
            host=cfg["DB_HOST"], port=cfg["DB_PORT"], user=cfg["DB_USER"], password=cfg["DB_PASSWORD"],
            database=cfg["DB_NAME"], charset="utf8mb4", cursorclass=DictCursor,
            autocommit=False, connect_timeout=5)
    except pymysql.MySQLError as exc:
        log.error("MySQL connection failed: %s", exc)
        raise DatabaseUnavailable("Cannot connect to the database.") from exc


def get_db():
    if "db" not in g:
        g.db = _connect(current_app.config)
    return g.db


def close_db(_exc=None):
    conn = g.pop("db", None)
    if conn is not None:
        try:
            conn.close()
        except Exception:  # pragma: no cover
            pass


def init_app(app):
    app.teardown_appcontext(close_db)


def _run(cursor, sql, params):
    try:
        cursor.execute(sql, params or ())
    except Exception as exc:
        log.error("Query failed: %s | %s", sql.strip().split("\n")[0][:120], exc)
        raise


def query_all(sql, params=None):
    conn = get_db()
    with conn.cursor() as cur:
        _run(cur, sql, params)
        rows = cur.fetchall()
    conn.commit()  # ends the read transaction so the next read sees fresh data
    return rows


def query_one(sql, params=None):
    conn = get_db()
    with conn.cursor() as cur:
        _run(cur, sql, params)
        row = cur.fetchone()
    conn.commit()
    return row


def execute(sql, params=None):
    """Run one write statement and commit. Returns lastrowid."""
    conn = get_db()
    try:
        with conn.cursor() as cur:
            _run(cur, sql, params)
            last_id = cur.lastrowid
        conn.commit()
        return last_id
    except Exception:
        conn.rollback()
        raise


@contextmanager
def transaction():
    """Several statements, one commit. Rolls back on any exception."""
    conn = get_db()
    cur = conn.cursor()
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()

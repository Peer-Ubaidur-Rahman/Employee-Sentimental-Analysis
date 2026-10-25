"""
sqlite_shim.py - lets the route tests run WITHOUT a MySQL server.

It replaces db.query_all/query_one/execute/transaction with SQLite equivalents (translating %s
placeholders). This verifies application logic (routing, auth, validation, privacy rules, ML
integration). It does NOT verify MySQL-specific behaviour: use tests/test_mysql_integration.py
(RUN_MYSQL_TESTS=1) for that.
"""
import os
import re
import sqlite3
from contextlib import contextmanager

import db

_SCHEMA = os.path.join(os.path.dirname(os.path.abspath(__file__)), "sqlite_schema.sql")
_INTERVAL = re.compile(r"DATE_SUB\(CURRENT_TIMESTAMP, INTERVAL %s MINUTE\)")


def _translate(sql):
    sql = _INTERVAL.sub("datetime('now', '-' || ? || ' minutes')", sql)
    return sql.replace("%s", "?")


def _dict_factory(cursor, row):
    return {col[0]: row[i] for i, col in enumerate(cursor.description)}


class SqliteBackend:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self.conn.row_factory = _dict_factory
        self.conn.execute("PRAGMA foreign_keys = ON")
        with open(_SCHEMA, encoding="utf-8") as fh:
            self.conn.executescript(fh.read())
        self._orig = {}

    # --- replacements for db.* -------------------------------------------------
    def query_all(self, sql, params=None):
        return self.conn.execute(_translate(sql), tuple(params or ())).fetchall()

    def query_one(self, sql, params=None):
        return self.conn.execute(_translate(sql), tuple(params or ())).fetchone()

    def execute(self, sql, params=None):
        try:
            cur = self.conn.execute(_translate(sql), tuple(params or ()))
            self.conn.commit()
            return cur.lastrowid
        except Exception:
            self.conn.rollback()
            raise

    @contextmanager
    def transaction(self):
        backend = self

        class _Cur:
            lastrowid = None

            def execute(self, sql, params=None):
                cur = backend.conn.execute(_translate(sql), tuple(params or ()))
                self.lastrowid = cur.lastrowid

        try:
            yield _Cur()
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    # --- install / uninstall ----------------------------------------------------
    def install(self):
        for name in ("query_all", "query_one", "execute", "transaction"):
            self._orig[name] = getattr(db, name)
            setattr(db, name, getattr(self, name))

    def uninstall(self):
        for name, fn in self._orig.items():
            setattr(db, name, fn)
        self.conn.close()

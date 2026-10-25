"""
init_db.py - apply database.sql using PyMySQL (handy on Windows when the `mysql` CLI is not on PATH).

The script is repeatable and non-destructive (CREATE ... IF NOT EXISTS / INSERT IGNORE only).
Connect as a user allowed to create the database, e.g. root:
    python init_db.py --user root --password-prompt
"""
import argparse
import getpass
import os
import sys

import pymysql

SQL_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database.sql")


def statements(text):
    lines = [ln for ln in text.splitlines() if not ln.strip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--host", default=os.environ.get("DB_HOST", "localhost"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("DB_PORT", "3306")))
    ap.add_argument("--user", default="root")
    ap.add_argument("--password-prompt", action="store_true", help="ask for the MySQL password")
    args = ap.parse_args()
    password = getpass.getpass("MySQL password: ") if args.password_prompt else os.environ.get("DB_ADMIN_PASSWORD", "")
    try:
        conn = pymysql.connect(host=args.host, port=args.port, user=args.user, password=password, charset="utf8mb4")
    except pymysql.MySQLError as exc:
        sys.exit(f"Could not connect to MySQL: {exc}")
    with conn, conn.cursor() as cur:
        with open(SQL_FILE, encoding="utf-8") as fh:
            for stmt in statements(fh.read()):
                cur.execute(stmt)
        conn.commit()
    print("Schema applied (existing data untouched).")


if __name__ == "__main__":
    main()

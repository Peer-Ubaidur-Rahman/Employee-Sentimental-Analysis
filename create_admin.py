"""
create_admin.py - create an HR administrator account (no default/known password exists).

Usage:  python create_admin.py
The password is read with getpass (not echoed, not stored in shell history) and only its
hash is saved. Roles: hr_admin (full access) or hr_analyst (read-only analytics).
"""
import getpass
import sys

from werkzeug.security import generate_password_hash

from app import create_app
from db import execute, query_one
from utils.security import validate_email, validate_password


def main():
    app = create_app()
    with app.app_context():
        name = input("Full name: ").strip()
        email = input("Email: ").strip().lower()
        role = input("Role [hr_admin/hr_analyst] (default hr_admin): ").strip() or "hr_admin"
        if role not in ("hr_admin", "hr_analyst"):
            sys.exit("Role must be hr_admin or hr_analyst.")
        ok, msg = validate_email(email)
        if not name or not ok:
            sys.exit(msg or "Name is required.")
        password = getpass.getpass("Password (min 10 chars, letter + digit): ")
        ok, msg = validate_password(password, getpass.getpass("Confirm password: "))
        if not ok:
            sys.exit(msg)
        if query_one("SELECT id FROM administrators WHERE email = %s", (email,)):
            sys.exit("An administrator with that email already exists.")
        execute("INSERT INTO administrators (full_name, email, password_hash, role) VALUES (%s,%s,%s,%s)",
                (name, email, generate_password_hash(password), role))
        print(f"Administrator {email} created with role {role}.")


if __name__ == "__main__":
    main()

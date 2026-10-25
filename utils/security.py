"""utils/security.py - CSRF, authorization decorators, audit logging, input validation."""
import logging
import re
import secrets
from functools import wraps

from flask import abort, current_app, flash, redirect, request, session, url_for

import db

log = logging.getLogger(__name__)

# ----------------------------------------------------------------- CSRF
CSRF_KEY = "_csrf_token"
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def generate_csrf_token() -> str:
    if CSRF_KEY not in session:
        session[CSRF_KEY] = secrets.token_hex(32)
    return session[CSRF_KEY]


def _csrf_valid() -> bool:
    sent = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token") or ""
    expected = session.get(CSRF_KEY, "")
    return bool(expected) and bool(sent) and secrets.compare_digest(expected, sent)


def init_csrf(app):
    app.jinja_env.globals["csrf_token"] = generate_csrf_token

    @app.before_request
    def _protect():
        if not current_app.config.get("CSRF_ENABLED", True):
            return None
        if request.method in SAFE_METHODS:
            return None
        if not _csrf_valid():
            log.warning("CSRF validation failed for %s %s", request.method, request.path)
            abort(400, description="Your form expired or was invalid. Please go back, refresh and try again.")
        return None


# ----------------------------------------------------------------- Authorization
def login_user(kind: str, user_id: int, **extra):
    """Start a fresh session (prevents session fixation)."""
    session.clear()
    session.permanent = True
    session["kind"] = kind
    session["user_id"] = user_id
    for k, v in extra.items():
        session[k] = v
    generate_csrf_token()


def employee_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if session.get("kind") != "employee":
            flash("Please sign in to continue.", "warning")
            return redirect(url_for("auth.employee_login"))
        row = db.query_one("SELECT is_active FROM employees WHERE id = %s", (session["user_id"],))
        if not row or not row["is_active"]:
            session.clear()
            flash("Your account is not active. Contact HR.", "danger")
            return redirect(url_for("auth.employee_login"))
        return view(*args, **kwargs)
    return wrapper


def admin_required(roles=None):
    """roles: None = any HR admin; or e.g. ('hr_admin',) to require full admins."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            if session.get("kind") != "admin":
                flash("HR administrator sign-in required.", "warning")
                return redirect(url_for("auth.admin_login"))
            row = db.query_one("SELECT is_active, role FROM administrators WHERE id = %s", (session["user_id"],))
            if not row or not row["is_active"]:
                session.clear()
                flash("Your administrator account is not active.", "danger")
                return redirect(url_for("auth.admin_login"))
            session["admin_role"] = row["role"]  # always trust the DB over the cookie
            if roles and row["role"] not in roles:
                abort(403)
            return view(*args, **kwargs)
        return wrapper
    return decorator


# ----------------------------------------------------------------- Audit
def client_ip() -> str:
    return (request.remote_addr or "")[:45]


def audit(actor_type, actor_id, action, target_type=None, target_id=None, details=None):
    """Write an audit row. Audit failures must never break the user's request."""
    try:
        db.execute(
            "INSERT INTO audit_logs (actor_type, actor_id, action, target_type, target_id, details, ip_address) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (actor_type, actor_id, action, target_type,
             None if target_id is None else str(target_id)[:60],
             None if details is None else str(details)[:255], client_ip()))
    except Exception:
        log.exception("Failed to write audit log for action %s", action)


# ----------------------------------------------------------------- Validation
EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def clean_str(value, max_len=255) -> str:
    return (value or "").strip()[:max_len]


def validate_email(email: str):
    if not email or len(email) > 180 or not EMAIL_RE.match(email):
        return False, "Enter a valid email address."
    return True, None


def validate_password(password: str, confirm: str = None):
    if len(password or "") < 10:
        return False, "Password must be at least 10 characters."
    if len(password) > 128:
        return False, "Password is too long (max 128 characters)."
    if not re.search(r"[A-Za-z]", password) or not re.search(r"\d", password):
        return False, "Password must contain at least one letter and one digit."
    if confirm is not None and password != confirm:
        return False, "Password confirmation does not match."
    return True, None


def validate_years(value):
    try:
        years = round(float(value), 1)
    except (TypeError, ValueError):
        return False, "Years of experience must be a number."
    if years < 0 or years > 60:
        return False, "Years of experience must be between 0 and 60."
    return True, years


def validate_rating(value, required=False):
    if value in (None, ""):
        return (False, "A rating is required.") if required else (True, None)
    try:
        rating = int(value)
    except (TypeError, ValueError):
        return False, "Ratings must be whole numbers from 1 to 5."
    if not 1 <= rating <= 5:
        return False, "Ratings must be between 1 and 5."
    return True, rating


def validate_feedback_text(text: str, min_len: int, max_len: int):
    text = (text or "").strip()
    if len(text) < min_len:
        return False, f"Please write at least {min_len} characters so the analysis is meaningful."
    if len(text) > max_len:
        return False, f"Feedback must be at most {max_len} characters."
    return True, text

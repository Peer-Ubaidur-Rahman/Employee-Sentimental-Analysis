"""blueprints/auth.py - employee + HR administrator authentication."""
from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from utils.security import (audit, clean_str, login_user, validate_email, validate_password,
                            validate_years)

auth_bp = Blueprint("auth", __name__)

# Used to burn comparable CPU time when the email is unknown (reduces user-enumeration timing).
_DUMMY_HASH = generate_password_hash("not-a-real-password-0")


def _locked_out(kind: str, email: str) -> bool:
    """Too many recent failures for this email? Time is computed by the DB so clocks cannot disagree."""
    cfg = current_app.config
    row = db.query_one(
        "SELECT COUNT(*) AS n FROM audit_logs WHERE action = %s AND target_id = %s "
        "AND created_at >= DATE_SUB(CURRENT_TIMESTAMP, INTERVAL %s MINUTE)",
        (f"{kind}_login_failed", email[:60], cfg["LOCKOUT_MINUTES"]))
    return bool(row) and row["n"] >= cfg["MAX_FAILED_LOGINS"]


def _departments():
    return db.query_all("SELECT id, name FROM departments ORDER BY name")


# ------------------------------------------------------------------ employee
@auth_bp.route("/employee/register", methods=["GET", "POST"])
def employee_register():
    departments = _departments()
    form = {}
    if request.method == "POST":
        form = {k: clean_str(request.form.get(k), 180) for k in
                ("full_name", "email", "role_title", "years_experience", "department_id")}
        email = form["email"].lower()
        errors = []
        if len(form["full_name"]) < 2:
            errors.append("Enter your full name.")
        if len(form["role_title"]) < 2:
            errors.append("Enter your job title.")
        ok, msg = validate_email(email)
        if not ok:
            errors.append(msg)
        domain = current_app.config.get("ALLOWED_EMAIL_DOMAIN")
        if ok and domain and not email.endswith("@" + domain.lower()):
            errors.append(f"Registration is limited to @{domain} addresses.")
        ok, years = validate_years(form["years_experience"])
        if not ok:
            errors.append(years)
        valid_ids = {str(d["id"]) for d in departments}
        if form["department_id"] not in valid_ids:
            errors.append("Choose a department from the list.")
        ok, msg = validate_password(request.form.get("password", ""), request.form.get("confirm_password", ""))
        if not ok:
            errors.append(msg)

        if not errors and db.query_one("SELECT id FROM employees WHERE email = %s", (email,)):
            errors.append("An account with this email already exists.")

        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            with db.transaction() as cur:
                cur.execute(
                    "INSERT INTO employees (full_name, email, password_hash, department_id, role_title, years_experience) "
                    "VALUES (%s,%s,%s,%s,%s,%s)",
                    (form["full_name"], email, generate_password_hash(request.form["password"]),
                     int(form["department_id"]), form["role_title"], years))
                new_id = cur.lastrowid
                cur.execute("UPDATE employees SET emp_code = %s WHERE id = %s", (f"EMP-{new_id:05d}", new_id))
            audit("employee", new_id, "employee_registered", "employee", new_id)
            flash("Account created. You can now sign in.", "success")
            return redirect(url_for("auth.employee_login"))
    return render_template("auth/employee_register.html", departments=departments, form=form)


@auth_bp.route("/employee/login", methods=["GET", "POST"])
def employee_login():
    if request.method == "POST":
        email = clean_str(request.form.get("email"), 180).lower()
        password = request.form.get("password", "")
        if _locked_out("employee", email):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return render_template("auth/employee_login.html"), 429
        user = db.query_one(
            "SELECT id, full_name, password_hash, is_active, must_change_password FROM employees WHERE email = %s",
            (email,))
        valid = check_password_hash(user["password_hash"] if user else _DUMMY_HASH, password)
        if user and valid and user["is_active"]:
            login_user("employee", user["id"], name=user["full_name"],
                       must_change_password=bool(user["must_change_password"]))
            db.execute("UPDATE employees SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s", (user["id"],))
            audit("employee", user["id"], "employee_login")
            return redirect(url_for("employee.dashboard"))
        audit("anonymous", None, "employee_login_failed", "email", email)
        if user and valid and not user["is_active"]:
            flash("This account is deactivated. Contact HR.", "danger")
        else:
            flash("Invalid email or password.", "danger")
    return render_template("auth/employee_login.html")


# ------------------------------------------------------------------ administrator
@auth_bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = clean_str(request.form.get("email"), 180).lower()
        password = request.form.get("password", "")
        if _locked_out("admin", email):
            flash("Too many failed attempts. Please wait a few minutes and try again.", "danger")
            return render_template("auth/admin_login.html"), 429
        admin = db.query_one(
            "SELECT id, full_name, password_hash, role, is_active FROM administrators WHERE email = %s", (email,))
        valid = check_password_hash(admin["password_hash"] if admin else _DUMMY_HASH, password)
        if admin and valid and admin["is_active"]:
            login_user("admin", admin["id"], name=admin["full_name"], admin_role=admin["role"])
            db.execute("UPDATE administrators SET last_login_at = CURRENT_TIMESTAMP WHERE id = %s", (admin["id"],))
            audit("admin", admin["id"], "admin_login")
            return redirect(url_for("admin.dashboard"))
        audit("anonymous", None, "admin_login_failed", "email", email)
        flash("Invalid administrator credentials.", "danger")
    return render_template("auth/admin_login.html")


# ------------------------------------------------------------------ shared
@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    """
    No email server is configured, so NO email is sent. The request is recorded in the
    audit log and an HR administrator can issue a one-time temporary password from the
    Employee Directory. The response is identical whether or not the email exists.
    """
    if request.method == "POST":
        email = clean_str(request.form.get("email"), 180).lower()
        ok, _ = validate_email(email)
        if ok:
            audit("anonymous", None, "password_reset_requested", "email", email)
        flash("Request recorded. No email is sent by this system: please contact your HR "
              "administrator, who can issue a temporary password.", "info")
        return redirect(url_for("auth.employee_login"))
    return render_template("auth/forgot_password.html")


@auth_bp.route("/logout", methods=["POST"])
def logout():
    kind, uid = session.get("kind"), session.get("user_id")
    if kind:
        audit(kind, uid, f"{kind}_logout")
    session.clear()
    flash("You have been signed out.", "info")
    return redirect(url_for("main.landing"))

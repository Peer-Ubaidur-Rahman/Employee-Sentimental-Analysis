"""
blueprints/admin.py - HR administrator portal.

Privacy rules enforced here:
  * anonymous submissions never expose the employee's identity in any view or export;
  * groups smaller than MIN_GROUP_SIZE never get a sentiment breakdown (re-identification risk);
  * hr_analyst is read-only and cannot see emails, export data, or manage accounts;
  * feedback views, exports and account changes are written to audit_logs.
"""
import csv
import io
import secrets
import string
from datetime import date, datetime, timedelta

from flask import (Blueprint, Response, abort, current_app, flash, jsonify, redirect,
                   render_template, request, session, url_for)
from werkzeug.security import generate_password_hash

import db
from predictor import get_predictor
from utils.security import admin_required, audit

admin_bp = Blueprint("admin", __name__)

SENTIMENTS = ("Positive", "Neutral", "Negative")
PERIODS = (7, 30, 90, 365)
FULL_ADMIN = ("hr_admin",)

SUBMITTER_SQL = "CASE WHEN s.is_anonymous = 1 THEN 'Anonymous' ELSE e.full_name END"


# ------------------------------------------------------------------ helpers
def _period():
    days = request.args.get("days", 30, type=int)
    days = days if days in PERIODS else 30
    since = (date.today() - timedelta(days=days - 1)).isoformat()
    return days, since


def _pct(part, whole):
    return round(100.0 * part / whole, 1) if whole else 0.0


def _like(term: str) -> str:
    """Escape LIKE wildcards in user input ('!' is the ESCAPE character)."""
    return "%" + term.replace("!", "!!").replace("%", "!%").replace("_", "!_") + "%"


def _parse_date(value):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date().isoformat()
    except ValueError:
        return None


def _csv_safe(value):
    """Neutralise spreadsheet formula injection in exported cells."""
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


def _csv_response(filename, header, rows):
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(header)
    for row in rows:
        writer.writerow([_csv_safe(c) for c in row])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": f"attachment; filename={filename}"})


def _dept_rows(since):
    """Per-department aggregates for the period, with small-group suppression applied."""
    min_n = current_app.config["MIN_GROUP_SIZE"]
    rows = db.query_all(
        "SELECT d.id, d.name, COUNT(s.id) AS n, COUNT(DISTINCT s.employee_id) AS submitters, "
        "SUM(CASE WHEN p.sentiment = 'Positive' THEN 1 ELSE 0 END) AS pos, "
        "SUM(CASE WHEN p.sentiment = 'Neutral' THEN 1 ELSE 0 END) AS neu, "
        "SUM(CASE WHEN p.sentiment = 'Negative' THEN 1 ELSE 0 END) AS neg, "
        "AVG(s.overall_rating) AS avg_rating, "
        "(SELECT COUNT(*) FROM employees x WHERE x.department_id = d.id AND x.is_active = 1) AS headcount "
        "FROM departments d "
        "LEFT JOIN feedback_submissions s ON s.department_id = d.id AND DATE(s.submitted_at) >= %s "
        "LEFT JOIN feedback_predictions p ON p.submission_id = s.id "
        "GROUP BY d.id, d.name ORDER BY n DESC, d.name", (since,))
    out = []
    for r in rows:
        n = int(r["n"] or 0)
        item = {"name": r["name"], "n": n, "headcount": int(r["headcount"] or 0),
                "suppressed": 0 < n < min_n, "empty": n == 0}
        if n >= min_n:
            pos, neu, neg = int(r["pos"] or 0), int(r["neu"] or 0), int(r["neg"] or 0)
            item.update(pos=pos, neu=neu, neg=neg, pos_pct=_pct(pos, n), neu_pct=_pct(neu, n),
                        neg_pct=_pct(neg, n),
                        avg_rating=round(float(r["avg_rating"]), 2) if r["avg_rating"] is not None else None,
                        participation=_pct(int(r["submitters"] or 0), item["headcount"]))
        out.append(item)
    return out


# ------------------------------------------------------------------ dashboard
@admin_bp.route("/dashboard")
@admin_required()
def dashboard():
    days, since = _period()
    predictor = get_predictor(current_app.config["MODEL_DIR"])

    employees = db.query_one("SELECT COUNT(*) AS n FROM employees WHERE is_active = 1")["n"]
    counts = {s: 0 for s in SENTIMENTS}
    for r in db.query_all(
            "SELECT p.sentiment, COUNT(*) AS n FROM feedback_submissions s "
            "JOIN feedback_predictions p ON p.submission_id = s.id "
            "WHERE DATE(s.submitted_at) >= %s GROUP BY p.sentiment", (since,)):
        counts[r["sentiment"]] = int(r["n"])
    total = sum(counts.values())

    labels = [(date.today() - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    series = {s: {d: 0 for d in labels} for s in SENTIMENTS}
    for r in db.query_all(
            "SELECT DATE(s.submitted_at) AS day, p.sentiment, COUNT(*) AS n FROM feedback_submissions s "
            "JOIN feedback_predictions p ON p.submission_id = s.id WHERE DATE(s.submitted_at) >= %s "
            "GROUP BY DATE(s.submitted_at), p.sentiment", (since,)):
        key = str(r["day"])
        if key in series[r["sentiment"]]:
            series[r["sentiment"]][key] = int(r["n"])

    latest = db.query_all(
        f"SELECT s.id, {SUBMITTER_SQL} AS submitter, d.name AS department, s.feedback_text, s.submitted_at, "
        "p.sentiment, p.confidence FROM feedback_submissions s "
        "JOIN employees e ON e.id = s.employee_id JOIN departments d ON d.id = s.department_id "
        "LEFT JOIN feedback_predictions p ON p.submission_id = s.id "
        "ORDER BY s.submitted_at DESC, s.id DESC LIMIT 8")

    depts = _dept_rows(since)
    chart = {
        "distribution": [counts[s] for s in SENTIMENTS],
        "trend": {"labels": labels, **{s.lower(): [series[s][d] for d in labels] for s in SENTIMENTS}},
        "departments": [{"name": d["name"], "pos": d["pos_pct"], "neu": d["neu_pct"], "neg": d["neg_pct"]}
                        for d in depts if "pos_pct" in d],
    }
    return render_template(
        "admin/dashboard.html", days=days, periods=PERIODS, employees=employees, total=total, counts=counts,
        pct={s: _pct(counts[s], total) for s in SENTIMENTS}, latest=latest, depts=depts, chart=chart,
        model_ready=predictor.is_ready, model_meta=predictor.metadata if predictor.is_ready else {},
        low_sample=0 < total < current_app.config["MIN_GROUP_SIZE"])


# ------------------------------------------------------------------ feedback explorer
@admin_bp.route("/feedback")
@admin_required()
def feedback_explorer():
    q = (request.args.get("q") or "").strip()[:100]
    sentiment = request.args.get("sentiment", "")
    dept = request.args.get("department", type=int)
    date_from = _parse_date(request.args.get("date_from"))
    date_to = _parse_date(request.args.get("date_to"))
    page = max(request.args.get("page", 1, type=int), 1)
    size = current_app.config["PAGE_SIZE"]

    where, params = [], []
    if q:
        where.append("(s.feedback_text LIKE %s ESCAPE '!' OR (s.is_anonymous = 0 AND e.full_name LIKE %s ESCAPE '!'))")
        params += [_like(q), _like(q)]
    if sentiment in SENTIMENTS:
        where.append("p.sentiment = %s")
        params.append(sentiment)
    if dept:
        where.append("s.department_id = %s")
        params.append(dept)
    if date_from:
        where.append("DATE(s.submitted_at) >= %s")
        params.append(date_from)
    if date_to:
        where.append("DATE(s.submitted_at) <= %s")
        params.append(date_to)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""

    base = ("FROM feedback_submissions s JOIN employees e ON e.id = s.employee_id "
            "JOIN departments d ON d.id = s.department_id "
            "LEFT JOIN feedback_predictions p ON p.submission_id = s.id ")
    total = db.query_one(f"SELECT COUNT(*) AS n {base}{where_sql}", tuple(params))["n"]
    rows = db.query_all(
        f"SELECT s.id, {SUBMITTER_SQL} AS submitter, d.name AS department, s.feedback_text, s.overall_rating, "
        f"s.submitted_at, p.sentiment, p.confidence {base}{where_sql} "
        "ORDER BY s.submitted_at DESC, s.id DESC LIMIT %s OFFSET %s",
        tuple(params) + (size, (page - 1) * size))
    departments = db.query_all("SELECT id, name FROM departments ORDER BY name")
    pages = max((total + size - 1) // size, 1)
    args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/feedback_explorer.html", rows=rows, total=total, page=page, pages=pages,
                           departments=departments, args=args, q=q, sentiment=sentiment, dept=dept,
                           date_from=date_from or "", date_to=date_to or "", sentiments=SENTIMENTS)


@admin_bp.route("/feedback/<int:feedback_id>")
@admin_required()
def feedback_detail(feedback_id):
    r = db.query_one(
        f"SELECT s.id, {SUBMITTER_SQL} AS submitter, d.name AS department, s.feedback_text, s.overall_rating, "
        "s.management_rating, s.workload_rating, s.culture_rating, s.submitted_at, p.sentiment, p.confidence, "
        "p.prob_positive, p.prob_neutral, p.prob_negative, p.model_version "
        "FROM feedback_submissions s JOIN employees e ON e.id = s.employee_id "
        "JOIN departments d ON d.id = s.department_id "
        "LEFT JOIN feedback_predictions p ON p.submission_id = s.id WHERE s.id = %s", (feedback_id,))
    if not r:
        abort(404)
    predictor = get_predictor(current_app.config["MODEL_DIR"])
    terms = predictor.explain(r["feedback_text"]) if predictor.is_ready else []
    audit("admin", session["user_id"], "feedback_viewed", "feedback", feedback_id)
    f = lambda v: None if v is None else float(v)  # noqa: E731  (Decimal -> JSON-safe)
    return jsonify({
        "id": r["id"], "submitter": r["submitter"], "department": r["department"],
        "text": r["feedback_text"], "submitted_at": str(r["submitted_at"]),
        "ratings": {"overall": r["overall_rating"], "management": r["management_rating"],
                    "workload": r["workload_rating"], "culture": r["culture_rating"]},
        "sentiment": r["sentiment"], "confidence": f(r["confidence"]),
        "probabilities": {"Positive": f(r["prob_positive"]), "Neutral": f(r["prob_neutral"]),
                          "Negative": f(r["prob_negative"])},
        "model_version": r["model_version"], "top_terms": terms})


# ------------------------------------------------------------------ department insights
@admin_bp.route("/departments")
@admin_required()
def department_insights():
    days, since = _period()
    depts = _dept_rows(since)
    chart = [{"name": d["name"], "pos": d["pos_pct"], "neu": d["neu_pct"], "neg": d["neg_pct"]}
             for d in depts if "pos_pct" in d]
    return render_template("admin/department_insights.html", depts=depts, chart=chart, days=days, periods=PERIODS)


# ------------------------------------------------------------------ employee directory
@admin_bp.route("/employees")
@admin_required()
def employee_directory():
    is_full = session.get("admin_role") in FULL_ADMIN
    q = (request.args.get("q") or "").strip()[:100]
    dept = request.args.get("department", type=int)
    status = request.args.get("status", "")
    page = max(request.args.get("page", 1, type=int), 1)
    size = current_app.config["PAGE_SIZE"]

    where, params = [], []
    if q:
        cols = "(e.full_name LIKE %s ESCAPE '!' OR e.emp_code LIKE %s ESCAPE '!'"
        params += [_like(q), _like(q)]
        if is_full:  # analysts cannot search by (or see) email addresses
            cols += " OR e.email LIKE %s ESCAPE '!'"
            params.append(_like(q))
        where.append(cols + ")")
    if dept:
        where.append("e.department_id = %s")
        params.append(dept)
    if status in ("active", "inactive"):
        where.append("e.is_active = %s")
        params.append(1 if status == "active" else 0)
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    base = "FROM employees e JOIN departments d ON d.id = e.department_id "
    total = db.query_one(f"SELECT COUNT(*) AS n {base}{where_sql}", tuple(params))["n"]
    rows = db.query_all(
        f"SELECT e.id, e.emp_code, e.full_name, e.email, e.role_title, e.years_experience, e.is_active, "
        f"e.last_login_at, d.name AS department {base}{where_sql} ORDER BY e.full_name LIMIT %s OFFSET %s",
        tuple(params) + (size, (page - 1) * size))
    if not is_full:
        for r in rows:
            r["email"] = None
    departments = db.query_all("SELECT id, name FROM departments ORDER BY name")
    pages = max((total + size - 1) // size, 1)
    args = {k: v for k, v in request.args.items() if k != "page" and v}
    return render_template("admin/employee_directory.html", rows=rows, total=total, page=page, pages=pages,
                           departments=departments, args=args, q=q, dept=dept, status=status, is_full=is_full)


@admin_bp.route("/employees/<int:emp_id>/status", methods=["POST"])
@admin_required(roles=FULL_ADMIN)
def set_employee_status(emp_id):
    target = db.query_one("SELECT id, full_name, is_active FROM employees WHERE id = %s", (emp_id,))
    if not target:
        abort(404)
    new_state = 0 if target["is_active"] else 1
    db.execute("UPDATE employees SET is_active = %s WHERE id = %s", (new_state, emp_id))
    audit("admin", session["user_id"], "employee_activated" if new_state else "employee_deactivated",
          "employee", emp_id)
    flash(f"{target['full_name']} is now {'active' if new_state else 'deactivated'}.", "success")
    return redirect(request.referrer or url_for("admin.employee_directory"))


@admin_bp.route("/employees/<int:emp_id>/reset-password", methods=["POST"])
@admin_required(roles=FULL_ADMIN)
def reset_employee_password(emp_id):
    """Development-friendly alternative to emailed reset links: one-time temporary password."""
    target = db.query_one("SELECT id, full_name FROM employees WHERE id = %s", (emp_id,))
    if not target:
        abort(404)
    alphabet = string.ascii_letters + string.digits
    while True:
        temp = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isalpha() for c in temp) and any(c.isdigit() for c in temp):
            break
    db.execute("UPDATE employees SET password_hash = %s, must_change_password = 1 WHERE id = %s",
               (generate_password_hash(temp), emp_id))
    audit("admin", session["user_id"], "employee_password_reset", "employee", emp_id)
    flash(f"Temporary password for {target['full_name']}: {temp}  (shown once; the employee must change it "
          f"at next sign-in. Share it securely.)", "warning")
    return redirect(request.referrer or url_for("admin.employee_directory"))


# ------------------------------------------------------------------ reports + exports
@admin_bp.route("/reports")
@admin_required()
def reports():
    min_n = current_app.config["MIN_GROUP_SIZE"]
    since = (date.today().replace(day=1) - timedelta(days=335)).isoformat()
    months = {}
    for r in db.query_all(
            "SELECT DATE(s.submitted_at) AS day, p.sentiment, COUNT(*) AS n, SUM(s.overall_rating) AS rsum, "
            "COUNT(s.overall_rating) AS rcnt FROM feedback_submissions s "
            "JOIN feedback_predictions p ON p.submission_id = s.id WHERE DATE(s.submitted_at) >= %s "
            "GROUP BY DATE(s.submitted_at), p.sentiment", (since,)):
        key = str(r["day"])[:7]
        m = months.setdefault(key, {"month": key, "n": 0, "pos": 0, "neu": 0, "neg": 0, "rsum": 0, "rcnt": 0})
        m["n"] += int(r["n"])
        m[{"Positive": "pos", "Neutral": "neu", "Negative": "neg"}[r["sentiment"]]] += int(r["n"])
        m["rsum"] += int(r["rsum"] or 0)
        m["rcnt"] += int(r["rcnt"] or 0)
    monthly = []
    for key in sorted(months, reverse=True):
        m = months[key]
        m["suppressed"] = m["n"] < min_n
        m["avg_rating"] = round(m["rsum"] / m["rcnt"], 2) if m["rcnt"] else None
        monthly.append(m)
    is_full = session.get("admin_role") in FULL_ADMIN
    audit_rows = []
    if is_full:
        audit_rows = db.query_all(
            "SELECT created_at, actor_type, actor_id, action, target_type, target_id, ip_address "
            "FROM audit_logs ORDER BY id DESC LIMIT 20")
    return render_template("admin/reports.html", monthly=monthly, depts=_dept_rows(
        (date.today() - timedelta(days=364)).isoformat()), is_full=is_full, audit_rows=audit_rows)


@admin_bp.route("/export/feedback.csv")
@admin_required(roles=FULL_ADMIN)
def export_feedback():
    include_text = request.args.get("include_text") == "1"
    rows = db.query_all(
        "SELECT s.id, s.submitted_at, d.name AS department, p.sentiment, p.confidence, s.overall_rating, "
        "s.management_rating, s.workload_rating, s.culture_rating, s.is_anonymous, s.feedback_text "
        "FROM feedback_submissions s JOIN departments d ON d.id = s.department_id "
        "LEFT JOIN feedback_predictions p ON p.submission_id = s.id ORDER BY s.id")
    header = ["id", "submitted_at", "department", "sentiment", "confidence", "overall_rating",
              "management_rating", "workload_rating", "culture_rating", "is_anonymous"]
    if include_text:
        header.append("feedback_text")
    out = []
    for r in rows:
        line = [r["id"], str(r["submitted_at"]), r["department"], r["sentiment"],
                None if r["confidence"] is None else float(r["confidence"]), r["overall_rating"],
                r["management_rating"], r["workload_rating"], r["culture_rating"], r["is_anonymous"]]
        if include_text:
            line.append(r["feedback_text"])
        out.append(line)
    audit("admin", session["user_id"], "export_feedback_csv", "export", None,
          f"rows={len(out)} include_text={int(include_text)}")
    return _csv_response("sentinel_feedback.csv", header, out)


@admin_bp.route("/export/departments.csv")
@admin_required(roles=FULL_ADMIN)
def export_departments():
    depts = _dept_rows((date.today() - timedelta(days=364)).isoformat())
    out = []
    for d in depts:
        if "pos_pct" in d:
            out.append([d["name"], d["n"], d["pos_pct"], d["neu_pct"], d["neg_pct"], d["avg_rating"]])
        else:
            out.append([d["name"], d["n"], "", "", "", ""])
    audit("admin", session["user_id"], "export_departments_csv", "export", None, f"rows={len(out)}")
    return _csv_response("sentinel_departments.csv",
                         ["department", "feedback_count_365d", "positive_pct", "neutral_pct", "negative_pct",
                          "avg_overall_rating"], out)

"""blueprints/employee.py - employee portal. Every query is scoped to session['user_id']."""
from flask import (Blueprint, current_app, flash, redirect, render_template, request,
                   session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

import db
from predictor import ModelNotTrainedError, get_predictor
from utils.security import (audit, clean_str, employee_required, validate_feedback_text,
                            validate_password, validate_rating, validate_years)

employee_bp = Blueprint("employee", __name__)

_ALLOWED_WHEN_PASSWORD_CHANGE_PENDING = {"employee.profile", "employee.change_password"}


@employee_bp.before_request
def _force_password_change():
    if (session.get("kind") == "employee" and session.get("must_change_password")
            and request.endpoint not in _ALLOWED_WHEN_PASSWORD_CHANGE_PENDING):
        flash("Please set a new password before continuing.", "warning")
        return redirect(url_for("employee.profile"))
    return None


def _sentiment_counts(employee_id):
    rows = db.query_all(
        "SELECT p.sentiment, COUNT(*) AS n FROM feedback_submissions s "
        "JOIN feedback_predictions p ON p.submission_id = s.id "
        "WHERE s.employee_id = %s GROUP BY p.sentiment", (employee_id,))
    counts = {"Positive": 0, "Neutral": 0, "Negative": 0}
    for r in rows:
        counts[r["sentiment"]] = r["n"]
    return counts


@employee_bp.route("/dashboard")
@employee_required
def dashboard():
    uid = session["user_id"]
    counts = _sentiment_counts(uid)
    recent = db.query_all(
        "SELECT s.id, s.feedback_text, s.overall_rating, s.submitted_at, p.sentiment, p.confidence "
        "FROM feedback_submissions s LEFT JOIN feedback_predictions p ON p.submission_id = s.id "
        "WHERE s.employee_id = %s ORDER BY s.submitted_at DESC, s.id DESC LIMIT 5", (uid,))
    me = db.query_one(
        "SELECT e.full_name, e.role_title, e.emp_code, d.name AS department FROM employees e "
        "JOIN departments d ON d.id = e.department_id WHERE e.id = %s", (uid,))
    return render_template("employee/dashboard.html", counts=counts, total=sum(counts.values()),
                           recent=recent, me=me)


@employee_bp.route("/feedback/new", methods=["GET", "POST"])
@employee_required
def submit_feedback():
    cfg = current_app.config
    predictor = get_predictor(cfg["MODEL_DIR"])
    model_ready = predictor.is_ready
    form = {}
    if request.method == "POST":
        form = {k: request.form.get(k, "") for k in
                ("feedback_text", "overall_rating", "management_rating", "workload_rating", "culture_rating")}
        errors = []
        ok, text = validate_feedback_text(form["feedback_text"], cfg["MIN_FEEDBACK_CHARS"], cfg["MAX_FEEDBACK_CHARS"])
        if not ok:
            errors.append(text)
        ratings = {}
        for name in ("overall_rating", "management_rating", "workload_rating", "culture_rating"):
            ok, val = validate_rating(form[name])
            if not ok:
                errors.append(val)
            ratings[name] = val if ok else None
        anonymous = 1 if request.form.get("is_anonymous") == "on" else 0

        result = None
        if not errors:
            try:
                result = predictor.predict(text)
            except ModelNotTrainedError:
                errors.append("The sentiment model has not been trained yet. Ask your administrator "
                              "to run 'python train_model.py'. Your feedback was NOT saved.")
            except ValueError as exc:
                errors.append(str(exc))
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            uid = session["user_id"]
            emp = db.query_one("SELECT department_id FROM employees WHERE id = %s", (uid,))
            probs = result["probabilities"]
            with db.transaction() as cur:  # feedback + prediction are stored together or not at all
                cur.execute(
                    "INSERT INTO feedback_submissions (employee_id, department_id, feedback_text, overall_rating, "
                    "management_rating, workload_rating, culture_rating, is_anonymous) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (uid, emp["department_id"], text, ratings["overall_rating"], ratings["management_rating"],
                     ratings["workload_rating"], ratings["culture_rating"], anonymous))
                sid = cur.lastrowid
                cur.execute(
                    "INSERT INTO feedback_predictions (submission_id, sentiment, confidence, prob_positive, "
                    "prob_neutral, prob_negative, model_version) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (sid, result["sentiment"], result["confidence"], probs["Positive"], probs["Neutral"],
                     probs["Negative"], result["model_version"]))
            audit("employee", uid, "feedback_submitted", "feedback", sid)
            flash("Thank you - your feedback was submitted.", "success")
            return redirect(url_for("employee.history", new=sid))
    return render_template("employee/submit_feedback.html", form=form, model_ready=model_ready,
                           max_chars=cfg["MAX_FEEDBACK_CHARS"], min_chars=cfg["MIN_FEEDBACK_CHARS"])


@employee_bp.route("/history")
@employee_required
def history():
    uid = session["user_id"]
    page = max(request.args.get("page", 1, type=int), 1)
    size = current_app.config["PAGE_SIZE"]
    total = db.query_one("SELECT COUNT(*) AS n FROM feedback_submissions WHERE employee_id = %s", (uid,))["n"]
    rows = db.query_all(
        "SELECT s.id, s.feedback_text, s.overall_rating, s.management_rating, s.workload_rating, s.culture_rating, "
        "s.is_anonymous, s.submitted_at, p.sentiment, p.confidence, p.prob_positive, p.prob_neutral, p.prob_negative "
        "FROM feedback_submissions s LEFT JOIN feedback_predictions p ON p.submission_id = s.id "
        "WHERE s.employee_id = %s ORDER BY s.submitted_at DESC, s.id DESC LIMIT %s OFFSET %s",
        (uid, size, (page - 1) * size))
    new_id = request.args.get("new", type=int)
    highlight = next((r for r in rows if r["id"] == new_id), None) if new_id else None
    pages = max((total + size - 1) // size, 1)
    return render_template("employee/history.html", rows=rows, page=page, pages=pages, total=total,
                           highlight=highlight)


@employee_bp.route("/profile", methods=["GET", "POST"])
@employee_required
def profile():
    uid = session["user_id"]
    departments = db.query_all("SELECT id, name FROM departments ORDER BY name")
    if request.method == "POST":
        full_name = clean_str(request.form.get("full_name"), 120)
        role_title = clean_str(request.form.get("role_title"), 120)
        dept_id = request.form.get("department_id", "")
        ok_y, years = validate_years(request.form.get("years_experience"))
        errors = []
        if len(full_name) < 2:
            errors.append("Enter your full name.")
        if len(role_title) < 2:
            errors.append("Enter your job title.")
        if dept_id not in {str(d["id"]) for d in departments}:
            errors.append("Choose a department from the list.")
        if not ok_y:
            errors.append(years)
        if errors:
            for e in errors:
                flash(e, "danger")
        else:
            db.execute("UPDATE employees SET full_name=%s, role_title=%s, department_id=%s, years_experience=%s "
                       "WHERE id=%s", (full_name, role_title, int(dept_id), years, uid))
            session["name"] = full_name
            audit("employee", uid, "profile_updated", "employee", uid)
            flash("Profile updated.", "success")
            return redirect(url_for("employee.profile"))
    me = db.query_one(
        "SELECT id, emp_code, full_name, email, role_title, department_id, years_experience "
        "FROM employees WHERE id = %s", (uid,))
    return render_template("employee/profile.html", me=me, departments=departments)


@employee_bp.route("/profile/password", methods=["POST"])
@employee_required
def change_password():
    uid = session["user_id"]
    row = db.query_one("SELECT password_hash FROM employees WHERE id = %s", (uid,))
    current = request.form.get("current_password", "")
    ok, msg = validate_password(request.form.get("new_password", ""), request.form.get("confirm_password", ""))
    if not check_password_hash(row["password_hash"], current):
        flash("Your current password is incorrect.", "danger")
    elif not ok:
        flash(msg, "danger")
    else:
        db.execute("UPDATE employees SET password_hash=%s, must_change_password=0 WHERE id=%s",
                   (generate_password_hash(request.form["new_password"]), uid))
        session["must_change_password"] = False
        audit("employee", uid, "password_changed", "employee", uid)
        flash("Password changed.", "success")
    return redirect(url_for("employee.profile"))

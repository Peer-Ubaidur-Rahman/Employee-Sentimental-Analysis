"""
app.py - Flask application factory.

Run (development):   python app.py            (set FLASK_DEBUG=true for auto-reload)
Run (production):    waitress-serve --call "app:create_app"   (see README)
"""
import logging
import os
from datetime import date, datetime
from logging.handlers import RotatingFileHandler

from flask import Blueprint, Flask, jsonify, render_template, request, session

import db
from blueprints.admin import admin_bp
from blueprints.auth import auth_bp
from blueprints.employee import employee_bp
from config import BASE_DIR, get_config
from predictor import get_predictor
from utils.security import init_csrf

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
def landing():
    return render_template("landing.html")


@main_bp.route("/healthz")
def healthz():
    """Liveness probe. Does not touch the database or expose any data."""
    return jsonify(status="ok")


def _fmt_dt(value, fmt="%d %b %Y, %H:%M"):
    if value is None or value == "":
        return "-"
    if isinstance(value, str):
        for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                value = datetime.strptime(value[:19], pattern)
                break
            except ValueError:
                continue
        else:
            return value
    if isinstance(value, date) and not isinstance(value, datetime):
        return value.strftime("%d %b %Y")
    return value.strftime(fmt)


def _configure_logging(app):
    level = logging.DEBUG if app.debug else logging.INFO
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    root = logging.getLogger()
    root.setLevel(level)
    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        stream = logging.StreamHandler()
        stream.setFormatter(fmt)
        root.addHandler(stream)
    if not app.testing:
        os.makedirs(os.path.join(BASE_DIR, "instance"), exist_ok=True)
        path = os.path.join(BASE_DIR, "instance", "sentinel.log")
        if not any(getattr(h, "baseFilename", None) == path for h in root.handlers):
            fh = RotatingFileHandler(path, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(fmt)
            root.addHandler(fh)


def create_app(config_name=None, overrides=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(get_config(config_name))
    if overrides:
        app.config.update(overrides)
    _configure_logging(app)

    db.init_app(app)
    init_csrf(app)
    app.jinja_env.filters["fmt_dt"] = _fmt_dt

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(employee_bp, url_prefix="/employee")
    app.register_blueprint(admin_bp, url_prefix="/admin")

    @app.context_processor
    def inject_globals():
        return {"current_kind": session.get("kind"), "current_name": session.get("name"),
                "current_admin_role": session.get("admin_role"), "min_group": app.config["MIN_GROUP_SIZE"]}

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        if not request.path.startswith("/static/"):
            resp.headers["Cache-Control"] = "no-store"  # never cache pages that may hold feedback
        return resp

    def _error(code, title, message):
        return render_template("error.html", code=code, title=title, message=message), code

    @app.errorhandler(400)
    def bad_request(e):
        return _error(400, "Request could not be processed", getattr(e, "description", "Bad request."))

    @app.errorhandler(403)
    def forbidden(_e):
        return _error(403, "Access denied", "Your account does not have permission to view this page.")

    @app.errorhandler(404)
    def not_found(_e):
        return _error(404, "Page not found", "The page you are looking for does not exist.")

    @app.errorhandler(db.DatabaseUnavailable)
    def db_down(_e):
        return _error(503, "Service temporarily unavailable",
                      "The database is not reachable right now. Please try again shortly.")

    @app.errorhandler(Exception)
    def unexpected(exc):
        from werkzeug.exceptions import HTTPException
        if isinstance(exc, HTTPException):
            return exc
        app.logger.exception("Unhandled exception")  # details go to the log, never to the browser
        return _error(500, "Something went wrong", "An unexpected error occurred. It has been logged.")

    # Warm the model so problems appear in the log at startup, not on a user's first click.
    predictor = get_predictor(app.config["MODEL_DIR"])
    if not app.testing:
        if predictor.is_ready:
            app.logger.info("Sentiment model loaded: %s", predictor.version)
            if predictor.backend_mismatch():
                app.logger.warning("Preprocessing backend differs from training (%s). Retrain with "
                                   "'python train_model.py' for consistent results.",
                                   predictor.metadata.get("preprocessing_backend"))
        else:
            app.logger.warning("No trained model found. Run 'python train_model.py'.")
    return app


if __name__ == "__main__":
    application = create_app()
    application.run(host="127.0.0.1", port=int(os.environ.get("PORT", "5000")),
                    debug=application.config.get("DEBUG", False))

"""Shared test helpers: trained-model fixture, app factory, form helpers."""
import atexit
import contextlib
import io
import os
import re
import shutil
import tempfile
import unittest

from werkzeug.security import generate_password_hash

import db
from app import create_app
from config import BaseConfig
from tests.sqlite_shim import SqliteBackend

_MODEL_DIR = None
STRONG_PW = "CorrectHorse42"


def trained_model_dir():
    """Train once per test run with the real pipeline (synthetic dataset) into a temp dir."""
    global _MODEL_DIR
    if _MODEL_DIR is None:
        import train_model
        _MODEL_DIR = tempfile.mkdtemp(prefix="sentinel_models_")
        with contextlib.redirect_stdout(io.StringIO()):
            train_model.run(BaseConfig.DATASET_PATH, BaseConfig.CHALLENGE_PATH, 0.2, _MODEL_DIR)
        atexit.register(cleanup_model_dir)
    return _MODEL_DIR


def cleanup_model_dir():
    if _MODEL_DIR:
        shutil.rmtree(_MODEL_DIR, ignore_errors=True)


def extract_csrf(html: str) -> str:
    match = re.search(r'name="csrf_token" value="([^"]+)"', html)
    assert match, "CSRF token not found in page"
    return match.group(1)


class AppTestCase(unittest.TestCase):
    """Fresh app + in-memory SQLite database per test."""
    model_ready = True

    def setUp(self):
        self.backend = SqliteBackend()
        self.backend.install()
        empty = tempfile.mkdtemp(prefix="sentinel_nomodel_")
        self._empty_dir = empty
        model_dir = trained_model_dir() if self.model_ready else empty
        self.app = create_app("testing", {"MODEL_DIR": model_dir, "MIN_GROUP_SIZE": 3})
        self.client = self.app.test_client()

    def tearDown(self):
        self.backend.uninstall()
        shutil.rmtree(self._empty_dir, ignore_errors=True)

    # ---- helpers ----
    def token(self, client=None, path="/auth/employee/login"):
        return extract_csrf((client or self.client).get(path).get_data(as_text=True))

    def post(self, path, data=None, client=None, token_path="/auth/employee/login", follow=True):
        client = client or self.client
        data = dict(data or {})
        data.setdefault("csrf_token", self.token(client, token_path))
        return client.post(path, data=data, follow_redirects=follow)

    def make_employee(self, email="emp@example.com", name="Emp Loyee", dept=1, active=1, password=STRONG_PW,
                      must_change=0):
        eid = db.execute(
            "INSERT INTO employees (full_name, email, password_hash, department_id, role_title, years_experience, "
            "is_active, must_change_password) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
            (name, email, generate_password_hash(password), dept, "Analyst", 2, active, must_change))
        db.execute("UPDATE employees SET emp_code = %s WHERE id = %s", (f"EMP-{eid:05d}", eid))
        return eid

    def make_admin(self, email="hr@example.com", role="hr_admin", password=STRONG_PW):
        return db.execute("INSERT INTO administrators (full_name, email, password_hash, role) VALUES (%s,%s,%s,%s)",
                          ("HR Person", email, generate_password_hash(password), role))

    def login_employee(self, client=None, email="emp@example.com", password=STRONG_PW):
        return self.post("/auth/employee/login", {"email": email, "password": password}, client=client)

    def login_admin(self, client=None, email="hr@example.com", password=STRONG_PW):
        return self.post("/auth/admin/login", {"email": email, "password": password}, client=client,
                         token_path="/auth/admin/login")

    def add_feedback(self, employee_id, text, sentiment, anonymous=0, dept=1, rating=4, day=None):
        sid = db.execute(
            "INSERT INTO feedback_submissions (employee_id, department_id, feedback_text, overall_rating, is_anonymous) "
            "VALUES (%s,%s,%s,%s,%s)", (employee_id, dept, text, rating, anonymous))
        if day:
            db.execute("UPDATE feedback_submissions SET submitted_at = %s WHERE id = %s", (day, sid))
        p = {"Positive": (0.8, 0.1, 0.1), "Neutral": (0.1, 0.8, 0.1), "Negative": (0.1, 0.1, 0.8)}[sentiment]
        db.execute("INSERT INTO feedback_predictions (submission_id, sentiment, confidence, prob_positive, prob_neutral, "
                   "prob_negative, model_version) VALUES (%s,%s,%s,%s,%s,%s,%s)", (sid, sentiment, 0.8, *p, "test"))
        return sid

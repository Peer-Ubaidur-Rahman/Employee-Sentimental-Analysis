"""Authentication, CSRF, lockout and session tests. Run against the SQLite stand-in (no MySQL needed)."""
import db
from tests.helpers import STRONG_PW, AppTestCase


def _register_data(**over):
    data = {"full_name": "Alice Example", "email": "alice@example.com", "department_id": "1", "years_experience": "3",
            "role_title": "Engineer", "password": STRONG_PW, "confirm_password": STRONG_PW}
    data.update(over)
    return data


class AuthTests(AppTestCase):
    def test_public_pages_render(self):
        for path in ("/", "/auth/employee/login", "/auth/employee/register", "/auth/admin/login",
                     "/auth/forgot-password", "/healthz"):
            self.assertEqual(self.client.get(path).status_code, 200, path)

    def test_register_hashes_password_and_assigns_code(self):
        r = self.post("/auth/employee/register", _register_data(), token_path="/auth/employee/register")
        self.assertIn(b"Account created", r.data)
        row = db.query_one("SELECT password_hash, emp_code FROM employees WHERE email = %s", ("alice@example.com",))
        self.assertNotIn(STRONG_PW, row["password_hash"])
        self.assertTrue(row["emp_code"].startswith("EMP-"))

    def test_register_rejects_weak_password_duplicate_and_bad_input(self):
        path = "/auth/employee/register"
        self.assertIn(b"at least 10", self.post(path, _register_data(password="short1", confirm_password="short1"), token_path=path).data)
        self.assertIn(b"letter and one digit", self.post(path, _register_data(password="onlyletterslong", confirm_password="onlyletterslong"), token_path=path).data)
        self.assertIn(b"does not match", self.post(path, _register_data(confirm_password="Different123456"), token_path=path).data)
        self.assertIn(b"valid email", self.post(path, _register_data(email="not-an-email"), token_path=path).data)
        self.assertIn(b"between 0 and 60", self.post(path, _register_data(years_experience="99"), token_path=path).data)
        self.assertIn(b"Choose a department", self.post(path, _register_data(department_id="999"), token_path=path).data)
        self.post(path, _register_data(), token_path=path)
        self.assertIn(b"already exists", self.post(path, _register_data(), token_path=path).data)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM employees")["n"], 1)

    def test_csrf_blocks_post_without_or_with_wrong_token(self):
        self.client.get("/auth/employee/login")
        r = self.client.post("/auth/employee/login", data={"email": "a@b.co", "password": "x"})
        self.assertEqual(r.status_code, 400)
        r = self.client.post("/auth/employee/login", data={"email": "a@b.co", "password": "x", "csrf_token": "forged"})
        self.assertEqual(r.status_code, 400)

    def test_login_success_and_generic_failure_message(self):
        self.make_employee()
        ok = self.login_employee()
        self.assertIn(b"Hello", ok.data)
        other = self.app.test_client()
        bad_pw = self.post("/auth/employee/login", {"email": "emp@example.com", "password": "WrongPassword1"}, client=other)
        no_user = self.post("/auth/employee/login", {"email": "ghost@example.com", "password": "WrongPassword1"}, client=other)
        self.assertIn(b"Invalid email or password", bad_pw.data)
        self.assertIn(b"Invalid email or password", no_user.data)  # same message: no user enumeration

    def test_lockout_after_repeated_failures(self):
        self.make_employee()
        for _ in range(self.app.config["MAX_FAILED_LOGINS"]):
            self.post("/auth/employee/login", {"email": "emp@example.com", "password": "WrongPassword1"})
        r = self.post("/auth/employee/login", {"email": "emp@example.com", "password": STRONG_PW}, follow=False)
        self.assertEqual(r.status_code, 429)

    def test_deactivated_employee_cannot_sign_in(self):
        self.make_employee(active=0)
        r = self.login_employee()
        self.assertIn(b"deactivated", r.data)

    def test_deactivation_ends_an_existing_session(self):
        eid = self.make_employee()
        self.login_employee()
        self.assertEqual(self.client.get("/employee/dashboard").status_code, 200)
        db.execute("UPDATE employees SET is_active = 0 WHERE id = %s", (eid,))
        r = self.client.get("/employee/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)

    def test_admin_login_is_separate_from_employee_login(self):
        self.make_employee()
        self.make_admin()
        r = self.post("/auth/admin/login", {"email": "emp@example.com", "password": STRONG_PW}, token_path="/auth/admin/login")
        self.assertIn(b"Invalid administrator credentials", r.data)
        self.assertIn(b"Executive workforce overview", self.login_admin().data)

    def test_logout_requires_post_and_clears_session(self):
        self.make_employee()
        self.login_employee()
        self.assertEqual(self.client.get("/auth/logout").status_code, 405)
        token = self.token(path="/employee/dashboard")
        self.client.post("/auth/logout", data={"csrf_token": token})
        self.assertEqual(self.client.get("/employee/dashboard").status_code, 302)

    def test_session_cookie_flags(self):
        self.assertTrue(self.app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(self.app.config["SESSION_COOKIE_SAMESITE"], "Lax")

    def test_forgot_password_is_honest_and_logged(self):
        r = self.post("/auth/forgot-password", {"email": "someone@example.com"}, token_path="/auth/forgot-password")
        self.assertIn(b"No email is sent", r.data)
        row = db.query_one("SELECT action FROM audit_logs WHERE action = 'password_reset_requested'")
        self.assertIsNotNone(row)

    def test_security_headers_present(self):
        r = self.client.get("/")
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(r.headers["X-Frame-Options"], "DENY")
        self.assertEqual(r.headers["Cache-Control"], "no-store")

    def test_404_page_has_no_stack_trace(self):
        r = self.client.get("/does-not-exist")
        self.assertEqual(r.status_code, 404)
        self.assertNotIn(b"Traceback", r.data)

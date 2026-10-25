"""
MySQL integration tests - REQUIRE a running MySQL 8.0.16+ server and are SKIPPED by default.

Enable with (PowerShell):
    $env:RUN_MYSQL_TESTS = "1"
    $env:DB_USER = "root"; $env:DB_PASSWORD = "your-password"      # needs CREATE/DROP on the test DB
    python -m unittest tests.test_mysql_integration -v

They use a SEPARATE database (default `sentinel_hr_test`, override with TEST_DB_NAME). The name must
end with `_test` because the test DROPS and recreates it. Your real `sentinel_hr` database is never touched.
"""
import os
import re
import unittest

RUN = os.environ.get("RUN_MYSQL_TESTS") == "1"


@unittest.skipUnless(RUN, "set RUN_MYSQL_TESTS=1 (and DB_USER/DB_PASSWORD) to run MySQL integration tests")
class MySQLIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import pymysql
        cls.pymysql = pymysql
        cls.test_db = os.environ.get("TEST_DB_NAME", "sentinel_hr_test")
        if not cls.test_db.endswith("_test"):
            raise RuntimeError("TEST_DB_NAME must end with '_test' (the database is dropped by this test).")
        cls.conn_args = dict(host=os.environ.get("DB_HOST", "localhost"), port=int(os.environ.get("DB_PORT", "3306")),
                             user=os.environ.get("DB_USER", "root"), password=os.environ.get("DB_PASSWORD", ""),
                             charset="utf8mb4", autocommit=True)
        conn = pymysql.connect(**cls.conn_args)
        with conn.cursor() as cur:
            cur.execute(f"DROP DATABASE IF EXISTS `{cls.test_db}`")
        conn.close()
        cls.apply_schema()

    @classmethod
    def apply_schema(cls):
        path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "database.sql")
        sql = open(path, encoding="utf-8").read().replace("sentinel_hr", cls.test_db)
        lines = [ln for ln in sql.splitlines() if not ln.strip().startswith("--")]
        conn = cls.pymysql.connect(**cls.conn_args)
        with conn.cursor() as cur:
            for stmt in "\n".join(lines).split(";"):
                if stmt.strip():
                    cur.execute(stmt)
        conn.close()

    def _query(self, sql, params=()):
        conn = self.pymysql.connect(database=self.test_db, cursorclass=self.pymysql.cursors.DictCursor, **self.conn_args)
        with conn.cursor() as cur:
            cur.execute(sql, params)
            rows = cur.fetchall() if cur.description else []
        conn.close()
        return rows

    def test_schema_is_repeatable_and_non_destructive(self):
        self._query("INSERT INTO departments (name, code) VALUES ('Temp Dept', 'TMP')")
        self.apply_schema()  # second run must not drop data
        self.assertEqual(len(self._query("SELECT id FROM departments WHERE code = 'TMP'")), 1)
        self.assertEqual(len(self._query("SELECT id FROM departments WHERE code = 'ENG'")), 1)  # INSERT IGNORE: no duplicates

    def test_constraints_are_enforced(self):
        with self.assertRaises(self.pymysql.MySQLError):
            self._query("INSERT INTO employees (full_name,email,password_hash,department_id,role_title) "
                        "VALUES ('x','x@y.co','h',99999,'r')")  # FK violation
        self._query("INSERT INTO employees (full_name,email,password_hash,department_id,role_title) "
                    "VALUES ('A','dup@y.co','h',1,'r')")
        with self.assertRaises(self.pymysql.MySQLError):
            self._query("INSERT INTO employees (full_name,email,password_hash,department_id,role_title) "
                        "VALUES ('B','dup@y.co','h',1,'r')")  # UNIQUE email
        eid = self._query("SELECT id FROM employees WHERE email='dup@y.co'")[0]["id"]
        with self.assertRaises(self.pymysql.MySQLError):  # CHECK constraint (MySQL >= 8.0.16)
            self._query("INSERT INTO feedback_submissions (employee_id, department_id, feedback_text, overall_rating) "
                        "VALUES (%s, 1, 'text', 9)", (eid,))

    def test_end_to_end_flow_on_mysql(self):
        os.environ["TEST_DB_NAME"] = self.test_db
        from app import create_app
        from config import TestingConfig
        TestingConfig.DB_NAME = self.test_db
        TestingConfig.DB_HOST = self.conn_args["host"]
        TestingConfig.DB_PORT = self.conn_args["port"]
        TestingConfig.DB_USER = self.conn_args["user"]
        TestingConfig.DB_PASSWORD = self.conn_args["password"]
        from tests.helpers import extract_csrf, trained_model_dir
        app = create_app("testing", {"MODEL_DIR": trained_model_dir(), "MIN_GROUP_SIZE": 1})
        c = app.test_client()
        tok = extract_csrf(c.get("/auth/employee/register").get_data(as_text=True))
        c.post("/auth/employee/register", follow_redirects=True, data={
            "csrf_token": tok, "full_name": "Mysql Tester", "email": "mysql.tester@example.com", "department_id": "1",
            "years_experience": "2", "role_title": "QA", "password": "CorrectHorse42", "confirm_password": "CorrectHorse42"})
        tok = extract_csrf(c.get("/auth/employee/login").get_data(as_text=True))
        c.post("/auth/employee/login", data={"csrf_token": tok, "email": "mysql.tester@example.com",
                                             "password": "CorrectHorse42"}, follow_redirects=True)
        tok = extract_csrf(c.get("/employee/feedback/new").get_data(as_text=True))
        r = c.post("/employee/feedback/new", follow_redirects=True, data={
            "csrf_token": tok, "feedback_text": "I really enjoy working with my team and my manager is supportive.",
            "overall_rating": "5"})
        self.assertIn(b"Predicted sentiment", r.data)
        rows = self._query("SELECT p.sentiment FROM feedback_predictions p JOIN feedback_submissions s ON s.id = p.submission_id "
                           "JOIN employees e ON e.id = s.employee_id WHERE e.email = 'mysql.tester@example.com'")
        self.assertEqual(len(rows), 1)
        # Admin dashboard queries must be valid MySQL
        from werkzeug.security import generate_password_hash
        self._query("INSERT INTO administrators (full_name,email,password_hash,role) VALUES ('HR','hr.mysql@example.com',%s,'hr_admin')",
                    (generate_password_hash("CorrectHorse42"),))
        a = app.test_client()
        tok = extract_csrf(a.get("/auth/admin/login").get_data(as_text=True))
        a.post("/auth/admin/login", data={"csrf_token": tok, "email": "hr.mysql@example.com", "password": "CorrectHorse42"})
        for path in ("/admin/dashboard", "/admin/feedback", "/admin/feedback?q=team&sentiment=Positive", "/admin/departments",
                     "/admin/employees", "/admin/reports", "/admin/export/feedback.csv", "/admin/export/departments.csv"):
            self.assertEqual(a.get(path).status_code, 200, path)


if __name__ == "__main__":
    unittest.main()

"""HR administrator tests: access control, live metrics, privacy rules, exports, audit trail."""
import csv
import io
import json
from datetime import date, timedelta

import db
from tests.helpers import STRONG_PW, AppTestCase


class AdminAccessTests(AppTestCase):
    ADMIN_PATHS = ("/admin/dashboard", "/admin/feedback", "/admin/departments", "/admin/employees", "/admin/reports")

    def test_admin_pages_require_admin_login(self):
        for path in self.ADMIN_PATHS + ("/admin/feedback/1", "/admin/export/feedback.csv"):
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/auth/admin/login", r.headers["Location"], path)

    def test_employee_cannot_open_admin_pages(self):
        self.make_employee()
        self.login_employee()
        for path in self.ADMIN_PATHS:
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/auth/admin/login", r.headers["Location"], path)

    def test_analyst_is_read_only(self):
        eid = self.make_employee()
        self.make_admin("analyst@example.com", role="hr_analyst")
        self.login_admin(email="analyst@example.com")
        for path in self.ADMIN_PATHS:
            self.assertEqual(self.client.get(path).status_code, 200, path)
        self.assertEqual(self.client.get("/admin/export/feedback.csv").status_code, 403)
        self.assertEqual(self.client.get("/admin/export/departments.csv").status_code, 403)
        token = self.token(path="/admin/employees")
        r = self.client.post(f"/admin/employees/{eid}/status", data={"csrf_token": token})
        self.assertEqual(r.status_code, 403)
        r = self.client.post(f"/admin/employees/{eid}/reset-password", data={"csrf_token": token})
        self.assertEqual(r.status_code, 403)

    def test_analyst_never_sees_employee_emails(self):
        self.make_employee("secret.email@example.com", "Visible Name")
        self.make_admin("analyst@example.com", role="hr_analyst")
        self.login_admin(email="analyst@example.com")
        page = self.client.get("/admin/employees").data
        self.assertIn(b"Visible Name", page)
        self.assertNotIn(b"secret.email@example.com", page)
        self.assertEqual(b"Visible Name" in self.client.get("/admin/employees?q=secret.email").data, False)  # cannot search by email

    def test_hr_admin_sees_emails(self):
        self.make_employee("secret.email@example.com", "Visible Name")
        self.make_admin()
        self.login_admin()
        self.assertIn(b"secret.email@example.com", self.client.get("/admin/employees").data)


class AdminDashboardTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.emp = self.make_employee()
        self.make_admin()

    def test_empty_state(self):
        self.login_admin()
        page = self.client.get("/admin/dashboard").data
        self.assertIn(b"No feedback has been submitted", page)
        self.assertNotIn(b"distChart", page)

    def test_metrics_are_calculated_from_records(self):
        for i in range(6):
            self.add_feedback(self.emp, f"positive comment number {i}", "Positive")
        for i in range(3):
            self.add_feedback(self.emp, f"negative comment number {i}", "Negative")
        self.add_feedback(self.emp, "neutral comment", "Neutral")
        self.login_admin()
        html = self.client.get("/admin/dashboard").get_data(as_text=True)
        self.assertIn(">60.0%<", html)   # 6/10 positive
        self.assertIn(">30.0%<", html)   # 3/10 negative
        self.assertIn(">10.0%<", html)   # 1/10 neutral
        self.assertIn('id="distChart"', html)
        start = html.index('<script id="chart-data"')
        payload = json.loads(html[html.index(">", start) + 1: html.index("</script>", start)])
        self.assertEqual(payload["distribution"], [6, 1, 3])
        self.assertEqual(sum(payload["trend"]["positive"]), 6)

    def test_period_filter_excludes_old_feedback(self):
        old = (date.today() - timedelta(days=200)).isoformat() + " 10:00:00"
        self.add_feedback(self.emp, "old comment from long ago", "Negative", day=old)
        self.add_feedback(self.emp, "recent comment this week", "Positive")
        self.login_admin()
        html = self.client.get("/admin/dashboard?days=30").get_data(as_text=True)
        start = html.index('<script id="chart-data"')
        payload = json.loads(html[html.index(">", start) + 1: html.index("</script>", start)])
        self.assertEqual(payload["distribution"], [1, 0, 0])
        html = self.client.get("/admin/dashboard?days=365").get_data(as_text=True)
        start = html.index('<script id="chart-data"')
        payload = json.loads(html[html.index(">", start) + 1: html.index("</script>", start)])
        self.assertEqual(payload["distribution"], [1, 0, 1])

    def test_small_groups_are_suppressed(self):
        for i in range(2):  # Engineering has 2 items, MIN_GROUP_SIZE is 3 in tests
            self.add_feedback(self.emp, f"eng comment {i}", "Negative", dept=1)
        for i in range(4):  # Sales has 4 items -> visible
            self.add_feedback(self.emp, f"sales comment {i}", "Positive", dept=2)
        self.login_admin()
        html = self.client.get("/admin/dashboard").get_data(as_text=True)
        self.assertIn("Hidden: fewer than 3 items", html)
        start = html.index('<script id="chart-data"')
        payload = json.loads(html[html.index(">", start) + 1: html.index("</script>", start)])
        self.assertEqual([d["name"] for d in payload["departments"]], ["Sales"])

    def test_invalid_period_falls_back_to_default(self):
        self.login_admin()
        self.assertEqual(self.client.get("/admin/dashboard?days=abc").status_code, 200)
        self.assertEqual(self.client.get("/admin/dashboard?days=-5").status_code, 200)


class ExplorerTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.named = self.make_employee("n@example.com", "Nora Named")
        self.anon = self.make_employee("s@example.com", "Secret Person")
        self.make_admin()
        self.add_feedback(self.named, "The onboarding was wonderful and welcoming.", "Positive", dept=1)
        self.add_feedback(self.anon, "My manager is unfair about overtime.", "Negative", anonymous=1, dept=2)
        self.add_feedback(self.named, "Cafeteria is fine, nothing special.", "Neutral", dept=2)
        self.login_admin()

    def test_anonymous_identity_is_never_exposed(self):
        page = self.client.get("/admin/feedback").get_data(as_text=True)
        self.assertNotIn("Secret Person", page)
        self.assertIn("Anonymous", page)
        self.assertEqual(b"My manager" in self.client.get("/admin/feedback?q=Secret").data, False)  # name search skips anonymous
        fid = db.query_one("SELECT id FROM feedback_submissions WHERE is_anonymous = 1")["id"]
        detail = self.client.get(f"/admin/feedback/{fid}").get_data(as_text=True)
        self.assertNotIn("Secret Person", detail)
        self.assertEqual(json.loads(detail)["submitter"], "Anonymous")
        self.assertNotIn("Secret Person", self.client.get("/admin/dashboard").get_data(as_text=True))

    def test_filters_change_results(self):
        self.assertIn(b"3 results", self.client.get("/admin/feedback").data)
        self.assertIn(b"1 result.", self.client.get("/admin/feedback?sentiment=Negative").data)
        self.assertIn(b"2 results", self.client.get("/admin/feedback?department=2").data)
        self.assertIn(b"1 result.", self.client.get("/admin/feedback?q=onboarding").data)
        self.assertIn(b"1 result.", self.client.get("/admin/feedback?q=Nora&sentiment=Positive").data)
        today = date.today().isoformat()
        self.assertIn(b"3 results", self.client.get(f"/admin/feedback?date_from={today}&date_to={today}").data)
        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        self.assertIn(b"0 results", self.client.get(f"/admin/feedback?date_from={tomorrow}").data)
        self.assertIn(b"3 results", self.client.get("/admin/feedback?sentiment=bogus&date_from=not-a-date").data)

    def test_like_wildcards_are_escaped(self):
        self.assertIn(b"0 results", self.client.get("/admin/feedback?q=%25").data)  # '%' must not match everything
        self.assertIn(b"0 results", self.client.get("/admin/feedback?q=_").data)

    def test_sql_injection_attempt_is_inert(self):
        r = self.client.get("/admin/feedback?q=%27%20OR%201%3D1%3B%20DROP%20TABLE%20employees%3B--")
        self.assertEqual(r.status_code, 200)
        self.assertIn(b"0 results", r.data)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM employees")["n"], 2)

    def test_pagination(self):
        for i in range(20):
            self.add_feedback(self.named, f"bulk comment {i}", "Neutral")
        page1 = self.client.get("/admin/feedback").get_data(as_text=True)
        page2 = self.client.get("/admin/feedback?page=2").get_data(as_text=True)
        self.assertIn("23 results", page1)
        self.assertNotEqual(page1.count("data-feedback-id"), 0)
        self.assertEqual(page1.count("data-feedback-id") + page2.count("data-feedback-id"), 23)
        self.assertEqual(self.client.get("/admin/feedback?page=999").status_code, 200)

    def test_detail_endpoint_returns_prediction_and_terms_and_is_audited(self):
        fid = db.query_one("SELECT id FROM feedback_submissions WHERE feedback_text LIKE %s", ("%onboarding%",))["id"]
        data = self.client.get(f"/admin/feedback/{fid}").get_json()
        self.assertEqual(data["sentiment"], "Positive")
        self.assertIn("top_terms", data)
        self.assertEqual(self.client.get("/admin/feedback/99999").status_code, 404)
        self.assertIsNotNone(db.query_one("SELECT id FROM audit_logs WHERE action = 'feedback_viewed'"))

    def test_html_in_feedback_is_escaped(self):
        self.add_feedback(self.named, "<script>alert(1)</script> workload is fine", "Neutral")
        page = self.client.get("/admin/feedback").get_data(as_text=True)
        self.assertNotIn("<script>alert(1)</script>", page)
        self.assertIn("&lt;script&gt;", page)


class DirectoryExportReportTests(AppTestCase):
    def setUp(self):
        super().setUp()
        self.emp = self.make_employee("target@example.com", "Target Person")
        self.make_admin()
        self.login_admin()

    def test_deactivate_blocks_login_and_is_audited(self):
        token = self.token(path="/admin/employees")
        self.client.post(f"/admin/employees/{self.emp}/status", data={"csrf_token": token})
        self.assertEqual(db.query_one("SELECT is_active FROM employees WHERE id = %s", (self.emp,))["is_active"], 0)
        self.assertIsNotNone(db.query_one("SELECT id FROM audit_logs WHERE action = 'employee_deactivated'"))
        other = self.app.test_client()
        r = self.post("/auth/employee/login", {"email": "target@example.com", "password": STRONG_PW}, client=other)
        self.assertIn(b"deactivated", r.data)

    def test_temporary_password_flow(self):
        token = self.token(path="/admin/employees")
        r = self.client.post(f"/admin/employees/{self.emp}/reset-password", data={"csrf_token": token}, follow_redirects=True)
        text = r.get_data(as_text=True)
        self.assertIn("Temporary password for Target Person", text)
        temp = text.split("Temporary password for Target Person: ")[1].split()[0]
        row = db.query_one("SELECT must_change_password FROM employees WHERE id = %s", (self.emp,))
        self.assertEqual(row["must_change_password"], 1)
        other = self.app.test_client()
        r = self.post("/auth/employee/login", {"email": "target@example.com", "password": temp}, client=other)
        self.assertIn(b"set a new password", r.data)
        r = self.post("/auth/employee/login", {"email": "target@example.com", "password": STRONG_PW},
                      client=self.app.test_client())
        self.assertIn(b"Invalid email or password", r.data)  # old password no longer works

    def test_state_changing_admin_posts_need_csrf(self):
        self.client.get("/admin/employees")
        r = self.client.post(f"/admin/employees/{self.emp}/status", data={})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(db.query_one("SELECT is_active FROM employees WHERE id = %s", (self.emp,))["is_active"], 1)

    def test_feedback_csv_export_masks_identity_and_omits_text_by_default(self):
        anon = self.make_employee("anon@example.com", "Hidden Hannah")
        self.add_feedback(anon, "private words here", "Negative", anonymous=1)
        r = self.client.get("/admin/export/feedback.csv")
        self.assertEqual(r.mimetype, "text/csv")
        body = r.get_data(as_text=True)
        self.assertNotIn("Hidden Hannah", body)
        self.assertNotIn("private words here", body)
        with_text = self.client.get("/admin/export/feedback.csv?include_text=1").get_data(as_text=True)
        self.assertIn("private words here", with_text)
        self.assertNotIn("Hidden Hannah", with_text)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM audit_logs WHERE action = 'export_feedback_csv'")["n"], 2)

    def test_csv_formula_injection_is_neutralised(self):
        self.add_feedback(self.emp, "=HYPERLINK(\"http://evil\",\"x\") is my comment", "Neutral")
        body = self.client.get("/admin/export/feedback.csv?include_text=1").get_data(as_text=True)
        rows = list(csv.reader(io.StringIO(body)))
        self.assertTrue(rows[1][-1].startswith("'="))

    def test_department_csv_applies_suppression(self):
        for i in range(2):
            self.add_feedback(self.emp, f"small group {i}", "Positive", dept=1)
        rows = list(csv.reader(io.StringIO(self.client.get("/admin/export/departments.csv").get_data(as_text=True))))
        eng = next(r for r in rows if r[0] == "Engineering")
        self.assertEqual(eng[1], "2")
        self.assertEqual(eng[2], "")  # percentages withheld below MIN_GROUP_SIZE

    def test_reports_and_department_pages_render_with_data(self):
        for i in range(4):
            self.add_feedback(self.emp, f"report comment {i}", "Positive")
        self.assertIn(b"Monthly summary", self.client.get("/admin/reports").data)
        page = self.client.get("/admin/departments?days=90").get_data(as_text=True)
        self.assertIn("Engineering", page)
        self.assertIn("Recent audit activity", self.client.get("/admin/reports").get_data(as_text=True))

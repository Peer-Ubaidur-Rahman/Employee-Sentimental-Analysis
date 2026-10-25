"""Employee portal tests: access control, feedback submission with real ML predictions, isolation."""
import db
from tests.helpers import STRONG_PW, AppTestCase

GOOD = "I am very happy with the management and the working environment here."
BAD = "The workload is exhausting and management never listens to employees."


class EmployeeTests(AppTestCase):
    def submit(self, text=GOOD, client=None, **extra):
        data = {"feedback_text": text, "overall_rating": "4"}
        data.update(extra)
        return self.post("/employee/feedback/new", data, client=client, token_path="/employee/feedback/new")

    def test_pages_require_login(self):
        for path in ("/employee/dashboard", "/employee/feedback/new", "/employee/history", "/employee/profile"):
            r = self.client.get(path, follow_redirects=False)
            self.assertEqual(r.status_code, 302, path)
            self.assertIn("/auth/employee/login", r.headers["Location"])

    def test_admin_session_cannot_use_employee_portal(self):
        self.make_admin()
        self.login_admin()
        r = self.client.get("/employee/dashboard", follow_redirects=False)
        self.assertEqual(r.status_code, 302)
        self.assertIn("/auth/employee/login", r.headers["Location"])

    def test_submit_feedback_stores_text_and_model_prediction(self):
        eid = self.make_employee()
        self.login_employee()
        r = self.submit(GOOD, management_rating="5")
        self.assertIn(b"Predicted sentiment", r.data)
        fb = db.query_one("SELECT * FROM feedback_submissions WHERE employee_id = %s", (eid,))
        self.assertEqual(fb["feedback_text"], GOOD)
        self.assertEqual(fb["management_rating"], 5)
        pred = db.query_one("SELECT * FROM feedback_predictions WHERE submission_id = %s", (fb["id"],))
        self.assertIn(pred["sentiment"], ("Positive", "Neutral", "Negative"))
        self.assertAlmostEqual(pred["prob_positive"] + pred["prob_neutral"] + pred["prob_negative"], 1.0, places=2)
        self.assertTrue(pred["model_version"].startswith("lr-tfidf-"))

    def test_different_texts_get_scored_by_the_model_not_a_lookup(self):
        eid = self.make_employee()
        self.login_employee()
        self.submit(GOOD)
        self.submit(BAD)
        rows = db.query_all("SELECT s.feedback_text, p.prob_positive, p.prob_negative FROM feedback_submissions s "
                            "JOIN feedback_predictions p ON p.submission_id = s.id WHERE s.employee_id = %s ORDER BY s.id", (eid,))
        self.assertGreater(rows[0]["prob_positive"], rows[1]["prob_positive"])
        self.assertGreater(rows[1]["prob_negative"], rows[0]["prob_negative"])

    def test_validation_rejects_bad_input_and_saves_nothing(self):
        self.make_employee()
        self.login_employee()
        self.assertIn(b"at least 15", self.submit("too short").data)
        self.assertIn(b"between 1 and 5", self.submit(GOOD, overall_rating="9").data)
        self.assertIn(b"whole numbers", self.submit(GOOD, culture_rating="abc").data)
        self.assertIn(b"at most 2000", self.submit("x" * 2001).data)
        self.assertIn(b"no analysable words", self.submit("1234567890 !!!!!!!!!! ??????").data)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM feedback_submissions")["n"], 0)

    def test_missing_model_gives_clear_error_and_does_not_save(self):
        class NoModel(AppTestCase):
            model_ready = False
        t = NoModel("run")
        t.setUp()
        try:
            t.make_employee()
            t.login_employee()
            r = t.post("/employee/feedback/new", {"feedback_text": GOOD}, token_path="/employee/feedback/new")
            self.assertIn(b"has not been trained", r.data)
            self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM feedback_submissions")["n"], 0)
        finally:
            t.tearDown()

    def test_history_is_private_to_each_employee(self):
        a = self.make_employee("a@example.com", "Ann A")
        b = self.make_employee("b@example.com", "Bob B")
        self.add_feedback(a, "Ann private comment about onboarding.", "Positive")
        self.add_feedback(b, "Bob private comment about workload.", "Negative")
        self.login_employee(email="a@example.com")
        page = self.client.get("/employee/history").data
        self.assertIn(b"Ann private comment", page)
        self.assertNotIn(b"Bob private comment", page)
        # ?new= pointing at someone else's submission must not highlight or reveal it
        bob_id = db.query_one("SELECT id FROM feedback_submissions WHERE employee_id = %s", (b,))["id"]
        page = self.client.get(f"/employee/history?new={bob_id}").data
        self.assertNotIn(b"Bob private comment", page)
        self.assertNotIn(b"Predicted sentiment of your latest feedback", page)

    def test_dashboard_counts_come_from_database(self):
        eid = self.make_employee()
        self.add_feedback(eid, "Great team and support overall.", "Positive")
        self.add_feedback(eid, "Great training budget this year.", "Positive")
        self.add_feedback(eid, "Deadlines are stressful lately.", "Negative")
        self.login_employee()
        html = self.client.get("/employee/dashboard").get_data(as_text=True)
        self.assertRegex(html, r"Feedback submitted</div><div class=\"metric-value\">3<")
        self.assertRegex(html, r"Positive</div><div class=\"metric-value c-pos\">2<")

    def test_profile_update_and_validation(self):
        eid = self.make_employee()
        self.login_employee()
        r = self.post("/employee/profile", {"full_name": "New Name", "role_title": "Lead", "department_id": "2",
                                            "years_experience": "5"}, token_path="/employee/profile")
        self.assertIn(b"Profile updated", r.data)
        row = db.query_one("SELECT full_name, department_id FROM employees WHERE id = %s", (eid,))
        self.assertEqual((row["full_name"], row["department_id"]), ("New Name", 2))
        r = self.post("/employee/profile", {"full_name": "X", "role_title": "Lead", "department_id": "2",
                                            "years_experience": "5"}, token_path="/employee/profile")
        self.assertIn(b"Enter your full name", r.data)

    def test_forced_password_change_flow(self):
        eid = self.make_employee(must_change=1)
        self.login_employee()
        r = self.client.get("/employee/dashboard", follow_redirects=True)
        self.assertIn(b"set a new password", r.data)
        wrong = self.post("/employee/profile/password", {"current_password": "nope", "new_password": "BrandNewPass99",
                                                          "confirm_password": "BrandNewPass99"}, token_path="/employee/profile")
        self.assertIn(b"current password is incorrect", wrong.data)
        ok = self.post("/employee/profile/password", {"current_password": STRONG_PW, "new_password": "BrandNewPass99",
                                                      "confirm_password": "BrandNewPass99"}, token_path="/employee/profile")
        self.assertIn(b"Password changed", ok.data)
        self.assertEqual(db.query_one("SELECT must_change_password AS m FROM employees WHERE id = %s", (eid,))["m"], 0)
        self.assertEqual(self.client.get("/employee/dashboard").status_code, 200)

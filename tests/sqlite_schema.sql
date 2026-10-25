-- SQLite stand-in for database.sql, used ONLY by the no-MySQL test suite (tests/sqlite_shim.py).
CREATE TABLE departments (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE, code TEXT NOT NULL UNIQUE, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE employees (id INTEGER PRIMARY KEY AUTOINCREMENT, emp_code TEXT UNIQUE, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL, department_id INTEGER NOT NULL REFERENCES departments(id), role_title TEXT NOT NULL, years_experience REAL NOT NULL DEFAULT 0,
  is_active INTEGER NOT NULL DEFAULT 1, must_change_password INTEGER NOT NULL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_login_at TEXT);
CREATE TABLE administrators (id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT NOT NULL, email TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL,
  role TEXT NOT NULL DEFAULT 'hr_analyst', is_active INTEGER NOT NULL DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP, last_login_at TEXT);
CREATE TABLE feedback_submissions (id INTEGER PRIMARY KEY AUTOINCREMENT, employee_id INTEGER NOT NULL REFERENCES employees(id) ON DELETE CASCADE,
  department_id INTEGER NOT NULL REFERENCES departments(id), feedback_text TEXT NOT NULL, overall_rating INTEGER, management_rating INTEGER,
  workload_rating INTEGER, culture_rating INTEGER, is_anonymous INTEGER NOT NULL DEFAULT 0, submitted_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE feedback_predictions (id INTEGER PRIMARY KEY AUTOINCREMENT, submission_id INTEGER NOT NULL UNIQUE REFERENCES feedback_submissions(id) ON DELETE CASCADE,
  sentiment TEXT NOT NULL, confidence REAL NOT NULL, prob_positive REAL NOT NULL, prob_neutral REAL NOT NULL, prob_negative REAL NOT NULL,
  model_version TEXT NOT NULL, predicted_at TEXT DEFAULT CURRENT_TIMESTAMP);
CREATE TABLE audit_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, actor_type TEXT NOT NULL, actor_id INTEGER, action TEXT NOT NULL, target_type TEXT,
  target_id TEXT, details TEXT, ip_address TEXT, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
INSERT INTO departments (name, code) VALUES ('Engineering','ENG'),('Sales','SAL'),('Human Resources','HR');

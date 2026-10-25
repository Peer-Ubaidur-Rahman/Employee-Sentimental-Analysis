# Sentinel HR — Employee Sentiment Analysis & Workforce Intelligence Platform

Final-year B.Tech AI & Data Science project (Human Resource Management, GE3754).
Employees submit free-text feedback; a **classical ML model (TF-IDF + Logistic Regression, scikit-learn)** estimates whether
each comment is Positive, Neutral or Negative; HR sees privacy-protected analytics. No BERT, transformers, TextBlob, VADER,
hosted inference APIs or generative AI are used anywhere.

> **Read this first — honest status**
> * The bundled model is trained on **synthetic demonstration data** (see [Dataset](#dataset)). Its scores prove the pipeline works; they are **not** evidence of real-world accuracy.
> * Predictions are statistical estimates, not diagnoses. See [Privacy, bias and surveillance risks](#privacy-bias-and-workplace-surveillance-risks).
> * Not production-ready merely because files exist: see [What was and was not verified](#what-was-and-was-not-verified).

---

## 1. Features (all implemented in code)

| Area | Implemented |
|------|-------------|
| Public | Landing page; employee register / login / logout; HR admin login; forgot-password page (see note below) |
| Security | Werkzeug password hashing, password policy (≥10 chars, letter + digit), CSRF tokens on every POST, session fixation protection (new session at login), HttpOnly/SameSite cookies, role-based authorization (`employee`, `hr_admin`, `hr_analyst`), login lockout (5 failures / 15 min), parameterized SQL only, security headers, no stack traces shown to users, audit log |
| Employee portal | Dashboard (own counts), feedback form (character counter, optional 1–5 ratings for overall/management/workload/culture, **anonymous option**), history with predicted label + confidence, profile + change password, privacy notice. Employees can only ever query their own rows |
| HR portal | Executive dashboard (KPIs, doughnut distribution chart, daily trend chart, department chart, latest feedback), feedback explorer (search, sentiment/department/date filters, pagination, detail drawer with probabilities and influential terms), department insights, employee directory (role-based), reports with monthly + department summaries and audit activity, CSV exports |
| ML | Reproducible training script, saved model + vectorizer + `metrics.json`, predictor that refuses to guess when the model is missing |
| Database | MySQL schema with PKs, FKs, indexes, CHECK/UNIQUE constraints, timestamps and audit logs; repeatable and non-destructive |

**Forgot password.** No mail server exists, so the system does **not** send email and says so. Submitting the form records an audit event;
an `hr_admin` can issue a one-time temporary password from *Employee directory → Reset password*. The employee is forced to change it at next sign-in.

**Role differences.** `hr_analyst` = read-only analytics, no emails visible, no exports, no account actions. `hr_admin` = everything.

## 2. Gaps found in the attachments and how they were handled

| Issue in `code.html` | Resolution |
|----------------------|------------|
| `database.sql` began with `DROP TABLE` for every table | Rewritten with `CREATE TABLE IF NOT EXISTS` / `INSERT IGNORE`; never deletes data |
| Seeded admin + employees with publicly documented passwords (`Admin@12345`) | No default accounts. `create_admin.py` prompts for credentials |
| 28 hand-written training sentences; test split of 7 | 732 synthetic rows + separate 45-row challenge set; limitations documented |
| Hard-coded `/auth/...` login URLs, no CSRF, no lockout | CSRF on all POSTs, lockout, audit trail |
| Dashboard dropdown items were `href="#"` (did nothing) | Period selector (7/30/90/365 days) is real and server-driven |
| Several listed templates/files were never provided (landing, forgot password, profile, history, reports, department/directory pages, tests, JS) | Implemented |
| Only 2 trivial tests | 65 tests (see §8) |
| Spec mentions "Q2 2024" and other static labels | Removed; all numbers come from the database |
| Tailwind CDN / three.js scaffolding inside `code.html` | Ignored (Stitch preview scaffolding, not application code); UI uses Bootstrap + `sentinel.css` per the brief |

## 3. Windows PowerShell setup (step by step)

### 3.1 Install Python
1. Download Python 3.10–3.12 from <https://www.python.org/downloads/windows/>.
2. In the installer **tick “Add python.exe to PATH”**, then Install.
3. Open a new PowerShell and check: `python --version`

### 3.2 Create a virtual environment and install dependencies
```powershell
cd path\to\sentinel_hr
python -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```
If activation is blocked: `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` and activate again.

### 3.3 Install and start MySQL (8.0.16 or newer — needed for CHECK constraints)
Install **MySQL Community Server** via the MySQL Installer (<https://dev.mysql.com/downloads/installer/>), keep the default service
name `MySQL80`, set a root password. Check it is running: `Get-Service MySQL80` (start with `Start-Service MySQL80`).

### 3.4 Configure `.env`
```powershell
Copy-Item .env.example .env
notepad .env
```
Generate a secret and paste it as `SECRET_KEY`:
```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```
Leave `DB_USER`/`DB_PASSWORD` for step 3.5. **Never commit `.env`.**

### 3.5 Initialise the database (repeatable, never deletes data)
Option A — Python (works even if `mysql.exe` is not on PATH):
```powershell
python init_db.py --user root --password-prompt
```
Option B — MySQL CLI: `mysql -u root -p < database.sql`

Create a least-privilege application user (run in `mysql -u root -p`):
```sql
CREATE USER 'sentinel_app'@'localhost' IDENTIFIED BY 'choose-a-strong-password';
GRANT SELECT, INSERT, UPDATE, DELETE ON sentinel_hr.* TO 'sentinel_app'@'localhost';
FLUSH PRIVILEGES;
```
Put `DB_USER=sentinel_app` and that password in `.env`.

### 3.6 NLTK data (one time, needs internet)
```powershell
python -m nltk.downloader stopwords wordnet omw-1.4 punkt punkt_tab
```
If you skip this, the code falls back to a simpler built-in tokenizer/lemmatizer and prints a warning. The training metrics file records which
backend was used; retrain if you later install the NLTK data so training and serving use the same preprocessing.

### 3.7 Train the model
```powershell
python train_model.py
```
Prints accuracy, precision, recall, F1, classification report and confusion matrix, and writes to `models/`:
`sentiment_classifier.joblib`, `tfidf_vectorizer.joblib`, `metrics.json`. **The application will not accept feedback until this has been run.**
Quick check on unseen sentences: `python predictor.py`.

### 3.8 Create the first HR administrator
```powershell
python create_admin.py
```

### 3.9 Run the tests
```powershell
python -m unittest discover -s tests -t . -v
```
(`pytest` also works if you `pip install pytest`.) See §8 for what each group needs.

### 3.10 Start the application
Development:
```powershell
$env:FLASK_DEBUG = "true"     # optional: auto-reload + debugger (development ONLY)
python app.py
```
Open <http://127.0.0.1:5000>. Employees register at `/auth/employee/register`; HR signs in at `/auth/admin/login`.

Production-style run (no debugger):
```powershell
pip install waitress
$env:APP_ENV = "production"            # requires SECRET_KEY (>=32 chars), DB_USER, DB_PASSWORD in the environment/.env
waitress-serve --listen=127.0.0.1:8000 --call app:create_app
```
Put it behind an HTTPS reverse proxy and set `SESSION_COOKIE_SECURE=true`. The app itself does not terminate TLS.
`python app.py` binds to 127.0.0.1 only. The debugger must never be enabled on a shared or public machine.

> The UI loads Bootstrap, Bootstrap Icons, Chart.js and the Inter font from public CDNs. Without internet the layout degrades and charts do not render.
> For an offline/air-gapped deployment, download these files into `static/` and change the `<link>`/`<script>` URLs.

## 4. Troubleshooting (Windows)

| Symptom | Fix |
|---------|-----|
| `python` is not recognized | Reinstall Python with “Add to PATH”, or use `py -3` |
| `Activate.ps1 cannot be loaded because running scripts is disabled` | `Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned` |
| `mysql` is not recognized | Use `python init_db.py ...`, or add `C:\Program Files\MySQL\MySQL Server 8.0\bin` to PATH |
| `Access denied for user` | Wrong `DB_USER`/`DB_PASSWORD` in `.env`, or the GRANT in §3.5 was not run |
| `Can't connect to MySQL server` / error 2003 | Service not running (`Start-Service MySQL80`) or wrong `DB_HOST`/`DB_PORT` |
| `Unknown database 'sentinel_hr'` | Run step 3.5 first |
| `'cryptography' package is required for sha256_password or caching_sha2_password` | `pip install cryptography` (already in requirements) |
| Page says “Service temporarily unavailable” | Database unreachable; check `instance\sentinel.log` |
| `Sentiment model not found` | Run `python train_model.py` |
| `LookupError: Resource stopwords not found` or SSL errors during NLTK download | Re-run the NLTK command (§3.6), or on corporate networks download the corpora manually; the app also works with the built-in fallback |
| `RuntimeError: Production requires SECRET_KEY` | Set `SECRET_KEY` (≥32 chars) when `APP_ENV=production` |
| “Your form expired or was invalid” | Reload the page and resubmit (CSRF token/session expired, or cookies are blocked) |
| `Port 5000 is in use` | `$env:PORT = "5050"; python app.py` |
| Register says “Choose a department” / dropdown empty | `database.sql` was not applied (departments are seeded there) |

## 5. Machine-learning pipeline

```
dataset/employee_feedback.csv -> validate columns/labels -> clean text -> train/test split (stratified, seed 42)
 -> TF-IDF fitted on the TRAIN split only -> LogisticRegression(class_weight="balanced")
 -> evaluate (accuracy, precision, recall, F1, confusion matrix) -> save model + vectorizer + metrics.json
```
Serving: `predictor.py` loads the saved artifacts, cleans text with the same `preprocessing.py`, transforms with the saved vectorizer and returns
`predict_proba`-based probabilities. There is **no** keyword list, dictionary lookup or fallback label anywhere. If the model is missing the
feedback form refuses to save anything.

Text cleaning: HTML stripped → contractions expanded → lowercase → digits/punctuation removed → tokenise → stop-words removed (**negations such as
“not”, “never”, “no” are deliberately kept**) → lemmatise (NLTK WordNet, or a simple suffix stemmer if NLTK data is unavailable).
TF-IDF: unigrams + bigrams, `min_df=2`, 5,000 features, sublinear TF.

### Dataset
`dataset/employee_feedback.csv` (732 rows) and `dataset/challenge_set.csv` (45 rows) are **synthetic**: written for this project (template-generated
plus hand-written sentences), released under **CC0**, copied from no external source. `dataset/build_synthetic_dataset.py` regenerates them.
To use real data, supply a CSV with columns `feedback,sentiment` (labels `Positive`/`Neutral`/`Negative`) and run
`python train_model.py --dataset path\to\data.csv`. You are responsible for consent, anonymisation and licensing of any real data.

### Results from the run used to prepare this package (not a guarantee for your machine)
Run in a sandbox **without NLTK data** (so the built-in fallback preprocessor was used), seed 42:

| Evaluation | n | Accuracy | Macro F1 |
|------------|---|----------|----------|
| Random 80/20 split of the synthetic data | 147 | 0.932 | 0.932 |
| Handwritten challenge set (never trained on) | 45 | 0.622 | 0.615 |

The 0.93 figure is **optimistic** because template sentences share phrases across the split. The 0.62 figure on 45 sentences is a better hint of how the model
copes with unfamiliar wording — and it is still synthetic. Your own `python train_model.py` prints the numbers for your environment (they will differ
slightly with NLTK installed). Do not quote either number as real-world accuracy.

### Model limitations
Bag-of-words models cannot understand sarcasm, context or mixed opinions (“I love my team but the deadlines are crushing”); Neutral is the hardest class;
vocabulary the model has never seen carries no signal; synthetic training text is far more regular than real employee writing; accuracy on your
organisation requires labelled data from your organisation; class labels reflect whoever labelled them.

## 6. Privacy, bias and workplace-surveillance risks

* **A prediction is not a fact about a person.** Never use a single label to evaluate, rank, discipline or dismiss anyone. The UI repeats this where labels appear.
* **Anonymity is real but fragile.** Anonymous feedback hides the name in all views and exports, but writing style, department and timing can still reveal people in small teams.
  To reduce this, department/month breakdowns are **suppressed below `MIN_GROUP_SIZE` (default 5)**.
* **Bias.** Models learn from their data: dialect, non-native phrasing, culture-specific politeness or humour can be mis-scored. Audit errors by group before relying on results.
* **Surveillance.** Analysing what employees write can chill honest speech. Be transparent (the submission page explains processing), keep scope narrow, avoid linking
  scores to individual performance, and involve employee representatives / legal counsel (e.g. GDPR / DPDP Act obligations: purpose limitation, retention, access rights).
* **Small samples** (a few comments) give meaningless percentages; the dashboard warns when totals are tiny.
* **Everything runs locally.** Feedback text is never sent to an external service.

### Safe handling of feedback data
Use least-privilege DB credentials; restrict who gets `hr_admin`; treat CSV exports (especially “with text”) as confidential and delete them after use;
back up the database encrypted; define a retention period and purge old rows; do not put credentials or sensitive personal data in feedback; serve over HTTPS;
review the audit log (Reports page) for unexpected exports or feedback views; rotate `SECRET_KEY` if exposed (it signs session cookies).

## 7. Project structure and file purposes

| Path | Purpose |
|------|---------|
| `app.py` | Application factory, error handlers, security headers, logging |
| `config.py` | Development / testing / production profiles from environment variables |
| `db.py` | PyMySQL access layer (parameterized queries, per-request connection, transactions) |
| `preprocessing.py` | Text cleaning (NLTK with automatic fallback) |
| `vectorizer.py` | TF-IDF configuration and persistence |
| `train_model.py` | Training + evaluation + saving artifacts |
| `predictor.py` | Loads artifacts; predictions, probabilities, influential terms |
| `database.sql` | Repeatable MySQL schema + reference departments |
| `init_db.py` | Applies `database.sql` through PyMySQL (Windows-friendly) |
| `create_admin.py` | Interactive creation of HR admin accounts |
| `utils/security.py` | CSRF, auth decorators, audit logging, validators |
| `blueprints/auth.py` · `employee.py` · `admin.py` | Routes for authentication, employee portal, HR portal |
| `templates/` | `base.html`, `base_auth.html`, `landing.html`, `error.html`, `_macros.html`, `auth/*`, `employee/*`, `admin/*` |
| `static/css/sentinel.css` | Design system from `DESIGN.md` (tokens, sidebar, cards, chips, tables, responsive rules) |
| `static/js/sentinel.js` · `dashboard_charts.js` · `feedback_explorer.js` | Drawer/counter/confirm behaviour · Chart.js charts · explorer detail drawer + filters |
| `dataset/` | Synthetic CSVs, generator script, provenance README |
| `models/` | Trained artifacts are written here (git-ignored) |
| `tests/` | Test suite (see §8) |
| `instance/` | Runtime log (`sentinel.log`) |
| `.env.example`, `.gitignore`, `requirements.txt` | Configuration template, ignore rules, dependencies |

Differences from the requested tree: added `utils/security.py`, `init_db.py`, `templates/_macros.html`, `templates/error.html`, `static/js/sentinel.js`,
`dataset/*` helper files and test helpers (`tests/helpers.py`, `tests/sqlite_shim.py`, `tests/sqlite_schema.sql`, `tests/test_mysql_integration.py`).
`templates/employee/dashboard.html` etc. follow the requested names. No required file was omitted.

## 8. Tests

| File | Needs MySQL? | Covers |
|------|:-----------:|--------|
| `tests/test_preprocessing.py` | No | Cleaning, negation handling, invalid input, dataset validation, training artifacts, predictor behaviour, missing-model error |
| `tests/test_auth.py` | No* | Registration/validation, hashing, CSRF, generic login errors, lockout, deactivation, admin/employee separation, logout, headers |
| `tests/test_employee.py` | No* | Access control, feedback submission with real model prediction, validation, missing model, history privacy, profile, forced password change |
| `tests/test_admin.py` | No* | Admin access control, analyst restrictions, live metrics, period filter, small-group suppression, anonymity, filters, LIKE-escaping, SQL-injection attempt, pagination, exports, CSV formula injection, audit |
| `tests/test_mysql_integration.py` | **Yes** (skipped unless `RUN_MYSQL_TESTS=1`) | Schema repeatability, FK/UNIQUE/CHECK enforcement on MySQL, full end-to-end flow and every admin page against real MySQL |

\* These use an in-memory **SQLite stand-in** (`tests/sqlite_shim.py`) so they run anywhere. They verify application logic, not MySQL-specific behaviour — run the
integration file against MySQL before trusting the SQL.

```powershell
# everything that does not need MySQL
python -m unittest discover -s tests -t . -v

# MySQL integration (uses a separate DB named sentinel_hr_test, which it drops/recreates)
$env:RUN_MYSQL_TESTS = "1"; $env:DB_USER = "root"; $env:DB_PASSWORD = "your-root-password"
python -m unittest tests.test_mysql_integration -v
```

## 9. What was and was not verified

Verified in the build environment (Python 3.12, scikit-learn 1.8, Flask 3.1):
* 65 tests discovered: 62 passed and 3 MySQL integration tests were skipped (no MySQL server available), 0 failures, and a few deliberate code “mutations” (exposing anonymous names, removing the
  per-employee filter, disabling CSRF) were confirmed to make the relevant tests fail;
* training and prediction run end-to-end and produce real metrics (§5).

**Not verified — be aware:**
* **No test was run against a real MySQL server** (none was available). SQL was written to be portable and reviewed by hand, but MySQL-specific issues are possible until
  you run `tests/test_mysql_integration.py`.
* **PyMySQL and NLTK were not installed in the build environment**, so the real NLTK path and the real PyMySQL driver were never exercised.
* **The UI was not opened in a browser**: templates render without errors, but layout, responsiveness and Chart.js rendering were not visually checked, and CDN assets could not be loaded.
* No load, penetration or accessibility testing; no email delivery; no HTTPS termination; sessions are signed cookies (not server-side).
* Self-registration is open to anyone who can reach the site. Set `ALLOWED_EMAIL_DOMAIN` and/or add an invitation step before real use.

## 10. Future work
Real labelled data and per-group error audits; probability calibration; server-side sessions; invitation-based onboarding; email password reset; PDF reports; data-retention job.

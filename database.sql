-- =====================================================================
-- Sentinel HR - MySQL schema (MySQL 8.0.16+ recommended)
-- REPEATABLE and NON-DESTRUCTIVE: uses IF NOT EXISTS / INSERT IGNORE only.
-- It never drops tables or deletes data. Safe to run more than once.
-- No administrator account is seeded: create one with `python create_admin.py`.
-- =====================================================================

CREATE DATABASE IF NOT EXISTS sentinel_hr CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE sentinel_hr;

CREATE TABLE IF NOT EXISTS departments (
    id          INT AUTO_INCREMENT PRIMARY KEY,
    name        VARCHAR(80) NOT NULL UNIQUE,
    code        VARCHAR(10) NOT NULL UNIQUE,
    created_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS employees (
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    emp_code             VARCHAR(20) NULL UNIQUE,
    full_name            VARCHAR(120) NOT NULL,
    email                VARCHAR(180) NOT NULL UNIQUE,
    password_hash        VARCHAR(255) NOT NULL,
    department_id        INT NOT NULL,
    role_title           VARCHAR(120) NOT NULL,
    years_experience     DECIMAL(4,1) NOT NULL DEFAULT 0.0,
    is_active            TINYINT(1) NOT NULL DEFAULT 1,
    must_change_password TINYINT(1) NOT NULL DEFAULT 0,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at        TIMESTAMP NULL DEFAULT NULL,
    CONSTRAINT chk_emp_years CHECK (years_experience >= 0 AND years_experience <= 60),
    CONSTRAINT fk_emp_department FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT,
    INDEX idx_emp_department (department_id),
    INDEX idx_emp_active (is_active)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS administrators (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    full_name      VARCHAR(120) NOT NULL,
    email          VARCHAR(180) NOT NULL UNIQUE,
    password_hash  VARCHAR(255) NOT NULL,
    -- hr_admin: full access incl. exports and employee management; hr_analyst: read-only analytics
    role           ENUM('hr_admin','hr_analyst') NOT NULL DEFAULT 'hr_analyst',
    is_active      TINYINT(1) NOT NULL DEFAULT 1,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_login_at  TIMESTAMP NULL DEFAULT NULL
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS feedback_submissions (
    id                INT AUTO_INCREMENT PRIMARY KEY,
    employee_id       INT NOT NULL,
    department_id     INT NOT NULL,            -- snapshot of the employee's department at submission time
    feedback_text     TEXT NOT NULL,
    overall_rating    TINYINT NULL,
    management_rating TINYINT NULL,
    workload_rating   TINYINT NULL,
    culture_rating    TINYINT NULL,
    is_anonymous      TINYINT(1) NOT NULL DEFAULT 0,   -- hide identity from HR views and exports
    submitted_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_fb_overall CHECK (overall_rating IS NULL OR overall_rating BETWEEN 1 AND 5),
    CONSTRAINT chk_fb_mgmt CHECK (management_rating IS NULL OR management_rating BETWEEN 1 AND 5),
    CONSTRAINT chk_fb_work CHECK (workload_rating IS NULL OR workload_rating BETWEEN 1 AND 5),
    CONSTRAINT chk_fb_cult CHECK (culture_rating IS NULL OR culture_rating BETWEEN 1 AND 5),
    CONSTRAINT fk_fb_employee FOREIGN KEY (employee_id) REFERENCES employees(id) ON DELETE CASCADE,
    CONSTRAINT fk_fb_department FOREIGN KEY (department_id) REFERENCES departments(id) ON DELETE RESTRICT,
    INDEX idx_fb_employee (employee_id),
    INDEX idx_fb_department (department_id),
    INDEX idx_fb_submitted (submitted_at)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS feedback_predictions (
    id             INT AUTO_INCREMENT PRIMARY KEY,
    submission_id  INT NOT NULL UNIQUE,
    sentiment      ENUM('Positive','Neutral','Negative') NOT NULL,
    confidence     DECIMAL(5,4) NOT NULL,
    prob_positive  DECIMAL(5,4) NOT NULL,
    prob_neutral   DECIMAL(5,4) NOT NULL,
    prob_negative  DECIMAL(5,4) NOT NULL,
    model_version  VARCHAR(64) NOT NULL,
    predicted_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_pred_submission FOREIGN KEY (submission_id) REFERENCES feedback_submissions(id) ON DELETE CASCADE,
    INDEX idx_pred_sentiment (sentiment)
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS audit_logs (
    id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    actor_type   ENUM('employee','admin','anonymous','system') NOT NULL,
    actor_id     INT NULL,
    action       VARCHAR(60) NOT NULL,
    target_type  VARCHAR(40) NULL,
    target_id    VARCHAR(60) NULL,
    details      VARCHAR(255) NULL,
    ip_address   VARCHAR(45) NULL,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_audit_action_time (action, created_at),
    INDEX idx_audit_actor (actor_type, actor_id),
    INDEX idx_audit_created (created_at)
) ENGINE=InnoDB;

-- Reference data only (department names are generic placeholders, not real personal data).
INSERT IGNORE INTO departments (name, code) VALUES
    ('Engineering', 'ENG'),
    ('Sales', 'SAL'),
    ('Marketing', 'MKT'),
    ('Human Resources', 'HR'),
    ('Finance', 'FIN'),
    ('Operations', 'OPS'),
    ('Customer Support', 'SUP'),
    ('Product & Design', 'PRD');

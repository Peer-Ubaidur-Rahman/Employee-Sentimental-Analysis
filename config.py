"""
config.py - environment-driven configuration profiles.

Select a profile with APP_ENV=development|testing|production (default: development).
Secrets and database credentials are ONLY read from environment variables / .env.
"""
import os

from dotenv import load_dotenv

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(BASE_DIR, ".env"))


def _bool(name: str, default: bool = False) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in ("1", "true", "yes", "on")


class BaseConfig:
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.environ.get("SECRET_KEY") or ""

    # Database (PyMySQL)
    DB_HOST = os.environ.get("DB_HOST", "localhost")
    DB_PORT = int(os.environ.get("DB_PORT", "3306"))
    DB_USER = os.environ.get("DB_USER", "")
    DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
    DB_NAME = os.environ.get("DB_NAME", "sentinel_hr")

    # Sessions / cookies
    PERMANENT_SESSION_LIFETIME = 60 * 60 * 2  # 2 hours
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", False)
    CSRF_ENABLED = True

    # Privacy: groups smaller than this never get a sentiment breakdown shown to HR
    MIN_GROUP_SIZE = int(os.environ.get("MIN_GROUP_SIZE", "5"))

    # Brute-force protection
    MAX_FAILED_LOGINS = 5
    LOCKOUT_MINUTES = 15

    # Optional: restrict self-registration to one email domain, e.g. "example.com"
    ALLOWED_EMAIL_DOMAIN = os.environ.get("ALLOWED_EMAIL_DOMAIN", "")

    # Input limits
    MAX_FEEDBACK_CHARS = 2000
    MIN_FEEDBACK_CHARS = 15
    PAGE_SIZE = 15

    # ML artifacts
    MODEL_DIR = os.path.join(BASE_DIR, "models")
    DATASET_PATH = os.path.join(BASE_DIR, "dataset", "employee_feedback.csv")
    CHALLENGE_PATH = os.path.join(BASE_DIR, "dataset", "challenge_set.csv")


class DevelopmentConfig(BaseConfig):
    DEBUG = _bool("FLASK_DEBUG", False)
    # Development convenience only: an obviously insecure key, never used in production.
    SECRET_KEY = BaseConfig.SECRET_KEY or "dev-only-insecure-key-do-not-use-in-production"


class TestingConfig(BaseConfig):
    TESTING = True
    SECRET_KEY = "testing-secret-key"
    DB_NAME = os.environ.get("TEST_DB_NAME", "sentinel_hr_test")
    SESSION_COOKIE_SECURE = False


class ProductionConfig(BaseConfig):
    DEBUG = False
    SESSION_COOKIE_SECURE = _bool("SESSION_COOKIE_SECURE", True)

    @classmethod
    def validate(cls):
        if not cls.SECRET_KEY or len(cls.SECRET_KEY) < 32:
            raise RuntimeError("Production requires SECRET_KEY (>= 32 chars) set in the environment.")
        if not cls.DB_USER or not cls.DB_PASSWORD:
            raise RuntimeError("Production requires DB_USER and DB_PASSWORD set in the environment.")


CONFIG_MAP = {
    "development": DevelopmentConfig,
    "testing": TestingConfig,
    "production": ProductionConfig,
}


def get_config(name: str = None):
    name = (name or os.environ.get("APP_ENV", "development")).lower()
    cfg = CONFIG_MAP.get(name)
    if cfg is None:
        raise RuntimeError(f"Unknown APP_ENV '{name}'. Use development, testing or production.")
    if hasattr(cfg, "validate"):
        cfg.validate()
    return cfg

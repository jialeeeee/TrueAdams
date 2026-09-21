import os


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev")
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
    CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")

    SMTP_HOST = os.environ.get("SMTP_HOST")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", 587))
    SMTP_USER = os.environ.get("SMTP_USER")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD")
    MAIL_FROM = os.environ.get("MAIL_FROM", "no-reply@connectsphere.io")


class TestConfig(Config):
    """Config for the test suite: no Postgres, no Redis, no real SMTP."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret-key"

    # In-memory SQLite keeps tests fast and isolated from the Supabase database.
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

    # Run Celery tasks inline instead of dispatching them to a broker.
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"

    SMTP_HOST = "smtp.test.invalid"
    SMTP_PORT = 587
    SMTP_USER = "test-user"
    SMTP_PASSWORD = "test-password"
    MAIL_FROM = "no-reply@test.invalid"

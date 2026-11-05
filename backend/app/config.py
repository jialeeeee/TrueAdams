import os

from dotenv import load_dotenv

# Load backend/.env before any setting below is read from the environment.
load_dotenv()

# SCRUM-99 AC5: how often coordinators are reminded about incomplete arrangements, unless
# REMINDER_INTERVAL_HOURS says otherwise. Release 1 has no administrator role, so whoever
# deploys the system changes it.
DEFAULT_REMINDER_INTERVAL_HOURS = 24


def reminder_interval_hours(value):
    """REMINDER_INTERVAL_HOURS as a number of hours: the default when it isn't set. A value
    that isn't a positive number stops the app starting, rather than running the reminders
    at some other frequency without anyone noticing."""
    if value is None or not value.strip():
        return DEFAULT_REMINDER_INTERVAL_HOURS
    try:
        hours = float(value)
    except ValueError:
        hours = None
    if hours is None or not 0 < hours < float("inf"):
        raise ValueError(f"REMINDER_INTERVAL_HOURS must be a positive number of hours, "
                         f"not {value!r}.")
    return hours


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

    REMINDER_INTERVAL_HOURS = reminder_interval_hours(os.environ.get("REMINDER_INTERVAL_HOURS"))


class TestConfig(Config):
    """Config for the test suite: Supabase via a restricted role, no Redis, no real SMTP."""

    TESTING = True
    SECRET_KEY = "test-secret-key"
    JWT_SECRET_KEY = "test-jwt-secret-key"

    # Connects as the `connectsphere_test` role (db/test_role.sql), which can read
    # and write rows in the public tables but never change them. Each test's rows
    # are rolled back (tests/base.py). Never DATABASE_URL.
    SQLALCHEMY_DATABASE_URI = os.environ.get("TEST_DATABASE_URL")

    # Run Celery tasks inline instead of dispatching them to a broker.
    CELERY_BROKER_URL = "memory://"
    CELERY_RESULT_BACKEND = "cache+memory://"

    SMTP_HOST = "smtp.test.invalid"
    SMTP_PORT = 587
    SMTP_USER = "test-user"
    SMTP_PASSWORD = "test-password"
    MAIL_FROM = "no-reply@test.invalid"

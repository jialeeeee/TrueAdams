import pytest

from app import tasks
from app.config import Config


class FakeSMTP:
    """Stand-in for smtplib.SMTP that records what would have been sent."""

    instances = []

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.started_tls = False
        self.login_args = None
        self.sent_messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.login_args = (user, password)

    def send_message(self, message):
        self.sent_messages.append(message)


@pytest.fixture
def smtp(monkeypatch):
    FakeSMTP.instances = []
    monkeypatch.setattr(tasks.smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(Config, "SMTP_HOST", "smtp.test.invalid")
    monkeypatch.setattr(Config, "SMTP_PORT", 587)
    monkeypatch.setattr(Config, "SMTP_USER", "test-user")
    monkeypatch.setattr(Config, "SMTP_PASSWORD", "test-password")
    monkeypatch.setattr(Config, "MAIL_FROM", "no-reply@test.invalid")
    return FakeSMTP


def test_send_notification_email_builds_the_expected_message(smtp):
    tasks.send_notification_email(
        "attendee@test.invalid", "Event approved", "Your event was approved."
    )

    connection = smtp.instances[0]
    message = connection.sent_messages[0]

    assert message["To"] == "attendee@test.invalid"
    assert message["From"] == "no-reply@test.invalid"
    assert message["Subject"] == "Event approved"
    assert message.get_content().strip() == "Your event was approved."


def test_send_notification_email_uses_tls_and_authenticates(smtp):
    tasks.send_notification_email("a@test.invalid", "Subject", "Body")

    connection = smtp.instances[0]

    assert (connection.host, connection.port) == ("smtp.test.invalid", 587)
    assert connection.started_tls is True
    assert connection.login_args == ("test-user", "test-password")


def test_task_is_registered_with_celery_under_a_stable_name():
    assert tasks.send_notification_email.name == "tasks.send_notification_email"

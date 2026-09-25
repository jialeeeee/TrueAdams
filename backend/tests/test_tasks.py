import unittest
from unittest import mock

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


class SendNotificationEmailTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.instances = []
        patches = [
            mock.patch.object(tasks.smtplib, "SMTP", FakeSMTP),
            mock.patch.object(Config, "SMTP_HOST", "smtp.test.invalid"),
            mock.patch.object(Config, "SMTP_PORT", 587),
            mock.patch.object(Config, "SMTP_USER", "test-user"),
            mock.patch.object(Config, "SMTP_PASSWORD", "test-password"),
            mock.patch.object(Config, "MAIL_FROM", "no-reply@test.invalid"),
        ]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)

    def test_send_notification_email_builds_the_expected_message(self):
        tasks.send_notification_email(
            "attendee@test.invalid", "Event approved", "Your event was approved."
        )

        connection = FakeSMTP.instances[0]
        message = connection.sent_messages[0]

        self.assertEqual(message["To"], "attendee@test.invalid")
        self.assertEqual(message["From"], "no-reply@test.invalid")
        self.assertEqual(message["Subject"], "Event approved")
        self.assertEqual(message.get_content().strip(), "Your event was approved.")

    def test_send_notification_email_uses_tls_and_authenticates(self):
        tasks.send_notification_email("a@test.invalid", "Subject", "Body")

        connection = FakeSMTP.instances[0]

        self.assertEqual((connection.host, connection.port), ("smtp.test.invalid", 587))
        self.assertIs(connection.started_tls, True)
        self.assertEqual(connection.login_args, ("test-user", "test-password"))


class CeleryRegistrationTests(unittest.TestCase):
    def test_task_is_registered_with_celery_under_a_stable_name(self):
        self.assertEqual(
            tasks.send_notification_email.name, "tasks.send_notification_email"
        )

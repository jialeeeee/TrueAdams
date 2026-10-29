import smtplib
from email.message import EmailMessage

from .config import Config
from .extensions import celery


@celery.task(name="tasks.send_notification_email")
def send_notification_email(to_address: str, subject: str, body: str) -> None:
    message = EmailMessage()
    message["From"] = Config.MAIL_FROM
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    with smtplib.SMTP(Config.SMTP_HOST, Config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
        smtp.send_message(message)


@celery.task(name="tasks.check_hold_expiries")
def check_hold_expiries() -> None:
    """SCRUM-86: record expired tentative holds and warn coordinators of those about to
    expire. Celery beat runs it every few minutes (app/venues/hold_expiry.py)."""
    # Imported here because the venues module imports this one.
    from .venues import hold_expiry

    hold_expiry.run()

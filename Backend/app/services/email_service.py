import logging
import smtplib
from email.message import EmailMessage

from app.settings import settings

logger = logging.getLogger(__name__)

# Console mode keeps the last 100 messages here (tests read them)
outbox: list[dict] = []


def send_email(to: str, subject: str, body: str) -> bool:
    """Send over SMTP when SMTP_HOST is set, otherwise print to the console."""
    if not settings.SMTP_HOST:
        outbox.append({"to": to, "subject": subject, "body": body})
        del outbox[:-100]
        print(f"\n--- EMAIL (console mode) ---\nTo: {to}\nSubject: {subject}\n\n{body}\n----------------------------\n")
        return True

    message = EmailMessage()
    message["From"] = settings.SMTP_FROM
    message["To"] = to
    message["Subject"] = subject
    message.set_content(body)
    try:
        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            if settings.SMTP_USE_TLS:
                server.starttls()
            if settings.SMTP_USER:
                server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.send_message(message)
        return True
    except Exception:  # a mail outage must never break the request
        logger.exception("Could not send email to %s", to)
        return False
"""
Email Service
Author: Amit Bhagat
Purpose: Send the temporary password to the employee's manager, and only when
         the operator asks for it.

Change #3 of the enhancement specification.

Two rules shape this module:

    No automatic sending. Nothing here is called by the password reset flow.
    It is called only from the explicit "Send Email To Manager" action, so an
    email cannot be sent as a side effect of a reset.

    The manager is the recipient, not the employee. A user whose password has
    just been reset may be locked out of the mailbox the credential would be
    sent to.

Credentials come from the environment. Nothing is hardcoded, and neither the
SMTP username, the SMTP password, nor the message body is ever logged.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from email.message import EmailMessage
from typing import Tuple

from loguru import logger

NOT_AVAILABLE = "Not Available"

EMAIL_SUBJECT = "[Confidential] Password Reset Successful - Employee Account"


class EmailConfig:
    """SMTP settings, read from the environment."""

    HOST = os.getenv("SMTP_HOST", "")
    PORT = int(os.getenv("SMTP_PORT", "587"))
    USERNAME = os.getenv("SMTP_USERNAME", "")
    PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SENDER = os.getenv("SMTP_SENDER", "")
    # STARTTLS is the default because port 587 is the documented example.
    USE_TLS = os.getenv("SMTP_USE_TLS", "true").strip().lower() in {"true", "1", "yes", "on"}
    TIMEOUT = int(os.getenv("SMTP_TIMEOUT", "20"))

    @classmethod
    def is_configured(cls) -> bool:
        """Return True when enough is set to attempt a send."""
        return bool(cls.HOST and cls.SENDER)

    @classmethod
    def missing_fields(cls) -> list:
        """Return the names of the settings that still need values."""
        missing = []
        if not cls.HOST:
            missing.append("SMTP_HOST")
        if not cls.SENDER:
            missing.append("SMTP_SENDER")
        return missing


def build_email_body(
    manager_name: str,
    username: str,
    employee_name: str,
    password: str,
) -> str:
    """
    Build the message body defined in the specification.

    Args:
        manager_name: The manager's display name.
        username: The employee's username.
        employee_name: The employee's display name.
        password: The original temporary password.

    Returns:
        The body text. Never logged.
    """
    return (
        f"Hello {manager_name},\n\n"
        "The password for the following employee has been reset by TechAdmin AI.\n\n"
        f"Employee Username:\n{username}\n\n"
        f"Employee Name:\n{employee_name or username}\n\n"
        f"Temporary Password:\n{password}\n\n"
        "This is one time only password. Please securely communicate this password to the employee.\n\n"
        "Regards,\n"
        "TechAdmin Support Team\n"
    )


def send_password_email(
    manager_email: str,
    manager_name: str,
    username: str,
    employee_name: str,
    password: str,
) -> Tuple[bool, str]:
    """
    Send the temporary password to the manager.

    Called only from the explicit operator action. Every failure path returns a
    status rather than raising, because the specification requires that a failed
    send must not bring down the application: the reset has already succeeded
    and the operator can still download the TXT file.

    Args:
        manager_email: Recipient. Must be a real address, not "Not Available".
        manager_name: Used in the greeting.
        username: The employee's username.
        employee_name: The employee's display name.
        password: The original temporary password.

    Returns:
        Tuple of (sent, message). The message is safe to show the operator.
    """
    if not manager_email or manager_email == NOT_AVAILABLE:
        logger.warning(
            "EMAIL_SEND_FAILED | username={} | reason=no_manager_email", username
        )
        return False, "No manager email address is available for this employee."

    if not EmailConfig.is_configured():
        missing = ", ".join(EmailConfig.missing_fields())
        logger.warning(
            "EMAIL_SEND_FAILED | username={} | reason=smtp_not_configured | missing={}",
            username,
            missing,
        )
        return False, f"Email is not configured. Missing in .env: {missing}"

    message = EmailMessage()
    message["Subject"] = EMAIL_SUBJECT
    message["From"] = EmailConfig.SENDER
    message["To"] = manager_email
    message.set_content(
        build_email_body(
            manager_name=manager_name or "Manager",
            username=username,
            employee_name=employee_name,
            password=password,
        )
    )

    try:
        with smtplib.SMTP(
            EmailConfig.HOST, EmailConfig.PORT, timeout=EmailConfig.TIMEOUT
        ) as server:
            if EmailConfig.USE_TLS:
                server.starttls(context=ssl.create_default_context())

            # Authentication is optional: an internal relay often accepts mail
            # from an allowed host without it.
            if EmailConfig.USERNAME and EmailConfig.PASSWORD:
                server.login(EmailConfig.USERNAME, EmailConfig.PASSWORD)

            server.send_message(message)

        # Recipient and outcome are logged. The body, the password and the SMTP
        # credentials are not.
        logger.info(
            "EMAIL_SEND_SUCCESS | username={} | recipient={}", username, manager_email
        )
        return True, f"Email sent to {manager_email}."

    except smtplib.SMTPAuthenticationError:
        logger.error(
            "EMAIL_SEND_FAILED | username={} | recipient={} | error_type=SMTPAuthenticationError",
            username,
            manager_email,
        )
        return False, "The mail server rejected the configured credentials."

    except smtplib.SMTPException as exc:
        logger.error(
            "EMAIL_SEND_FAILED | username={} | recipient={} | error_type={}",
            username,
            manager_email,
            type(exc).__name__,
        )
        return False, "The mail server refused the message."

    except Exception as exc:
        logger.error(
            "EMAIL_SEND_FAILED | username={} | recipient={} | error_type={}",
            username,
            manager_email,
            type(exc).__name__,
        )
        return False, "Could not reach the mail server."


# ---------------------------------------------------------------------------
# Help & Support
# ---------------------------------------------------------------------------

DEFAULT_SUPPORT_EMAIL = "TechAdmin@coforge.com"
SUPPORT_SUBJECT_PREFIX = "[TechAdmin Help & Support]"
SUPPORT_QUERY_MAX_CHARS = 4000


def support_recipient() -> str:
    """Mailbox that receives Help & Support queries (override with SUPPORT_EMAIL)."""
    return (os.getenv("SUPPORT_EMAIL") or DEFAULT_SUPPORT_EMAIL).strip()


def _single_line(value: str, limit: int = 120) -> str:
    """Strip line breaks so user-supplied text cannot inject mail headers."""
    return " ".join(str(value or "").split())[:limit]


def build_support_email_body(
    requester_name: str,
    requester_email: str,
    query: str,
    submitted_at: str,
) -> str:
    """Build the automated Help & Support message body."""
    return (
        "Hello TechAdmin Support Team,\n\n"
        "A new Help & Support query has been submitted from the TechAdmin AI portal.\n\n"
        f"Submitted by:\n{requester_name or 'Not Available'}\n\n"
        f"Email:\n{requester_email or 'Not Available'}\n\n"
        f"Submitted at:\n{submitted_at}\n\n"
        f"Query:\n{query}\n\n"
        "This is an automated message generated by TechAdmin AI. "
        "Reply to this email to respond to the requester directly.\n\n"
        "Regards,\n"
        "TechAdmin AI\n"
    )


def send_support_email(
    requester_name: str,
    requester_email: str,
    query: str,
    submitted_at: str,
) -> Tuple[bool, str]:
    """
    Send a Help & Support query to the TechAdmin support mailbox.

    Uses the same SMTP settings as the manager email. Every failure path returns
    a status rather than raising, so a failed send never breaks the UI.

    Returns:
        Tuple of (sent, message). The message is safe to show the operator.
    """
    query = (query or "").strip()
    if not query:
        return False, "Please describe your query before submitting."
    if len(query) > SUPPORT_QUERY_MAX_CHARS:
        return False, f"Please keep your query under {SUPPORT_QUERY_MAX_CHARS} characters."

    recipient = support_recipient()

    # Read SMTP settings at call time so values loaded from .env after this
    # module was imported are still honoured.
    host = os.getenv("SMTP_HOST", EmailConfig.HOST)
    port = int(os.getenv("SMTP_PORT", str(EmailConfig.PORT)))
    username = os.getenv("SMTP_USERNAME", EmailConfig.USERNAME)
    password = os.getenv("SMTP_PASSWORD", EmailConfig.PASSWORD)
    sender = os.getenv("SMTP_SENDER", EmailConfig.SENDER)
    use_tls = os.getenv("SMTP_USE_TLS", "true" if EmailConfig.USE_TLS else "false").strip().lower() in {
        "true", "1", "yes", "on"
    }
    timeout = int(os.getenv("SMTP_TIMEOUT", str(EmailConfig.TIMEOUT)))

    missing = [name for name, value in (("SMTP_HOST", host), ("SMTP_SENDER", sender)) if not value]
    if missing:
        logger.warning(
            "SUPPORT_EMAIL_FAILED | requester={} | reason=smtp_not_configured | missing={}",
            requester_email,
            ", ".join(missing),
        )
        return False, f"Email is not configured. Missing in .env: {', '.join(missing)}"

    name_line = _single_line(requester_name) or "TechAdmin user"
    message = EmailMessage()
    message["Subject"] = f"{SUPPORT_SUBJECT_PREFIX} Query from {name_line}"
    message["From"] = sender
    message["To"] = recipient
    reply_to = _single_line(requester_email, 254)
    if reply_to and "@" in reply_to:
        message["Reply-To"] = reply_to
    message.set_content(
        build_support_email_body(
            requester_name=name_line,
            requester_email=reply_to,
            query=query,
            submitted_at=submitted_at,
        )
    )

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as server:
            if use_tls:
                server.starttls(context=ssl.create_default_context())
            if username and password:
                server.login(username, password)
            server.send_message(message)

        # The query text itself is not logged.
        logger.info("SUPPORT_EMAIL_SUCCESS | requester={} | recipient={}", requester_email, recipient)
        return True, f"Your query has been sent to {recipient}. The TechAdmin team will get back to you."

    except smtplib.SMTPAuthenticationError:
        logger.error("SUPPORT_EMAIL_FAILED | requester={} | error_type=SMTPAuthenticationError", requester_email)
        return False, "The mail server rejected the configured credentials."
    except smtplib.SMTPException as exc:
        logger.error("SUPPORT_EMAIL_FAILED | requester={} | error_type={}", requester_email, type(exc).__name__)
        return False, "The mail server refused the message."
    except Exception as exc:
        logger.error("SUPPORT_EMAIL_FAILED | requester={} | error_type={}", requester_email, type(exc).__name__)
        return False, "Could not reach the mail server."

 
"""Consolidated GNOC notification sent to one or more recipients."""
from __future__ import annotations
import os
import re
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from typing import Iterable
from App.services.infrastructure.models import InfrastructureSiteAlert

@dataclass(frozen=True)
class InfrastructureNotificationItem:
    alert: InfrastructureSiteAlert
    ticket_success: bool
    ticket_id: str | None
    ticket_message: str

def _recipients() -> list[str]:
    raw = os.getenv("INFRA_ALERT_EMAIL_TO", "gnoc@coforge.com")
    return list(dict.fromkeys(v.strip() for v in re.split(r"[,;]", raw) if v.strip()))

def send_consolidated_site_alert_email(items: Iterable[InfrastructureNotificationItem], *, poll_completed_at: datetime) -> tuple[bool, str]:
    rows = list(items)
    recipients = _recipients()
    if not rows:
        return True, "No new incidents required an email."
    if not recipients:
        return False, "No email recipients are configured."
    host = os.getenv("SMTP_HOST", "").strip()
    if not host:
        return False, "SMTP_HOST is not configured."
    p1 = sum(item.alert.priority == "P1" for item in rows)
    p2 = sum(item.alert.priority == "P2" for item in rows)
    body = [
        "TechAdmin Infrastructure Agent completed a SolarWinds site-health check.",
        "",
        f"Completed: {poll_completed_at}",
        f"P1 sites: {p1}",
        f"P2 sites: {p2}",
        "",
    ]
    body.extend(
        f"- {item.alert.priority} | {item.alert.location_name} | "
        f"{item.alert.site_status} | affected SolarWinds devices: "
        f"{item.alert.affected_count} | ticket: {item.ticket_id or 'not returned'}"
        for item in rows
    )
    message = EmailMessage()
    message["From"] = os.getenv("SMTP_SENDER", "TechAdmin@Coforge.com")
    message["To"] = ", ".join(recipients)
    message["Subject"] = f"[TechAdmin Infrastructure] {p1} P1 and {p2} P2 incidents"
    message.set_content("\n".join(body))
    try:
        with smtplib.SMTP(host, int(os.getenv("SMTP_PORT", "25")), timeout=int(os.getenv("SMTP_TIMEOUT", "20"))) as client:
            if os.getenv("SMTP_USE_TLS", "false").strip().casefold() in {"1", "true", "yes", "on"}:
                client.starttls()
            username = os.getenv("SMTP_USERNAME", "").strip()
            if username:
                client.login(username, os.getenv("SMTP_PASSWORD", ""))
            client.send_message(message, to_addrs=recipients)
        return True, f"Sent to {', '.join(recipients)}."
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

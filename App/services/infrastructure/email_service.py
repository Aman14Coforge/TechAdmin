"""Consolidated GNOC email notifications for Infrastructure Agent polls."""
from __future__ import annotations

import os
import smtplib
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from html import escape
from typing import Iterable

from App.services.infrastructure.models import InfrastructureSiteAlert


@dataclass(frozen=True)
class InfrastructureNotificationItem:
    """One site-level ticket result included in the consolidated email."""

    alert: InfrastructureSiteAlert
    ticket_success: bool
    ticket_id: str | None
    ticket_message: str


def _format_value(value: object) -> str:
    return "Not available" if value in (None, "") else str(value)


def _site_line(item: InfrastructureNotificationItem) -> str:
    alert = item.alert
    ticket_label = item.ticket_id or (
        "Accepted without returned ticket ID"
        if item.ticket_success
        else "Ticket creation failed"
    )
    return (
        f"- {alert.location_name} | status={alert.site_status.upper()} | "
        f"score={_format_value(alert.site_score)} | "
        f"affected devices={alert.affected_count} | "
        f"reason={_format_value(alert.site_reason)} | "
        f"iEngage={ticket_label}"
    )


def _plain_text_body(
    items: list[InfrastructureNotificationItem],
    *,
    poll_completed_at: datetime,
) -> str:
    p1 = [item for item in items if item.alert.priority == "P1"]
    p2 = [item for item in items if item.alert.priority == "P2"]
    successful = [item for item in items if item.ticket_success]
    failed = [item for item in items if not item.ticket_success]

    sections = [
        "TechAdmin Infrastructure Agent completed an ITOM site-health poll.",
        "",
        "Summary",
        f"- Poll completed: {poll_completed_at:%d %b %Y, %H:%M:%S %Z}",
        f"- Newly processed site incidents: {len(items)}",
        f"- P1 critical sites: {len(p1)}",
        f"- P2 warning sites: {len(p2)}",
        f"- Successful iEngage ticket operations: {len(successful)}",
        f"- Failed iEngage ticket operations: {len(failed)}",
        "",
    ]

    if p1:
        sections.extend(["P1 critical sites", *[_site_line(item) for item in p1], ""])

    if p2:
        sections.extend(["P2 warning sites", *[_site_line(item) for item in p2], ""])

    sections.extend(
        [
            "Detailed affected-device evidence and the copyable SolarWinds investigation prompt",
            "are available in the corresponding iEngage incident and in TechAdmin Infrastructure Agent.",
            "",
            "This is one consolidated notification for the polling cycle. No device-level emails were sent.",
        ]
    )

    return "\n".join(sections)


def _html_table_rows(items: list[InfrastructureNotificationItem]) -> str:
    rows: list[str] = []
    for item in items:
        alert = item.alert
        ticket = item.ticket_id or (
            "Accepted without ID" if item.ticket_success else "Failed"
        )
        ticket_status = "Created" if item.ticket_success else "Failed"
        rows.append(
            "<tr>"
            f"<td>{escape(alert.priority)}</td>"
            f"<td>{escape(alert.location_name)}</td>"
            f"<td>{escape(alert.site_status.upper())}</td>"
            f"<td>{escape(_format_value(alert.site_score))}</td>"
            f"<td>{alert.affected_count}</td>"
            f"<td>{escape(_format_value(alert.site_reason))}</td>"
            f"<td>{escape(ticket_status)}</td>"
            f"<td>{escape(ticket)}</td>"
            "</tr>"
        )
    return "".join(rows)


def _html_body(
    items: list[InfrastructureNotificationItem],
    *,
    poll_completed_at: datetime,
) -> str:
    p1_count = sum(item.alert.priority == "P1" for item in items)
    p2_count = sum(item.alert.priority == "P2" for item in items)
    successful = sum(item.ticket_success for item in items)
    failed = len(items) - successful

    return f"""
    <html>
      <body style="font-family:Segoe UI,Arial,sans-serif;color:#1f2937">
        <h2 style="margin-bottom:4px">TechAdmin Infrastructure Agent</h2>
        <p style="margin-top:0;color:#667085">Consolidated ITOM site-health notification</p>
        <table cellpadding="6" cellspacing="0" style="border-collapse:collapse;margin-bottom:18px">
          <tr><td><strong>Poll completed</strong></td><td>{escape(poll_completed_at.strftime('%d %b %Y, %H:%M:%S %Z'))}</td></tr>
          <tr><td><strong>New site incidents</strong></td><td>{len(items)}</td></tr>
          <tr><td><strong>P1 critical</strong></td><td>{p1_count}</td></tr>
          <tr><td><strong>P2 warning</strong></td><td>{p2_count}</td></tr>
          <tr><td><strong>Successful ticket operations</strong></td><td>{successful}</td></tr>
          <tr><td><strong>Failed ticket operations</strong></td><td>{failed}</td></tr>
        </table>
        <table cellpadding="7" cellspacing="0" border="1" style="border-collapse:collapse;border-color:#d0d5dd;font-size:13px">
          <thead style="background:#f2f4f7">
            <tr>
              <th>Priority</th><th>Site</th><th>Status</th><th>Score</th>
              <th>Affected devices</th><th>Reason</th><th>Ticket status</th><th>Ticket ID</th>
            </tr>
          </thead>
          <tbody>{_html_table_rows(items)}</tbody>
        </table>
        <p style="margin-top:18px">
          Detailed affected-device evidence and the SolarWinds investigation prompt are available
          in the corresponding iEngage incident and in TechAdmin Infrastructure Agent.
        </p>
        <p style="color:#667085">
          This is one consolidated notification for the polling cycle. No device-level emails were sent.
        </p>
      </body>
    </html>
    """.strip()


def send_consolidated_site_alert_email(
    items: Iterable[InfrastructureNotificationItem],
    *,
    poll_completed_at: datetime,
) -> tuple[bool, str]:
    """Send exactly one GNOC email for newly processed sites in one poll.

    Existing active incidents that were skipped are not emailed again. Device
    details are deliberately excluded from email and remain in iEngage and UI.
    """
    notification_items = list(items)
    if not notification_items:
        return True, "No newly processed site incidents required an email."

    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_SENDER", "TechAdmin@Coforge.com").strip()
    recipient = os.getenv("INFRA_ALERT_EMAIL_TO", "gnoc@coforge.com").strip()

    if not host:
        return False, "SMTP_HOST is not configured."
    if not recipient:
        return False, "INFRA_ALERT_EMAIL_TO is not configured."

    p1_count = sum(item.alert.priority == "P1" for item in notification_items)
    p2_count = sum(item.alert.priority == "P2" for item in notification_items)
    successful = sum(item.ticket_success for item in notification_items)

    message = EmailMessage()
    message["From"] = sender
    message["To"] = recipient
    message["Subject"] = (
        f"[TechAdmin Infrastructure] {p1_count} P1 and {p2_count} P2 "
        f"site incidents | {successful} iEngage ticket operations successful"
    )
    message.set_content(
        _plain_text_body(
            notification_items,
            poll_completed_at=poll_completed_at,
        )
    )
    message.add_alternative(
        _html_body(
            notification_items,
            poll_completed_at=poll_completed_at,
        ),
        subtype="html",
    )

    port = int(os.getenv("SMTP_PORT", "25"))
    timeout = int(os.getenv("SMTP_TIMEOUT", "20"))
    use_tls = os.getenv("SMTP_USE_TLS", "false").strip().casefold() in {
        "1", "true", "yes", "on"
    }
    username = os.getenv("SMTP_USERNAME", "").strip()
    password = os.getenv("SMTP_PASSWORD", "")

    try:
        with smtplib.SMTP(host, port, timeout=timeout) as client:
            if use_tls:
                client.starttls()
            if username:
                client.login(username, password)
            client.send_message(message)
        return True, (
            f"One consolidated Infrastructure Agent notification was sent to {recipient} "
            f"for {len(notification_items)} site incidents."
        )
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

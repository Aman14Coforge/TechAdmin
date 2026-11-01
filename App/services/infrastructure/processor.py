"""One Infrastructure Agent polling and automation cycle."""
from __future__ import annotations

import asyncio
import os
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger

from App.services.infrastructure.email_service import (
    InfrastructureNotificationItem,
    send_consolidated_site_alert_email,
)
from App.services.infrastructure.itom_repository import ITOMSiteRepository
from App.services.infrastructure.prompt_builder import build_ticket_description
from App.services.infrastructure.state_repository import InfrastructureStateRepository
from App.services.infrastructure.ticket_service import InfrastructureTicketService


def _flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on"}


def _ticket_id(result: Any) -> str | None:
    value = getattr(result, "ticket_id", None)
    return str(value) if value else None


def _now_ist() -> datetime:
    return datetime.now(ZoneInfo("Asia/Kolkata"))


async def process_infrastructure_sites_async(
    *,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    """Process one poll and always persist its execution history."""
    state = InfrastructureStateRepository()
    run_id = state.start_poll_run(trigger_type)
    source_sync_run_id: str | None = None
    summary: dict[str, Any] = {
        "poll_run_id": run_id,
        "trigger_type": trigger_type,
        "alerts": 0,
        "tickets_attempted": 0,
        "tickets_created": 0,
        "emails_sent": 0,
        "email_sites": 0,
        "skipped": 0,
        "recovered": 0,
        "errors": [],
    }

    try:
        source = ITOMSiteRepository()
        ticket_service = InfrastructureTicketService()
        alerts = source.latest_alerts()
        summary["alerts"] = len(alerts)
        source_sync_run_id = str(alerts[0].sync_run_id) if alerts else None

        active_locations = {alert.location_name for alert in alerts}
        summary["recovered"] = state.mark_recovered_except(active_locations)
        max_tickets = max(1, int(os.getenv("INFRA_MAX_AUTOMATIC_TICKETS_PER_RUN", "50")))
        notification_items: list[InfrastructureNotificationItem] = []

        for alert in alerts:
            description, prompt = build_ticket_description(alert)
            create_ticket, reason = state.should_create_ticket(alert)
            state.upsert_detection(alert, description=description, prompt=prompt)

            if not create_ticket:
                summary["skipped"] += 1
                continue

            if summary["tickets_attempted"] >= max_tickets:
                summary["errors"].append("Automatic ticket limit reached for this poll.")
                break

            summary["tickets_attempted"] += 1
            try:
                result = await ticket_service.create(alert, description)
                success = bool(getattr(result, "success", False))
                ticket_id = _ticket_id(result)
                message = str(getattr(result, "message", "Ticket operation completed."))
                state.record_ticket(
                    alert.location_name,
                    success=success,
                    ticket_id=ticket_id,
                    message=message,
                )
                if success:
                    summary["tickets_created"] += 1
                notification_items.append(
                    InfrastructureNotificationItem(
                        alert=alert,
                        ticket_success=success,
                        ticket_id=ticket_id,
                        ticket_message=message,
                    )
                )
            except Exception as exc:
                logger.exception(
                    "INFRASTRUCTURE_TICKET_FAILED | location={} | reason={}",
                    alert.location_name,
                    reason,
                )
                message = f"{type(exc).__name__}: {exc}"
                state.record_ticket(
                    alert.location_name,
                    success=False,
                    ticket_id=None,
                    message=message,
                )
                notification_items.append(
                    InfrastructureNotificationItem(
                        alert=alert,
                        ticket_success=False,
                        ticket_id=None,
                        ticket_message=message,
                    )
                )
                summary["errors"].append(f"{alert.location_name}: {message}")

        if notification_items and _flag("INFRA_EMAIL_ENABLED", "true"):
            email_success, email_message = send_consolidated_site_alert_email(
                notification_items,
                poll_completed_at=_now_ist(),
            )
            summary["email_sites"] = len(notification_items)
            summary["emails_sent"] = 1 if email_success else 0
            for item in notification_items:
                state.record_email(
                    item.alert.location_name,
                    email_success,
                    email_message,
                )
            if not email_success:
                summary["errors"].append(f"Consolidated GNOC email: {email_message}")

        status = "completed" if not summary["errors"] else "completed_with_errors"
        state.complete_poll_run(
            run_id,
            status=status,
            summary=summary,
            source_sync_run_id=source_sync_run_id,
        )
        logger.info("INFRASTRUCTURE_POLL_COMPLETED | summary={}", summary)
        return summary

    except Exception as exc:
        message = f"{type(exc).__name__}: {exc}"
        summary["errors"].append(message)
        try:
            state.complete_poll_run(
                run_id,
                status="failed",
                summary=summary,
                source_sync_run_id=source_sync_run_id,
                error_summary=message,
            )
        except Exception:
            logger.exception("INFRASTRUCTURE_POLL_HISTORY_WRITE_FAILED | run_id={}", run_id)
        raise


def process_infrastructure_sites(
    *,
    trigger_type: str = "manual",
) -> dict[str, Any]:
    return asyncio.run(
        process_infrastructure_sites_async(trigger_type=trigger_type)
    )

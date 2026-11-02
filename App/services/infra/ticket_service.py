"""Raise one iEngage ticket per site for the selected problem devices."""
from __future__ import annotations

import asyncio
from typing import Any, Optional

from loguru import logger

from App.integration.iengage.infra_ticket_service import InfraTicketService
from App.integration.iengage.models import InfraTicketDevice, InfraTicketInput


class InfrastructureTicketService:
    def __init__(self, integration: Optional[InfraTicketService] = None) -> None:
        self.integration = integration or InfraTicketService()

    @staticmethod
    def _run(coro):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(coro)
        raise RuntimeError("Use the synchronous infrastructure ticket service outside an active event loop.")

    @staticmethod
    def build_input(
        site: dict[str, Any],
        devices: list[dict[str, Any]],
        *,
        requested_by: str,
        note: str | None = None,
    ) -> InfraTicketInput:
        status = str(site.get("site_status") or "").casefold() or None
        return InfraTicketInput(
            location_name=str(site.get("location_name") or ""),
            site_status=status,
            site_score=site.get("site_score"),
            priority=site.get("priority") or {"critical": "P1", "warning": "P2"}.get(status or ""),
            site_reason=site.get("site_reason"),
            devices=[
                InfraTicketDevice(
                    device_name=str(device.get("device_name") or ""),
                    device_status=device.get("device_status"),
                    source_system=device.get("source_system"),
                    ci_type=device.get("ci_type"),
                    details=dict(device),
                )
                for device in devices
            ],
            triggered_by=requested_by or "TechAdmin",
            additional_description=(note or "").strip() or None,
        )

    def preview_description(self, ticket_input: InfraTicketInput) -> str:
        return self.integration._build_description(ticket_input)

    def preview_attachment(self, ticket_input: InfraTicketInput):
        """The CSV that will be attached, or None when INFRA_IENGAGE_ATTACH_CSV=false."""
        from App.integration.iengage.infra_ticket_service import attach_csv_enabled, build_device_csv

        return build_device_csv(ticket_input) if attach_csv_enabled() else None

    def raise_ticket(self, ticket_input: InfraTicketInput) -> dict[str, Any]:
        result = self._run(self.integration.create_infra_ticket(ticket_input))
        status = (
            "DRY_RUN" if result.dry_run
            else "CREATED" if result.success and result.ticket_id
            else "ACCEPTED" if result.success
            else "FAILED"
        )
        logger.info(
            "INFRA_TICKET | site={} | devices={} | status={} | ticket_id={} | by={}",
            ticket_input.location_name,
            len(ticket_input.devices),
            status,
            result.ticket_id,
            ticket_input.triggered_by,
        )
        return {
            "success": result.success,
            "status": status,
            "ticket_id": result.ticket_id,
            "message": result.message,
            "location_name": ticket_input.location_name,
            "device_names": [device.device_name for device in ticket_input.devices],
            "attachment": (result.request_preview or {}).get("attachments"),
            "dry_run": result.dry_run,
            "sent": result.sent,
            "status_code": result.status_code,
            "response_data": result.response_data,
        }

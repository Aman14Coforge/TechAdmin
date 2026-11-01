"""iEngage adapter for site incidents, reusing the proven TechAdmin transport."""
from __future__ import annotations

import os
from dataclasses import replace
from typing import Any

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import PatchTicketInput
from App.integration.iengage.ticket_service import PatchTicketService
from App.services.infrastructure.models import InfrastructureSiteAlert


def _priority_overrides(config: IEngageConfig, priority: str) -> IEngageConfig:
    """Apply priority-specific values only when the existing config exposes them."""
    prefix = f"INFRA_IENGAGE_{priority}_"
    candidates: dict[str, Any] = {
        "priority_id": os.getenv(prefix + "PRIORITY_ID", "").strip(),
        "priority_name": os.getenv(prefix + "PRIORITY_NAME", "").strip(),
    }
    updates: dict[str, Any] = {}
    for field, value in candidates.items():
        if value and hasattr(config, field):
            current = getattr(config, field)
            updates[field] = int(value) if isinstance(current, int) else value
    return replace(config, **updates) if updates else config


class InfrastructureTicketService:
    async def create(self, alert: InfrastructureSiteAlert, description: str):
        config = _priority_overrides(IEngageConfig.from_env(), alert.priority)
        detail_names = [
            f"{device.device_name} [{device.source_system}/{device.device_status}]"
            for device in alert.devices[:100]
        ]
        ticket_input = PatchTicketInput(
            device_name=f"SITE::{alert.location_name}",
            missing_patch_count=max(1, alert.affected_count),
            missing_patch_names=detail_names or ["Site health degradation"],
            consecutive_non_compliant_days=1,
            discovery_id=f"ITOM-SYNC-{alert.sync_run_id}:{alert.location_name}",
            device_id=f"ITOM-SITE:{alert.location_name}",
            operating_system="Infrastructure site health",
            triggered_by="TechAdmin Infrastructure Agent",
            trigger_type=f"automatic-{alert.priority.casefold()}",
            additional_description=description,
        )
        return await PatchTicketService(config).create_patch_ticket(ticket_input)

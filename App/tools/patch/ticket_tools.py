from __future__ import annotations
from typing import Any
from App.services.patch.ticket_service import PatchTicketService


def raise_patch_ticket(device_name: str, reason: str | None = None) -> dict[str, Any]:
    return PatchTicketService().raise_for_device(device_name, reason=reason, mode="USER")

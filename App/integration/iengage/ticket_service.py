from __future__ import annotations

from typing import Optional

from App.integration.iengage.client import IEngageClient
from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import IEngageRequest, IEngageResult, PatchTicketInput


class PatchTicketService:
    def __init__(self, config: Optional[IEngageConfig] = None, client: Optional[IEngageClient] = None) -> None:
        self.config = config or IEngageConfig.from_env()
        self.client = client or IEngageClient(self.config)

    async def create_patch_ticket(self, ticket_input: PatchTicketInput) -> IEngageResult:
        self._validate_input(ticket_input)
        payload = self._build_service_details(ticket_input)
        return await self.client.create_ticket(IEngageRequest(service_details=payload))

    def _build_service_details(self, item: PatchTicketInput) -> dict[str, str]:
        return {
            "RequesterCode": self.config.requester_code,
            "EmpCode": self.config.emp_code,
            "RequesterMobile": self.config.requester_mobile,
            "RequesterProjectCode": self.config.requester_project_code,
            "RequestType": self.config.request_type,
            "PriorityName": self.config.priority_name,
            "RequesterLocationName": self.config.location_name,
            "CatID": self.config.category_id,
            "SubCatID": self.config.subcategory_id,
            "PriorityID": self.config.priority_id,
            "LocationID": self.config.location_id,
            "RequesterAssetCode": item.device_name.strip(),
            "Description": self._description(item),
        }

    @staticmethod
    def _description(item: PatchTicketInput) -> str:
        patches = list(dict.fromkeys(str(value).strip() for value in item.missing_patch_names if str(value).strip()))
        parts = [
            "Patch compliance issue detected.",
            f"Device name: {item.device_name.strip()}.",
            f"Missing patch count: {item.missing_patch_count}.",
            f"Consecutive non-compliant days: {item.consecutive_non_compliant_days}.",
            f"Missing patches: {', '.join(patches) if patches else 'Details unavailable'}.",
        ]
        if item.discovery_id:
            parts.append(f"Ivanti Discovery ID: {item.discovery_id}.")
        if item.device_id:
            parts.append(f"Device ID: {item.device_id}.")
        if item.operating_system:
            parts.append(f"Operating system: {item.operating_system}.")
        if item.ip_address:
            parts.append(f"IP address: {item.ip_address}.")
        parts.extend((f"Trigger type: {item.trigger_type}.", f"Triggered by: {item.triggered_by}."))
        if item.additional_description:
            parts.append(item.additional_description.strip())
        return " ".join(parts)

    @staticmethod
    def _validate_input(item: PatchTicketInput) -> None:
        if not item.device_name.strip():
            raise ValueError("device_name is required.")
        if item.missing_patch_count < 0:
            raise ValueError("missing_patch_count cannot be negative.")
        if item.consecutive_non_compliant_days < 0:
            raise ValueError("consecutive_non_compliant_days cannot be negative.")

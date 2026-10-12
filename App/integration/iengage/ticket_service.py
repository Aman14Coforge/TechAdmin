from __future__ import annotations

from typing import Optional

from App.integration.iengage.client import IEngageClient
from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import IEngageRequest, IEngageResult, PatchTicketInput


class PatchTicketService:
    def __init__(
        self,
        config: Optional[IEngageConfig] = None,
        client: Optional[IEngageClient] = None,
    ) -> None:
        self.config = config or IEngageConfig.from_env()
        self.client = client or IEngageClient(config=self.config)

    async def create_patch_ticket(self, ticket_input: PatchTicketInput) -> IEngageResult:
        self._validate_input(ticket_input)
        service_details = self._build_service_details(ticket_input)
        return await self.client.create_ticket(IEngageRequest(service_details=service_details))

    def _build_service_details(self, item: PatchTicketInput) -> dict[str, object]:
        return {
            "RequestID": self.config.request_id,
            "RequesterCode": self.config.requester_code,
            "EmpCode": self.config.emp_code,
            "RequesterMobile": self.config.requester_mobile,
            "RequesterProjectCode": self.config.requester_project_code,
            "RequestType": self.config.request_type,
            "RequestPriorityName": self.config.priority_name,
            "RequesterLocationName": self.config.location_name,
            "RequestCategoryId": self.config.category_id,
            "RequestSubCategoryId": self.config.subcategory_id,
            "RequestPriorityId": self.config.priority_id,
            "RequesterLocationId": self.config.location_id,
            "OtherLocation": self.config.other_location,
            "RequesterSeatNo": self.config.requester_seat_no,
            "RequesterIP": item.ip_address or self.config.requester_ip,
            "RequesterAssetCode": item.device_name.strip(),
            "RequestDescription": self._build_description(item),
            "RequestDurationId": self.config.request_duration_id,
            "DurationFromDate": self.config.duration_from_date,
            "DurationToDate": self.config.duration_to_date,
            "ManagerID": self.config.manager_id,
            "ReviewingManagerID": self.config.reviewing_manager_id,
            "isMgrOnLeave": self.config.is_manager_on_leave,
            "isSave": True,
            "SmBand": self.config.sm_band,
            "Witness": self.config.witness,
            "ThirdWitness": self.config.third_witness,
            "IncidentDate": self.config.incident_date,
            "SoftwareIds": self.config.software_ids,
        }

    def _build_description(self, item: PatchTicketInput) -> str:
        patch_names = list(dict.fromkeys(
            str(value).strip()
            for value in item.missing_patch_names
            if str(value).strip()
        ))
        parts = [
            "Patch compliance issue detected.",
            f"Device name: {item.device_name.strip()}.",
            f"Missing patch count: {item.missing_patch_count}.",
            f"Consecutive non-compliant days: {item.consecutive_non_compliant_days}.",
        ]
        if item.discovery_id:
            parts.append(f"Ivanti Discovery ID: {item.discovery_id}.")
        if item.device_id:
            parts.append(f"Device ID: {item.device_id}.")
        if item.operating_system:
            parts.append(f"Operating system: {item.operating_system}.")
        if item.ip_address:
            parts.append(f"IP address: {item.ip_address}.")
        parts.append(f"Trigger type: {item.trigger_type}.")
        parts.append(f"Triggered by: {item.triggered_by}.")
        if item.additional_description:
            parts.append(item.additional_description.strip())
        parts.append("Missing patches: " + (", ".join(patch_names) if patch_names else "Details unavailable") + ".")
        text = " ".join(parts)
        limit = self.config.description_max_length
        if len(text) > limit:
            suffix = " ... Full patch evidence is available in TechAdmin for this device."
            text = text[:limit - len(suffix)].rstrip() + suffix
        return text

    @staticmethod
    def _validate_input(item: PatchTicketInput) -> None:
        if not item.device_name.strip():
            raise ValueError("device_name is required.")
        if item.missing_patch_count < 0:
            raise ValueError("missing_patch_count cannot be negative.")
        if item.consecutive_non_compliant_days < 0:
            raise ValueError("consecutive_non_compliant_days cannot be negative.")

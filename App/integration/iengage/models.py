from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass(frozen=True)
class PatchTicketInput:
    device_name: str
    missing_patch_count: int
    missing_patch_names: list[str] = field(default_factory=list)
    consecutive_non_compliant_days: int = 0
    discovery_id: Optional[str] = None
    device_id: Optional[str] = None
    operating_system: Optional[str] = None
    ip_address: Optional[str] = None
    triggered_by: str = "TechAdmin"
    trigger_type: str = "manual-ui"
    additional_description: Optional[str] = None


@dataclass(frozen=True)
class IEngageAttachment:
    file_name: str
    content: bytes
    content_type: str = "text/csv"


@dataclass(frozen=True)
class IEngageRequest:
    service_details: dict[str, Any]
    attachments: list[IEngageAttachment] = field(default_factory=list)


@dataclass(frozen=True)
class IEngageResult:
    success: bool
    sent: bool
    dry_run: bool
    ticket_id: Optional[str]
    message: str
    status_code: Optional[int] = None
    response_data: dict[str, Any] = field(default_factory=dict)
    request_preview: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InfraTicketDevice:
    device_name: str
    device_status: Optional[str] = None
    source_system: Optional[str] = None
    ci_type: Optional[str] = None
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class InfraTicketInput:
    location_name: str
    devices: list[InfraTicketDevice]
    site_status: Optional[str] = None
    site_score: Optional[float] = None
    priority: Optional[str] = None
    site_reason: Optional[str] = None
    triggered_by: str = "TechAdmin"
    additional_description: Optional[str] = None

    @property
    def device_name(self) -> str:
        """Asset code sent to iEngage: the first selected device."""
        return self.devices[0].device_name if self.devices else ""

    @property
    def ip_address(self) -> Optional[str]:
        return None

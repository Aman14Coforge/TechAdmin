"""Environment configuration for the TechAdmin iEngage integration."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"

TRUE_VALUES = {"1", "true", "yes", "y", "on"}
FALSE_VALUES = {"0", "false", "no", "n", "off"}


def get_text(name: str, default: str = "") -> str:
    """Return one trimmed environment variable."""
    value = os.getenv(name)
    return default if value is None else value.strip()


def get_boolean(name: str, default: bool) -> bool:
    """Read a Boolean environment variable using strict accepted values."""
    value = os.getenv(name)
    if value is None:
        return default

    normalized = value.strip().casefold()
    if normalized in TRUE_VALUES:
        return True
    if normalized in FALSE_VALUES:
        return False

    accepted = ", ".join(sorted(TRUE_VALUES | FALSE_VALUES))
    raise ValueError(
        f"{name} must be one of: {accepted}. Received: {value!r}"
    )


def get_integer(name: str, default: int) -> int:
    """Read a positive or negative whole-number environment variable."""
    value = get_text(name)
    if not value:
        return default

    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(
            f"{name} must be a whole number. Received: {value!r}"
        ) from exc


def get_csv(name: str, default: str) -> tuple[str, ...]:
    """Read a comma-separated environment variable."""
    return tuple(
        item.strip()
        for item in get_text(name, default).split(",")
        if item.strip()
    )


def mask_value(value: Any) -> str:
    """Mask a secret while retaining minimal diagnostic context."""
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


@dataclass(frozen=True)
class IEngageConfig:
    """Immutable configuration for the iEngage ticket integration."""

    enabled: bool
    dry_run: bool
    url: str
    ecserp: str
    auth_key: str
    request_id: str
    requester_code: str
    emp_code: str
    requester_mobile: str
    requester_project_code: str
    request_type: str
    priority_name: str
    location_name: str
    category_id: str
    subcategory_id: str
    priority_id: str
    location_id: str
    other_location: str
    requester_seat_no: str
    requester_ip: str
    request_duration_id: str
    duration_from_date: str
    duration_to_date: str
    manager_id: str
    reviewing_manager_id: str
    is_manager_on_leave: str
    sm_band: str
    witness: str
    third_witness: str
    incident_date: str
    software_ids: str
    timeout_seconds: int
    verify_ssl: bool
    ticket_id_fields: tuple[str, ...]
    success_markers: tuple[str, ...]
    failure_markers: tuple[str, ...]
    description_max_length: int = 1000

    @classmethod
    def from_env(cls) -> "IEngageConfig":
        """Load project defaults while preserving explicitly supplied environment values."""
        load_dotenv(ENV_FILE, override=False)
        config = cls(
            enabled=get_boolean("IENGAGE_ENABLED", False),
            dry_run=get_boolean("IENGAGE_DRY_RUN", True),
            url=get_text("IENGAGE_URL"),
            ecserp=get_text("IENGAGE_ECSERP"),
            auth_key=get_text("IENGAGE_AUTH_KEY"),
            request_id=get_text("IENGAGE_REQUEST_ID"),
            requester_code=get_text("IENGAGE_REQUESTER_CODE"),
            emp_code=get_text("IENGAGE_EMP_CODE"),
            requester_mobile=get_text("IENGAGE_REQUESTER_MOBILE"),
            requester_project_code=get_text("IENGAGE_REQUESTER_PROJECT_CODE"),
            request_type=get_text("IENGAGE_REQUEST_TYPE"),
            priority_name=get_text(
                "IENGAGE_PRIORITY_NAME",
                "Low (A single user is impacted)",
            ),
            location_name=get_text("IENGAGE_LOCATION_NAME"),
            category_id=get_text("IENGAGE_CATEGORY_ID"),
            subcategory_id=get_text("IENGAGE_SUBCATEGORY_ID"),
            priority_id=get_text("IENGAGE_PRIORITY_ID"),
            location_id=get_text("IENGAGE_LOCATION_ID"),
            other_location=get_text("IENGAGE_OTHER_LOCATION"),
            requester_seat_no=get_text("IENGAGE_REQUESTER_SEAT_NO"),
            requester_ip=get_text("IENGAGE_REQUESTER_IP"),
            request_duration_id=get_text("IENGAGE_REQUEST_DURATION_ID"),
            duration_from_date=get_text("IENGAGE_DURATION_FROM_DATE"),
            duration_to_date=get_text("IENGAGE_DURATION_TO_DATE"),
            manager_id=get_text("IENGAGE_MANAGER_ID"),
            reviewing_manager_id=get_text("IENGAGE_REVIEWING_MANAGER_ID"),
            is_manager_on_leave=get_text("IENGAGE_IS_MANAGER_ON_LEAVE"),
            sm_band=get_text("IENGAGE_SM_BAND"),
            witness=get_text("IENGAGE_WITNESS"),
            third_witness=get_text("IENGAGE_THIRD_WITNESS"),
            incident_date=get_text("IENGAGE_INCIDENT_DATE"),
            software_ids=get_text("IENGAGE_SOFTWARE_IDS"),
            timeout_seconds=get_integer("IENGAGE_TIMEOUT_SECONDS", 60),
            verify_ssl=get_boolean("IENGAGE_VERIFY_SSL", True),
            ticket_id_fields=get_csv(
                "IENGAGE_TICKET_ID_FIELDS",
                (
                    "RequestID,RequestId,request_id,RequestNo,RequestNumber,"
                    "requestNumber,ServiceRequestNo,ServiceRequestNumber,"
                    "TicketID,TicketId,ticket_id,ticketNumber,ticketNo,"
                    "IncidentID,IncidentId,incident_id,IncidentNo,"
                    "IncidentNumber,incidentNumber,CaseID,CaseNumber,"
                    "SRNumber,INCNumber"
                ),
            ),
            success_markers=get_csv(
                "IENGAGE_SUCCESS_MARKERS",
                (
                    "saved successfully,created successfully,"
                    "submitted successfully,request created,"
                    "request submitted,incident created,ticket created,success"
                ),
            ),
            failure_markers=get_csv(
                "IENGAGE_FAILURE_MARKERS",
                (
                    "exception thrown,insert fails,cannot insert,"
                    "unable to create,request failed,invalid request,"
                    "validation failed"
                ),
            ),
            description_max_length=get_integer("IENGAGE_DESCRIPTION_MAX_LENGTH", 1000),
        )
        config.validate()
        return config

    def validate(self) -> None:
        """Validate all values required by the selected execution mode."""
        if self.enabled and not self.url:
            raise ValueError("IENGAGE_URL is missing.")

        if self.url and not self.url.startswith(("http://", "https://")):
            raise ValueError("IENGAGE_URL must be a plain HTTP/HTTPS URL.")

        normalized_url = self.url.casefold()
        if any(
            marker in normalized_url
            for marker in ("<a ", "</a>", "&lt;a ", "&lt;/a&gt;")
        ):
            raise ValueError(
                "IENGAGE_URL contains HTML. Store only the plain URL in .env."
            )

        if self.timeout_seconds <= 0:
            raise ValueError(
                "IENGAGE_TIMEOUT_SECONDS must be greater than zero."
            )
        if self.description_max_length < 100:
            raise ValueError("IENGAGE_DESCRIPTION_MAX_LENGTH must be at least 100.")

        if not self.ticket_id_fields:
            raise ValueError(
                "At least one iEngage ticket ID field must be configured."
            )

        if not self.enabled or self.dry_run:
            return

        required = {
            "IENGAGE_ECSERP": self.ecserp,
            "IENGAGE_AUTH_KEY": self.auth_key,
            "IENGAGE_REQUESTER_CODE": self.requester_code,
            "IENGAGE_EMP_CODE": self.emp_code,
            "IENGAGE_REQUESTER_MOBILE": self.requester_mobile,
            "IENGAGE_REQUEST_TYPE": self.request_type,
            "IENGAGE_CATEGORY_ID": self.category_id,
            "IENGAGE_SUBCATEGORY_ID": self.subcategory_id,
            "IENGAGE_PRIORITY_ID": self.priority_id,
            "IENGAGE_LOCATION_ID": self.location_id,
        }

        missing = [
            name
            for name, value in required.items()
            if not str(value or "").strip()
        ]
        if missing:
            raise ValueError(
                "Live ticket creation is blocked. Missing configuration: "
                + ", ".join(missing)
            )

    def safe_summary(self) -> dict[str, Any]:
        """Return non-sensitive diagnostics for startup checks and logs."""
        return {
            "enabled": self.enabled,
            "dry_run": self.dry_run,
            "url": self.url,
            "ecserp": mask_value(self.ecserp),
            "auth_key": mask_value(self.auth_key),
            "requester_code": self.requester_code,
            "emp_code": self.emp_code,
            "request_type": self.request_type,
            "category_id": self.category_id,
            "subcategory_id": self.subcategory_id,
            "priority_id": self.priority_id,
            "location_id": self.location_id,
            "timeout_seconds": self.timeout_seconds,
            "verify_ssl": self.verify_ssl,
            "ticket_id_fields": list(self.ticket_id_fields),
            "success_markers": list(self.success_markers),
            "failure_markers": list(self.failure_markers),
        }

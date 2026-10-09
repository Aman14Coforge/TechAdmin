from __future__ import annotations

import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def _text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def _boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


def _integer(name: str, default: int) -> int:
    value = _text(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number; received {value!r}.") from exc


def _csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in _text(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class IEngageConfig:
    enabled: bool
    dry_run: bool
    url: str
    ecserp: str
    auth_key: str
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
    timeout_seconds: int
    verify_ssl: bool
    ticket_id_fields: tuple[str, ...]
    success_markers: tuple[str, ...]
    failure_markers: tuple[str, ...]

    @classmethod
    def from_env(cls) -> "IEngageConfig":
        config = cls(
            enabled=_boolean("IENGAGE_ENABLED", False),
            dry_run=_boolean("IENGAGE_DRY_RUN", True),
            url=_text("IENGAGE_URL"),
            ecserp=_text("IENGAGE_ECSERP"),
            auth_key=_text("IENGAGE_AUTH_KEY"),
            requester_code=_text("IENGAGE_REQUESTER_CODE"),
            emp_code=_text("IENGAGE_EMP_CODE"),
            requester_mobile=_text("IENGAGE_REQUESTER_MOBILE"),
            requester_project_code=_text("IENGAGE_REQUESTER_PROJECT_CODE"),
            request_type=_text("IENGAGE_REQUEST_TYPE", "1"),
            priority_name=_text("IENGAGE_PRIORITY_NAME", "Low (A single user is impacted)"),
            location_name=_text("IENGAGE_LOCATION_NAME"),
            category_id=_text("IENGAGE_CATEGORY_ID"),
            subcategory_id=_text("IENGAGE_SUBCATEGORY_ID"),
            priority_id=_text("IENGAGE_PRIORITY_ID", "1"),
            location_id=_text("IENGAGE_LOCATION_ID", "0"),
            timeout_seconds=_integer("IENGAGE_TIMEOUT_SECONDS", 60),
            verify_ssl=_boolean("IENGAGE_VERIFY_SSL", True),
            ticket_id_fields=_csv(
                "IENGAGE_TICKET_ID_FIELDS",
                "ticketNumber,ticketNo,requestId,RequestID,incidentNumber,IncidentNumber,ServiceRequestNo,RequestNo,id",
            ),
            success_markers=_csv(
                "IENGAGE_SUCCESS_MARKERS",
                "saved successfully,request created,incident created,ticket created",
            ),
            failure_markers=_csv(
                "IENGAGE_FAILURE_MARKERS",
                "exception thrown,insert fails,cannot insert,error,failed,invalid",
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.url:
            raise ValueError("IENGAGE_URL is missing from .env.")
        if self.timeout_seconds <= 0:
            raise ValueError("IENGAGE_TIMEOUT_SECONDS must be greater than zero.")
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
        missing = [name for name, value in required.items() if not value]
        if missing:
            raise ValueError("Live ticket creation blocked. Missing: " + ", ".join(missing))

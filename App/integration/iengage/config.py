from __future__ import annotations

import os
from dataclasses import dataclass

TRUE_VALUES = {"1", "true", "yes", "y", "on"}


def get_text(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return default if value is None else value.strip()


def get_boolean(name: str, default: bool) -> bool:
    value = os.getenv(name)
    return default if value is None else value.strip().lower() in TRUE_VALUES


def get_integer(name: str, default: int) -> int:
    value = get_text(name)
    if not value:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be a whole number. Received: {value!r}") from exc


def get_csv(name: str, default: str) -> tuple[str, ...]:
    return tuple(item.strip() for item in get_text(name, default).split(",") if item.strip())


@dataclass(frozen=True)
class IEngageConfig:
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

    @classmethod
    def from_env(cls) -> "IEngageConfig":
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
            priority_name=get_text("IENGAGE_PRIORITY_NAME", "Low (A single user is impacted)"),
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
                "RequestID,RequestNo,ServiceRequestNo,ticketNumber,ticketNo,incidentNumber,id",
            ),
            success_markers=get_csv(
                "IENGAGE_SUCCESS_MARKERS",
                "saved successfully,request created,incident created,ticket created",
            ),
            failure_markers=get_csv(
                "IENGAGE_FAILURE_MARKERS",
                "exception thrown,insert fails,cannot insert,error,failed,invalid",
            ),
        )
        config.validate()
        return config

    def validate(self) -> None:
        if not self.url:
            raise ValueError("IENGAGE_URL is missing.")
        if not self.url.startswith(("http://", "https://")):
            raise ValueError("IENGAGE_URL must be a plain HTTP/HTTPS URL.")
        if "<a " in self.url or "</a>" in self.url:
            raise ValueError("IENGAGE_URL contains HTML. Store only the plain URL in .env.")
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
            raise ValueError("Live ticket creation is blocked. Missing configuration: " + ", ".join(missing))

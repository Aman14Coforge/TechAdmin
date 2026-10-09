from __future__ import annotations

import json
import logging
from typing import Any, Optional

import httpx

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import IEngageRequest, IEngageResult

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "authkey",
    "ecserp",
    "requestermobile",
    "mobile",
    "phonenumber",
}


def mask_sensitive_value(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


def redact_sensitive_data(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {
            key: redact_sensitive_data(item_value, key)
            for key, item_value in value.items()
        }

    if isinstance(value, list):
        return [
            redact_sensitive_data(item, parent_key)
            for item in value
        ]

    if parent_key.casefold() in SENSITIVE_KEYS:
        return mask_sensitive_value(value)

    return value


class IEngageClient:
    """Client for creating iEngage tickets using multipart/form-data."""

    def __init__(
        self,
        config: Optional[IEngageConfig] = None,
    ) -> None:
        self.config = config or IEngageConfig.from_env()

    async def create_ticket(
        self,
        request: IEngageRequest,
    ) -> IEngageResult:
        self._validate_service_details(request.service_details)

        request_preview = self._build_safe_preview(
            request.service_details
        )

        if not self.config.enabled:
            return IEngageResult(
                success=False,
                sent=False,
                dry_run=True,
                ticket_id=None,
                message=(
                    "iEngage integration is disabled. "
                    "Set IENGAGE_ENABLED=true to enable it."
                ),
                status_code=None,
                response_data={},
                request_preview=request_preview,
            )

        if self.config.dry_run:
            logger.info(
                "iEngage dry-run request: %s",
                json.dumps(
                    request_preview,
                    ensure_ascii=False,
                    default=str,
                ),
            )

            return IEngageResult(
                success=True,
                sent=False,
                dry_run=True,
                ticket_id="DRY-RUN",
                message=(
                    "Dry run completed successfully. "
                    "No request was sent to iEngage."
                ),
                status_code=None,
                response_data={},
                request_preview=request_preview,
            )

        service_details_json = json.dumps(
            request.service_details,
            ensure_ascii=False,
            default=str,
        )

        multipart_files = {
            "ECSerp": (
                None,
                self.config.ecserp,
            ),
            "AuthKey": (
                None,
                self.config.auth_key,
            ),
            "serviceDetails": (
                None,
                service_details_json,
            ),
        }

        headers = {
            "Accept": "application/json, text/plain, */*",
        }

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(
                    self.config.timeout_seconds
                ),
                verify=self.config.verify_ssl,
                follow_redirects=False,
            ) as http_client:
                response = await http_client.post(
                    self.config.url,
                    files=multipart_files,
                    headers=headers,
                )

        except httpx.TimeoutException as exc:
            logger.exception("The iEngage request timed out.")
            return IEngageResult(
                success=False,
                sent=False,
                dry_run=False,
                ticket_id=None,
                message=(
                    "The iEngage request timed out after "
                    f"{self.config.timeout_seconds} seconds."
                ),
                status_code=None,
                response_data={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                request_preview=request_preview,
            )

        except httpx.RequestError as exc:
            logger.exception("The iEngage network request failed.")
            return IEngageResult(
                success=False,
                sent=False,
                dry_run=False,
                ticket_id=None,
                message=(
                    "The iEngage request could not be sent: "
                    f"{exc}"
                ),
                status_code=None,
                response_data={
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                request_preview=request_preview,
            )

        response_data = self._parse_response(response)
        safe_response_data = redact_sensitive_data(response_data)

        if not 200 <= response.status_code < 300:
            return IEngageResult(
                success=False,
                sent=True,
                dry_run=False,
                ticket_id=None,
                message=(
                    "iEngage rejected the request with HTTP "
                    f"{response.status_code}."
                ),
                status_code=response.status_code,
                response_data=safe_response_data,
                request_preview=request_preview,
            )

        application_error = self._find_application_error(
            response_data
        )

        if application_error:
            return IEngageResult(
                success=False,
                sent=True,
                dry_run=False,
                ticket_id=None,
                message=(
                    "iEngage returned an application error: "
                    f"{application_error}"
                ),
                status_code=response.status_code,
                response_data=safe_response_data,
                request_preview=request_preview,
            )

        ticket_id = self._extract_ticket_id(response_data)
        success_marker = self._find_success_marker(response_data)

        if ticket_id:
            return IEngageResult(
                success=True,
                sent=True,
                dry_run=False,
                ticket_id=ticket_id,
                message="iEngage ticket created successfully.",
                status_code=response.status_code,
                response_data=safe_response_data,
                request_preview=request_preview,
            )

        if success_marker:
            return IEngageResult(
                success=True,
                sent=True,
                dry_run=False,
                ticket_id=None,
                message=(
                    "iEngage indicated that the ticket was created, "
                    "but no configured ticket ID field was found."
                ),
                status_code=response.status_code,
                response_data=safe_response_data,
                request_preview=request_preview,
            )

        return IEngageResult(
            success=False,
            sent=True,
            dry_run=False,
            ticket_id=None,
            message=(
                "iEngage returned HTTP 200, but the response did "
                "not contain a ticket ID or success marker."
            ),
            status_code=response.status_code,
            response_data=safe_response_data,
            request_preview=request_preview,
        )

    def _build_safe_preview(
        self,
        service_details: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "url": self.config.url,
            "method": "POST",
            "encoding": "multipart/form-data",
            "form": {
                "ECSerp": mask_sensitive_value(
                    self.config.ecserp
                ),
                "AuthKey": mask_sensitive_value(
                    self.config.auth_key
                ),
                "serviceDetails": redact_sensitive_data(
                    service_details
                ),
            },
        }

    def _validate_service_details(
        self,
        service_details: dict[str, Any],
    ) -> None:
        required_fields = (
            "RequesterCode",
            "EmpCode",
            "RequesterMobile",
            "RequestType",
            "RequestCategoryId",
            "RequestSubCategoryId",
            "RequestPriorityId",
            "RequesterLocationId",
            "RequesterAssetCode",
            "RequestDescription",
        )

        missing_fields = [
            field_name
            for field_name in required_fields
            if not str(
                service_details.get(field_name, "") or ""
            ).strip()
        ]

        if not self.config.dry_run and missing_fields:
            raise ValueError(
                "Live iEngage request blocked because required "
                "serviceDetails fields are empty: "
                + ", ".join(missing_fields)
            )

        if "isSave" not in service_details:
            raise ValueError(
                "serviceDetails must include the isSave property."
            )

        if service_details.get("isSave") is not True:
            raise ValueError(
                "serviceDetails.isSave must be the JSON boolean true."
            )

    @staticmethod
    def _parse_response(
        response: httpx.Response,
    ) -> dict[str, Any]:
        try:
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            return {"data": payload}
        except ValueError:
            return {"text": response.text[:10000]}

    def _find_application_error(
        self,
        response_data: Any,
    ) -> Optional[str]:
        response_text = json.dumps(
            response_data,
            ensure_ascii=False,
            default=str,
        ).casefold()

        for marker in self.config.failure_markers:
            normalized_marker = marker.casefold().strip()
            if normalized_marker and normalized_marker in response_text:
                return self._extract_message(response_data) or marker

        return None

    def _find_success_marker(
        self,
        response_data: Any,
    ) -> Optional[str]:
        response_text = json.dumps(
            response_data,
            ensure_ascii=False,
            default=str,
        ).casefold()

        for marker in self.config.success_markers:
            normalized_marker = marker.casefold().strip()
            if normalized_marker and normalized_marker in response_text:
                return marker

        return None

    def _extract_ticket_id(
        self,
        value: Any,
    ) -> Optional[str]:
        configured_fields = {
            field.casefold()
            for field in self.config.ticket_id_fields
        }

        if isinstance(value, dict):
            for key, item_value in value.items():
                if key.casefold() in configured_fields:
                    ticket_value = str(item_value or "").strip()
                    if ticket_value:
                        return ticket_value

                nested_result = self._extract_ticket_id(item_value)
                if nested_result:
                    return nested_result

        elif isinstance(value, list):
            for item in value:
                nested_result = self._extract_ticket_id(item)
                if nested_result:
                    return nested_result

        return None

    @staticmethod
    def _extract_message(
        value: Any,
    ) -> Optional[str]:
        message_keys = {
            "message",
            "errormessage",
            "error_message",
            "description",
            "detail",
        }

        if isinstance(value, dict):
            for key, item_value in value.items():
                if key.casefold() in message_keys:
                    message = str(item_value or "").strip()
                    if message:
                        return message

            for item_value in value.values():
                nested_message = IEngageClient._extract_message(
                    item_value
                )
                if nested_message:
                    return nested_message

        elif isinstance(value, list):
            for item in value:
                nested_message = IEngageClient._extract_message(item)
                if nested_message:
                    return nested_message

        return None

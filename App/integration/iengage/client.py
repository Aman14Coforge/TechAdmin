"""Asynchronous iEngage multipart ticket client."""
from __future__ import annotations

import json
import logging
import re
from html import unescape
from typing import Any, Iterator, Optional

import httpx

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import IEngageRequest, IEngageResult

logger = logging.getLogger(__name__)

SENSITIVE_KEYS = {
    "authkey", "auth_key", "ecserp", "requestermobile",
    "requester_mobile", "mobile", "phonenumber", "phone_number",
    "authorization", "token", "access_token", "refresh_token", "client_secret",
}

DEFAULT_TICKET_ID_FIELDS = {
    "ticketid", "ticketnumber", "requestid", "requestnumber",
    "incidentid", "incidentnumber", "caseid", "casenumber",
    "servicerequestid", "servicerequestnumber", "srnumber", "incnumber",
    "id", "ticketreference", "requestreference", "referencenumber",
}

MESSAGE_KEYS = {
    "message", "msg", "responsemessage", "successmessage", "errormessage",
    "description", "detail", "details", "resultmessage",
}

SUCCESS_VALUES = {
    "true", "success", "successful", "succeeded", "created", "completed",
    "complete", "ok", "accepted", "saved", "submitted", "200",
}

FAILURE_VALUES = {
    "false", "failed", "failure", "error", "rejected", "invalid",
    "denied", "notcreated", "unsuccessful",
}

TICKET_PATTERNS = (
    re.compile(r"(?<![A-Z0-9])INC[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])SR[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])REQ[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])RITM[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])CASE[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])TKT[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
    re.compile(r"(?<![A-Z0-9])WO[-_ ]?\d{3,}(?!\d)", re.IGNORECASE),
)

LABELED_TICKET_PATTERN = re.compile(
    r"(?:ticket|request|incident|case|service[\s_-]*request)"
    r"\s*(?:id|number|no|reference|ref)?\s*[:=#-]?\s*"
    r"([A-Z][A-Z0-9_-]{2,}|\d{4,})",
    re.IGNORECASE,
)


def normalize_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value or "").casefold())


def mask_sensitive_value(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 4:
        return "***"
    return f"{text[:2]}***{text[-2:]}"


def redact_sensitive_data(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        return {key: redact_sensitive_data(item, str(key)) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_sensitive_data(item, parent_key) for item in value]
    if normalize_key(parent_key) in {normalize_key(key) for key in SENSITIVE_KEYS}:
        return mask_sensitive_value(value)
    return value


def walk_response(value: Any) -> Iterator[Any]:
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk_response(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk_response(item)


def clean_ticket_identifier(value: Any) -> Optional[str]:
    if value is None or isinstance(value, (dict, list, tuple, set, bool)):
        return None
    text = str(value).strip()
    if not text or len(text) < 4 or len(text) > 150:
        return None
    if text.isdigit() and len(text) < 4:
        return None
    if re.fullmatch(r"20\d{2}[-_/]\d{1,2}[-_/]\d{1,2}", text):
        return None
    if text.casefold() in SUCCESS_VALUES | FAILURE_VALUES | {
        "none", "null", "nil", "n/a", "na", "undefined", "dry-run", "dry_run"
    }:
        return None
    return text.upper()


class IEngageClient:
    """Create iEngage tickets using multipart/form-data."""

    def __init__(self, config: Optional[IEngageConfig] = None) -> None:
        self.config = config or IEngageConfig.from_env()
        logger.info(
            "IEngageClient initialized | enabled=%s | dry_run=%s | url=%s",
            self.config.enabled,
            self.config.dry_run,
            self.config.url,
        )

    async def create_ticket(self, request: IEngageRequest) -> IEngageResult:
        self._validate_service_details(request.service_details)
        request_preview = self._build_safe_preview(request.service_details)

        if not self.config.enabled:
            return IEngageResult(
                success=False, sent=False, dry_run=False, ticket_id=None,
                message="iEngage integration is disabled. Set IENGAGE_ENABLED=true and restart TechAdmin.",
                status_code=None, response_data={}, request_preview=request_preview,
            )

        if self.config.dry_run:
            logger.info("iEngage dry-run request: %s", json.dumps(request_preview, default=str))
            return IEngageResult(
                success=True, sent=False, dry_run=True, ticket_id="DRY-RUN",
                message="Dry run completed successfully. No request was sent to iEngage.",
                status_code=None, response_data={}, request_preview=request_preview,
            )

        multipart_files = {
            "ECSerp": (None, self.config.ecserp),
            "AuthKey": (None, self.config.auth_key),
            "serviceDetails": (
                None,
                json.dumps(request.service_details, ensure_ascii=False, default=str),
            ),
        }
        headers = {"Accept": "application/json, text/plain, */*"}

        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                verify=self.config.verify_ssl,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.config.url,
                    files=multipart_files,
                    headers=headers,
                )
        except httpx.TimeoutException as exc:
            logger.exception("The iEngage request timed out.")
            return self._failure(
                message=(f"The iEngage request timed out after {self.config.timeout_seconds} seconds. "
                         "Check iEngage for an existing ticket before retrying; creation may have completed."),
                request_preview=request_preview,
                response_data={"error_type": type(exc).__name__, "error": str(exc)},
                sent=not isinstance(exc, (httpx.ConnectTimeout, httpx.PoolTimeout)),
            )
        except httpx.RequestError as exc:
            logger.exception("The iEngage network request failed.")
            return self._failure(
                message=f"The iEngage request could not be sent: {exc}",
                request_preview=request_preview,
                response_data={"error_type": type(exc).__name__, "error": str(exc)},
                sent=False,
            )

        response_data = self._parse_response(response)
        safe_response = redact_sensitive_data(response_data)
        logger.info(
            "iEngage response | http_status=%s | response=%s",
            response.status_code,
            json.dumps(safe_response, ensure_ascii=False, default=str),
        )

        if not 200 <= response.status_code < 300:
            return self._failure(
                message=f"iEngage rejected the request with HTTP {response.status_code}.",
                request_preview=request_preview,
                response_data=safe_response,
                sent=True,
                status_code=response.status_code,
            )

        application_error = self._find_application_error(response_data)
        if application_error:
            return self._failure(
                message=f"iEngage returned an application error: {application_error}",
                request_preview=request_preview,
                response_data=safe_response,
                sent=True,
                status_code=response.status_code,
            )

        ticket_id = self._extract_ticket_id(response_data)
        if not ticket_id:
            ticket_id = self._extract_ticket_id_from_message(response_data)
        success_marker = self._find_success_marker(response_data)

        if ticket_id:
            return IEngageResult(
                success=True, sent=True, dry_run=False, ticket_id=ticket_id,
                message=f"iEngage ticket {ticket_id} was created successfully.",
                status_code=response.status_code,
                response_data=safe_response,
                request_preview=request_preview,
            )

        if success_marker:
            source_message = self._extract_message(safe_response)
            return IEngageResult(
                success=True, sent=True, dry_run=False, ticket_id=None,
                message=(
                    f"iEngage accepted the ticket request. Response: {source_message}"
                    if source_message else
                    "iEngage accepted the ticket request, but returned no response message or recognized ticket identifier."
                ),
                status_code=response.status_code,
                response_data=safe_response,
                request_preview=request_preview,
            )

        return self._failure(
            message=(
                f"iEngage returned HTTP {response.status_code}, but the response did not contain "
                "a recognized ticket ID or success marker. Review the logged response."
            ),
            request_preview=request_preview,
            response_data=safe_response,
            sent=True,
            status_code=response.status_code,
        )

    def _failure(
        self,
        *,
        message: str,
        request_preview: dict[str, Any],
        response_data: dict[str, Any],
        sent: bool,
        status_code: Optional[int] = None,
    ) -> IEngageResult:
        return IEngageResult(
            success=False, sent=sent, dry_run=False, ticket_id=None,
            message=message, status_code=status_code,
            response_data=response_data, request_preview=request_preview,
        )

    def _build_safe_preview(self, service_details: dict[str, Any]) -> dict[str, Any]:
        return {
            "url": self.config.url,
            "method": "POST",
            "encoding": "multipart/form-data",
            "dry_run": self.config.dry_run,
            "form": {
                "ECSerp": mask_sensitive_value(self.config.ecserp),
                "AuthKey": mask_sensitive_value(self.config.auth_key),
                "serviceDetails": redact_sensitive_data(service_details),
            },
        }

    def _validate_service_details(self, service_details: dict[str, Any]) -> None:
        required_fields = (
            "RequesterCode", "EmpCode", "RequesterMobile", "RequestType",
            "RequestCategoryId", "RequestSubCategoryId", "RequestPriorityId",
            "RequesterLocationId", "RequesterAssetCode", "RequestDescription",
        )
        missing = [
            field for field in required_fields
            if not str(service_details.get(field, "") or "").strip()
        ]
        if not self.config.dry_run and missing:
            raise ValueError(
                "Live iEngage request blocked because required serviceDetails fields are empty: "
                + ", ".join(missing)
            )
        if service_details.get("isSave") is not True:
            raise ValueError("serviceDetails.isSave must be the JSON boolean true.")

    @staticmethod
    def _parse_response(response: httpx.Response) -> dict[str, Any]:
        try:
            payload = response.json()
        except ValueError:
            payload = response.text or ""

        if isinstance(payload, str):
            text = payload.strip()
            if text.startswith(("{", "[")):
                try:
                    payload = json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text[:10000]}
            else:
                return {"text": text[:10000]}

        return payload if isinstance(payload, dict) else {"data": payload}

    def _find_application_error(self, response_data: Any) -> Optional[str]:
        for node in walk_response(response_data):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                normalized_key = normalize_key(key)
                if normalized_key in {"success", "issuccess", "succeeded"}:
                    if value is False or normalize_key(value) in FAILURE_VALUES:
                        return self._extract_message(node) or "The API returned success=false."
                if normalized_key in {"error", "errors", "errormessage", "exception", "fault"}:
                    if value not in (None, "", False, [], {}):
                        return str(value)
                if normalized_key in {"status", "result", "responsecode", "statuscode"}:
                    if normalize_key(value) in FAILURE_VALUES:
                        return self._extract_message(node) or str(value)

        for message in self._extract_all_messages(response_data):
            lowered = message.casefold()
            for marker in self.config.failure_markers:
                marker_text = str(marker).strip().casefold()
                if marker_text and marker_text in lowered:
                    return message
        return None

    def _find_success_marker(self, response_data: Any) -> Optional[str]:
        for node in walk_response(response_data):
            if not isinstance(node, dict):
                continue
            for key, value in node.items():
                if normalize_key(key) in {
                    "success", "issuccess", "succeeded", "status",
                    "statuscode", "result", "response", "responsecode",
                }:
                    if value is True or normalize_key(value) in SUCCESS_VALUES:
                        return f"{key}={value}"

        for message in self._extract_all_messages(response_data):
            lowered = message.casefold()
            for marker in self.config.success_markers:
                marker_text = str(marker).strip().casefold()
                if marker_text and marker_text in lowered:
                    return str(marker)
            if any(phrase in lowered for phrase in (
                "ticket created", "request created", "incident created",
                "created successfully", "saved successfully",
                "submitted successfully", "request submitted",
            )):
                return message
        return None

    def _ticket_id_fields(self) -> set[str]:
        configured = {normalize_key(field) for field in self.config.ticket_id_fields}
        return configured | {normalize_key(field) for field in DEFAULT_TICKET_ID_FIELDS}

    def _extract_ticket_id(self, value: Any, parent_context: str = "") -> Optional[str]:
        fields = self._ticket_id_fields()
        if isinstance(value, dict):
            for key, item in value.items():
                if normalize_key(key) in fields:
                    candidate = clean_ticket_identifier(item)
                    if candidate and self._identifier_has_reference_context(value, key, parent_context):
                        return candidate
            for key,item in value.items():
                candidate = self._extract_ticket_id(item, f"{parent_context} {key}")
                if candidate:
                    return candidate
        elif isinstance(value, list):
            for item in value:
                candidate = self._extract_ticket_id(item, parent_context)
                if candidate:
                    return candidate
        return None

    @staticmethod
    def _identifier_has_reference_context(node: dict[str, Any], key: Any, parent_context: str = "") -> bool:
        normalized_key=normalize_key(key)
        if normalized_key!="id":
            return True
        other_keys={normalize_key(name) for name in node if normalize_key(name)!="id"}
        context=" ".join(other_keys)+" "+normalize_key(parent_context)
        return any(term in context for term in ("ticket","request","incident","case","service","data","result"))

    @staticmethod
    def _extract_ticket_id_from_message(value: Any) -> Optional[str]:
        texts = IEngageClient._extract_all_messages(value)
        texts.append(json.dumps(value, ensure_ascii=False, default=str))
        for raw_text in texts:
            text = unescape(re.sub(r"<[^>]+>", " ", raw_text))
            for pattern in TICKET_PATTERNS:
                match = pattern.search(text)
                if match:
                    return match.group(0).replace(" ", "").upper()
            match = LABELED_TICKET_PATTERN.search(text)
            if match:
                candidate = clean_ticket_identifier(match.group(1))
                if candidate and any(char.isdigit() for char in candidate):
                    return candidate
            # iEngage sometimes says only "ID: <value>" in a success message.
            match = re.search(
                r"\b(?:ticket\s+)?(?:reference|ref|id|number|no)\s*[:=#-]\s*([A-Z0-9][A-Z0-9_-]{3,})",
                text,
                re.IGNORECASE,
            )
            if match:
                candidate = clean_ticket_identifier(match.group(1))
                if candidate and any(char.isdigit() for char in candidate):
                    return candidate
        return None

    @staticmethod
    def _extract_all_messages(value: Any) -> list[str]:
        messages: list[str] = []
        message_keys = {normalize_key(key) for key in MESSAGE_KEYS}
        if isinstance(value, dict):
            for key, item in value.items():
                if normalize_key(key) in message_keys and isinstance(item, (str, int, float)):
                    text = str(item).strip()
                    if text:
                        messages.append(text)
                messages.extend(IEngageClient._extract_all_messages(item))
        elif isinstance(value, list):
            for item in value:
                messages.extend(IEngageClient._extract_all_messages(item))
        elif isinstance(value, str):
            text = value.strip()
            if text:
                messages.append(text)
        return list(dict.fromkeys(messages))

    @staticmethod
    def _extract_message(value: Any) -> Optional[str]:
        messages = IEngageClient._extract_all_messages(value)
        return messages[0] if messages else None

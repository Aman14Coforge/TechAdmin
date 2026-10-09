from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import IEngageRequest, IEngageResult

SENSITIVE_KEYS = {"authkey", "ecserp", "requestermobile", "mobile", "phonenumber"}


def _mask(value: Any) -> str:
    text = str(value or "")
    if not text:
        return ""
    return "***" if len(text) <= 4 else f"{text[:2]}***{text[-2:]}"


def _redact(value: Any, key: str = "") -> Any:
    if isinstance(value, dict):
        return {child_key: _redact(child_value, child_key) for child_key, child_value in value.items()}
    if isinstance(value, list):
        return [_redact(item, key) for item in value]
    return _mask(value) if key.casefold() in SENSITIVE_KEYS else value


class IEngageClient:
    def __init__(self, config: Optional[IEngageConfig] = None) -> None:
        self.config = config or IEngageConfig.from_env()

    async def create_ticket(self, request: IEngageRequest) -> IEngageResult:
        self._validate_payload(request.service_details)
        preview = self._preview(request.service_details)

        if not self.config.enabled:
            return IEngageResult(False, False, True, None, "iEngage integration is disabled.", request_preview=preview)
        if self.config.dry_run:
            return IEngageResult(True, False, True, "DRY-RUN", "Dry run completed. No request was sent.", request_preview=preview)

        data = {
            "ECSerp": self.config.ecserp,
            "AuthKey": self.config.auth_key,
            "serviceDetails": json.dumps(request.service_details, ensure_ascii=False),
        }
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.config.timeout_seconds),
                verify=self.config.verify_ssl,
                follow_redirects=False,
            ) as client:
                response = await client.post(
                    self.config.url,
                    data=data,
                    headers={"Accept": "application/json, text/plain, */*"},
                )
        except httpx.TimeoutException as exc:
            return IEngageResult(False, False, False, None, "iEngage request timed out.", response_data={"error": str(exc)}, request_preview=preview)
        except httpx.RequestError as exc:
            return IEngageResult(False, False, False, None, f"iEngage request failed: {exc}", response_data={"error": str(exc)}, request_preview=preview)

        body = self._body(response)
        safe_body = _redact(body)
        body_text = json.dumps(body, ensure_ascii=False, default=str).casefold()
        failure = next((marker for marker in self.config.failure_markers if marker.casefold() in body_text), None)

        if not 200 <= response.status_code < 300:
            return IEngageResult(False, True, False, None, f"iEngage returned HTTP {response.status_code}.", response.status_code, safe_body, preview)
        if failure:
            return IEngageResult(False, True, False, None, f"iEngage returned an application error: {failure}.", response.status_code, safe_body, preview)

        ticket_id = self._ticket_id(body)
        success = ticket_id is not None or any(marker.casefold() in body_text for marker in self.config.success_markers)
        if not success:
            return IEngageResult(False, True, False, None, "HTTP 200 received, but no ticket ID or success marker was found.", response.status_code, safe_body, preview)
        return IEngageResult(True, True, False, ticket_id, "iEngage ticket created successfully.", response.status_code, safe_body, preview)

    def _preview(self, details: dict[str, Any]) -> dict[str, Any]:
        return {
            "url": self.config.url,
            "method": "POST",
            "form": {
                "ECSerp": _mask(self.config.ecserp),
                "AuthKey": _mask(self.config.auth_key),
                "serviceDetails": _redact(details),
            },
        }

    def _validate_payload(self, details: dict[str, Any]) -> None:
        required = (
            "RequesterCode", "EmpCode", "RequesterMobile", "RequestType",
            "CatID", "SubCatID", "PriorityID", "LocationID",
            "RequesterAssetCode", "Description",
        )
        missing = [key for key in required if not str(details.get(key, "") or "").strip()]
        if not self.config.dry_run and missing:
            raise ValueError("Live request blocked. Missing serviceDetails fields: " + ", ".join(missing))

    @staticmethod
    def _body(response: httpx.Response) -> dict[str, Any]:
        try:
            value = response.json()
            return value if isinstance(value, dict) else {"data": value}
        except ValueError:
            return {"text": response.text[:10000]}

    def _ticket_id(self, value: Any) -> Optional[str]:
        names = {name.casefold() for name in self.config.ticket_id_fields}
        if isinstance(value, dict):
            for key, child in value.items():
                if key.casefold() in names and str(child or "").strip():
                    return str(child).strip()
                found = self._ticket_id(child)
                if found:
                    return found
        elif isinstance(value, list):
            for child in value:
                found = self._ticket_id(child)
                if found:
                    return found
        return None

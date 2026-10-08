"""Ivanti API client for compact patch-compliance collection."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

import httpx
from loguru import logger

from App.services.patch.config import PatchSettings, settings


class IvantiAuthenticationError(RuntimeError):
    """Raised when an Ivanti authentication request fails."""


class IvantiAPIError(RuntimeError):
    """Raised when an Ivanti API request fails."""


class IvantiPatchClient:
    """Separate clients for People/Devices authentication and Patch OAuth."""

    def __init__(self, config: PatchSettings = settings) -> None:
        config.validate()
        self.config = config
        self.http = httpx.Client(
            timeout=httpx.Timeout(config.timeout),
            follow_redirects=True,
        )
        self._people_token: tuple[str, datetime] | None = None
        self._patch_token: tuple[str, datetime] | None = None

    def close(self) -> None:
        self.http.close()

    @staticmethod
    def _valid(cached: tuple[str, datetime] | None) -> bool:
        return bool(cached and cached[1] > datetime.now(timezone.utc))

    @staticmethod
    def _normalize_token(value: Any) -> str:
        token = str(value or "").strip()
        if token.casefold().startswith("bearer "):
            token = token[7:].strip()
        if len(token) >= 2 and token[0] == token[-1] == '"':
            token = token[1:-1].strip()
        if (
            len(token) >= 2
            and token.startswith("{")
            and token.endswith("}")
            and ":" not in token[1:-1]
        ):
            token = token[1:-1].strip()
        return "".join(token.split())

    @classmethod
    def fingerprint(cls, token: str) -> dict[str, Any]:
        value = cls._normalize_token(token)
        return {
            "length": len(value),
            "prefix": value[:6],
            "sha256_12": hashlib.sha256(value.encode()).hexdigest()[:12],
        }

    @staticmethod
    def _preview(response: httpx.Response, limit: int = 500) -> str:
        text = response.text.strip()
        return text[:limit] if text else "<empty response>"

    def generated_people_token(self, force: bool = False) -> str:
        """Get the People/Devices bearer token."""
        if not force and self._valid(self._people_token):
            return self._people_token[0]

        response = self.http.get(
            f"{self.config.base_url}{self.config.people_token_path}",
            headers={
                "X-ClientId": self.config.client_id,
                "X-ClientSecret": self.config.client_secret,
                "X-TenantId": self.config.tenant_id,
                "Accept": "text/plain, application/json",
            },
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IvantiAuthenticationError(
                f"People token HTTP {response.status_code}: {self._preview(response)}"
            ) from exc

        value: Any = response.text
        expires_in = 3600
        try:
            body = response.json()
            if isinstance(body, dict):
                value = body.get("access_token") or body.get("accessToken") or body.get("token")
                expires_in = int(body.get("expires_in") or 3600)
            elif isinstance(body, str):
                value = body
        except (ValueError, TypeError):
            pass

        token = self._normalize_token(value)
        if not token:
            raise IvantiAuthenticationError("People token response was empty")
        self._people_token = (
            token,
            datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 300)),
        )
        logger.info("IVANTI_GENERATED_PEOPLE_TOKEN | fingerprint={}", self.fingerprint(token))
        return token

    def people_token(self, force: bool = False) -> str:
        """Use optional diagnostic override, otherwise generated token."""
        override = str(
            getattr(self.config, "people_bearer_override", "")
            or getattr(self.config, "people_bearer_token", "")
            or ""
        ).strip()
        if override:
            token = self._normalize_token(override)
            logger.warning("IVANTI_PEOPLE_TOKEN_OVERRIDE_ACTIVE | fingerprint={}", self.fingerprint(token))
            return token
        return self.generated_people_token(force=force)

    def patch_token(self, force: bool = False) -> str:
        """Get the Patch Management OAuth token."""
        if not force and self._valid(self._patch_token):
            return self._patch_token[0]

        form = {
            "grant_type": "client_credentials",
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
        }
        if self.config.patch_scope:
            form["scope"] = self.config.patch_scope

        response = self.http.post(
            self.config.patch_token_url,
            data=form,
            headers={"Accept": "application/json"},
        )
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IvantiAuthenticationError(
                f"Patch token HTTP {response.status_code}: {self._preview(response)}"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise IvantiAuthenticationError("Patch token response was not JSON") from exc

        token = self._normalize_token(body.get("access_token") if isinstance(body, dict) else None)
        if not token:
            raise IvantiAuthenticationError("Patch authentication returned no access_token")
        expires_in = int(body.get("expires_in") or 3600)
        self._patch_token = (
            token,
            datetime.now(timezone.utc) + timedelta(seconds=max(60, expires_in - 300)),
        )
        logger.info("IVANTI_PATCH_TOKEN | fingerprint={}", self.fingerprint(token))
        return token

    def _get_json(
        self,
        path_or_url: str,
        *,
        family: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """GET JSON with one token refresh retry."""
        url = path_or_url if path_or_url.startswith("http") else f"{self.config.base_url}{path_or_url}"
        response: httpx.Response | None = None

        for attempt in (1, 2):
            token = (
                self.patch_token(force=attempt == 2)
                if family == "patch"
                else self.people_token(force=attempt == 2)
            )
            response = self.http.get(
                url,
                params=params,
                headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            )
            if response.status_code != 401:
                break
            if family == "patch":
                self._patch_token = None
            else:
                self._people_token = None
            logger.warning(
                "IVANTI_TOKEN_REJECTED | family={} | endpoint={} | attempt={}",
                family,
                url.split("?", 1)[0],
                attempt,
            )

        assert response is not None
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            raise IvantiAPIError(
                f"Ivanti {family} HTTP {response.status_code}; "
                f"endpoint={url.split('?', 1)[0]}; response={self._preview(response)}"
            ) from exc

        try:
            body = response.json()
        except ValueError as exc:
            raise IvantiAPIError(
                f"Ivanti {family} endpoint returned non-JSON content"
            ) from exc
        if not isinstance(body, dict):
            raise IvantiAPIError("Ivanti returned an unexpected JSON structure")
        return body

    def inventory_auth_diagnostic(self) -> dict[str, Any]:
        """Retained for compatibility with App.services.patch.preflight."""
        generated = self.generated_people_token(force=True)
        response = self.http.get(
            f"{self.config.base_url}/api/apigatewaydataservices/v1/devices",
            headers={"Authorization": f"Bearer {generated}", "Accept": "application/json"},
        )
        results = [{
            "name": "generated_people",
            "status_code": response.status_code,
            "fingerprint": self.fingerprint(generated),
        }]
        return {
            "success": response.status_code == 200,
            "results": results,
            "note": "This checks the first inventory page only. Full inventory scrolling is not required by the compact patch scan.",
        }

    def preflight(self) -> dict[str, Any]:
        """Validate first page of inventory plus the Patch Management API."""
        checks: dict[str, dict[str, Any]] = {}
        for name, path, family, params in (
            ("people", "/api/apigatewaydataservices/v1/people", "people", None),
            ("devices", "/api/apigatewaydataservices/v1/devices", "people", None),
            (
                "endpoint_vulnerability",
                "/api/patch/content/v1/endpoint-vulnerability",
                "patch",
                {"PageNumber": 1, "PageSize": 1, "Filter": "missingPatches gt 0"},
            ),
        ):
            try:
                body = self._get_json(path, family=family, params=params)
                checks[name] = {
                    "ok": True,
                    "count": body.get("@odata.count") or body.get("totalRecords"),
                }
            except Exception as exc:
                checks[name] = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

        # Patch collection can run when Patch Management works. People/Devices
        # is reported separately because it is optional enrichment.
        patch_ready = bool(checks["endpoint_vulnerability"]["ok"])
        return {
            "success": patch_ready,
            "patch_scan_ready": patch_ready,
            "optional_inventory_ready": bool(checks["people"]["ok"] and checks["devices"]["ok"]),
            "checks": checks,
            "scan_strategy": "endpoint_vulnerability_missing_patches_only",
        }

    def iter_vulnerable_devices(self) -> Iterator[dict[str, Any]]:
        """Yield only devices with missing patches using stable page-number pagination."""
        page = 1
        page_size = 150
        while True:
            body = self._get_json(
                "/api/patch/content/v1/endpoint-vulnerability",
                family="patch",
                params={
                    "PageNumber": page,
                    "PageSize": page_size,
                    "Filter": "missingPatches gt 0",
                },
            )
            rows = body.get("data") or []
            page_count = int(body.get("pageCount") or 0)
            logger.info(
                "IVANTI_VULNERABILITY_PAGE | page={} | rows={} | total={} | page_count={}",
                page,
                len(rows),
                body.get("totalRecords"),
                page_count,
            )
            for row in rows:
                if isinstance(row, dict):
                    yield row
            if not rows or (page_count and page >= page_count):
                break
            if not page_count and len(rows) < page_size:
                break
            page += 1

    def vulnerability(self, discovery_id: str, machine_name: str) -> dict[str, Any] | None:
        """Retrieve one vulnerable endpoint."""
        for field, value in (("discoveryId", discovery_id), ("machineName", machine_name)):
            if not value:
                continue
            safe = value.replace("'", "''")
            body = self._get_json(
                "/api/patch/content/v1/endpoint-vulnerability",
                family="patch",
                params={
                    "PageNumber": 1,
                    "PageSize": 150,
                    "Filter": f"{field} eq '{safe}' and missingPatches gt 0",
                },
            )
            rows = body.get("data") or []
            if rows and isinstance(rows[0], dict):
                return rows[0]
        return None

    def deployments(self, machine_name: str) -> list[dict[str, Any]]:
        """On-demand deployment telemetry for an individual machine."""
        safe = machine_name.replace("'", "''")
        body = self._get_json(
            "/api/patch/content/v1/deployment-history",
            family="patch",
            params={"PageNumber": 1, "PageSize": 150, "Filter": f"machineName eq '{safe}'"},
        )
        return [row for row in (body.get("data") or []) if isinstance(row, dict)]

    def notification(self, notification_id: str) -> dict[str, Any] | None:
        safe = notification_id.replace("'", "''")
        body = self._get_json(
            "/api/patch/content/v1/notification",
            family="patch",
            params={"PageNumber": 1, "PageSize": 1, "Filter": f"notificationId eq '{safe}'"},
        )
        rows = body.get("data") or []
        return rows[0] if rows and isinstance(rows[0], dict) else None

    def patch(self, patch_id: str) -> dict[str, Any] | None:
        safe = patch_id.replace("'", "''")
        body = self._get_json(
            "/api/patch/content/v1/patch",
            family="patch",
            params={"PageNumber": 1, "PageSize": 1, "Filter": f"patchId eq '{safe}'"},
        )
        rows = body.get("data") or []
        return rows[0] if rows and isinstance(rows[0], dict) else None

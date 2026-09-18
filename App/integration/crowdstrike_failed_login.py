"""
CrowdStrike Windows Security Investigation Client

Purpose:
    Authenticate to CrowdStrike Falcon US-2, create and poll Humio/LogScale
    query jobs, retrieve only Windows Security events 4625, 4740, and 4771,
    normalize the evidence, and build a structured failed-login and lockout
    investigation report for the TechAdmin Streamlit UI.

Confirmed CrowdStrike schema:
    Dataset:          #event.dataset = windows.security
    Event ID:         event.code
    Event ID fallback: windows.EventID
    Target username:  windows.EventData.TargetUserName
    Username fallback: user.target.name
    Timestamp:        @timestamp

Security guarantees:
    - Client secrets and bearer tokens are never logged.
    - Only events 4625, 4740, and 4771 are queried and retained.
    - Arbitrary numeric substrings in UUIDs, PIDs, timestamps, hashes, and
      command lines are never interpreted as Windows Event IDs.
    - User-supplied values are validated before being inserted into a query.
"""

from __future__ import annotations

import os
import re
import time
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from loguru import logger


ALLOWED_EVENT_IDS: tuple[int, ...] = (
    4625,
    4740,
    4771,
)

EVENT_NAMES: dict[int, str] = {
    4625: "Failed logon",
    4740: "Account locked out",
    4771: "Kerberos pre-authentication failed",
}


class CrowdStrikeError(RuntimeError):
    """Controlled CrowdStrike integration error safe for UI display."""


class CrowdStrikeFailedLoginClient:
    """
    OAuth2 client for CrowdStrike Humio/LogScale query jobs.

    The client follows the same pattern as MicrosoftGraphClient:
      1. Load credentials and configuration from environment variables.
      2. Obtain and cache an OAuth2 access token.
      3. Create a query job.
      4. Poll the query job until completion.
      5. Strictly normalize only the approved Windows Security events.
      6. Return a structured report to the application tool.
    """

    TOKEN_PATH = "/oauth2/token"
    QUERY_JOB_PATH_TEMPLATE = (
        "/humio/api/v1/repositories/{repository}/queryjobs"
    )

    def __init__(
        self,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        base_url: Optional[str] = None,
        repository: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
        poll_interval_seconds: Optional[float] = None,
        poll_timeout_seconds: Optional[int] = None,
        max_events: Optional[int] = None,
        verify_ssl: Optional[bool] = None,
    ) -> None:
        self.client_id = (
            client_id
            or os.getenv("CROWDSTRIKE_CLIENT_ID", "")
        ).strip()

        self.client_secret = (
            client_secret
            or os.getenv("CROWDSTRIKE_CLIENT_SECRET", "")
        )

        self.base_url = (
            base_url
            or os.getenv(
                "CROWDSTRIKE_BASE_URL",
                "https://api.us-2.crowdstrike.com",
            )
        ).strip().rstrip("/")

        self.repository = (
            repository
            or os.getenv(
                "CROWDSTRIKE_REPOSITORY",
                "search-all",
            )
        ).strip()

        self.timeout_seconds = (
            timeout_seconds
            if timeout_seconds is not None
            else int(
                os.getenv(
                    "CROWDSTRIKE_TIMEOUT_SECONDS",
                    "60",
                )
            )
        )

        self.poll_interval_seconds = (
            poll_interval_seconds
            if poll_interval_seconds is not None
            else float(
                os.getenv(
                    "CROWDSTRIKE_POLL_INTERVAL_SECONDS",
                    "2",
                )
            )
        )

        self.poll_timeout_seconds = (
            poll_timeout_seconds
            if poll_timeout_seconds is not None
            else int(
                os.getenv(
                    "CROWDSTRIKE_POLL_TIMEOUT_SECONDS",
                    "300",
                )
            )
        )

        self.max_events = (
            max_events
            if max_events is not None
            else int(
                os.getenv(
                    "CROWDSTRIKE_MAX_EVENTS",
                    "1000",
                )
            )
        )

        if verify_ssl is None:
            self.verify_ssl = os.getenv(
                "CROWDSTRIKE_VERIFY_SSL",
                "true",
            ).strip().casefold() in {
                "1",
                "true",
                "yes",
                "on",
            }
        else:
            self.verify_ssl = verify_ssl

        self.access_token: Optional[str] = None
        self._token_expires_at = 0.0

        logger.info(
            "CrowdStrikeFailedLoginClient initialized | "
            "base_url={} | repository={} | "
            "timeout_seconds={} | poll_timeout_seconds={} | "
            "max_events={} | verify_ssl={}",
            self.base_url,
            self.repository,
            self.timeout_seconds,
            self.poll_timeout_seconds,
            self.max_events,
            self.verify_ssl,
        )

    # ------------------------------------------------------------------
    # Configuration and authentication
    # ------------------------------------------------------------------

    def _validate_configuration(self) -> None:
        """Validate required settings without displaying their values."""

        missing: list[str] = []

        for name, value in (
            (
                "CROWDSTRIKE_CLIENT_ID",
                self.client_id,
            ),
            (
                "CROWDSTRIKE_CLIENT_SECRET",
                self.client_secret,
            ),
            (
                "CROWDSTRIKE_BASE_URL",
                self.base_url,
            ),
            (
                "CROWDSTRIKE_REPOSITORY",
                self.repository,
            ),
        ):
            if not value:
                missing.append(name)

        if missing:
            raise CrowdStrikeError(
                "Missing CrowdStrike configuration: "
                + ", ".join(missing)
            )

        if not re.fullmatch(
            r"[A-Za-z0-9._-]{1,128}",
            self.repository,
        ):
            raise CrowdStrikeError(
                "The CrowdStrike repository name is invalid."
            )

        if self.timeout_seconds < 1:
            raise CrowdStrikeError(
                "CROWDSTRIKE_TIMEOUT_SECONDS must be positive."
            )

        if self.poll_timeout_seconds < 1:
            raise CrowdStrikeError(
                "CROWDSTRIKE_POLL_TIMEOUT_SECONDS must be positive."
            )

        if self.max_events < 1 or self.max_events > 10000:
            raise CrowdStrikeError(
                "CROWDSTRIKE_MAX_EVENTS must be between 1 and 10000."
            )

    def authenticate(self) -> bool:
        """
        Obtain and cache a CrowdStrike OAuth2 bearer token.

        The method deliberately logs neither the client secret nor the token.
        """

        try:
            self._validate_configuration()

            response = requests.post(
                f"{self.base_url}{self.TOKEN_PATH}",
                data={
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                },
                headers={
                    "Accept": "application/json",
                },
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )

            if response.status_code not in (
                200,
                201,
            ):
                logger.error(
                    "CROWDSTRIKE_AUTH_FAILED | status_code={}",
                    response.status_code,
                )
                return False

            token_payload = response.json()
            token = token_payload.get("access_token")

            if not isinstance(token, str) or not token:
                logger.error(
                    "CROWDSTRIKE_AUTH_FAILED | reason=token_missing"
                )
                return False

            try:
                expires_in = int(
                    token_payload.get(
                        "expires_in",
                        1800,
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                expires_in = 1800

            self.access_token = token
            self._token_expires_at = (
                time.time()
                + max(
                    30,
                    expires_in - 60,
                )
            )

            logger.info(
                "CROWDSTRIKE_AUTH_SUCCESS"
            )
            return True

        except requests.RequestException as exc:
            logger.error(
                "CROWDSTRIKE_AUTH_FAILED | error_type={}",
                type(exc).__name__,
            )
            return False

        except (
            CrowdStrikeError,
            ValueError,
            TypeError,
        ) as exc:
            logger.error(
                "CROWDSTRIKE_AUTH_FAILED | error_type={}",
                type(exc).__name__,
            )
            return False

    def _ensure_token(self) -> None:
        """Ensure a non-expired token is available."""

        if (
            self.access_token
            and time.time() < self._token_expires_at
        ):
            return

        if not self.authenticate():
            raise CrowdStrikeError(
                "CrowdStrike OAuth authentication failed."
            )

    def _headers(self) -> dict[str, str]:
        """Build authenticated request headers."""

        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Query construction
    # ------------------------------------------------------------------

    def _query_jobs_url(self) -> str:
        """Return the query-job collection URL."""

        path = self.QUERY_JOB_PATH_TEMPLATE.format(
            repository=self.repository,
        )
        return f"{self.base_url}{path}"

    @staticmethod
    def _normalize_username(
        value: str,
    ) -> str:
        """Validate a target account and return its local username."""

        username = (
            value
            .split("@", 1)[0]
            .strip()
        )

        if not re.fullmatch(
            r"[A-Za-z0-9._-]{1,128}",
            username,
        ):
            raise CrowdStrikeError(
                "The target username contains unsupported characters."
            )

        return username

    @staticmethod
    def _parse_time_window(
        value: Optional[str],
    ) -> tuple[str, str, str]:
        """Convert a natural time window into LogScale relative time."""

        text = (
            value
            or "24 hours"
        ).strip().casefold()

        match = re.search(
            r"(\d+)\s*"
            r"(minute|minutes|min|m|"
            r"hour|hours|hr|h|"
            r"day|days|d)",
            text,
        )

        if not match:
            return (
                "24h",
                "now",
                "24 hours",
            )

        amount = max(
            1,
            int(match.group(1)),
        )
        unit = match.group(2)

        if unit in {
            "minute",
            "minutes",
            "min",
            "m",
        }:
            amount = min(
                amount,
                43200,
            )
            return (
                f"{amount}m",
                "now",
                f"{amount} minute(s)",
            )

        if unit in {
            "day",
            "days",
            "d",
        }:
            amount = min(
                amount,
                30,
            )
            return (
                f"{amount}d",
                "now",
                f"{amount} day(s)",
            )

        amount = min(
            amount,
            720,
        )
        return (
            f"{amount}h",
            "now",
            f"{amount} hour(s)",
        )

    def _build_query(
        self,
        username: str,
    ) -> str:
        """
        Build a strict query for the confirmed Windows Security schema.

        Only Event IDs 4625, 4740, and 4771 are included. The account match
        is case-insensitive and anchored to avoid matching a partial username.
        """

        normalized_username = self._normalize_username(
            username
        )
        escaped_username = (
            re.escape(normalized_username)
            .replace(
                "/",
                r"\/",
            )
        )

        return (
            '#event.dataset="windows.security" '
            '| ('
            'event.code="4625" '
            'OR event.code="4740" '
            'OR event.code="4771"'
            ') '
            '| windows.EventData.TargetUserName='
            f'/^{escaped_username}$/i '
            f'| head({self.max_events})'
        )

    # ------------------------------------------------------------------
    # Query-job execution
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_job_id(
        response: requests.Response,
    ) -> str:
        """Extract a query-job ID from JSON or Location header."""

        try:
            payload = response.json()
        except ValueError:
            payload = {}

        if isinstance(payload, dict):
            for key in (
                "id",
                "jobId",
                "job_id",
                "queryJobId",
            ):
                value = payload.get(key)

                if isinstance(value, str) and value:
                    return value

        location = response.headers.get(
            "Location",
            "",
        )

        if location:
            job_id = (
                urlparse(location)
                .path
                .rstrip("/")
                .split("/")[-1]
            )

            if job_id:
                return job_id

        raise CrowdStrikeError(
            "CrowdStrike query-job creation did not return a job ID."
        )

    def _create_query_job(
        self,
        *,
        username: str,
        start: str,
        end: str,
        correlation_id: str,
    ) -> tuple[str, str]:
        """Create a targeted CrowdStrike query job."""

        query = self._build_query(
            username
        )

        logger.info(
            "CROWDSTRIKE_QUERY_CREATE | "
            "correlation_id={} | repository={} | "
            "allowed_event_ids=4625,4740,4771 | "
            "target_user_present=true | start={} | end={}",
            correlation_id,
            self.repository,
            start,
            end,
        )

        response = requests.post(
            self._query_jobs_url(),
            headers=self._headers(),
            json={
                "queryString": query,
                "start": start,
                "end": end,
                "isLive": False,
            },
            timeout=self.timeout_seconds,
            verify=self.verify_ssl,
        )

        if response.status_code not in (
            200,
            201,
            202,
        ):
            logger.error(
                "CROWDSTRIKE_QUERY_CREATE_FAILED | "
                "correlation_id={} | status_code={}",
                correlation_id,
                response.status_code,
            )
            raise CrowdStrikeError(
                "CrowdStrike query-job creation returned "
                f"HTTP {response.status_code}."
            )

        return (
            self._extract_job_id(response),
            query,
        )

    def _poll_query_job(
        self,
        *,
        job_id: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        """Poll a query job until completion, cancellation, or timeout."""

        deadline = (
            time.monotonic()
            + self.poll_timeout_seconds
        )
        poll_url = (
            f"{self._query_jobs_url()}"
            f"/{job_id}"
        )
        latest_payload: dict[str, Any] = {}

        while time.monotonic() < deadline:
            response = requests.get(
                poll_url,
                headers=self._headers(),
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )

            if response.status_code != 200:
                raise CrowdStrikeError(
                    "CrowdStrike query-job polling returned "
                    f"HTTP {response.status_code}."
                )

            payload = response.json()

            if not isinstance(payload, dict):
                raise CrowdStrikeError(
                    "CrowdStrike returned an invalid query-job response."
                )

            latest_payload = payload

            if payload.get("cancelled"):
                raise CrowdStrikeError(
                    "CrowdStrike query job was cancelled."
                )

            if payload.get("done"):
                logger.info(
                    "CROWDSTRIKE_QUERY_COMPLETED | "
                    "correlation_id={}",
                    correlation_id,
                )
                return payload

            metadata = payload.get("metaData")

            if not isinstance(metadata, dict):
                metadata = {}

            logger.info(
                "CROWDSTRIKE_QUERY_RUNNING | "
                "correlation_id={} | processed_events={} | "
                "processed_bytes={} | work_done={} | total_work={}",
                correlation_id,
                metadata.get("processedEvents"),
                metadata.get("processedBytes"),
                metadata.get("workDone"),
                metadata.get("totalWork"),
            )

            try:
                poll_after_seconds = (
                    float(
                        metadata.get(
                            "pollAfter",
                            1000,
                        )
                    )
                    / 1000.0
                )
            except (
                TypeError,
                ValueError,
            ):
                poll_after_seconds = 1.0

            delay = max(
                self.poll_interval_seconds,
                poll_after_seconds,
            )

            time.sleep(
                min(
                    delay,
                    5.0,
                )
            )

        metadata = latest_payload.get("metaData")

        if not isinstance(metadata, dict):
            metadata = {}

        raise CrowdStrikeError(
            "CrowdStrike query job exceeded the local "
            f"{self.poll_timeout_seconds}-second polling limit. "
            "Latest progress: "
            f"processedEvents={metadata.get('processedEvents')}, "
            f"processedBytes={metadata.get('processedBytes')}, "
            f"workDone={metadata.get('workDone')}, "
            f"totalWork={metadata.get('totalWork')}."
        )

    # ------------------------------------------------------------------
    # Event normalization
    # ------------------------------------------------------------------

    @staticmethod
    def _get_first(
        event: dict[str, Any],
        *keys: str,
    ) -> Any:
        """Return the first non-empty value for a list of field names."""

        for key in keys:
            value = event.get(key)

            if value not in (
                None,
                "",
            ):
                return value

        return None

    @classmethod
    def _normalize_event(
        cls,
        *,
        event: dict[str, Any],
        expected_username: str,
    ) -> Optional[dict[str, Any]]:
        """Normalize one genuine allowed Windows Security event."""

        raw_event_id = cls._get_first(
            event,
            "event.code",
            "windows.EventID",
        )

        try:
            event_id = int(
                str(raw_event_id).strip()
            )
        except (
            TypeError,
            ValueError,
        ):
            return None

        if event_id not in ALLOWED_EVENT_IDS:
            return None

        dataset = cls._get_first(
            event,
            "#event.dataset",
        )

        if (
            dataset
            and str(dataset).casefold()
            != "windows.security"
        ):
            return None

        username = cls._get_first(
            event,
            "windows.EventData.TargetUserName",
            "user.target.name",
        )

        if not username:
            return None

        normalized_event_user = (
            str(username)
            .strip()
            .split("\\")[-1]
            .split("@", 1)[0]
            .casefold()
        )

        if (
            normalized_event_user
            != expected_username.casefold()
        ):
            return None

        return {
            "event_id": event_id,
            "event_name": EVENT_NAMES[event_id],
            "timestamp": cls._get_first(
                event,
                "@timestamp",
                "windows.TimeCreated",
                "@collect.timestamp",
            ),
            "username": username,
            "domain": cls._get_first(
                event,
                "windows.EventData.TargetDomainName",
                "user.target.domain",
                "destination.domain",
            ),
            "computer": cls._get_first(
                event,
                "windows.Computer",
                "host.name",
                "@collect.host",
            ),
            "workstation": cls._get_first(
                event,
                "windows.EventData.WorkstationName",
                "windows.EventData.CallerComputerName",
            ),
            "source_ip": cls._get_first(
                event,
                "source.ip",
                "windows.EventData.IpAddress",
                "client.ip",
                "source.address",
            ),
            "source_port": cls._get_first(
                event,
                "source.port",
                "windows.EventData.IpPort",
                "client.port",
            ),
            "status": cls._get_first(
                event,
                "windows.EventData.Status",
            ),
            "sub_status": cls._get_first(
                event,
                "windows.EventData.SubStatus",
            ),
            "failure_code": cls._get_first(
                event,
                "windows.EventData.FailureCode",
                "windows.EventData.Status",
                "event.code_detail",
            ),
            "failure_reason": cls._get_first(
                event,
                "event.reason",
                "windows.EventData.FailureReason",
            ),
            "logon_type": cls._get_first(
                event,
                "windows.EventData.LogonType",
                "Vendor.LogonTypeString",
            ),
            "authentication_package": cls._get_first(
                event,
                "windows.EventData.AuthenticationPackageName",
            ),
            "pre_auth_type": cls._get_first(
                event,
                "windows.EventData.PreAuthType",
            ),
            "service_name": cls._get_first(
                event,
                "windows.EventData.ServiceName",
            ),
            "ticket_options": cls._get_first(
                event,
                "windows.EventData.TicketOptions",
            ),
            "record_id": cls._get_first(
                event,
                "windows.EventRecordId",
                "event.id",
                "@id",
            ),
            "provider": cls._get_first(
                event,
                "event.provider",
                "windows.ProviderName",
            ),
            "repository": event.get("#repo"),
        }

    # ------------------------------------------------------------------
    # Report generation
    # ------------------------------------------------------------------

    @staticmethod
    def _build_report(
        *,
        username: str,
        time_window: str,
        events: list[dict[str, Any]],
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        """Build structured data consumed by the visual Streamlit report."""

        event_counts = Counter(
            event["event_id"]
            for event in events
        )

        source_counts = Counter(
            str(
                event.get("workstation")
                or event.get("source_ip")
                or event.get("computer")
                or "Source unavailable"
            )
            for event in events
        )

        failure_counts = Counter(
            str(
                event.get("failure_code")
                or event.get("sub_status")
                or event.get("status")
                or event.get("failure_reason")
                or "Reason unavailable"
            )
            for event in events
        )

        timeline = sorted(
            events,
            key=lambda event: str(
                event.get("timestamp")
                or ""
            ),
        )

        failed_logon_count = event_counts.get(
            4625,
            0,
        )
        lockout_count = event_counts.get(
            4740,
            0,
        )
        kerberos_failure_count = event_counts.get(
            4771,
            0,
        )

        if lockout_count:
            assessment = (
                "Account lockout confirmed by "
                f"{lockout_count} Event 4740 record(s). "
                "Related evidence includes "
                f"{failed_logon_count} Event 4625 record(s) "
                "and "
                f"{kerberos_failure_count} Event 4771 record(s)."
            )
        elif (
            failed_logon_count
            or kerberos_failure_count
        ):
            assessment = (
                "Authentication failures were found: "
                f"{failed_logon_count} Event 4625 record(s) "
                "and "
                f"{kerberos_failure_count} Event 4771 record(s). "
                "No Event 4740 account-lockout record was found "
                "in the selected time window."
            )
        else:
            assessment = (
                "No matching Windows Security Events 4625, 4740, "
                "or 4771 were found for the target account in the "
                "selected time window."
            )

        return {
            "title": (
                "Failed Login and Account Lockout Investigation"
            ),
            "target_user": username,
            "time_window": time_window,
            "generated_at_utc": datetime.now(
                timezone.utc
            ).isoformat(),
            "total_matching_events": len(events),
            "event_counts": {
                "4625": failed_logon_count,
                "4740": lockout_count,
                "4771": kerberos_failure_count,
            },
            "lockout_detected": bool(lockout_count),
            "assessment": assessment,
            "top_sources": [
                {
                    "source": source,
                    "count": count,
                }
                for source, count in source_counts.most_common(10)
            ],
            "top_failure_codes": [
                {
                    "value": value,
                    "count": count,
                }
                for value, count in failure_counts.most_common(10)
            ],
            "timeline": timeline,
            "diagnostics": diagnostics,
        }

    # ------------------------------------------------------------------
    # Public operation
    # ------------------------------------------------------------------

    def investigate_failed_login(
        self,
        *,
        username: str,
        email: Optional[str],
        employee_number: Optional[str],
        time_window: Optional[str],
        correlation_id: str,
    ) -> dict[str, Any]:
        """Execute one failed-login and lockout investigation."""

        # The current CrowdStrike query uses the account name. The argument is
        # retained for compatibility with the injected client protocol.
        del employee_number

        try:
            self._ensure_token()

            target_identifier = (
                username
                or email
                or ""
            )
            target_username = self._normalize_username(
                target_identifier
            )

            start, end, normalized_window = (
                self._parse_time_window(
                    time_window
                )
            )

            job_id, query = self._create_query_job(
                username=target_username,
                start=start,
                end=end,
                correlation_id=correlation_id,
            )

            payload = self._poll_query_job(
                job_id=job_id,
                correlation_id=correlation_id,
            )

            raw_events_value = payload.get("events")
            raw_events = (
                raw_events_value
                if isinstance(raw_events_value, list)
                else []
            )

            normalized_events: list[dict[str, Any]] = []

            for raw_event in raw_events:
                if not isinstance(raw_event, dict):
                    continue

                normalized_event = self._normalize_event(
                    event=raw_event,
                    expected_username=target_username,
                )

                if normalized_event is not None:
                    normalized_events.append(
                        normalized_event
                    )

            metadata = payload.get("metaData")

            if not isinstance(metadata, dict):
                metadata = {}

            diagnostics = {
                "query_completed": bool(
                    payload.get("done")
                ),
                "query_cancelled": bool(
                    payload.get("cancelled")
                ),
                "raw_events_returned": len(raw_events),
                "matching_events": len(normalized_events),
                "processed_events": metadata.get(
                    "processedEvents"
                ),
                "processed_bytes": metadata.get(
                    "processedBytes"
                ),
                "files_used_count": len(
                    payload.get("filesUsed")
                    or []
                ),
                "repository": self.repository,
                "query": query,
            }

            report = self._build_report(
                username=target_username,
                time_window=normalized_window,
                events=normalized_events,
                diagnostics=diagnostics,
            )

            matching_count = report[
                "total_matching_events"
            ]

            if matching_count:
                message = (
                    "CrowdStrike investigation completed. "
                    f"{matching_count} matching Windows Security "
                    "event(s) found."
                )
            else:
                message = (
                    "CrowdStrike investigation completed, but no "
                    "matching Windows Security events were found."
                )

            logger.info(
                "CROWDSTRIKE_INVESTIGATION_COMPLETED | "
                "correlation_id={} | target_user={} | "
                "matching_events={} | lockout_detected={}",
                correlation_id,
                target_username,
                matching_count,
                report["lockout_detected"],
            )

            return {
                "success": True,
                "message": message,
                "result": {
                    "source": (
                        "CrowdStrike Humio/LogScale query jobs"
                    ),
                    "allowed_event_ids": list(
                        ALLOWED_EVENT_IDS
                    ),
                    "report": report,
                },
                "error": None,
            }

        except CrowdStrikeError as exc:
            logger.error(
                "CROWDSTRIKE_INVESTIGATION_FAILED | "
                "correlation_id={} | error_type={}",
                correlation_id,
                type(exc).__name__,
            )

            return {
                "success": False,
                "message": (
                    "CrowdStrike failed-login investigation failed."
                ),
                "result": None,
                "error": str(exc),
            }

        except requests.RequestException as exc:
            logger.error(
                "CROWDSTRIKE_INVESTIGATION_FAILED | "
                "correlation_id={} | error_type={}",
                correlation_id,
                type(exc).__name__,
            )

            return {
                "success": False,
                "message": (
                    "CrowdStrike failed-login investigation failed."
                ),
                "result": None,
                "error": type(exc).__name__,
            }

        except Exception as exc:
            logger.exception(
                "CROWDSTRIKE_INVESTIGATION_FAILED | "
                "correlation_id={} | error_type={}",
                correlation_id,
                type(exc).__name__,
            )

            return {
                "success": False,
                "message": (
                    "CrowdStrike failed-login investigation failed."
                ),
                "result": None,
                "error": type(exc).__name__,
            }

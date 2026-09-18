"""
CrowdStrike Windows Security Investigation Client.

Queries Windows Security events 4625, 4740 and 4771, enforces the requested
window again locally, normalizes IPv4-mapped IPv6 addresses, excludes configured
infrastructure addresses ending in .252 or .253, deduplicates evidence,
calculates source-first statistics, and optionally enriches the report through
Ollama while retaining a deterministic fallback.
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import time
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from urllib.parse import urlparse

import requests
from loguru import logger

ALLOWED_EVENT_IDS: tuple[int, ...] = (4625, 4740, 4771)
EVENT_NAMES = {
    4625: "Failed logon",
    4740: "Account locked out",
    4771: "Kerberos pre-authentication failed",
}
DEFAULT_TIME_WINDOW = "24 hours"
EXCLUDED_LAST_OCTETS = {252, 253}


class CrowdStrikeError(RuntimeError):
    """Controlled CrowdStrike integration error safe for UI display."""


class CrowdStrikeFailedLoginClient:
    TOKEN_PATH = "/oauth2/token"
    QUERY_JOB_PATH_TEMPLATE = "/humio/api/v1/repositories/{repository}/queryjobs"

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
        self.client_id = (client_id or os.getenv("CROWDSTRIKE_CLIENT_ID", "")).strip()
        self.client_secret = client_secret or os.getenv("CROWDSTRIKE_CLIENT_SECRET", "")
        self.base_url = (base_url or os.getenv("CROWDSTRIKE_BASE_URL", "https://api.us-2.crowdstrike.com")).strip().rstrip("/")
        self.repository = (repository or os.getenv("CROWDSTRIKE_REPOSITORY", "search-all")).strip()
        self.timeout_seconds = timeout_seconds if timeout_seconds is not None else int(os.getenv("CROWDSTRIKE_TIMEOUT_SECONDS", "60"))
        self.poll_interval_seconds = poll_interval_seconds if poll_interval_seconds is not None else float(os.getenv("CROWDSTRIKE_POLL_INTERVAL_SECONDS", "2"))
        self.poll_timeout_seconds = poll_timeout_seconds if poll_timeout_seconds is not None else int(os.getenv("CROWDSTRIKE_POLL_TIMEOUT_SECONDS", "300"))
        self.max_events = max_events if max_events is not None else int(os.getenv("CROWDSTRIKE_MAX_EVENTS", "1000"))
        self.verify_ssl = (
            os.getenv("CROWDSTRIKE_VERIFY_SSL", "true").strip().casefold() in {"1", "true", "yes", "on"}
            if verify_ssl is None else verify_ssl
        )
        self.enable_llm_analysis = os.getenv("CROWDSTRIKE_ENABLE_LLM_ANALYSIS", "true").strip().casefold() in {"1", "true", "yes", "on"}
        self.ollama_host = os.getenv("OLLAMA_HOST", "http://localhost:11434").strip().rstrip("/")
        self.model_name = os.getenv("MODEL_NAME", "qwen3:14b").strip()
        self.access_token: Optional[str] = None
        self._token_expires_at = 0.0
        logger.info(
            "CrowdStrikeFailedLoginClient initialized | base_url={} | repository={} | timeout_seconds={} | poll_timeout_seconds={} | max_events={} | verify_ssl={} | llm_analysis={}",
            self.base_url, self.repository, self.timeout_seconds, self.poll_timeout_seconds,
            self.max_events, self.verify_ssl, self.enable_llm_analysis,
        )

    def _validate_configuration(self) -> None:
        missing = [name for name, value in (
            ("CROWDSTRIKE_CLIENT_ID", self.client_id),
            ("CROWDSTRIKE_CLIENT_SECRET", self.client_secret),
            ("CROWDSTRIKE_BASE_URL", self.base_url),
            ("CROWDSTRIKE_REPOSITORY", self.repository),
        ) if not value]
        if missing:
            raise CrowdStrikeError("Missing CrowdStrike configuration: " + ", ".join(missing))
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", self.repository):
            raise CrowdStrikeError("The CrowdStrike repository name is invalid.")
        if self.timeout_seconds < 1 or self.poll_timeout_seconds < 1:
            raise CrowdStrikeError("CrowdStrike timeout settings must be positive.")
        if self.max_events < 1 or self.max_events > 10000:
            raise CrowdStrikeError("CROWDSTRIKE_MAX_EVENTS must be between 1 and 10000.")

    def authenticate(self) -> bool:
        try:
            self._validate_configuration()
            response = requests.post(
                f"{self.base_url}{self.TOKEN_PATH}",
                data={"client_id": self.client_id, "client_secret": self.client_secret},
                headers={"Accept": "application/json"},
                timeout=self.timeout_seconds,
                verify=self.verify_ssl,
            )
            if response.status_code not in (200, 201):
                logger.error("CROWDSTRIKE_AUTH_FAILED | status_code={}", response.status_code)
                return False
            payload = response.json()
            token = payload.get("access_token")
            if not isinstance(token, str) or not token:
                return False
            try:
                expires_in = int(payload.get("expires_in", 1800))
            except (TypeError, ValueError):
                expires_in = 1800
            self.access_token = token
            self._token_expires_at = time.time() + max(30, expires_in - 60)
            logger.info("CROWDSTRIKE_AUTH_SUCCESS")
            return True
        except (requests.RequestException, CrowdStrikeError, ValueError, TypeError) as exc:
            logger.error("CROWDSTRIKE_AUTH_FAILED | error_type={}", type(exc).__name__)
            return False

    def _ensure_token(self) -> None:
        if self.access_token and time.time() < self._token_expires_at:
            return
        if not self.authenticate():
            raise CrowdStrikeError("CrowdStrike OAuth authentication failed.")

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _query_jobs_url(self) -> str:
        return f"{self.base_url}{self.QUERY_JOB_PATH_TEMPLATE.format(repository=self.repository)}"

    @staticmethod
    def _normalize_username(value: str) -> str:
        username = value.split("@", 1)[0].strip()
        if not re.fullmatch(r"[A-Za-z0-9._-]{1,128}", username):
            raise CrowdStrikeError("The target username contains unsupported characters.")
        return username

    @staticmethod
    def _parse_time_window(value: Optional[str]) -> tuple[str, str, str, timedelta]:
        """Return LogScale start/end, display label and precise local duration."""
        text = (value or DEFAULT_TIME_WINDOW).strip().casefold()
        match = re.search(r"(\d+)\s*(minute|minutes|min|m|hour|hours|hr|h|day|days|d)", text)
        if not match:
            return "24h", "now", DEFAULT_TIME_WINDOW, timedelta(hours=24)
        amount = max(1, int(match.group(1)))
        unit = match.group(2)
        if unit in {"minute", "minutes", "min", "m"}:
            amount = min(amount, 43200)
            return f"{amount}m", "now", f"{amount} minute(s)", timedelta(minutes=amount)
        if unit in {"day", "days", "d"}:
            amount = min(amount, 30)
            return f"{amount}d", "now", f"{amount} day(s)", timedelta(days=amount)
        amount = min(amount, 720)
        return f"{amount}h", "now", f"{amount} hour(s)", timedelta(hours=amount)

    def _build_query(self, username: str) -> str:
        escaped = re.escape(self._normalize_username(username)).replace("/", r"\/")
        return (
            '#event.dataset="windows.security" '
            '| (event.code="4625" OR event.code="4740" OR event.code="4771") '
            '| windows.EventData.TargetUserName=' f'/^{escaped}$/i '
            f'| head({self.max_events})'
        )

    @staticmethod
    def _extract_job_id(response: requests.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if isinstance(payload, dict):
            for key in ("id", "jobId", "job_id", "queryJobId"):
                value = payload.get(key)
                if isinstance(value, str) and value:
                    return value
        location = response.headers.get("Location", "")
        if location:
            job_id = urlparse(location).path.rstrip("/").split("/")[-1]
            if job_id:
                return job_id
        raise CrowdStrikeError("CrowdStrike query-job creation did not return a job ID.")

    def _create_query_job(self, *, username: str, start: str, end: str, correlation_id: str) -> tuple[str, str]:
        query = self._build_query(username)
        logger.info(
            "CROWDSTRIKE_QUERY_CREATE | correlation_id={} | repository={} | allowed_event_ids=4625,4740,4771 | start={} | end={}",
            correlation_id, self.repository, start, end,
        )
        response = requests.post(
            self._query_jobs_url(), headers=self._headers(),
            json={"queryString": query, "start": start, "end": end, "isLive": False},
            timeout=self.timeout_seconds, verify=self.verify_ssl,
        )
        if response.status_code not in (200, 201, 202):
            raise CrowdStrikeError(f"CrowdStrike query-job creation returned HTTP {response.status_code}.")
        return self._extract_job_id(response), query

    def _poll_query_job(self, *, job_id: str, correlation_id: str) -> dict[str, Any]:
        deadline = time.monotonic() + self.poll_timeout_seconds
        poll_url = f"{self._query_jobs_url()}/{job_id}"
        latest: dict[str, Any] = {}
        while time.monotonic() < deadline:
            response = requests.get(
                poll_url, headers=self._headers(), timeout=self.timeout_seconds, verify=self.verify_ssl
            )
            if response.status_code != 200:
                raise CrowdStrikeError(f"CrowdStrike query-job polling returned HTTP {response.status_code}.")
            payload = response.json()
            if not isinstance(payload, dict):
                raise CrowdStrikeError("CrowdStrike returned an invalid query-job response.")
            latest = payload
            if payload.get("cancelled"):
                raise CrowdStrikeError("CrowdStrike query job was cancelled.")
            if payload.get("done"):
                logger.info("CROWDSTRIKE_QUERY_COMPLETED | correlation_id={}", correlation_id)
                return payload
            metadata = payload.get("metaData") if isinstance(payload.get("metaData"), dict) else {}
            try:
                poll_after = float(metadata.get("pollAfter", 1000)) / 1000.0
            except (TypeError, ValueError):
                poll_after = 1.0
            time.sleep(min(max(self.poll_interval_seconds, poll_after), 5.0))
        metadata = latest.get("metaData") if isinstance(latest.get("metaData"), dict) else {}
        raise CrowdStrikeError(
            f"CrowdStrike query exceeded the {self.poll_timeout_seconds}-second polling limit. "
            f"processedEvents={metadata.get('processedEvents')}."
        )

    @staticmethod
    def _get_first(event: dict[str, Any], *keys: str) -> Any:
        for key in keys:
            value = event.get(key)
            if value not in (None, ""):
                return value
        return None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime | None:
        if value is None:
            return None
        try:
            if isinstance(value, (int, float)) or str(value).strip().isdigit():
                number = float(value)
                while number > 10_000_000_000:
                    number /= 1000.0
                return datetime.fromtimestamp(number, tz=timezone.utc)
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except (ValueError, TypeError, OSError):
            return None

    @staticmethod
    def _normalize_ip(value: Any) -> tuple[str | None, bool]:
        """Return normalized IP and whether the address must be excluded."""
        if value is None:
            return None, False
        text = str(value).strip()
        if not text or text in {"-", "::", "0.0.0.0", "Unknown", "None", "null"}:
            return None, False
        if text.casefold().startswith("::ffff:"):
            text = text[7:]
        try:
            parsed = ipaddress.ip_address(text)
        except ValueError:
            return text, False
        if isinstance(parsed, ipaddress.IPv6Address) and parsed.ipv4_mapped:
            parsed = parsed.ipv4_mapped
        if isinstance(parsed, ipaddress.IPv4Address):
            last_octet = int(str(parsed).split(".")[-1])
            if last_octet in EXCLUDED_LAST_OCTETS:
                return None, True
        return str(parsed), False

    @classmethod
    def _normalize_event(cls, *, event: dict[str, Any], expected_username: str) -> Optional[dict[str, Any]]:
        raw_event_id = cls._get_first(event, "event.code", "windows.EventID")
        try:
            event_id = int(str(raw_event_id).strip())
        except (TypeError, ValueError):
            return None
        if event_id not in ALLOWED_EVENT_IDS:
            return None
        dataset = cls._get_first(event, "#event.dataset")
        if dataset and str(dataset).casefold() != "windows.security":
            return None
        username = cls._get_first(event, "windows.EventData.TargetUserName", "user.target.name")
        if not username:
            return None
        event_user = str(username).strip().split("\\")[-1].split("@", 1)[0].casefold()
        if event_user != expected_username.casefold():
            return None
        raw_source_ip = cls._get_first(
            event, "source.ip", "windows.EventData.IpAddress", "client.ip", "source.address"
        )
        source_ip, excluded = cls._normalize_ip(raw_source_ip)
        timestamp = cls._get_first(event, "@timestamp", "windows.TimeCreated", "@collect.timestamp")
        return {
            "event_id": event_id,
            "event_name": EVENT_NAMES[event_id],
            "timestamp": timestamp,
            "timestamp_utc": cls._parse_timestamp(timestamp).isoformat() if cls._parse_timestamp(timestamp) else None,
            "username": username,
            "domain": cls._get_first(event, "windows.EventData.TargetDomainName", "user.target.domain", "destination.domain"),
            "computer": cls._get_first(event, "windows.Computer", "host.name", "@collect.host"),
            "workstation": cls._get_first(event, "windows.EventData.WorkstationName", "windows.EventData.CallerComputerName"),
            "source_ip": source_ip,
            "source_ip_excluded": excluded,
            "source_port": cls._get_first(event, "source.port", "windows.EventData.IpPort", "client.port"),
            "status": cls._get_first(event, "windows.EventData.Status"),
            "sub_status": cls._get_first(event, "windows.EventData.SubStatus"),
            "failure_code": cls._get_first(event, "windows.EventData.FailureCode", "windows.EventData.Status", "event.code_detail"),
            "failure_reason": cls._get_first(event, "event.reason", "windows.EventData.FailureReason"),
            "logon_type": cls._get_first(event, "windows.EventData.LogonType", "Vendor.LogonTypeString"),
            "authentication_package": cls._get_first(event, "windows.EventData.AuthenticationPackageName"),
            "pre_auth_type": cls._get_first(event, "windows.EventData.PreAuthType"),
            "service_name": cls._get_first(event, "windows.EventData.ServiceName"),
            "ticket_options": cls._get_first(event, "windows.EventData.TicketOptions"),
            "record_id": cls._get_first(event, "windows.EventRecordId", "event.id", "@id"),
            "provider": cls._get_first(event, "event.provider", "windows.ProviderName"),
            "repository": event.get("#repo"),
        }

    @classmethod
    def _filter_and_deduplicate(
        cls,
        events: list[dict[str, Any]],
        *,
        effective_start: datetime,
        effective_end: datetime,
    ) -> tuple[list[dict[str, Any]], dict[str, int]]:
        retained: list[dict[str, Any]] = []
        outside_window = 0
        excluded_source = 0
        invalid_timestamp = 0
        duplicates = 0
        seen: set[tuple[Any, ...]] = set()
        for event in events:
            timestamp = cls._parse_timestamp(event.get("timestamp"))
            if timestamp is None:
                invalid_timestamp += 1
                continue
            if timestamp < effective_start or timestamp > effective_end:
                outside_window += 1
                continue
            if bool(event.get("source_ip_excluded")):
                excluded_source += 1
                continue
            key = (
                event.get("record_id"), event.get("event_id"), timestamp.isoformat(),
                event.get("computer"), event.get("workstation"), event.get("source_ip"),
                event.get("failure_code"), event.get("status"), event.get("sub_status"),
            )
            if key in seen:
                duplicates += 1
                continue
            seen.add(key)
            cleaned = dict(event)
            cleaned.pop("source_ip_excluded", None)
            cleaned["timestamp_utc"] = timestamp.isoformat()
            retained.append(cleaned)
        retained.sort(key=lambda item: item.get("timestamp_utc") or "")
        return retained, {
            "events_outside_requested_window": outside_window,
            "excluded_source_events": excluded_source,
            "invalid_timestamp_events": invalid_timestamp,
            "duplicate_events_removed": duplicates,
        }

    @staticmethod
    def _build_source_statistics(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
        aggregate: dict[str, dict[str, Any]] = {}
        for event in events:
            source_ip = event.get("source_ip")
            workstation = event.get("workstation")
            computer = event.get("computer")
            source = source_ip or workstation or computer
            if not source:
                continue
            row = aggregate.setdefault(str(source), {
                "source": str(source),
                "source_type": "IP address" if source_ip else "Device",
                "failed_logons": 0,
                "lockouts": 0,
                "kerberos_failures": 0,
                "total_events": 0,
                "first_seen": event.get("timestamp_utc"),
                "last_seen": event.get("timestamp_utc"),
            })
            event_id = int(event.get("event_id", 0) or 0)
            if event_id == 4625:
                row["failed_logons"] += 1
            elif event_id == 4740:
                row["lockouts"] += 1
            elif event_id == 4771:
                row["kerberos_failures"] += 1
            row["total_events"] += 1
            stamp = event.get("timestamp_utc")
            if stamp and (not row["first_seen"] or stamp < row["first_seen"]):
                row["first_seen"] = stamp
            if stamp and (not row["last_seen"] or stamp > row["last_seen"]):
                row["last_seen"] = stamp
        return sorted(aggregate.values(), key=lambda item: item["total_events"], reverse=True)

    @staticmethod
    def _deterministic_analysis(report: dict[str, Any]) -> dict[str, Any]:
        counts = report["event_counts"]
        sources = report.get("source_statistics") or []
        failed = counts["4625"]
        lockouts = counts["4740"]
        kerberos = counts["4771"]
        top_source = sources[0] if sources else None
        if lockouts and (failed or kerberos):
            summary = "Confirmed account lockout events occurred in the same effective window as repeated authentication failures."
            cause = "Recurring invalid or stale credentials"
            confidence = "High"
        elif failed or kerberos:
            summary = "Authentication failures were observed, but no Event 4740 lockout record was retained in the effective window."
            cause = "Authentication failure without confirmed lockout evidence"
            confidence = "Medium"
        else:
            summary = "No matching authentication evidence remained after validation, time-window enforcement, source filtering, and deduplication."
            cause = "Insufficient evidence"
            confidence = "Low"
        if top_source:
            summary += f" The highest-frequency visible source was {top_source['source']} with {top_source['total_events']} event(s)."
        return {
            "executive_summary": summary,
            "primary_cause": cause,
            "primary_cause_detail": "Review the visible source distribution and failure codes before unlocking or changing credentials.",
            "confidence": confidence,
            "event_sequence": [
                f"{kerberos} Kerberos pre-authentication failure(s) occurred.",
                f"{failed} failed Windows logon event(s) occurred.",
                f"{lockouts} account-lockout event(s) occurred.",
            ],
            "evidence": [
                f"Final filtered events: {report['total_matching_events']}",
                f"Unique visible sources: {len(sources)}",
                f"Evidence coverage: {report.get('first_event_utc') or 'none'} to {report.get('last_event_utc') or 'none'}",
            ],
            "recommended_actions": [
                "Investigate the highest-frequency visible source first.",
                "Check services, scheduled tasks, mapped drives, mobile clients, and cached credentials for stale passwords.",
                "Stop recurring attempts before unlocking the account.",
                "Escalate unrecognized sources or abnormal frequency to security operations.",
            ],
            "limitations": "Windows Security evidence may not identify the exact application or person that submitted a credential.",
            "analysis_source": "Validated deterministic evidence analysis",
        }

    def _llm_analysis(self, report: dict[str, Any]) -> dict[str, Any] | None:
        """Ask Ollama to explain precomputed evidence without allowing it to invent counts."""
        if not self.enable_llm_analysis or not report.get("timeline"):
            return None
        evidence_payload = {
            "target_user": report["target_user"],
            "requested_time_window": report["requested_time_window"],
            "effective_start_utc": report["effective_start_utc"],
            "effective_end_utc": report["effective_end_utc"],
            "first_event_utc": report.get("first_event_utc"),
            "last_event_utc": report.get("last_event_utc"),
            "event_counts": report["event_counts"],
            "total_matching_events": report["total_matching_events"],
            "source_statistics": report["source_statistics"][:10],
            "top_failure_codes": report["top_failure_codes"][:10],
            "timeline": report["timeline"][:100],
        }
        prompt = (
            "You are an enterprise identity security analyst. Analyze only the supplied validated evidence. "
            "All numerical values are precomputed and must be repeated exactly. Do not invent an IP, device, event, "
            "date, failure code, cause, or count. Clearly separate facts from hypotheses. Focus first on source frequency, "
            "then chronology, likely stale-credential sources, lockout evidence, limitations, and prioritized remediation. "
            "Return JSON only with keys: executive_summary, primary_cause, primary_cause_detail, confidence, "
            "event_sequence (array), evidence (array), recommended_actions (array), limitations.\nEVIDENCE:\n"
            + json.dumps(evidence_payload, ensure_ascii=False, default=str)
        )
        try:
            response = requests.post(
                f"{self.ollama_host}/api/generate",
                json={"model": self.model_name, "prompt": prompt, "stream": False, "format": "json"},
                timeout=max(self.timeout_seconds, 120),
            )
            response.raise_for_status()
            body = response.json()
            text = body.get("response")
            parsed = json.loads(text) if isinstance(text, str) else None
            if not isinstance(parsed, dict):
                return None
            parsed["analysis_source"] = f"Ollama evidence analysis ({self.model_name})"
            return parsed
        except Exception as exc:
            logger.warning("CROWDSTRIKE_LLM_ANALYSIS_FAILED | error_type={}", type(exc).__name__)
            return None

    def _build_report(
        self,
        *,
        username: str,
        requested_time_window: str,
        effective_start: datetime,
        effective_end: datetime,
        events: list[dict[str, Any]],
        diagnostics: dict[str, Any],
    ) -> dict[str, Any]:
        event_counts = Counter(event["event_id"] for event in events)
        source_statistics = self._build_source_statistics(events)
        failure_counts = Counter(str(
            event.get("failure_code") or event.get("sub_status") or event.get("status")
            or event.get("failure_reason") or "Reason unavailable"
        ) for event in events)
        failed = event_counts.get(4625, 0)
        lockouts = event_counts.get(4740, 0)
        kerberos = event_counts.get(4771, 0)
        if lockouts:
            assessment = f"Account lockout confirmed by {lockouts} Event 4740 record(s), with {failed} Event 4625 and {kerberos} Event 4771 record(s) in the same effective window."
        elif failed or kerberos:
            assessment = f"Authentication failures were found: {failed} Event 4625 and {kerberos} Event 4771 record(s). No Event 4740 remained in the effective window."
        else:
            assessment = "No matching Windows Security events remained after validation and filtering."
        report = {
            "title": "Failed Login and Account Lockout Investigation",
            "target_user": username,
            "time_window": requested_time_window,
            "requested_time_window": requested_time_window,
            "effective_start_utc": effective_start.isoformat(),
            "effective_end_utc": effective_end.isoformat(),
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "first_event_utc": events[0].get("timestamp_utc") if events else None,
            "last_event_utc": events[-1].get("timestamp_utc") if events else None,
            "total_matching_events": len(events),
            "event_counts": {"4625": failed, "4740": lockouts, "4771": kerberos},
            "lockout_detected": bool(lockouts),
            "assessment": assessment,
            "source_statistics": source_statistics,
            "top_sources": [{"source": row["source"], "count": row["total_events"]} for row in source_statistics[:10]],
            "top_failure_codes": [{"value": value, "count": count} for value, count in failure_counts.most_common(10)],
            "timeline": events,
            "diagnostics": diagnostics,
        }
        report["analysis"] = self._llm_analysis(report) or self._deterministic_analysis(report)
        return report

    def investigate_failed_login(
        self,
        *,
        username: str,
        email: Optional[str],
        employee_number: Optional[str],
        time_window: Optional[str],
        correlation_id: str,
    ) -> dict[str, Any]:
        del employee_number
        try:
            self._ensure_token()
            target_username = self._normalize_username(username or email or "")
            start, end, normalized_window, duration = self._parse_time_window(time_window)
            effective_end = datetime.now(timezone.utc)
            effective_start = effective_end - duration
            job_id, query = self._create_query_job(
                username=target_username, start=start, end=end, correlation_id=correlation_id
            )
            payload = self._poll_query_job(job_id=job_id, correlation_id=correlation_id)
            raw_events = payload.get("events") if isinstance(payload.get("events"), list) else []
            normalized_events = []
            for raw_event in raw_events:
                if not isinstance(raw_event, dict):
                    continue
                normalized = self._normalize_event(event=raw_event, expected_username=target_username)
                if normalized is not None:
                    normalized_events.append(normalized)
            filtered_events, filter_counts = self._filter_and_deduplicate(
                normalized_events, effective_start=effective_start, effective_end=effective_end
            )
            metadata = payload.get("metaData") if isinstance(payload.get("metaData"), dict) else {}
            diagnostics = {
                "query_completed": bool(payload.get("done")),
                "query_cancelled": bool(payload.get("cancelled")),
                "raw_events_returned": len(raw_events),
                "valid_account_events": len(normalized_events),
                "matching_events": len(filtered_events),
                "processed_events": metadata.get("processedEvents"),
                "processed_bytes": metadata.get("processedBytes"),
                "files_used_count": len(payload.get("filesUsed") or []),
                "repository": self.repository,
                "query": query,
                **filter_counts,
            }
            report = self._build_report(
                username=target_username,
                requested_time_window=normalized_window,
                effective_start=effective_start,
                effective_end=effective_end,
                events=filtered_events,
                diagnostics=diagnostics,
            )
            count = report["total_matching_events"]
            message = (
                f"CrowdStrike investigation completed. {count} matching filtered Windows Security event(s) found."
                if count else
                "CrowdStrike investigation completed, but no matching events remained after validation and filtering."
            )
            logger.info(
                "CROWDSTRIKE_INVESTIGATION_COMPLETED | correlation_id={} | target_user={} | requested_window={} | raw_events={} | filtered_events={} | excluded_source_events={} | duplicate_events_removed={} | lockout_detected={}",
                correlation_id, target_username, normalized_window, len(raw_events), count,
                filter_counts["excluded_source_events"], filter_counts["duplicate_events_removed"],
                report["lockout_detected"],
            )
            return {
                "success": True,
                "message": message,
                "result": {
                    "source": "CrowdStrike Humio/LogScale query jobs",
                    "allowed_event_ids": list(ALLOWED_EVENT_IDS),
                    "report": report,
                },
                "error": None,
            }
        except CrowdStrikeError as exc:
            logger.error("CROWDSTRIKE_INVESTIGATION_FAILED | correlation_id={} | error_type={}", correlation_id, type(exc).__name__)
            return {"success": False, "message": "CrowdStrike failed-login investigation failed.", "result": None, "error": str(exc)}
        except requests.RequestException as exc:
            logger.error("CROWDSTRIKE_INVESTIGATION_FAILED | correlation_id={} | error_type={}", correlation_id, type(exc).__name__)
            return {"success": False, "message": "CrowdStrike failed-login investigation failed.", "result": None, "error": type(exc).__name__}
        except Exception as exc:
            logger.exception("CROWDSTRIKE_INVESTIGATION_FAILED | correlation_id={} | error_type={}", correlation_id, type(exc).__name__)
            return {"success": False, "message": "CrowdStrike failed-login investigation failed.", "result": None, "error": type(exc).__name__}

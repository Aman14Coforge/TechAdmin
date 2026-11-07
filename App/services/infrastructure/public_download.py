"""Signed, expiring CSV download service for affected SolarWinds devices.

This is a separate lightweight HTTP endpoint. It does not expose the TechAdmin
Streamlit workspace and therefore does not redirect to Microsoft sign-in.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import hmac
import io
import os
import re
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

from loguru import logger

from App.services.infrastructure.itom_repository import ITOMSiteRepository

_SERVER: ThreadingHTTPServer | None = None
_LOCK = threading.Lock()


def _secret() -> bytes:
    value = os.getenv("INFRA_DOWNLOAD_SIGNING_SECRET", "").strip()
    if len(value) < 32:
        raise RuntimeError(
            "INFRA_DOWNLOAD_SIGNING_SECRET must contain at least 32 characters."
        )
    return value.encode("utf-8")


def _signature(site: str, expires: int) -> str:
    payload = f"{site}\n{expires}".encode("utf-8")
    digest = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_affected_device_csv_url(site: str) -> str:
    """Create exactly one signed URL using the configured local or public base."""
    base_url = os.getenv(
        "INFRA_DOWNLOAD_BASE_URL",
        "http://localhost:8503",
    ).strip().rstrip("/")
    lifetime_hours = max(1, int(os.getenv("INFRA_DOWNLOAD_LINK_HOURS", "168")))
    expires = int(time.time()) + lifetime_hours * 3600
    return (
        f"{base_url}/affected-devices.csv"
        f"?site={quote(site, safe='')}"
        f"&expires={expires}"
        f"&signature={quote(_signature(site, expires), safe='')}"
    )


def _validate(site: str, expires_text: str, signature: str) -> tuple[bool, str]:
    if not site:
        return False, "Missing site"
    try:
        expires = int(expires_text)
    except (TypeError, ValueError):
        return False, "Invalid expiry"
    if expires < int(time.time()):
        return False, "This download link has expired"
    if not hmac.compare_digest(_signature(site, expires), signature):
        return False, "Invalid download signature"
    return True, "OK"


def _csv_bytes(site: str) -> tuple[bytes | None, str]:
    alert = ITOMSiteRepository().get_site_alert(site)
    if alert is None:
        return None, "The site is not present in the latest affected SolarWinds data"

    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "Site",
            "Priority",
            "Reported site status",
            "Reported site score",
            "Device",
            "Device status",
            "Type",
            "Location",
            "Last seen IST",
            "Unreachable for",
        ],
    )
    writer.writeheader()
    for device in alert.devices:
        writer.writerow(
            {
                "Site": alert.location_name,
                "Priority": alert.priority,
                "Reported site status": alert.site_status,
                "Reported site score": alert.site_score,
                "Device": device.device_name,
                "Device status": device.device_status,
                "Type": device.ci_type or "Not available",
                "Location": device.source_location or "Not available",
                "Last seen IST": device.device_last_seen_ist or "Not available",
                "Unreachable for": device.device_silent_for or "Not available",
            }
        )
    return output.getvalue().encode("utf-8-sig"), "OK"


class _DownloadHandler(BaseHTTPRequestHandler):
    server_version = "TechAdminInfrastructureDownload/1.0"

    def log_message(self, format: str, *args: object) -> None:
        logger.info("INFRA_DOWNLOAD | " + format, *args)

    def _text(self, status: int, message: str) -> None:
        payload = message.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/health":
            self._text(HTTPStatus.OK, "TechAdmin Infrastructure download service is running")
            return
        if parsed.path != "/affected-devices.csv":
            self._text(HTTPStatus.NOT_FOUND, "Not found")
            return

        params = parse_qs(parsed.query)
        site = (params.get("site") or [""])[0].strip()
        expires = (params.get("expires") or [""])[0].strip()
        signature = (params.get("signature") or [""])[0].strip()
        valid, message = _validate(site, expires, signature)
        if not valid:
            self._text(HTTPStatus.FORBIDDEN, message)
            return

        try:
            content, message = _csv_bytes(site)
        except Exception as exc:
            logger.exception("INFRA_DOWNLOAD_FAILED | site={}", site)
            self._text(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                f"The CSV could not be generated: {type(exc).__name__}",
            )
            return
        if content is None:
            self._text(HTTPStatus.NOT_FOUND, message)
            return

        filename = re.sub(r"[^A-Za-z0-9_-]+", "_", site).strip("_")
        filename = f"{filename or 'site'}_solarwinds_devices.csv"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)


def start_public_download_service() -> ThreadingHTTPServer | None:
    """Start once per TechAdmin application process."""
    global _SERVER
    enabled = os.getenv("INFRA_DOWNLOAD_SERVICE_ENABLED", "true").strip().casefold()
    if enabled not in {"1", "true", "yes", "on"}:
        return None

    _secret()  # fail at startup when security is not configured
    with _LOCK:
        if _SERVER is not None:
            return _SERVER
        host = os.getenv("INFRA_DOWNLOAD_BIND_HOST", "127.0.0.1").strip()
        port = int(os.getenv("INFRA_DOWNLOAD_PORT", "8503"))
        server = ThreadingHTTPServer((host, port), _DownloadHandler)
        thread = threading.Thread(
            target=server.serve_forever,
            name="techadmin-infrastructure-download",
            daemon=True,
        )
        thread.start()
        _SERVER = server
        logger.info("Infrastructure CSV download service started on {}:{}", host, port)
        return server

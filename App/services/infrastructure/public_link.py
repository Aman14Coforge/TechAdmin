"""Signed, expiring public CSV links for Infrastructure Agent.

The link exposes only one site's affected SolarWinds CSV. It never exposes the
TechAdmin workspace, ticket history, email history, or other sites.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time
from urllib.parse import quote


def _secret() -> bytes:
    value = os.getenv("INFRA_PUBLIC_LINK_SECRET", "").strip()
    if len(value) < 32:
        raise RuntimeError(
            "INFRA_PUBLIC_LINK_SECRET must contain at least 32 characters."
        )
    return value.encode("utf-8")


def _signature(site: str, expires: int) -> str:
    payload = f"{site}\n{expires}".encode("utf-8")
    digest = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def create_public_csv_url(site: str) -> str:
    """Create one production-or-local URL based on TECHADMIN_PUBLIC_URL."""
    base = os.getenv(
        "TECHADMIN_PUBLIC_URL",
        "https://techadmin.coforge.com",
    ).strip().rstrip("/")
    lifetime_hours = max(
        1,
        int(os.getenv("INFRA_PUBLIC_LINK_HOURS", "168")),
    )
    expires = int(time.time()) + lifetime_hours * 3600
    signature = _signature(site, expires)
    return (
        f"{base}/?public_infra_csv=1"
        f"&site={quote(site, safe='')}"
        f"&expires={expires}"
        f"&signature={quote(signature, safe='')}"
    )


def validate_public_csv_request(
    site: str,
    expires: str,
    signature: str,
) -> tuple[bool, str]:
    if not site:
        return False, "Missing site."
    try:
        expires_value = int(expires)
    except (TypeError, ValueError):
        return False, "Invalid expiry."
    if expires_value < int(time.time()):
        return False, "This CSV link has expired."
    expected = _signature(site, expires_value)
    if not hmac.compare_digest(expected, str(signature or "")):
        return False, "Invalid link signature."
    return True, "OK"

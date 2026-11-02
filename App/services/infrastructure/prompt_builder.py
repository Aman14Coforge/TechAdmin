"""Build short iEngage text with no device names and one CSV link."""
from __future__ import annotations

import os

from App.services.infrastructure.models import InfrastructureSiteAlert
from App.services.infrastructure.public_download import create_affected_device_csv_url


def _value(value: object) -> str:
    return "Not available" if value in (None, "") else str(value)


def build_solarwinds_prompt(alert: InfrastructureSiteAlert) -> str:
    csv_url = create_affected_device_csv_url(alert.location_name)
    return f"""Investigate this SolarWinds site-health incident.

Site: {alert.location_name}
Priority: {alert.priority}
ITOM-reported status: {alert.site_status}
ITOM-reported score: {_value(alert.site_score)}
ITOM-reported reason: {_value(alert.site_reason)}
Affected SolarWinds devices: {alert.affected_count}
Critical/down SolarWinds devices: {alert.critical_devices}
Warning SolarWinds devices: {alert.degraded}
Affected-device CSV: {csv_url}

Using current SolarWinds evidence, provide the shared cause or dependency, node/interface/WAN/reachability/latency/packet-loss/power evidence, failure timeline, validation checks, restoration steps, evidence to attach, and data gaps. Do not invent evidence.""".strip()


def build_ticket_description(alert: InfrastructureSiteAlert) -> tuple[str, str]:
    csv_url = create_affected_device_csv_url(alert.location_name)
    prompt = build_solarwinds_prompt(alert)
    description = f"""INFRASTRUCTURE SITE HEALTH ALERT

Site: {alert.location_name}
Priority: {alert.priority}
ITOM-reported status: {alert.site_status}
ITOM-reported score: {_value(alert.site_score)}
ITOM-reported reason: {_value(alert.site_reason)}
Affected SolarWinds devices: {alert.affected_count}
Critical/down SolarWinds devices: {alert.critical_devices}
Warning SolarWinds devices: {alert.degraded}
Latest sync completed IST: {_value(alert.sync_completed_ist)}

DOWNLOAD AFFECTED SOLARWINDS DEVICE CSV
{csv_url}

COPY INTO SOLARWINDS CHAT
-------------------------
{prompt}
-------------------------
Created automatically by TechAdmin Infrastructure Agent.""".strip()

    max_chars = min(
        4000,
        max(1000, int(os.getenv("IENGAGE_DESCRIPTION_MAX_CHARS", "3900"))),
    )
    if len(description) > max_chars:
        fixed = f"""INFRASTRUCTURE SITE HEALTH ALERT

Site: {alert.location_name}
Priority: {alert.priority}
ITOM-reported status: {alert.site_status}
ITOM-reported score: {_value(alert.site_score)}
ITOM-reported reason: {_value(alert.site_reason)}
Affected SolarWinds devices: {alert.affected_count}

DOWNLOAD AFFECTED SOLARWINDS DEVICE CSV
{csv_url}

COPY INTO SOLARWINDS CHAT
-------------------------
"""
        suffix = "\n-------------------------\nCreated by TechAdmin Infrastructure Agent."
        description = fixed + prompt[: max(0, max_chars - len(fixed) - len(suffix))] + suffix
    return description, prompt

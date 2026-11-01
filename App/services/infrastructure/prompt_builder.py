"""Build deterministic iEngage descriptions and SolarWinds investigation prompts."""
from __future__ import annotations

import os

from App.services.infrastructure.models import InfrastructureSiteAlert


def _value(value: object) -> str:
    return "Not available" if value in (None, "") else str(value)


def _device_limit() -> int:
    try:
        value = int(os.getenv("INFRA_TICKET_DEVICE_DETAIL_LIMIT", "50"))
    except ValueError:
        value = 50
    return max(1, min(value, 200))


def _selected_devices(alert: InfrastructureSiteAlert):
    limit = _device_limit()
    return alert.devices[:limit], max(0, len(alert.devices) - limit)


def build_solarwinds_prompt(alert: InfrastructureSiteAlert) -> str:
    selected, omitted = _selected_devices(alert)
    device_lines = "\n".join(
        f"- {device.device_name} | type={_value(device.ci_type)} | "
        f"status={device.device_status} | source={device.source_system} | "
        f"source location={_value(device.source_location)} | "
        f"last seen IST={_value(device.device_last_seen_ist)} | "
        f"silent for={_value(device.device_silent_for)}"
        for device in selected
    ) or "- No affected-device detail was returned."

    if omitted:
        device_lines += (
            f"\n- {omitted} additional affected devices are omitted from this prompt. "
            "Use the TechAdmin Infrastructure Agent incident detail or CSV export for the complete list."
        )

    return f"""Investigate the following site-health incident using SolarWinds evidence.

Site: {alert.location_name}
Priority: {alert.priority}
Site status: {alert.site_status}
Site score: {_value(alert.site_score)}
Site reason: {_value(alert.site_reason)}
Score calculated IST: {_value(alert.score_calculated_ist)}
Latest sync completed IST: {_value(alert.sync_completed_ist)}
Total affected devices: {alert.affected_count}
Affected-device sample:
{device_lines}

Provide a concise operations-ready response with:
1. Most likely reason the site is critical/warning.
2. Device or dependency most likely driving the site status.
3. Correlated node, interface, WAN, power, reachability, packet-loss, latency, and alert evidence to inspect.
4. Timeline of first failure, latest state change, and current duration where available.
5. Whether the pattern indicates a site-wide outage, WAN issue, device issue, telemetry delay, or false positive.
6. Exact validation commands/checks for the network operations team.
7. Immediate containment or restoration steps, ordered by priority.
8. Evidence that should be attached to the iEngage incident.
9. Data gaps or assumptions. Do not invent unavailable SolarWinds evidence.
""".strip()


def build_ticket_description(alert: InfrastructureSiteAlert) -> tuple[str, str]:
    prompt = build_solarwinds_prompt(alert)
    selected, omitted = _selected_devices(alert)
    device_lines = "\n".join(
        f"{index}. {device.device_name} | {device.source_system} | "
        f"{device.device_status} | {_value(device.ci_type)} | "
        f"last seen IST: {_value(device.device_last_seen_ist)}"
        for index, device in enumerate(selected, start=1)
    ) or "1. No affected-device detail was returned."

    if omitted:
        device_lines += (
            f"\n... {omitted} additional affected devices are not printed here. "
            "The complete list remains available in TechAdmin Infrastructure Agent and CSV export."
        )

    description = f"""INFRASTRUCTURE SITE HEALTH ALERT

Site details
- Site: {alert.location_name}
- Match level: {_value(alert.match_level)}
- Priority: {alert.priority}
- Site status: {alert.site_status}
- Site score: {_value(alert.site_score)}
- Site reason: {_value(alert.site_reason)}
- Healthy percentage: {_value(alert.healthy_pct)}
- Total devices: {alert.total_devices}
- Healthy devices: {alert.healthy}
- Critical/down devices: {alert.critical_devices}
- Degraded devices: {alert.degraded}
- Not assessed: {alert.not_assessed}
- Total affected devices in this incident: {alert.affected_count}
- Affected devices listed below: {len(selected)}
- Latest sync completed IST: {_value(alert.sync_completed_ist)}
- Score calculated IST: {_value(alert.score_calculated_ist)}
- Data age: {_value(alert.data_age)}

Affected-device sample
{device_lines}

COPY THE PROMPT BELOW INTO SOLARWINDS CHAT
------------------------------------------------------------
{prompt}
------------------------------------------------------------

This incident was created automatically by TechAdmin Infrastructure Agent from the latest successful ITOM synchronization. Validate current SolarWinds evidence before applying remediation.
""".strip()
    return description, prompt

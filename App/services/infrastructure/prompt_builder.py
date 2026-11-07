# """Build short iEngage text with no device names and one CSV link."""
# from __future__ import annotations

# import os

# from App.services.infrastructure.models import InfrastructureSiteAlert
# from App.services.infrastructure.public_download import create_affected_device_csv_url


# def _value(value: object) -> str:
#     return "Not available" if value in (None, "") else str(value)


# def build_solarwinds_prompt(alert: InfrastructureSiteAlert) -> str:
#     csv_url = create_affected_device_csv_url(alert.location_name)
#     return f"""Investigate this SolarWinds site-health incident.

# Site: {alert.location_name}
# Priority: {alert.priority}
# ITOM-reported status: {alert.site_status}
# ITOM-reported score: {_value(alert.site_score)}
# ITOM-reported reason: {_value(alert.site_reason)}
# Affected SolarWinds devices: {alert.affected_count}
# Critical/down SolarWinds devices: {alert.critical_devices}
# Warning SolarWinds devices: {alert.degraded}
# Affected-device CSV: {csv_url}

# Using current SolarWinds evidence, provide the shared cause or dependency, node/interface/WAN/reachability/latency/packet-loss/power evidence, failure timeline, validation checks, restoration steps, evidence to attach, and data gaps. Do not invent evidence.""".strip()


# def build_ticket_description(alert: InfrastructureSiteAlert) -> tuple[str, str]:
#     csv_url = create_affected_device_csv_url(alert.location_name)
#     prompt = build_solarwinds_prompt(alert)
#     description = f"""INFRASTRUCTURE SITE HEALTH ALERT

# Site: {alert.location_name}
# Priority: {alert.priority}
# ITOM-reported status: {alert.site_status}
# ITOM-reported score: {_value(alert.site_score)}
# ITOM-reported reason: {_value(alert.site_reason)}
# Affected SolarWinds devices: {alert.affected_count}
# Critical/down SolarWinds devices: {alert.critical_devices}
# Warning SolarWinds devices: {alert.degraded}
# Latest sync completed IST: {_value(alert.sync_completed_ist)}

# DOWNLOAD AFFECTED SOLARWINDS DEVICE CSV
# {csv_url}

# COPY INTO SOLARWINDS CHAT
# -------------------------
# {prompt}
# -------------------------
# Created automatically by TechAdmin Infrastructure Agent.""".strip()

#     max_chars = min(
#         4000,
#         max(1000, int(os.getenv("IENGAGE_DESCRIPTION_MAX_CHARS", "3900"))),
#     )
#     if len(description) > max_chars:
#         fixed = f"""INFRASTRUCTURE SITE HEALTH ALERT

# Site: {alert.location_name}
# Priority: {alert.priority}
# ITOM-reported status: {alert.site_status}
# ITOM-reported score: {_value(alert.site_score)}
# ITOM-reported reason: {_value(alert.site_reason)}
# Affected SolarWinds devices: {alert.affected_count}

# DOWNLOAD AFFECTED SOLARWINDS DEVICE CSV
# {csv_url}

# COPY INTO SOLARWINDS CHAT
# -------------------------
# """
#         suffix = "\n-------------------------\nCreated by TechAdmin Infrastructure Agent."
#         description = fixed + prompt[: max(0, max_chars - len(fixed) - len(suffix))] + suffix
#     return description, prompt


"""Build concise iEngage content without affected-device download URLs."""
from __future__ import annotations

import os

from App.services.infrastructure.models import InfrastructureSiteAlert


def _value(value: object) -> str:
    if value in (None, ""):
        return "Not available"

    return str(value)


def build_solarwinds_prompt(
    alert: InfrastructureSiteAlert,
) -> str:
    """Build the prompt copied into SolarWinds Chat.

    Device names and download URLs are intentionally excluded.
    """

    return f"""Investigate this SolarWinds site-health incident.

Site: {alert.location_name}
Priority: {alert.priority}
ITOM-reported status: {alert.site_status}
ITOM-reported score: {_value(alert.site_score)}
ITOM-reported reason: {_value(alert.site_reason)}
Affected SolarWinds devices: {alert.affected_count}
Critical/down SolarWinds devices: {alert.critical_devices}
Warning SolarWinds devices: {alert.degraded}

Using current SolarWinds evidence, provide:

1. The most likely shared cause or dependency.
2. Relevant node, interface, WAN, reachability, latency, packet-loss, and power evidence.
3. The failure timeline and current outage duration where available.
4. Whether the incident is site-wide, WAN-related, device-specific, stale telemetry, or a false positive.
5. Exact validation checks and restoration steps.
6. Evidence that should be attached to the iEngage ticket.
7. Any data gaps.

Do not invent evidence.
""".strip()


def build_ticket_description(
    alert: InfrastructureSiteAlert,
) -> tuple[str, str]:
    """Build a concise iEngage description.

    No device names, localhost URL, production URL, or CSV URL is included.
    """

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

COPY INTO SOLARWINDS CHAT
-------------------------
{prompt}
-------------------------

Created automatically by TechAdmin Infrastructure Agent.
""".strip()

    try:
        max_chars = int(
            os.getenv(
                "IENGAGE_DESCRIPTION_MAX_CHARS",
                "3900",
            )
        )
    except ValueError:
        max_chars = 3900

    max_chars = min(
        4000,
        max(1000, max_chars),
    )

    if len(description) > max_chars:
        fixed_content = f"""INFRASTRUCTURE SITE HEALTH ALERT

Site: {alert.location_name}
Priority: {alert.priority}
ITOM-reported status: {alert.site_status}
ITOM-reported score: {_value(alert.site_score)}
ITOM-reported reason: {_value(alert.site_reason)}
Affected SolarWinds devices: {alert.affected_count}

COPY INTO SOLARWINDS CHAT
-------------------------
"""

        suffix = """
-------------------------

Created automatically by TechAdmin Infrastructure Agent.
"""

        available_prompt_length = (
            max_chars
            - len(fixed_content)
            - len(suffix)
        )

        description = (
            fixed_content
            + prompt[: max(0, available_prompt_length)]
            + suffix
        )

    return description, prompt
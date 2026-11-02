"""Sample ITOM data for UI preview and tests (ITOM_USE_MOCK_DATA=true).

The first 17 sites mirror a real query-2 result; the rest are invented so the
distribution has critical, warning and healthy sites. Device rows are generated
deterministically in the shape of query 1.
"""
from __future__ import annotations

import random
import re
from datetime import datetime, timedelta

# location, status, score, total, healthy, critical, degraded, not_assessed, match_level
_SITES = [
    ("Pune", "warning", 85.3, 2199, 1962, 16, 199, 22, "city"),
    ("Greater Noida / Tower D", "warning", 89.2, 5492, 4851, 15, 558, 68, "building"),
    ("Greater Noida / Tower C", "warning", 89.1, 3384, 3006, 15, 313, 50, "building"),
    ("Greater Noida / Tower A", "warning", 87.5, 457, 435, 15, 7, 0, "building"),
    ("Greater Noida / Tower B", "warning", 92.3, 470, 448, 15, 7, 0, "building"),
    ("Brazil", "critical", 62.3, 667, 366, 13, 288, 0, "country"),
    ("Bengaluru / BPS", "warning", 87.9, 566, 491, 11, 52, 12, "building"),
    ("Bengaluru", "warning", 89.5, 2900, 2655, 11, 200, 34, "city"),
    ("Costa Rica", "warning", 90.2, 1393, 1320, 8, 64, 1, "country"),
    ("United States", "warning", 93.8, 357, 318, 5, 10, 24, "country"),
    ("Mexico", "warning", 90.1, 496, 444, 4, 43, 5, "country"),
    ("Ahmedabad", "critical", 83.1, 251, 230, 4, 17, 0, "city"),
    ("New Jersey", "critical", 76.1, 943, 612, 3, 236, 92, "city"),
    ("Manila", "warning", 91.9, 605, 560, 3, 32, 10, "city"),
    ("Charleston", "warning", 89.9, 159, 142, 2, 7, 8, "city"),
    ("Kolhapur", "critical", 81.1, 223, 168, 1, 47, 7, "city"),
    ("United Kingdom", "critical", 84.1, 74, 63, 1, 6, 4, "country"),
    ("Hyderabad", "critical", 79.4, 812, 640, 9, 150, 13, "city"),
    ("Chennai", "critical", 82.6, 534, 441, 6, 80, 7, "city"),
    ("Noida / Sector 62", "critical", 80.2, 1210, 978, 12, 201, 19, "building"),
    ("Kolkata", "critical", 84.7, 318, 270, 2, 41, 5, "city"),
    ("Mumbai", "critical", 83.9, 702, 590, 5, 98, 9, "city"),
    ("Singapore", "warning", 91.2, 140, 128, 1, 9, 2, "country"),
    ("Australia", "warning", 92.8, 96, 89, 1, 5, 1, "country"),
    ("Dubai", "healthy", 97.6, 88, 86, 0, 2, 0, "city"),
    ("Germany", "healthy", 98.1, 54, 53, 0, 1, 0, "country"),
    ("Canada", "healthy", 96.9, 65, 63, 0, 2, 0, "country"),
    ("South Africa", "healthy", 97.2, 37, 36, 0, 1, 0, "country"),
]

_REASONS = {
    "critical": "A component is below 75%",
    "warning": "Down or Critical nodes need attention",
}

_SOLARWINDS_TYPES = ["Cisco ASA 5555-X", "FortiSwitch 124E", "Windows 2022 Server", "PDM_14P", "Unknown", "Cisco Catalyst 9300"]
_INTUNE_TYPES = ["Windows 11 Laptop", "Windows 10 Laptop", "macOS Laptop"]
_DEVICE_STATUS_ORDER = {"Down": 1, "Critical": 2, "Warning": 3, "NonCompliant": 4}

_SYNC_COMPLETED = datetime(2026, 10, 30, 10, 56, 36)


def _site_code(location: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", location)
    return "".join(word[0] for word in words).upper()[:4] if len(words) > 1 else location[:3].upper()


def _healthy_pct(total: int, healthy: int) -> float:
    return round(100.0 * healthy / total, 1) if total else 0.0


def mock_site_scores() -> list[dict]:
    rows = [
        {
            "location_name": location,
            "site_status": status,
            "site_score": score,
            "total_devices": total,
            "healthy": healthy,
            "critical_devices": critical,
            "degraded": degraded,
            "not_assessed": not_assessed,
            "healthy_pct": _healthy_pct(total, healthy),
        }
        for location, status, score, total, healthy, critical, degraded, not_assessed, _ in _SITES
    ]
    return sorted(rows, key=lambda row: (-row["critical_devices"], row["healthy_pct"]))


def mock_site_alerts() -> list[dict]:
    rng = random.Random(42)
    rows: list[dict] = []
    for location, status, score, _total, _healthy, critical, degraded, _na, match_level in _SITES:
        if status not in _REASONS:
            continue
        code = _site_code(location)
        problem_count = min(critical + max(degraded // 20, 1), 14)
        for index in range(1, problem_count + 1):
            if index <= critical:
                source, device_status = "SOLARWINDS", rng.choice(["Down", "Critical"])
            elif index % 3 == 0:
                source, device_status = "INTUNE", rng.choice(["NonCompliant", "Unknown"])
            else:
                source, device_status = "SOLARWINDS", "Warning"
            if source == "SOLARWINDS":
                ci_type = rng.choice(_SOLARWINDS_TYPES)
                name = f"{code}-{rng.choice(['SW', 'FW', 'RTR', 'SRV', 'AP'])}-{index:02d}"
            else:
                ci_type = rng.choice(_INTUNE_TYPES)
                name = f"CFG-{code}-LT{rng.randint(1000, 9999)}"
            silent_minutes = rng.randint(30, 60 * 24 * 9)
            last_seen = _SYNC_COMPLETED - timedelta(minutes=silent_minutes)
            rows.append(
                {
                    "location_name": location,
                    "match_level": match_level,
                    "site_status": status,
                    "site_score": score,
                    "site_reason": _REASONS[status],
                    "priority": "P1" if status == "critical" else "P2",
                    "source_system": source,
                    "device_name": name,
                    "ci_type": ci_type,
                    "device_status": device_status,
                    "source_location": f"India-{location}" if match_level != "country" else location,
                    "sync_completed_ist": _SYNC_COMPLETED,
                    "score_calculated_ist": _SYNC_COMPLETED + timedelta(seconds=1),
                    "device_last_pulled_ist": _SYNC_COMPLETED - timedelta(minutes=1),
                    "device_last_seen_ist": last_seen,
                    "data_age": "2h 14m",
                    "device_silent_for": f"{silent_minutes // 1440}d {silent_minutes % 1440 // 60}h {silent_minutes % 60}m",
                }
            )
    rows.sort(key=lambda row: (_DEVICE_STATUS_ORDER.get(row["device_status"], 5), row["location_name"], row["source_system"], row["device_name"]))
    return rows

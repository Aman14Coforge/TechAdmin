"""Site score and device alert views for the Infrastructure Agent."""
from __future__ import annotations

from collections import Counter
from typing import Any, Optional

from App.integration.itom.client import ItomReadOnlyClient

SITE_STATUSES = ("critical", "warning", "healthy")
PRIORITY_BY_STATUS = {"critical": "P1", "warning": "P2"}


class InfrastructureService:
    """Combine query 2 (site scores) and query 1 (problem devices)."""

    def __init__(self, client: Optional[ItomReadOnlyClient] = None) -> None:
        self.client = client or ItomReadOnlyClient()

    @property
    def uses_mock_data(self) -> bool:
        return self.client.uses_mock_data

    def site_scores(self) -> list[dict[str, Any]]:
        return self.client.fetch_site_scores()

    def site_alerts(self) -> list[dict[str, Any]]:
        return self.client.fetch_site_alerts()

    @staticmethod
    def summarize(sites: list[dict[str, Any]]) -> dict[str, Any]:
        """Count locations per combined status for the donut chart."""
        counts = Counter(str(site.get("site_status") or "unknown").casefold() for site in sites)
        ordered = {status: counts.get(status, 0) for status in SITE_STATUSES}
        ordered.update({status: count for status, count in counts.items() if status not in ordered})
        return {
            "total_locations": len(sites),
            "by_status": ordered,
            "total_devices": sum(int(site.get("total_devices") or 0) for site in sites),
            "critical_devices": sum(int(site.get("critical_devices") or 0) for site in sites),
            "degraded_devices": sum(int(site.get("degraded") or 0) for site in sites),
        }

    @staticmethod
    def sites_with_status(sites: list[dict[str, Any]], status: str) -> list[dict[str, Any]]:
        wanted = status.casefold()
        return [site for site in sites if str(site.get("site_status") or "").casefold() == wanted]

    @staticmethod
    def devices_for_site(alerts: list[dict[str, Any]], location_name: str) -> list[dict[str, Any]]:
        return [row for row in alerts if row.get("location_name") == location_name]

    @staticmethod
    def data_freshness(alerts: list[dict[str, Any]]) -> dict[str, Any]:
        first = alerts[0] if alerts else {}
        return {
            "sync_completed_ist": first.get("sync_completed_ist"),
            "data_age": first.get("data_age"),
        }

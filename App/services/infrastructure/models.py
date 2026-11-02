"""Infrastructure Agent data contracts."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

@dataclass(frozen=True)
class InfrastructureDevice:
    source_system: str
    device_name: str
    ci_type: str | None
    device_status: str
    source_location: str | None
    device_last_pulled_ist: datetime | None
    device_last_seen_ist: datetime | None
    device_silent_for: str | None

@dataclass
class InfrastructureSiteAlert:
    sync_run_id: str
    location_name: str
    match_level: str | None
    site_status: str
    site_score: float | None
    site_reason: str | None
    priority: str
    sync_completed_ist: datetime | None
    score_calculated_ist: datetime | None
    data_age: str | None
    total_devices: int = 0
    healthy: int = 0
    critical_devices: int = 0
    degraded: int = 0
    not_assessed: int = 0
    healthy_pct: float | None = None
    devices: list[InfrastructureDevice] = field(default_factory=list)

    @property
    def affected_count(self) -> int:
        return len(self.devices)

    def as_dict(self) -> dict[str, Any]:
        return {
            "sync_run_id": self.sync_run_id,
            "location_name": self.location_name,
            "match_level": self.match_level,
            "site_status": self.site_status,
            "site_score": self.site_score,
            "site_reason": self.site_reason,
            "priority": self.priority,
            "sync_completed_ist": self.sync_completed_ist,
            "score_calculated_ist": self.score_calculated_ist,
            "data_age": self.data_age,
            "total_devices": self.total_devices,
            "healthy": self.healthy,
            "critical_devices": self.critical_devices,
            "degraded": self.degraded,
            "not_assessed": self.not_assessed,
            "healthy_pct": self.healthy_pct,
            "affected_count": self.affected_count,
            "devices": [device.__dict__ for device in self.devices],
        }

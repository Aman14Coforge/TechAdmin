"""Device, selected-device and fleet patch analytics from persisted evidence."""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta
from typing import Any

from App.services.patch.ollama_analyzer import OllamaSecurityAnalyzer
from App.services.patch.config import settings
from App.services.patch.security_query_service import SecurityPatchQueryService


class PatchAnalyticsService:
    def __init__(self) -> None:
        self.query = SecurityPatchQueryService()
        self.ai = OllamaSecurityAnalyzer()

    @staticmethod
    def _patch_id(patch: dict[str, Any]) -> str:
        return str(
            patch.get("KB number") or patch.get("Patch name")
            or patch.get("kb_number") or patch.get("patch_name") or "Unknown"
        )

    @staticmethod
    def _release_age(released: Any, snapshot: date) -> int | None:
        if not released:
            return None
        try:
            return (snapshot - date.fromisoformat(str(released)[:10])).days
        except ValueError:
            return None

    def device_report(
        self,
        device_name: str,
        *,
        report_date: date | None = None,
    ) -> dict[str, Any]:
        details = self.query.device_details(device_name)
        snapshots = sorted(
            [item for item in details.get("history", [])
             if not report_date or item["scan_date"] <= report_date.isoformat()],
            key=lambda item: item["scan_date"],
        )
        snapshot_day = report_date or date.today()
        trends = []
        patch_snapshots: list[set[str]] = []
        severity_counts: Counter[str] = Counter()
        release_age_counts: Counter[str] = Counter()
        latest_findings = snapshots[-1].get("patches", []) if snapshots else []
        for snapshot in snapshots:
            trends.append({
                "date": snapshot["scan_date"],
                "missing_patches": int(snapshot.get("missing_patch_count") or 0),
                "risk_score": float(snapshot.get("risk_score") or 0),
            })
            ids = {self._patch_id(item) for item in snapshot.get("patches", [])}
            patch_snapshots.append(ids)
        for patch in latest_findings:
            severity = patch.get("Severity")
            severity_counts["Unknown" if severity is None else str(severity)] += 1
            age = self._release_age(patch.get("Released"), snapshot_day)
            age_bucket = (
                "Unknown release date" if age is None else
                "0-30 days" if age <= 30 else
                "31-90 days" if age <= 90 else ">90 days"
            )
            release_age_counts[age_bucket] += 1

        first_count = trends[0]["missing_patches"] if trends else 0
        latest_count = trends[-1]["missing_patches"] if trends else 0
        previous_ids = patch_snapshots[-2] if len(patch_snapshots) > 1 else set()
        latest_ids = patch_snapshots[-1] if patch_snapshots else set()
        added = sorted(latest_ids - previous_ids)
        cleared = sorted(previous_ids - latest_ids)
        persistent = sorted(set.intersection(*patch_snapshots)) if patch_snapshots else []
        evidence = {
            "device": {
                key: details.get(key) for key in (
                    "device_name", "discovery_id", "active", "first_seen_date",
                    "last_seen_date", "days_open", "ticket_status", "ticket_reference",
                )
            },
            "snapshot": snapshot_day.isoformat(),
            "summary": {
                "snapshots": len(snapshots),
                "current_missing": latest_count,
                "unique_current_patches": len(latest_ids),
                "missing_change_since_first_snapshot": latest_count - first_count,
                "direction": (
                    "insufficient_data" if len(trends) < 2 else
                    "improving" if latest_count < first_count else
                    "worsening" if latest_count > first_count else "unchanged"
                ),
                "new_since_previous_snapshot": len(added),
                "cleared_since_previous_snapshot": len(cleared),
                "persistent_across_all_snapshots": len(persistent),
            },
            "trend": trends,
            "latest_severity_counts": dict(severity_counts),
            "latest_release_age_counts": dict(release_age_counts),
            "new_patch_ids_since_previous": added[:50],
            "cleared_patch_ids_since_previous": cleared[:50],
            "persistent_patch_ids": persistent[:50],
            "latest_patch_sample": latest_findings[:100],
            "history": snapshots,
            "data_limitations": [
                "Changes compare stored Ivanti snapshots only; no deployment success, reboot, or causality is inferred."
            ],
        }
        prompt_evidence = {
            **evidence,
            "history": [
                {key: value for key, value in snapshot.items() if key != "patches"}
                for snapshot in snapshots
            ],
            "latest_patch_sample": latest_findings[:60],
        }
        return {
            "report_type": "device",
            "evidence": evidence,
            "ai": self.ai.analyze(prompt_evidence, report_type="device"),
        }

    def fleet_report(
        self,
        *,
        report_date: date,
        device_names: list[str] | None = None,
    ) -> dict[str, Any]:
        if not device_names:
            evidence = self.query.fleet_report_evidence(report_date)
            ai = self.ai.analyze(evidence, report_type="fleet")
            return {"report_type": "fleet", "evidence": evidence, "ai": ai}

        # Selected reports load histories only for requested devices.
        requested = list(dict.fromkeys(
            str(name).strip() for name in device_names if str(name).strip()
        ))
        rows: list[dict[str, Any]] = []
        details_by_name: dict[str, dict[str, Any]] = {}
        errors: list[dict[str, str]] = []
        for name in requested:
            try:
                details = self.query.device_details(name)
                details_by_name[details["device_name"].upper()] = details
                snapshots = [
                    item for item in details.get("history", [])
                    if item["scan_date"] <= report_date.isoformat()
                ]
                latest = snapshots[-1] if snapshots else None
                if latest:
                    rows.append({
                        "device_name": details["device_name"],
                        "discovery_id": details["discovery_id"],
                        "ip_address": latest.get("ip_address"),
                        "os_name": latest.get("os_name"),
                        "missing_patch_count": int(latest.get("missing_patch_count") or 0),
                        "risk_score": latest.get("risk_score"),
                        "consecutive_days": details.get("days_open"),
                        "ticket_status": details.get("ticket_status"),
                        "ticket_reference": details.get("ticket_reference"),
                        "ticket_eligible": bool(
                            details.get("active")
                            and int(details.get("days_open") or 0) >= settings.days
                            and int(latest.get("missing_patch_count") or 0) > 0
                        ),
                        "latest_patches": latest.get("patches", []),
                    })
                else:
                    errors.append({"device_name": name, "error": f"No snapshot on or before {report_date.isoformat()}"})
            except Exception as exc:
                errors.append({"device_name": name, "error": f"{type(exc).__name__}: {exc}"})

        patch_devices: dict[str, set[str]] = defaultdict(set)
        severity_counts: Counter[str] = Counter()
        release_age_counts: Counter[str] = Counter()
        for row in rows:
            for patch in row["latest_patches"]:
                patch_devices[self._patch_id(patch)].add(row["device_name"])
                severity = patch.get("Severity")
                severity_counts["Unknown" if severity is None else str(severity)] += 1
                age = self._release_age(patch.get("Released"), report_date)
                release_age_counts[
                    "Unknown release date" if age is None else
                    "0-30 days" if age <= 30 else
                    "31-90 days" if age <= 90 else ">90 days"
                ] += 1

        priority = sorted(
            rows,
            key=lambda row: (
                float(row.get("risk_score") or 0),
                int(row.get("missing_patch_count") or 0),
                int(row.get("consecutive_days") or 0),
            ),
            reverse=True,
        )
        patch_exposure = [
            {"patch": patch, "affected_devices": len(affected)}
            for patch, affected in sorted(
                patch_devices.items(), key=lambda item: len(item[1]), reverse=True
            )[:30]
        ]
        evidence = {
            "scope": "selected_devices",
            "snapshot": report_date.isoformat(),
            "summary": {
                "devices": len(rows),
                "total_missing_instances": sum(row["missing_patch_count"] for row in rows),
                "ticket_eligible": sum(bool(row["ticket_eligible"]) for row in rows),
                "high_risk_devices": sum(float(row.get("risk_score") or 0) >= 80 for row in rows),
                "persistent_14_day_devices": sum(bool(row["ticket_eligible"]) for row in rows),
            },
            "priority_devices": [
                {key: row.get(key) for key in (
                    "device_name", "missing_patch_count", "risk_score",
                    "consecutive_days", "ticket_status", "ticket_reference",
                )}
                for row in priority[:30]
            ],
            "top_missing_patches": patch_exposure,
            "severity": dict(severity_counts),
            "release_age": dict(release_age_counts),
            "devices": rows,
            "data_errors": errors,
            "unavailable_devices": [error["device_name"] for error in errors],
            "data_limitations": [
                "Counts describe only the selected devices; patch detail is based on each selected device's latest stored snapshot on or before the requested date."
            ],
        }
        ai = self.ai.analyze(evidence, report_type="multi_device")
        return {"report_type": "multi_device", "evidence": evidence, "ai": ai}

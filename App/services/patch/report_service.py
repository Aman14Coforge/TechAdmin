from __future__ import annotations

import json
from collections import Counter
from datetime import date
from html import escape
from typing import Any

from sqlalchemy import select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceObservation, PatchDeviceState, PatchFinding


class PatchReportService:
    def build(
        self,
        *,
        start_date: date,
        end_date: date,
        device_name: str | None = None,
        patch_query: str | None = None,
        include_resolved: bool = True,
        compliance_category: str | None = None,
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            query = (
                select(PatchDeviceObservation, PatchDeviceState)
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id,
                )
                .where(PatchDeviceObservation.scan_date.between(start_date, end_date))
            )
            if device_name:
                query = query.where(PatchDeviceObservation.device_name.ilike(f"%{device_name}%"))
            if not include_resolved:
                query = query.where(PatchDeviceState.is_active.is_(True))
            if compliance_category:
                query = query.where(
                    PatchDeviceObservation.compliance_category == compliance_category
                )
            pairs = db.execute(
                query.order_by(
                    PatchDeviceObservation.scan_date.desc(),
                    PatchDeviceObservation.missing_patch_count.desc(),
                )
            ).all()

            allowed = {(observation.scan_date, observation.discovery_id) for observation, _ in pairs}
            finding_query = select(PatchFinding).where(
                PatchFinding.scan_date.between(start_date, end_date),
                PatchFinding.evidence_type == "CONFIRMED_MISSING",
            )
            if patch_query:
                finding_query = finding_query.where(
                    PatchFinding.patch_name.ilike(f"%{patch_query}%")
                )
            findings = [
                finding
                for finding in db.scalars(finding_query).all()
                if (finding.scan_date, finding.discovery_id) in allowed
            ]

        patch_counts = Counter(
            finding.patch_name or finding.kb_number or "Unknown patch"
            for finding in findings
        )
        devices: list[dict[str, Any]] = []
        for observation, state in pairs:
            device_findings = [
                finding
                for finding in findings
                if finding.scan_date == observation.scan_date
                and finding.discovery_id == observation.discovery_id
            ]
            if patch_query and not device_findings:
                continue
            devices.append(
                {
                    "scan_date": observation.scan_date.isoformat(),
                    "device_name": observation.device_name,
                    "discovery_id": observation.discovery_id,
                    "ip_address": observation.ip_address,
                    "os_name": observation.os_name,
                    "missing_patch_count": observation.missing_patch_count,
                    "risk_score": observation.risk_score,
                    "last_scanned_at": (
                        observation.last_scanned_at.isoformat()
                        if observation.last_scanned_at
                        else None
                    ),
                    "scan_age_days": observation.scan_age_days,
                    "freshness_status": observation.freshness_status,
                    "compliance_category": observation.compliance_category,
                    "inclusion_reason": observation.inclusion_reason,
                    "assigned_policy": observation.assigned_policy,
                    "management_sources": observation.management_sources or [],
                    "persistent_14_days": state.persistent_14_days,
                    "observed_successful_snapshots": state.successful_snapshot_days_14,
                    "required_successful_snapshots": state.required_snapshot_days_14,
                    "first_seen_date": state.first_seen_date.isoformat(),
                    "last_seen_date": state.last_seen_date.isoformat(),
                    "days_open": state.consecutive_days,
                    "active": state.is_active,
                    "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
                    "ticket_status": state.ticket_status,
                    "ticket_reference": state.ticket_reference,
                    "critical_missing": state.security_critical,
                    "important_missing": state.security_important,
                    "exploited_missing": state.exploited_missing_patches,
                    "patches": [
                        {
                            "name": finding.patch_name,
                            "kb": finding.kb_number,
                            "severity": finding.severity,
                            "released_at": (
                                finding.released_at.isoformat()
                                if finding.released_at
                                else None
                            ),
                        }
                        for finding in device_findings
                    ],
                }
            )

        unique = {item["discovery_id"] for item in devices}
        return {
            "period": {"start": start_date.isoformat(), "end": end_date.isoformat()},
            "summary": {
                "observations": len(devices),
                "unique_devices": len(unique),
                "missing_patch_instances": sum(item["missing_patch_count"] for item in devices),
                "active_fresh": len(
                    {
                        item["discovery_id"]
                        for item in devices
                        if item["compliance_category"] == "ACTIVE_NON_COMPLIANT"
                    }
                ),
                "persistent_14_days": len(
                    {
                        item["discovery_id"]
                        for item in devices
                        if item["persistent_14_days"]
                    }
                ),
                "stale_reporting": len(
                    {
                        item["discovery_id"]
                        for item in devices
                        if item["compliance_category"] == "STALE_REPORTING"
                    }
                ),
                "unknown_freshness": len(
                    {
                        item["discovery_id"]
                        for item in devices
                        if item["compliance_category"] == "UNKNOWN_FRESHNESS"
                    }
                ),
                "resolved_devices": len(
                    {item["discovery_id"] for item in devices if not item["active"]}
                ),
            },
            "top_missing_patches": [
                {"patch": patch, "occurrences": count}
                for patch, count in patch_counts.most_common(20)
            ],
            "devices": devices,
        }

    @staticmethod
    def to_json(report: dict[str, Any]) -> bytes:
        return json.dumps(report, indent=2, ensure_ascii=False).encode()

    @staticmethod
    def to_html(report: dict[str, Any]) -> bytes:
        summary = report["summary"]
        rows = "".join(
            "<tr>"
            f"<td>{escape(item['scan_date'])}</td>"
            f"<td>{escape(item['device_name'])}</td>"
            f"<td>{escape(item['compliance_category'])}</td>"
            f"<td>{item['missing_patch_count']}</td>"
            f"<td>{escape(str(item['last_scanned_at'] or 'Unknown'))}</td>"
            f"<td>{item['observed_successful_snapshots']}/14</td>"
            f"<td>{escape(item['ticket_reference'] or '')}</td>"
            "</tr>"
            for item in report["devices"]
        )
        return f"""<!doctype html><html><head><meta charset='utf-8'><style>
        body{{font-family:Segoe UI;color:#1B2433;margin:36px}}.cards{{display:flex;gap:12px;flex-wrap:wrap}}
        .card{{border:1px solid #e6e9ef;border-radius:12px;padding:14px 18px}}
        table{{border-collapse:collapse;width:100%;margin-top:20px}}th,td{{border-bottom:1px solid #eee;padding:9px;text-align:left}}
        </style></head><body><h1>Ivanti Patch Compliance Report</h1>
        <p>{report['period']['start']} to {report['period']['end']}</p><div class='cards'>
        <div class='card'>Active fresh<br><b>{summary['active_fresh']}</b></div>
        <div class='card'>Persistent 14/14<br><b>{summary['persistent_14_days']}</b></div>
        <div class='card'>Stale reporting<br><b>{summary['stale_reporting']}</b></div>
        <div class='card'>Unknown freshness<br><b>{summary['unknown_freshness']}</b></div>
        <div class='card'>Resolved<br><b>{summary['resolved_devices']}</b></div></div>
        <h2>Device observations</h2><table><tr><th>Date</th><th>Device</th><th>Category</th>
        <th>Missing</th><th>Last scanned</th><th>14-day evidence</th><th>Ticket</th></tr>{rows}</table>
        </body></html>""".encode()

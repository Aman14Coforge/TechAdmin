"""Evidence-grounded deterministic analytics plus Ollama interpretation."""
from __future__ import annotations

import json
from collections import Counter
from datetime import date, datetime
from html import escape
from typing import Any

from langchain_ollama import ChatOllama
from sqlalchemy import select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceState, PatchFinding
from App.services.patch.config import settings
from App.services.patch.security_query_service import SecurityPatchQueryService

ANALYSIS_PROMPT = """
You are a senior endpoint-security and Ivanti operations analyst.
Analyze only the supplied evidence. Never invent patch names, root causes,
deployment attempts, return codes, reboot status, CVEs, disk state, user logons,
or remediation outcomes.

Return JSON only:
{
  "executive_summary": "",
  "compliance_assessment": {
    "direction": "improving|worsening|unchanged|insufficient_data",
    "confidence": "high|medium|limited",
    "explanation": ""
  },
  "risk_assessment": {"level": "critical|high|medium|low|unknown", "explanation": ""},
  "notable_findings": [],
  "persistent_patch_findings": [],
  "release_age_findings": [],
  "operational_hypotheses": [
    {"hypothesis": "", "status": "requires_verification", "evidence_needed": []}
  ],
  "recommended_checks": [],
  "prioritized_actions": [],
  "ticket_recommendation": {"recommended": false, "reason": ""},
  "data_limitations": []
}
Evidence: {evidence}
"""


def _parse_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _percentage_change(first: int, current: int) -> float | None:
    if first == 0:
        return None
    return round(((current - first) / first) * 100, 2)


class SecurityReportService:
    def _ai_analysis(self, evidence: dict[str, Any]) -> dict[str, Any]:
        fallback = {
            "executive_summary": (
                "The evidence package was generated, but AI interpretation was unavailable."
            ),
            "compliance_assessment": {
                "direction": evidence.get("analytics", {}).get(
                    "compliance_direction", "insufficient_data"
                ),
                "confidence": evidence.get("analytics", {}).get(
                    "data_confidence", "limited"
                ),
                "explanation": "Review the deterministic analytics and evidence tabs.",
            },
            "risk_assessment": {
                "level": "unknown",
                "explanation": "Risk could not be interpreted by the configured model.",
            },
            "notable_findings": [],
            "persistent_patch_findings": [],
            "release_age_findings": [],
            "operational_hypotheses": [],
            "recommended_checks": [],
            "prioritized_actions": [],
            "ticket_recommendation": {"recommended": False, "reason": ""},
            "data_limitations": evidence.get("analytics", {}).get(
                "data_limitations", []
            ),
        }
        try:
            response = ChatOllama(
                model=settings.ai_model,
                base_url=settings.ollama_host,
                temperature=0,
                format="json",
            ).invoke(
                ANALYSIS_PROMPT.format(
                    evidence=json.dumps(evidence, ensure_ascii=False, default=str)
                )
            )
            parsed = json.loads(response.content)
            return parsed if isinstance(parsed, dict) else fallback
        except Exception:
            return fallback

    def device_report(
        self,
        device_name: str,
        *,
        include_ai: bool = True,
    ) -> dict[str, Any]:
        device = SecurityPatchQueryService().device_details(device_name)
        history = sorted(device.get("history") or [], key=lambda item: item["scan_date"])

        severity_distribution: Counter[str] = Counter()
        recurring_patches: Counter[str] = Counter()
        patch_first_seen: dict[str, str] = {}
        patch_last_seen: dict[str, str] = {}
        trend: list[dict[str, Any]] = []
        current_patches: list[dict[str, Any]] = []
        release_records: dict[str, dict[str, Any]] = {}

        for snapshot in history:
            trend.append(
                {
                    "Date": snapshot["scan_date"],
                    "Missing patches": int(snapshot.get("missing_patch_count") or 0),
                    "Risk score": float(snapshot.get("risk_score") or 0),
                }
            )
            for patch in snapshot.get("patches") or []:
                identity = str(
                    patch.get("Patch name")
                    or patch.get("patch_name")
                    or patch.get("KB number")
                    or patch.get("kb_number")
                    or "Unknown patch"
                )
                recurring_patches[identity] += 1
                patch_first_seen.setdefault(identity, snapshot["scan_date"])
                patch_last_seen[identity] = snapshot["scan_date"]
                severity = str(
                    patch.get("Severity") or patch.get("severity") or "Unknown"
                )
                severity_distribution[severity] += 1
                release_value = patch.get("Released") or patch.get("released_at")
                release_date = _parse_date(release_value)
                release_records[identity] = {
                    "Patch": identity,
                    "KB number": patch.get("KB number") or patch.get("kb_number"),
                    "Severity": severity,
                    "Release date": release_date.isoformat() if release_date else None,
                }

        if history:
            current_patches = list(history[-1].get("patches") or [])

        first_count = int(history[0].get("missing_patch_count") or 0) if history else 0
        current_count = int(history[-1].get("missing_patch_count") or 0) if history else 0
        change = current_count - first_count
        if len(history) < 2:
            direction = "insufficient_data"
        elif change < 0:
            direction = "improving"
        elif change > 0:
            direction = "worsening"
        else:
            direction = "unchanged"

        today = date.today()
        release_age_buckets = {
            "0-7 days": 0,
            "8-30 days": 0,
            "31-90 days": 0,
            "More than 90 days": 0,
            "Release date unavailable": 0,
        }
        oldest_patch = None
        newest_patch = None
        released_patch_rows = []

        for record in release_records.values():
            release_date = _parse_date(record.get("Release date"))
            row = dict(record)
            if not release_date:
                release_age_buckets["Release date unavailable"] += 1
                row["Age days"] = None
            else:
                age = max(0, (today - release_date).days)
                row["Age days"] = age
                if age <= 7:
                    release_age_buckets["0-7 days"] += 1
                elif age <= 30:
                    release_age_buckets["8-30 days"] += 1
                elif age <= 90:
                    release_age_buckets["31-90 days"] += 1
                else:
                    release_age_buckets["More than 90 days"] += 1
                if oldest_patch is None or age > oldest_patch["Age days"]:
                    oldest_patch = row
                if newest_patch is None or age < newest_patch["Age days"]:
                    newest_patch = row
            released_patch_rows.append(row)

        persistence_rows = []
        for patch_name, count in recurring_patches.most_common():
            persistence_rows.append(
                {
                    "Patch": patch_name,
                    "Snapshots affected": count,
                    "First observed": patch_first_seen.get(patch_name),
                    "Last observed": patch_last_seen.get(patch_name),
                    "Still in latest snapshot": any(
                        patch_name
                        == str(
                            patch.get("Patch name")
                            or patch.get("patch_name")
                            or patch.get("KB number")
                            or patch.get("kb_number")
                            or "Unknown patch"
                        )
                        for patch in current_patches
                    ),
                }
            )

        snapshot_count = len(history)
        confidence = "high" if snapshot_count >= 7 else "medium" if snapshot_count >= 3 else "limited"
        data_limitations = []
        if snapshot_count < 3:
            data_limitations.append(
                "Fewer than three stored snapshots are available, so trend confidence is limited."
            )
        if not severity_distribution:
            data_limitations.append("Detailed patch severity evidence is unavailable.")
        if release_age_buckets["Release date unavailable"]:
            data_limitations.append("Some missing patches have no stored release date.")
        data_limitations.extend(
            [
                "Ivanti deployment attempts and return codes are not stored in this dataset.",
                "Endpoint pending-reboot state is not stored in this dataset.",
                "Disk capacity and Windows Update service state are not stored in this dataset.",
                "User sign-in and shutdown events are not stored in this dataset.",
                "Patch policy assignment, approval, exclusion, and deferral evidence are not stored.",
            ]
        )

        analytics = {
            "compliance_direction": direction,
            "first_missing_count": first_count,
            "current_missing_count": current_count,
            "missing_count_change": change,
            "percentage_change": _percentage_change(first_count, current_count),
            "data_confidence": confidence,
            "release_age_buckets": release_age_buckets,
            "oldest_missing_patch": oldest_patch,
            "newest_missing_patch": newest_patch,
            "data_limitations": data_limitations,
        }
        summary = {
            "snapshots": snapshot_count,
            "current_missing_patches": current_count,
            "unique_missing_patches": len(recurring_patches),
            "days_open": device.get("days_open") or 0,
        }
        evidence = {
            "device": {
                "device_name": device.get("device_name"),
                "discovery_id": device.get("discovery_id"),
                "active": device.get("active"),
                "first_seen_date": device.get("first_seen_date"),
                "last_seen_date": device.get("last_seen_date"),
                "ticket_status": device.get("ticket_status"),
                "ticket_reference": device.get("ticket_reference"),
            },
            "summary": summary,
            "analytics": analytics,
            "severity_distribution": dict(severity_distribution),
            "trend": trend,
            "persistent_patches": persistence_rows[:30],
            "current_patch_sample": current_patches[:100],
        }

        return {
            **device,
            "report_type": "device",
            "summary": summary,
            "analytics": analytics,
            "trend": trend,
            "severity_distribution": dict(severity_distribution),
            "release_age_buckets": release_age_buckets,
            "release_age_details": released_patch_rows,
            "persistent_patches": persistence_rows,
            "current_patches": current_patches,
            "ai_analysis": self._ai_analysis(evidence) if include_ai else None,
        }

    def patch_report(
        self,
        patch_query: str,
        *,
        start_date: date | None = None,
        end_date: date | None = None,
        include_ai: bool = True,
    ) -> dict[str, Any]:
        query_text = str(patch_query or "").strip()
        if not query_text:
            raise ValueError("Patch name or KB number is required.")

        with SessionLocal() as db:
            query = (
                select(PatchFinding, PatchDeviceState)
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchFinding.discovery_id,
                )
                .where(
                    PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    (
                        PatchFinding.patch_name.ilike(f"%{query_text}%")
                        | PatchFinding.kb_number.ilike(f"%{query_text}%")
                    ),
                )
            )
            if start_date:
                query = query.where(PatchFinding.scan_date >= start_date)
            if end_date:
                query = query.where(PatchFinding.scan_date <= end_date)
            pairs = db.execute(
                query.order_by(PatchFinding.scan_date.desc())
            ).all()

        observations = []
        latest_by_device = {}
        severity_distribution: Counter[str] = Counter()
        for finding, state in pairs:
            row = {
                "scan_date": finding.scan_date.isoformat(),
                "device_name": finding.device_name,
                "patch_name": finding.patch_name,
                "kb_number": finding.kb_number,
                "severity": finding.severity,
                "vendor": finding.vendor_name,
                "released_at": (
                    finding.released_at.isoformat() if finding.released_at else None
                ),
                "device_active": state.is_active,
                "days_open": state.consecutive_days,
                "ticket_status": state.ticket_status,
                "ticket_reference": state.ticket_reference,
            }
            observations.append(row)
            latest_by_device.setdefault(finding.discovery_id, row)
            severity_distribution[str(finding.severity or "Unknown")] += 1

        devices = list(latest_by_device.values())
        active = sum(bool(row["device_active"]) for row in devices)
        summary = {
            "affected_devices": len(devices),
            "active_affected_devices": active,
            "resolved_affected_devices": len(devices) - active,
            "historical_observations": len(observations),
        }
        evidence = {
            "patch_query": query_text,
            "summary": summary,
            "severity_distribution": dict(severity_distribution),
            "devices": devices[:200],
        }
        return {
            "report_type": "patch",
            "patch_query": query_text,
            "period": {
                "start": start_date.isoformat() if start_date else None,
                "end": end_date.isoformat() if end_date else None,
            },
            "summary": summary,
            "severity_distribution": dict(severity_distribution),
            "devices": devices,
            "observations": observations,
            "ai_analysis": self._ai_analysis(evidence) if include_ai else None,
        }

    @staticmethod
    def to_json(report: dict[str, Any]) -> bytes:
        return json.dumps(report, indent=2, ensure_ascii=False, default=str).encode("utf-8")

    @staticmethod
    def to_html(report: dict[str, Any]) -> bytes:
        title = (
            "Device patch intelligence report"
            if report.get("report_type") == "device"
            else "Patch impact intelligence report"
        )
        analysis = report.get("ai_analysis") or {}
        summary_cards = "".join(
            f"<div class='card'><span>{escape(str(key).replace('_', ' ').title())}</span>"
            f"<b>{escape(str(value))}</b></div>"
            for key, value in report.get("summary", {}).items()
        )
        findings = "".join(
            f"<li>{escape(str(value))}</li>"
            for value in analysis.get("notable_findings", [])
        )
        actions = "".join(
            f"<li>{escape(str(value))}</li>"
            for value in analysis.get("prioritized_actions", [])
        )
        html = f"""<!doctype html>
<html><head><meta charset='utf-8'><style>
body{{font-family:Segoe UI,Arial;margin:36px;color:#172033}}
.cards{{display:flex;flex-wrap:wrap;gap:12px;margin:20px 0}}
.card{{border:1px solid #dde3ea;border-radius:12px;padding:14px 18px}}
.card span{{display:block;color:#667085;font-size:12px}}.card b{{font-size:20px}}
section{{margin:24px 0}} h1,h2{{color:#10283f}}
</style></head><body>
<h1>{escape(title)}</h1><div class='cards'>{summary_cards}</div>
<section><h2>Executive summary</h2><p>{escape(str(analysis.get('executive_summary') or ''))}</p></section>
<section><h2>Risk assessment</h2><p>{escape(str((analysis.get('risk_assessment') or {{}}).get('explanation') or ''))}</p></section>
<section><h2>Notable findings</h2><ul>{findings}</ul></section>
<section><h2>Prioritized actions</h2><ul>{actions}</ul></section>
</body></html>"""
        return html.encode("utf-8")

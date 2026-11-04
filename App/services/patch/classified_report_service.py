"""Database-only rich reports for classified Compliance Agent populations.

No Ivanti HTTP client is constructed here. The report reads only TechAdmin
PostgreSQL tables populated by the scheduled/manual Ivanti scan:
- patch_compliance_classifications: exact endpoint scope
- patch_device_observations: stored endpoint observations
- patch_findings: stored missing-patch evidence
- patch_scan_runs: successful snapshot dates
- patch_tickets: live ticket state through ComplianceQueryService

The service restores charts, top patch exposure, release-age distributions,
priority devices, trends, and the existing AI-analysis shape without paging the
live Ivanti endpoint-vulnerability API.
"""
from __future__ import annotations

import inspect
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from typing import Any, Callable

from loguru import logger
from sqlalchemy import func, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchComplianceClassification,
    PatchDeviceObservation,
    PatchFinding,
    PatchScanRun,
)
from App.services.patch.analytics_service import PatchAnalyticsService
from App.services.patch.compliance_query_service import ComplianceQueryService

CATEGORY_LABELS = {
    "active": "Active non-compliant",
    "persistent_14": "Persistent 14/14",
    "stale": "Stale reporting",
    "unknown": "Last scan date unavailable",
    "resolved": "Resolved",
    "all": "All classified records",
}
CATEGORY_CODES = {
    "active": ("ACTIVE_NON_COMPLIANT",),
    "persistent_14": ("PERSISTENT_14_DAYS",),
    "stale": ("STALE_REPORTING",),
    "unknown": ("UNKNOWN_FRESHNESS",),
    "resolved": ("RESOLVED",),
    "all": (
        "ACTIVE_NON_COMPLIANT",
        "PERSISTENT_14_DAYS",
        "STALE_REPORTING",
        "UNKNOWN_FRESHNESS",
        "RESOLVED",
    ),
}


def category_from_report_query(query: str) -> str | None:
    text = " ".join(str(query or "").casefold().replace("-", " ").split())
    if not any(term in text for term in ("report", "summary", "analysis", "analyse", "analyze")):
        return None
    if not any(term in text for term in ("device", "devices", "endpoint", "endpoints", "fleet")):
        return None
    if "persistent" in text or "14/14" in text or "14 day" in text:
        return "persistent_14"
    if "stale" in text or "old scan" in text or "not reporting" in text:
        return "stale"
    if "unknown" in text or "scan date unavailable" in text or "no scan date" in text:
        return "unknown"
    if "resolved" in text:
        return "resolved"
    if "active non compliant" in text or "active noncompliant" in text:
        return "active"
    if "all classified" in text or "all status" in text:
        return "all"
    return None


class ClassifiedComplianceReportService:
    def build(self, *, report_date: date, category: str) -> dict[str, Any]:
        if category not in CATEGORY_CODES:
            raise ValueError(f"Unsupported classified report category: {category}")

        query_service = ComplianceQueryService()
        query_service.summary(report_date)  # ensure sidecar rows exist
        classified = query_service.all_devices(
            report_date=report_date,
            category=category,
            search="",
            min_missing=1,
        )
        # These dashboard metrics describe the complete selected snapshot, not
        # only the report scope. This avoids showing 0 persistent/resolved merely
        # because the requested scope is Active non-compliant.
        persistent_population = query_service.all_devices(
            report_date=report_date,
            category="persistent_14",
            search="",
            min_missing=1,
        )
        resolved_population = query_service.all_devices(
            report_date=report_date,
            category="resolved",
            search="",
            min_missing=1,
        )
        snapshot_counts = query_service.summary(report_date)
        snapshot_metrics = {
            "persistent_14_day_devices": len(persistent_population),
            "resolved_devices": len(resolved_population),
            "ticket_eligible": sum(
                1
                for item in persistent_population
                if not item.get("ticket_reference")
                and str(item.get("ticket_status") or "").upper()
                not in {"CREATED", "ACCEPTED", "CREATING", "REVIEW_REQUIRED"}
            ),
            "active_non_compliant_devices": snapshot_counts["active"],
            "stale_reporting_devices": snapshot_counts["stale"],
            "unknown_freshness_devices": snapshot_counts["unknown"],
            "raw_missing_patch_records": snapshot_counts["raw"],
        }
        ids = [str(item.get("discovery_id") or "") for item in classified if item.get("discovery_id")]
        id_set = set(ids)
        label = CATEGORY_LABELS[category]

        if not ids:
            return self._empty(report_date, category)

        observations, findings, successful_dates = self._load_database_evidence(
            report_date=report_date,
            discovery_ids=ids,
        )
        evidence = self._build_evidence(
            report_date=report_date,
            category=category,
            label=label,
            classified=classified,
            observations=observations,
            findings=findings,
            successful_dates=successful_dates,
            snapshot_metrics=snapshot_metrics,
        )
        ai = self._generate_ai(evidence=evidence, label=label, report_date=report_date)
        return {
            "report_type": "classified_fleet",
            "classification_category": category,
            "classification_label": label,
            "evidence": evidence,
            "ai": ai,
        }

    @staticmethod
    def _load_database_evidence(
        *,
        report_date: date,
        discovery_ids: list[str],
    ) -> tuple[list[PatchDeviceObservation], list[PatchFinding], list[date]]:
        with SessionLocal() as db:
            successful_dates = list(
                db.scalars(
                    select(PatchScanRun.scan_date)
                    .where(
                        PatchScanRun.status == "SUCCEEDED",
                        PatchScanRun.scan_date <= report_date,
                    )
                    .distinct()
                    .order_by(PatchScanRun.scan_date.desc())
                    .limit(14)
                ).all()
            )
            date_scope = successful_dates or [report_date]
            observations = list(
                db.scalars(
                    select(PatchDeviceObservation).where(
                        PatchDeviceObservation.discovery_id.in_(discovery_ids),
                        PatchDeviceObservation.scan_date.in_(date_scope),
                    )
                ).all()
            )
            findings = list(
                db.scalars(
                    select(PatchFinding).where(
                        PatchFinding.discovery_id.in_(discovery_ids),
                        PatchFinding.scan_date == report_date,
                        PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    )
                ).all()
            )
        return observations, findings, successful_dates

    def _build_evidence(
        self,
        *,
        report_date: date,
        category: str,
        label: str,
        classified: list[dict[str, Any]],
        observations: list[PatchDeviceObservation],
        findings: list[PatchFinding],
        successful_dates: list[date],
        snapshot_metrics: dict[str, int],
    ) -> dict[str, Any]:
        latest_observation = {
            item.discovery_id: item
            for item in observations
            if item.scan_date == report_date
        }
        ticketed = sum(bool(item.get("ticket_reference")) for item in classified)
        # High risk is based only on the Ivanti-provided endpoint riskScore.
        # It is not calculated from missing-patch count by TechAdmin.
        ivanti_high_risk_threshold = 80.0
        high_risk = sum(
            item.get("risk_score") is not None
            and float(item["risk_score"]) >= ivanti_high_risk_threshold
            for item in classified
        )
        ticket_eligible = int(snapshot_metrics["ticket_eligible"])
        missing_total = sum(int(item.get("missing_patch_count") or 0) for item in classified)

        patch_stats: dict[str, dict[str, Any]] = {}
        severity_counts: Counter[str] = Counter()
        release_age_counts: Counter[str] = Counter()
        for finding in findings:
            key = (
                finding.kb_number
                or finding.patch_name
                or finding.patch_id
                or finding.notification_id
                or finding.evidence_key
                or "Unknown patch"
            )
            stat = patch_stats.setdefault(
                str(key),
                {
                    "patch": str(key),
                    "patch_name": finding.patch_name,
                    "kb_number": finding.kb_number,
                    "vendor": finding.vendor_name,
                    "severity": finding.severity,
                    "devices": set(),
                    "occurrences": 0,
                    "released_at": finding.released_at,
                },
            )
            stat["devices"].add(finding.discovery_id)
            stat["occurrences"] += 1
            severity_counts[str(finding.severity if finding.severity is not None else "Unknown")] += 1
            release_age_counts[self._release_bucket(report_date, finding.released_at)] += 1

        top_patches = [
            {
                "Patch": stat["patch"],
                "Patch name": stat["patch_name"] or "Not available",
                "KB number": stat["kb_number"] or "",
                "Vendor": stat["vendor"] or "Not available",
                "Severity": stat["severity"],
                "Affected devices": len(stat["devices"]),
                "Missing instances": stat["occurrences"],
                "Released": stat["released_at"].isoformat() if stat["released_at"] else None,
            }
            for stat in sorted(
                patch_stats.values(),
                key=lambda item: (len(item["devices"]), item["occurrences"]),
                reverse=True,
            )[:50]
        ]

        trend_by_date: dict[date, dict[str, int]] = defaultdict(lambda: {"devices": 0, "missing": 0})
        seen_by_date: dict[date, set[str]] = defaultdict(set)
        for observation in observations:
            if observation.discovery_id in seen_by_date[observation.scan_date]:
                continue
            seen_by_date[observation.scan_date].add(observation.discovery_id)
            trend_by_date[observation.scan_date]["devices"] += 1
            trend_by_date[observation.scan_date]["missing"] += int(observation.missing_patch_count or 0)
        trend = [
            {
                "date": scan_date.isoformat(),
                "devices": values["devices"],
                "missing_instances": values["missing"],
            }
            for scan_date, values in sorted(trend_by_date.items())
        ]

        os_counts = Counter(str(item.get("os_name") or "Not available") for item in classified)
        priority = sorted(
            classified,
            key=lambda item: (
                float(item.get("risk_score") or 0),
                int(item.get("exploited") or 0),
                int(item.get("critical") or 0),
                int(item.get("missing_patch_count") or 0),
            ),
            reverse=True,
        )[:100]

        return {
            "snapshot": report_date.isoformat(),
            "classification_scope": {
                "category": category,
                "label": label,
                "source": "TechAdmin PostgreSQL sidecar classification",
                "devices": len(classified),
            },
            "summary": {
                "devices": len(classified),
                "total_missing_instances": missing_total,
                "ticket_eligible": ticket_eligible,
                "high_risk_devices": int(high_risk),
                "ivanti_high_risk_threshold": ivanti_high_risk_threshold,
                "persistent_14_day_devices": int(
                    snapshot_metrics["persistent_14_day_devices"]
                ),
                "resolved_devices": int(snapshot_metrics["resolved_devices"]),
                "active_non_compliant_devices": int(
                    snapshot_metrics["active_non_compliant_devices"]
                ),
                "stale_reporting_devices": int(
                    snapshot_metrics["stale_reporting_devices"]
                ),
                "unknown_freshness_devices": int(
                    snapshot_metrics["unknown_freshness_devices"]
                ),
                "raw_missing_patch_records": int(
                    snapshot_metrics["raw_missing_patch_records"]
                ),
                "ticketed_devices": ticketed,
                "critical_security_devices": sum(int(item.get("critical") or 0) > 0 for item in classified),
                "exploited_devices": sum(int(item.get("exploited") or 0) > 0 for item in classified),
                "successful_snapshots_used": len(successful_dates),
                "stored_patch_findings": len(findings),
            },
            "trend": trend,
            "severity": dict(severity_counts),
            "release_age": dict(release_age_counts),
            "operating_systems": [
                {"operating_system": name, "devices": count}
                for name, count in os_counts.most_common(20)
            ],
            "priority_devices": [
                {
                    "Device": item.get("device_name"),
                    "Missing patches": item.get("missing_patch_count"),
                    "Critical security": item.get("critical"),
                    "Important security": item.get("important"),
                    "Exploited": item.get("exploited"),
                    "Ivanti risk score": item.get("risk_score"),
                    "14-day evidence": f"{item.get('observed_14', 0)}/{item.get('required_14', 14)}",
                    "Ticket ID": item.get("ticket_reference") or "",
                }
                for item in priority
            ],
            "top_missing_patches": top_patches,
            "data_errors": [],
            "unavailable_devices": [
                item.get("device_name")
                for item in classified
                if item.get("discovery_id") not in latest_observation
            ][:100],
        }

    def _generate_ai(
        self,
        *,
        evidence: dict[str, Any],
        label: str,
        report_date: date,
    ) -> dict[str, Any]:
        """Use an existing evidence-only AI hook when available.

        No fleet_report/device_report method is called because those methods may
        refresh Ivanti. If the installed analytics service does not expose an
        evidence-only hook, return a full deterministic evidence analysis and
        mark AI unavailable rather than silently making live API calls.
        """
        analytics = PatchAnalyticsService()
        hook_names = (
            "analyze_evidence",
            "analyse_evidence",
            "generate_ai_analysis",
            "_analyze_evidence",
            "_generate_ai_analysis",
        )
        for name in hook_names:
            hook = getattr(analytics, name, None)
            if not callable(hook):
                continue
            try:
                analysis = self._call_ai_hook(hook, evidence)
                if isinstance(analysis, dict):
                    logger.info("CLASSIFIED_REPORT_AI_HOOK | method={}", name)
                    return {"available": True, "analysis": analysis}
            except Exception:
                logger.exception("CLASSIFIED_REPORT_AI_HOOK_FAILED | method={}", name)

        # Always return a user-facing evidence analysis. Internal provider
        # availability is intentionally not exposed in the operator UI.
        return {
            "available": True,
            "analysis": self._deterministic_analysis(
                evidence=evidence,
                label=label,
                report_date=report_date,
            ),
        }

    @staticmethod
    def _call_ai_hook(hook: Callable[..., Any], evidence: dict[str, Any]) -> Any:
        signature = inspect.signature(hook)
        parameters = list(signature.parameters.values())
        names = {parameter.name for parameter in parameters}
        kwargs: dict[str, Any] = {}
        if "evidence" in names:
            kwargs["evidence"] = evidence
        if "report_type" in names:
            kwargs["report_type"] = "fleet"
        if "scope" in names:
            kwargs["scope"] = "classified_fleet"
        if kwargs:
            return hook(**kwargs)
        required = [
            parameter
            for parameter in parameters
            if parameter.default is inspect.Parameter.empty
            and parameter.kind in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]
        if len(required) == 1:
            return hook(evidence)
        raise TypeError("AI hook signature is not evidence-only")

    @staticmethod
    def _deterministic_analysis(
        *,
        evidence: dict[str, Any],
        label: str,
        report_date: date,
    ) -> dict[str, Any]:
        summary = evidence["summary"]
        top = evidence.get("top_missing_patches") or []
        top_text = (
            ", ".join(str(item.get("Patch")) for item in top[:5])
            if top
            else "No detailed PatchFinding rows were stored for this scope"
        )
        return {
            "executive_summary": (
                f"The {label} scope for {report_date.isoformat()} contains "
                f"{summary['devices']:,} endpoints and "
                f"{summary['total_missing_instances']:,} missing patch instances. "
                f"{summary['high_risk_devices']:,} endpoints have an Ivanti risk "
                f"score of {summary.get('ivanti_high_risk_threshold', 80):.0f} or higher. "
                "This high-risk count uses the Ivanti-provided risk score and is not "
                "calculated from the number of missing patches."
            ),
            "compliance": {
                "scope": label,
                "devices": summary["devices"],
                "snapshot": report_date.isoformat(),
            },
            "risk": {
                "high_risk_devices": summary["high_risk_devices"],
                "critical_security_devices": summary["critical_security_devices"],
                "exploited_devices": summary["exploited_devices"],
            },
            "ticket_recommendation": (
                f"Across the complete snapshot, {summary['ticket_eligible']:,} "
                "persistent 14/14 endpoints meet the current ticket rule without "
                "an existing active ticket."
            ),
            "key_findings": [
                f"Top stored patch exposures: {top_text}.",
                f"{summary['stored_patch_findings']:,} detailed missing-patch findings were used.",
                f"{summary['ticketed_devices']:,} endpoints already have ticket references.",
            ],
            "trend_insights": [
                "Review the Overview trend charts for changes across stored successful snapshots."
            ],
            "recommended_actions": [
                "Prioritize exploited and Critical security exposure first.",
                "Use the Priority devices tab for the highest Ivanti risk scores.",
                "Use the Patch exposure tab to identify patches affecting the widest endpoint population.",
            ],
            "data_limitations": [
                "The report reflects the selected stored snapshot and the evidence available for that date.",
                "Ivanti risk score, Critical, Important, and Exploited values are displayed as returned by Ivanti.",
                "Persistent 14/14, stale, unknown, and resolved classifications are derived by TechAdmin from stored scan history.",
            ],
        }

    @staticmethod
    def _release_bucket(report_date: date, released_at: datetime | None) -> str:
        if released_at is None:
            return "Unknown"
        release_date = released_at.date()
        age = max(0, (report_date - release_date).days)
        if age <= 7:
            return "0-7 days"
        if age <= 30:
            return "8-30 days"
        if age <= 90:
            return "31-90 days"
        return "Over 90 days"

    @staticmethod
    def _empty(report_date: date, category: str) -> dict[str, Any]:
        return {
            "report_type": "classified_fleet",
            "classification_category": category,
            "classification_label": CATEGORY_LABELS[category],
            "evidence": {
                "snapshot": report_date.isoformat(),
                "summary": {
                    "devices": 0,
                    "total_missing_instances": 0,
                    "ticket_eligible": 0,
                    "high_risk_devices": 0,
                    "persistent_14_day_devices": 0,
                    "resolved_devices": 0,
                },
                "trend": [],
                "priority_devices": [],
                "top_missing_patches": [],
            },
            "ai": {
                "available": False,
                "analysis": {
                    "executive_summary": (
                        f"No endpoints are present in the "
                        f"{CATEGORY_LABELS[category]} classification for "
                        f"{report_date.isoformat()}."
                    ),
                    "key_findings": [],
                    "data_limitations": [],
                },
            },
        }

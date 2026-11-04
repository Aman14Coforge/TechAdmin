"""Query classified compliance data with live ticket information."""
from __future__ import annotations
from datetime import date
from typing import Any
from sqlalchemy import func, or_, select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchComplianceClassification,
    PatchScanClassificationSummary,
    PatchScanRun,
    PatchTicket,
)

CATEGORY_MAP = {
    "active": ("ACTIVE_NON_COMPLIANT",),
    "persistent_14": ("PERSISTENT_14_DAYS",),
    "stale": ("STALE_REPORTING",),
    "unknown": ("UNKNOWN_FRESHNESS",),
    "resolved": ("RESOLVED",),
    "all": (
        "ACTIVE_NON_COMPLIANT", "PERSISTENT_14_DAYS",
        "STALE_REPORTING", "UNKNOWN_FRESHNESS", "RESOLVED",
    ),
}

class ComplianceQueryService:
    def latest_snapshot_date(self) -> date | None:
        with SessionLocal() as db:
            return db.scalar(select(func.max(PatchScanRun.scan_date)).where(PatchScanRun.status.in_(("SUCCEEDED", "PARTIAL"))))

    def summary(self, report_date: date) -> dict[str, int]:
        with SessionLocal() as db:
            row = db.scalar(
                select(PatchScanClassificationSummary)
                .where(PatchScanClassificationSummary.scan_date == report_date)
                .order_by(PatchScanClassificationSummary.completed_at.desc().nullslast())
            )
        if row is None:
            return {"raw": 0, "active": 0, "persistent_14": 0, "stale": 0, "unknown": 0, "resolved": 0}
        return {
            "raw": int(row.raw_missing_patch_records or 0),
            "active": int(row.active_non_compliant_devices or 0),
            "persistent_14": int(row.persistent_14_devices or 0),
            "stale": int(row.stale_reporting_devices or 0),
            "unknown": int(row.unknown_freshness_devices or 0),
            "resolved": int(row.resolved_devices or 0),
        }

    def _filters(self, report_date: date, category: str, search: str, min_missing: int) -> list[Any]:
        values: list[Any] = [
            PatchComplianceClassification.scan_date == report_date,
            PatchComplianceClassification.compliance_category.in_(CATEGORY_MAP.get(category, CATEGORY_MAP["active"])),
        ]
        if category != "resolved":
            values.append(PatchComplianceClassification.missing_patch_count >= min_missing)
        if search.strip():
            pattern = f"%{search.strip()}%"
            values.append(or_(
                PatchComplianceClassification.device_name.ilike(pattern),
                PatchComplianceClassification.discovery_id.ilike(pattern),
                PatchComplianceClassification.ip_address.ilike(pattern),
            ))
        return values

    @staticmethod
    def _tickets(db: Any, discovery_ids: list[str]) -> dict[str, PatchTicket]:
        if not discovery_ids:
            return {}
        tickets = list(db.scalars(
            select(PatchTicket)
            .where(
                PatchTicket.discovery_id.in_(discovery_ids),
                PatchTicket.status.in_(("CREATED", "ACCEPTED", "CREATING", "REVIEW_REQUIRED", "DRY_RUN")),
            )
            .order_by(PatchTicket.discovery_id.asc(), PatchTicket.requested_at.desc())
        ).all())
        output: dict[str, PatchTicket] = {}
        for ticket in tickets:
            output.setdefault(ticket.discovery_id, ticket)
        return output

    @staticmethod
    def _row(row: PatchComplianceClassification, ticket: PatchTicket | None) -> dict[str, Any]:
        return {
            "device_name": row.device_name,
            "discovery_id": row.discovery_id,
            "ip_address": row.ip_address,
            "os_name": row.os_name,
            "compliance_category": row.compliance_category,
            "inclusion_reason": row.inclusion_reason,
            "missing_patch_count": row.missing_patch_count,
            "risk_score": row.risk_score,
            "last_scanned_at": row.last_scanned_at.isoformat() if row.last_scanned_at else None,
            "observed_14": row.successful_snapshot_days_14,
            "required_14": row.required_snapshot_days_14,
            "critical": row.security_critical,
            "important": row.security_important,
            "exploited": row.exploited_missing_patches,
            "ticket_status": ticket.status if ticket else (row.ticket_status or "NOT_CREATED"),
            "ticket_reference": (
                ticket.external_ticket_id if ticket and ticket.external_ticket_id
                else row.ticket_reference
            ),
        }

    def list_devices(self, *, report_date: date, category: str = "active", search: str = "", min_missing: int = 1, page: int = 1, page_size: int = 100) -> dict[str, Any]:
        filters = self._filters(report_date, category, search, min_missing)
        with SessionLocal() as db:
            total = int(db.scalar(select(func.count(PatchComplianceClassification.classification_id)).where(*filters)) or 0)
            rows = list(db.scalars(
                select(PatchComplianceClassification).where(*filters)
                .order_by(
                    PatchComplianceClassification.missing_patch_count.desc(),
                    PatchComplianceClassification.risk_score.desc().nullslast(),
                    PatchComplianceClassification.device_name.asc(),
                )
                .offset((page - 1) * page_size).limit(page_size)
            ).all())
            tickets = self._tickets(db, [row.discovery_id for row in rows])
        pages = max(1, (total + page_size - 1) // page_size)
        return {"total": total, "page": min(page, pages), "pages": pages,
                "rows": [self._row(row, tickets.get(row.discovery_id)) for row in rows]}

    def all_devices(self, *, report_date: date, category: str = "active", search: str = "", min_missing: int = 1) -> list[dict[str, Any]]:
        filters = self._filters(report_date, category, search, min_missing)
        with SessionLocal() as db:
            rows = list(db.scalars(
                select(PatchComplianceClassification).where(*filters)
                .order_by(
                    PatchComplianceClassification.missing_patch_count.desc(),
                    PatchComplianceClassification.risk_score.desc().nullslast(),
                    PatchComplianceClassification.device_name.asc(),
                )
            ).all())
            tickets = self._tickets(db, [row.discovery_id for row in rows])
        return [self._row(row, tickets.get(row.discovery_id)) for row in rows]

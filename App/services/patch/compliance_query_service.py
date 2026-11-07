"""Build and query compliance sidecar classifications from stored scan data.

This service deliberately treats SUCCEEDED and PARTIAL snapshots differently:
- SUCCEEDED can include resolved endpoints.
- PARTIAL classifies successfully stored observations, but never infers
  resolution from absence.
"""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from sqlalchemy import delete, func, or_, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchComplianceClassification,
    PatchDeviceObservation,
    PatchDeviceState,
    PatchScanClassificationSummary,
    PatchScanRun,
    PatchTicket,
)
from App.services.patch.classification import (
    ACTIVE_FRESH,
    PERSISTENT,
    RESOLVED,
    STALE,
    UNKNOWN,
    active_device_days,
    classify,
)

CATEGORY_MAP = {
    "active": (ACTIVE_FRESH,),
    "persistent_14": (PERSISTENT,),
    "stale": (STALE,),
    "unknown": (UNKNOWN,),
    "resolved": (RESOLVED,),
    "all": (ACTIVE_FRESH, PERSISTENT, STALE, UNKNOWN, RESOLVED),
}


class ComplianceQueryService:
    def latest_snapshot_date(self) -> date | None:
        with SessionLocal() as db:
            return db.scalar(
                select(func.max(PatchScanRun.scan_date)).where(
                    PatchScanRun.status.in_(("SUCCEEDED", "PARTIAL"))
                )
            )

    def _latest_run(self, db: Any, report_date: date) -> PatchScanRun | None:
        return db.scalar(
            select(PatchScanRun)
            .where(
                PatchScanRun.scan_date == report_date,
                PatchScanRun.status.in_(("SUCCEEDED", "PARTIAL")),
            )
            .order_by(
                PatchScanRun.completed_at.desc().nullslast(),
                PatchScanRun.started_at.desc(),
            )
            .limit(1)
        )

    def ensure_classified(
        self,
        report_date: date,
        force: bool = False,
    ) -> dict[str, int]:
        with SessionLocal() as db:
            run = self._latest_run(db, report_date)
            if run is None:
                return self._zero_summary()

            existing_summary = db.scalar(
                select(PatchScanClassificationSummary).where(
                    PatchScanClassificationSummary.scan_id == run.scan_id
                )
            )
            existing_count = int(
                db.scalar(
                    select(func.count(PatchComplianceClassification.classification_id)).where(
                        PatchComplianceClassification.scan_id == run.scan_id
                    )
                )
                or 0
            )
            if (
                not force
                and existing_summary is not None
                and existing_summary.calculation_status == "SUCCEEDED"
                and existing_count > 0
            ):
                return self.summary(report_date, ensure=False)

            started = datetime.now(timezone.utc)
            if existing_summary is None:
                summary_row = PatchScanClassificationSummary(
                    summary_id=uuid.uuid4(),
                    scan_id=run.scan_id,
                    scan_date=report_date,
                    calculation_status="RUNNING",
                    freshness_threshold_days=active_device_days(),
                )
                db.add(summary_row)
            else:
                summary_row = existing_summary
                summary_row.calculation_status = "RUNNING"
                summary_row.calculation_error = None
                summary_row.started_at = started
                summary_row.completed_at = None

            # A date can have multiple manual/scheduled attempts. The UI is a
            # date snapshot, so replace all prior classifications for that date
            # with the latest completed SUCCEEDED/PARTIAL run.
            db.execute(
                delete(PatchComplianceClassification).where(
                    PatchComplianceClassification.scan_date == report_date
                )
            )

            observations = list(
                db.scalars(
                    select(PatchDeviceObservation).where(
                        PatchDeviceObservation.scan_date == report_date
                    )
                ).all()
            )
            state_by_id = {
                state.discovery_id: state
                for state in db.scalars(select(PatchDeviceState)).all()
            }

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

            counts = {
                ACTIVE_FRESH: 0,
                PERSISTENT: 0,
                STALE: 0,
                UNKNOWN: 0,
                RESOLVED: 0,
            }

            for observation in observations:
                state = state_by_id.get(observation.discovery_id)
                result = classify(
                    scan_date=report_date,
                    last_scanned_at=observation.last_scanned_at,
                    missing_patches=int(observation.missing_patch_count or 0),
                )

                observed_14 = 0
                if successful_dates:
                    observed_14 = int(
                        db.scalar(
                            select(
                                func.count(
                                    func.distinct(PatchDeviceObservation.scan_date)
                                )
                            ).where(
                                PatchDeviceObservation.discovery_id
                                == observation.discovery_id,
                                PatchDeviceObservation.scan_date.in_(
                                    successful_dates
                                ),
                                PatchDeviceObservation.missing_patch_count > 0,
                            )
                        )
                        or 0
                    )

                persistent = (
                    len(successful_dates) == 14
                    and observed_14 == 14
                    and result["category"] == ACTIVE_FRESH
                )
                category = PERSISTENT if persistent else result["category"]
                reason = (
                    "Endpoint was fresh and non-compliant in all 14 latest "
                    "successful daily snapshots."
                    if persistent
                    else result["reason"]
                )
                telemetry = observation.telemetry or {}

                db.add(
                    PatchComplianceClassification(
                        classification_id=uuid.uuid4(),
                        scan_id=run.scan_id,
                        scan_date=report_date,
                        discovery_id=observation.discovery_id,
                        device_name=observation.device_name,
                        compliance_category=category,
                        freshness_status=result["freshness"],
                        inclusion_reason=reason,
                        last_scanned_at=observation.last_scanned_at,
                        scan_age_days=result["scan_age_days"],
                        missing_patch_count=int(
                            observation.missing_patch_count or 0
                        ),
                        risk_score=observation.risk_score,
                        successful_snapshot_days_14=observed_14,
                        required_snapshot_days_14=14,
                        persistent_14_days=persistent,
                        assigned_policy=telemetry.get("assigned_policy"),
                        platform=telemetry.get("platform"),
                        os_name=observation.os_name,
                        ip_address=observation.ip_address,
                        management_sources=telemetry.get(
                            "management_sources"
                        )
                        or [],
                        security_critical=int(
                            telemetry.get("security_critical") or 0
                        ),
                        security_important=int(
                            telemetry.get("security_important") or 0
                        ),
                        security_moderate=int(
                            telemetry.get("security_moderate") or 0
                        ),
                        security_low=int(
                            telemetry.get("security_low") or 0
                        ),
                        exploited_missing_patches=int(
                            telemetry.get("exploited_missing_patches") or 0
                        ),
                        is_active=bool(state.is_active) if state else True,
                        resolved_at=state.resolved_at if state else None,
                        ticket_status=state.ticket_status if state else None,
                        ticket_reference=(
                            state.ticket_reference if state else None
                        ),
                    )
                )
                counts[category] += 1

            # Only a complete successful scan can infer resolution by absence.
            if run.status == "SUCCEEDED":
                for state in db.scalars(
                    select(PatchDeviceState).where(
                        PatchDeviceState.is_active.is_(False),
                        PatchDeviceState.resolved_at.is_not(None),
                        func.date(PatchDeviceState.resolved_at) == report_date,
                    )
                ).all():
                    if any(
                        observation.discovery_id == state.discovery_id
                        for observation in observations
                    ):
                        continue
                    db.add(
                        PatchComplianceClassification(
                            classification_id=uuid.uuid4(),
                            scan_id=run.scan_id,
                            scan_date=report_date,
                            discovery_id=state.discovery_id,
                            device_name=state.device_name,
                            compliance_category=RESOLVED,
                            freshness_status="NOT_APPLICABLE",
                            inclusion_reason=(
                                "Previously vulnerable endpoint was absent from "
                                "the latest complete successful snapshot."
                            ),
                            missing_patch_count=int(
                                state.missing_patch_count or 0
                            ),
                            risk_score=state.risk_score,
                            is_active=False,
                            resolved_at=state.resolved_at,
                            ticket_status=state.ticket_status,
                            ticket_reference=state.ticket_reference,
                        )
                    )
                    counts[RESOLVED] += 1

            completed = datetime.now(timezone.utc)
            summary_row.raw_missing_patch_records = len(observations)
            summary_row.active_non_compliant_devices = counts[ACTIVE_FRESH]
            summary_row.persistent_14_devices = counts[PERSISTENT]
            summary_row.stale_reporting_devices = counts[STALE]
            summary_row.unknown_freshness_devices = counts[UNKNOWN]
            summary_row.resolved_devices = counts[RESOLVED]
            summary_row.ticket_eligible_devices = 0
            summary_row.successful_snapshots_available = len(successful_dates)
            summary_row.required_successful_snapshots = 14
            summary_row.calculation_status = "SUCCEEDED"
            summary_row.completed_at = completed
            summary_row.duration_seconds = (
                completed - started
            ).total_seconds()
            db.commit()

        return self.summary(report_date, ensure=False)

    def summary(
        self,
        report_date: date,
        ensure: bool = True,
    ) -> dict[str, int]:
        if ensure:
            with SessionLocal() as db:
                run = self._latest_run(db, report_date)
                if run is None:
                    return self._zero_summary()
                valid_summary = db.scalar(
                    select(PatchScanClassificationSummary.summary_id).where(
                        PatchScanClassificationSummary.scan_id == run.scan_id,
                        PatchScanClassificationSummary.calculation_status
                        == "SUCCEEDED",
                    )
                )
            if not valid_summary:
                return self.ensure_classified(report_date, force=True)

        with SessionLocal() as db:
            run = self._latest_run(db, report_date)
            if run is None:
                return self._zero_summary()
            row = db.scalar(
                select(PatchScanClassificationSummary).where(
                    PatchScanClassificationSummary.scan_id == run.scan_id
                )
            )
            if row is None:
                return self._zero_summary()
            return {
                "raw": int(row.raw_missing_patch_records or 0),
                "active": int(row.active_non_compliant_devices or 0),
                "persistent_14": int(row.persistent_14_devices or 0),
                "stale": int(row.stale_reporting_devices or 0),
                "unknown": int(row.unknown_freshness_devices or 0),
                "resolved": int(row.resolved_devices or 0),
            }

    def _filters(
        self,
        report_date: date,
        category: str,
        search: str,
        min_missing: int,
    ) -> list[Any]:
        values: list[Any] = [
            PatchComplianceClassification.scan_date == report_date,
            PatchComplianceClassification.compliance_category.in_(
                CATEGORY_MAP.get(category, CATEGORY_MAP["active"])
            ),
        ]
        if category != "resolved":
            values.append(
                PatchComplianceClassification.missing_patch_count >= min_missing
            )
        if search.strip():
            pattern = f"%{search.strip()}%"
            values.append(
                or_(
                    PatchComplianceClassification.device_name.ilike(pattern),
                    PatchComplianceClassification.discovery_id.ilike(pattern),
                    PatchComplianceClassification.ip_address.ilike(pattern),
                )
            )
        return values

    @staticmethod
    def _latest_tickets(
        db: Any,
        discovery_ids: list[str],
    ) -> dict[str, PatchTicket]:
        if not discovery_ids:
            return {}
        tickets = list(
            db.scalars(
                select(PatchTicket)
                .where(
                    PatchTicket.discovery_id.in_(discovery_ids),
                    PatchTicket.status.in_(
                        (
                            "CREATED",
                            "ACCEPTED",
                            "CREATING",
                            "REVIEW_REQUIRED",
                            "DRY_RUN",
                        )
                    ),
                )
                .order_by(
                    PatchTicket.discovery_id.asc(),
                    PatchTicket.requested_at.desc(),
                )
            ).all()
        )
        latest: dict[str, PatchTicket] = {}
        for ticket in tickets:
            latest.setdefault(ticket.discovery_id, ticket)
        return latest

    @staticmethod
    def _row(
        row: PatchComplianceClassification,
        ticket: PatchTicket | None,
    ) -> dict[str, Any]:
        return {
            "device_name": row.device_name,
            "discovery_id": row.discovery_id,
            "ip_address": row.ip_address,
            "os_name": row.os_name,
            "compliance_category": row.compliance_category,
            "freshness_status": row.freshness_status,
            "inclusion_reason": row.inclusion_reason,
            "missing_patch_count": row.missing_patch_count,
            "risk_score": row.risk_score,
            "last_scanned_at": (
                row.last_scanned_at.isoformat()
                if row.last_scanned_at
                else None
            ),
            "persistent_14_days": row.persistent_14_days,
            "observed_14": row.successful_snapshot_days_14,
            "required_14": row.required_snapshot_days_14,
            "critical": row.security_critical,
            "important": row.security_important,
            "exploited": row.exploited_missing_patches,
            "ticket_status": (
                ticket.status if ticket else row.ticket_status or "NOT_CREATED"
            ),
            "ticket_reference": (
                ticket.external_ticket_id
                if ticket and ticket.external_ticket_id
                else row.ticket_reference
            ),
            "active": row.is_active,
            "resolved_at": (
                row.resolved_at.isoformat() if row.resolved_at else None
            ),
        }

    def list_devices(
        self,
        *,
        report_date: date,
        category: str = "active",
        search: str = "",
        min_missing: int = 1,
        page: int = 1,
        page_size: int = 100,
    ) -> dict[str, Any]:
        self.summary(report_date, ensure=True)
        filters = self._filters(
            report_date,
            category,
            search,
            min_missing,
        )
        with SessionLocal() as db:
            total = int(
                db.scalar(
                    select(
                        func.count(
                            PatchComplianceClassification.classification_id
                        )
                    ).where(*filters)
                )
                or 0
            )
            rows = list(
                db.scalars(
                    select(PatchComplianceClassification)
                    .where(*filters)
                    .order_by(
                        PatchComplianceClassification.missing_patch_count.desc(),
                        PatchComplianceClassification.risk_score.desc().nullslast(),
                        PatchComplianceClassification.device_name.asc(),
                    )
                    .offset((page - 1) * page_size)
                    .limit(page_size)
                ).all()
            )
            tickets = self._latest_tickets(
                db,
                [row.discovery_id for row in rows],
            )
        pages = max(1, (total + page_size - 1) // page_size)
        return {
            "total": total,
            "page": min(page, pages),
            "pages": pages,
            "rows": [
                self._row(row, tickets.get(row.discovery_id))
                for row in rows
            ],
        }

    def all_devices(
        self,
        *,
        report_date: date,
        category: str = "active",
        search: str = "",
        min_missing: int = 1,
    ) -> list[dict[str, Any]]:
        self.summary(report_date, ensure=True)
        filters = self._filters(
            report_date,
            category,
            search,
            min_missing,
        )
        with SessionLocal() as db:
            rows = list(
                db.scalars(
                    select(PatchComplianceClassification)
                    .where(*filters)
                    .order_by(
                        PatchComplianceClassification.missing_patch_count.desc(),
                        PatchComplianceClassification.risk_score.desc().nullslast(),
                        PatchComplianceClassification.device_name.asc(),
                    )
                ).all()
            )
            tickets = self._latest_tickets(
                db,
                [row.discovery_id for row in rows],
            )
        return [
            self._row(row, tickets.get(row.discovery_id)) for row in rows
        ]

    @staticmethod
    def _zero_summary() -> dict[str, int]:
        return {
            "raw": 0,
            "active": 0,
            "persistent_14": 0,
            "stale": 0,
            "unknown": 0,
            "resolved": 0,
        }

"""Server-side patch-compliance queries for the Security Agent UI."""
from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, or_, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchDeviceObservation,
    PatchDeviceState,
    PatchFinding,
)
from App.services.patch.config import settings


SORTS = {
    "missing_desc": (
        PatchDeviceObservation.missing_patch_count.desc(),
        PatchDeviceObservation.device_name.asc(),
    ),
    "risk_desc": (
        PatchDeviceObservation.risk_score.desc().nullslast(),
        PatchDeviceObservation.device_name.asc(),
    ),
    "days_desc": (
        PatchDeviceState.consecutive_days.desc(),
        PatchDeviceObservation.device_name.asc(),
    ),
    "name_asc": (
        PatchDeviceObservation.device_name.asc(),
    ),
}


class SecurityPatchQueryService:
    """Read stored patch records without triggering live Ivanti calls."""

    def latest_snapshot_date(self) -> date | None:
        with SessionLocal() as db:
            return db.scalar(
                select(func.max(PatchDeviceObservation.scan_date))
            )

    def list_devices(
        self,
        *,
        report_date: date,
        search: str = "",
        sort: str = "missing_desc",
        page: int = 1,
        page_size: int = 25,
        include_resolved: bool = False,
        patch_query: str | None = None,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = max(10, min(int(page_size), 200))
        offset = (page - 1) * page_size

        join_condition = (
            PatchDeviceState.discovery_id
            == PatchDeviceObservation.discovery_id
        )

        filters: list[Any] = [
            PatchDeviceObservation.scan_date == report_date,
        ]

        if not include_resolved:
            filters.append(
                PatchDeviceState.is_active.is_(True)
            )

        normalized_search = str(search or "").strip()
        if normalized_search:
            pattern = f"%{normalized_search}%"
            filters.append(
                or_(
                    PatchDeviceObservation.device_name.ilike(pattern),
                    PatchDeviceObservation.discovery_id.ilike(pattern),
                    PatchDeviceObservation.ip_address.ilike(pattern),
                )
            )

        with SessionLocal() as db:
            query = (
                select(
                    PatchDeviceObservation,
                    PatchDeviceState,
                )
                .join(
                    PatchDeviceState,
                    join_condition,
                )
                .where(*filters)
            )

            patch_text = str(patch_query or "").strip()
            if patch_text:
                patch_pattern = f"%{patch_text}%"
                query = (
                    query
                    .join(
                        PatchFinding,
                        (
                            PatchFinding.discovery_id
                            == PatchDeviceObservation.discovery_id
                        )
                        & (
                            PatchFinding.scan_date
                            == PatchDeviceObservation.scan_date
                        ),
                    )
                    .where(
                        PatchFinding.evidence_type
                        == "CONFIRMED_MISSING",
                        or_(
                            PatchFinding.patch_name.ilike(patch_pattern),
                            PatchFinding.kb_number.ilike(patch_pattern),
                        ),
                    )
                    .distinct()
                )

            total = int(
                db.scalar(
                    select(func.count())
                    .select_from(
                        query.order_by(None).subquery()
                    )
                )
                or 0
            )

            pairs = db.execute(
                query
                .order_by(
                    *SORTS.get(
                        sort,
                        SORTS["missing_desc"],
                    )
                )
                .offset(offset)
                .limit(page_size)
            ).all()

        rows: list[dict[str, Any]] = []
        for observation, state in pairs:
            rows.append(
                {
                    "device_name": observation.device_name,
                    "discovery_id": observation.discovery_id,
                    "ip_address": observation.ip_address,
                    "os_name": observation.os_name,
                    "missing_patch_count": observation.missing_patch_count,
                    "risk_score": observation.risk_score,
                    "consecutive_days": state.consecutive_days,
                    "active": state.is_active,
                    "ticket_eligible": bool(
                        state.is_active
                        and state.consecutive_days >= settings.days
                        and state.missing_patch_count > 0
                    ),
                    "ticket_status": state.ticket_status,
                    "ticket_reference": state.ticket_reference,
                }
            )

        pages = max(
            1,
            (total + page_size - 1) // page_size,
        )

        return {
            "date": report_date.isoformat(),
            "total": total,
            "page": min(page, pages),
            "page_size": page_size,
            "pages": pages,
            "rows": rows,
        }

    def device_details(
        self,
        device_name: str,
    ) -> dict[str, Any]:
        normalized = str(device_name or "").strip()
        if not normalized:
            raise ValueError("Device name is required.")

        with SessionLocal() as db:
            state = db.scalar(
                select(PatchDeviceState)
                .where(
                    PatchDeviceState.device_name.ilike(normalized)
                )
                .order_by(
                    PatchDeviceState.is_active.desc(),
                    PatchDeviceState.last_seen_date.desc(),
                )
            )

            if state is None:
                raise ValueError(
                    f"No stored patch history was found for device '{normalized}'."
                )

            observations = list(
                db.scalars(
                    select(PatchDeviceObservation)
                    .where(
                        PatchDeviceObservation.discovery_id
                        == state.discovery_id
                    )
                    .order_by(
                        PatchDeviceObservation.scan_date.desc()
                    )
                ).all()
            )

            findings = list(
                db.scalars(
                    select(PatchFinding)
                    .where(
                        PatchFinding.discovery_id
                        == state.discovery_id,
                        PatchFinding.evidence_type
                        == "CONFIRMED_MISSING",
                    )
                    .order_by(
                        PatchFinding.scan_date.desc(),
                        PatchFinding.patch_name.asc().nullslast(),
                    )
                ).all()
            )

        findings_by_date: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            day = finding.scan_date.isoformat()
            findings_by_date.setdefault(day, []).append(
                {
                    "Patch name": finding.patch_name,
                    "KB number": finding.kb_number,
                    "Severity": finding.severity,
                    "Vendor": finding.vendor_name,
                    "Status": finding.patch_status,
                    "Released": (
                        finding.released_at.isoformat()
                        if finding.released_at
                        else None
                    ),
                }
            )

        history: list[dict[str, Any]] = []
        for observation in observations:
            day = observation.scan_date.isoformat()
            history.append(
                {
                    "scan_date": day,
                    "missing_patch_count": observation.missing_patch_count,
                    "risk_score": observation.risk_score,
                    "ip_address": observation.ip_address,
                    "os_name": observation.os_name,
                    "last_scanned_at": (
                        observation.last_scanned_at.isoformat()
                        if observation.last_scanned_at
                        else None
                    ),
                    "patches": findings_by_date.get(day, []),
                }
            )

        return {
            "device_name": state.device_name,
            "discovery_id": state.discovery_id,
            "active": state.is_active,
            "first_seen_date": state.first_seen_date.isoformat(),
            "last_seen_date": state.last_seen_date.isoformat(),
            "days_open": state.consecutive_days,
            "resolved_at": (
                state.resolved_at.isoformat()
                if state.resolved_at
                else None
            ),
            "ticket_status": state.ticket_status,
            "ticket_reference": state.ticket_reference,
            "history": history,
        }

    def fleet_report_evidence(self, report_date: date) -> dict[str, Any]:
        """Build compact fleet-wide evidence with set-based database queries."""
        with SessionLocal() as db:
            summary_row = db.execute(
                select(
                    func.count(PatchDeviceObservation.discovery_id),
                    func.coalesce(func.sum(PatchDeviceObservation.missing_patch_count), 0),
                    func.count(
                        PatchDeviceState.discovery_id
                    ).filter(
                        PatchDeviceState.consecutive_days >= settings.days,
                        PatchDeviceObservation.missing_patch_count > 0,
                    ),
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id,
                )
                .where(
                    PatchDeviceObservation.scan_date == report_date,
                    PatchDeviceState.is_active.is_(True),
                )
            ).one()

            priority_rows = db.execute(
                select(
                    PatchDeviceObservation.device_name,
                    PatchDeviceObservation.missing_patch_count,
                    PatchDeviceObservation.risk_score,
                    PatchDeviceState.consecutive_days,
                    PatchDeviceState.ticket_status,
                    PatchDeviceState.ticket_reference,
                    PatchDeviceObservation.ip_address,
                    PatchDeviceObservation.os_name,
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id,
                )
                .where(
                    PatchDeviceObservation.scan_date == report_date,
                    PatchDeviceState.is_active.is_(True),
                )
                .order_by(
                    PatchDeviceObservation.risk_score.desc().nullslast(),
                    PatchDeviceObservation.missing_patch_count.desc(),
                    PatchDeviceState.consecutive_days.desc(),
                )
                .limit(30)
            ).all()

            patch_name = func.coalesce(
                PatchFinding.patch_name,
                PatchFinding.kb_number,
                "Unknown patch",
            )
            patch_rows = db.execute(
                select(
                    patch_name.label("patch"),
                    func.count(func.distinct(PatchFinding.discovery_id)).label("affected_devices"),
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchFinding.discovery_id,
                )
                .where(
                    PatchFinding.scan_date == report_date,
                    PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    PatchDeviceState.is_active.is_(True),
                )
                .group_by(patch_name)
                .order_by(func.count(func.distinct(PatchFinding.discovery_id)).desc())
                .limit(30)
            ).all()
            severity_rows = db.execute(
                select(
                    PatchFinding.severity,
                    func.count(PatchFinding.finding_id),
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id == PatchFinding.discovery_id,
                )
                .where(
                    PatchFinding.scan_date == report_date,
                    PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    PatchDeviceState.is_active.is_(True),
                )
                .group_by(PatchFinding.severity)
            ).all()

        devices = [
            {
                "device_name": row[0],
                "missing_patch_count": row[1],
                "risk_score": row[2],
                "consecutive_days": row[3],
                "ticket_status": row[4],
                "ticket_reference": row[5],
                "ip_address": row[6],
                "operating_system": row[7],
            }
            for row in priority_rows
        ]
        return {
            "scope": "all_non_compliant_devices",
            "snapshot": report_date.isoformat(),
            "summary": {
                "devices": int(summary_row[0] or 0),
                "total_missing_instances": int(summary_row[1] or 0),
                "ticket_eligible": int(summary_row[2] or 0),
            },
            "top_missing_patches": [
                {"patch": row[0], "affected_devices": int(row[1] or 0)}
                for row in patch_rows
            ],
            "priority_devices": devices,
            "severity": {
                "Unknown" if severity is None else str(severity): int(count or 0)
                for severity, count in severity_rows
            },
            "data_limitations": [
                "Fleet totals include every active device; the ranked device sample and patch exposure list show the top 30."
            ],
        }

"""Server-side patch-compliance queries for the Compliance Agent UI."""
from __future__ import annotations

import json
from datetime import date, timedelta
from typing import Any

from sqlalchemy import Date, cast, func, or_, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchDeviceObservation,
    PatchDeviceState,
    PatchFinding,
    PatchScanRun,
    PatchTicket,
)
from App.integration.iengage.client import IEngageClient
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
    "name_asc": (PatchDeviceObservation.device_name.asc(),),
}


class SecurityPatchQueryService:
    """Read stored patch evidence without triggering a live Ivanti request."""

    @staticmethod
    def _ticket_references(states: list[PatchDeviceState]) -> dict[str, str]:
        if not states:
            return {}
        identifiers = {state.discovery_id for state in states}
        episodes = {state.first_seen_date for state in states}
        with SessionLocal() as db:
            tickets = list(
                db.scalars(
                    select(PatchTicket)
                    .where(
                        PatchTicket.discovery_id.in_(identifiers),
                        PatchTicket.episode_first_seen.in_(episodes),
                        PatchTicket.status.in_(
                            ("CREATED", "ACCEPTED", "ALREADY_EXISTS")
                        ),
                    )
                    .order_by(PatchTicket.requested_at.desc())
                ).all()
            )
        latest: dict[tuple[Any, Any], PatchTicket] = {}
        for ticket in tickets:
            latest.setdefault(
                (ticket.discovery_id, ticket.episode_first_seen), ticket
            )
        references: dict[str, str] = {}
        for state in states:
            ticket = latest.get((state.discovery_id, state.first_seen_date))
            reference = state.ticket_reference or (
                ticket.external_ticket_id if ticket else None
            )
            if not reference and ticket and ticket.response_summary:
                try:
                    payload = json.loads(ticket.response_summary)
                except (TypeError, ValueError):
                    payload = {"message": ticket.response_summary}
                reference = IEngageClient._extract_ticket_id_from_message(payload)
            if reference:
                references[state.discovery_id] = str(reference)
        return references

    def latest_snapshot_date(self) -> date | None:
        with SessionLocal() as db:
            completed = db.scalar(
                select(func.max(PatchScanRun.scan_date)).where(
                    PatchScanRun.status.in_(("SUCCEEDED", "PARTIAL"))
                )
            )
            return completed or db.scalar(
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
        device_status: str = "non_compliant",
    ) -> dict[str, Any]:
        page = max(1, int(page))
        page_size = max(10, min(int(page_size), 200))
        offset = (page - 1) * page_size
        normalized_search = str(search or "").strip()

        if device_status == "resolved":
            return self._list_resolved(
                report_date=report_date,
                search=normalized_search,
                page=page,
                page_size=page_size,
                offset=offset,
                patch_query=patch_query,
            )

        # This definition is also used by fleet_report_evidence. Keeping it
        # identical guarantees that table totals and report totals match.
        filters: list[Any] = [
            PatchDeviceObservation.scan_date == report_date,
            PatchDeviceObservation.missing_patch_count > 0,
        ]
        if normalized_search:
            pattern = f"%{normalized_search}%"
            filters.append(
                or_(
                    PatchDeviceObservation.device_name.ilike(pattern),
                    PatchDeviceObservation.discovery_id.ilike(pattern),
                    PatchDeviceObservation.ip_address.ilike(pattern),
                )
            )

        join_condition = (
            PatchDeviceState.discovery_id == PatchDeviceObservation.discovery_id
        )
        with SessionLocal() as db:
            query = (
                select(PatchDeviceObservation, PatchDeviceState)
                .join(PatchDeviceState, join_condition)
                .where(*filters)
            )
            patch_text = str(patch_query or "").strip()
            if patch_text:
                pattern = f"%{patch_text}%"
                query = (
                    query.join(
                        PatchFinding,
                        (PatchFinding.discovery_id == PatchDeviceObservation.discovery_id)
                        & (PatchFinding.scan_date == PatchDeviceObservation.scan_date),
                    )
                    .where(
                        PatchFinding.evidence_type == "CONFIRMED_MISSING",
                        or_(
                            PatchFinding.patch_name.ilike(pattern),
                            PatchFinding.kb_number.ilike(pattern),
                        ),
                    )
                    .distinct()
                )
            total = int(
                db.scalar(
                    select(func.count()).select_from(
                        query.order_by(None).subquery()
                    )
                )
                or 0
            )
            pairs = db.execute(
                query.order_by(*SORTS.get(sort, SORTS["missing_desc"]))
                .offset(offset)
                .limit(page_size)
            ).all()

        states = [state for _, state in pairs]
        references = self._ticket_references(states)
        rows = [
            {
                "device_name": observation.device_name,
                "discovery_id": observation.discovery_id,
                "ip_address": observation.ip_address,
                "os_name": observation.os_name,
                "missing_patch_count": int(observation.missing_patch_count or 0),
                "risk_score": observation.risk_score,
                "consecutive_days": int(state.consecutive_days or 0),
                # Active in this historical snapshot means missing_count > 0.
                "active": True,
                "ticket_eligible": bool(
                    state.is_active
                    and int(state.consecutive_days or 0) >= settings.days
                    and int(observation.missing_patch_count or 0) > 0
                ),
                "ticket_status": state.ticket_status,
                "ticket_reference": references.get(state.discovery_id),
            }
            for observation, state in pairs
        ]
        pages = max(1, (total + page_size - 1) // page_size)
        return {
            "date": report_date.isoformat(),
            "status": device_status,
            "total": total,
            "page": min(page, pages),
            "page_size": page_size,
            "pages": pages,
            "rows": rows,
        }

    def _list_resolved(
        self,
        *,
        report_date: date,
        search: str,
        page: int,
        page_size: int,
        offset: int,
        patch_query: str | None,
    ) -> dict[str, Any]:
        filters: list[Any] = [
            PatchDeviceState.is_active.is_(False),
            PatchDeviceState.resolved_at.is_not(None),
            cast(PatchDeviceState.resolved_at, Date) <= report_date,
        ]
        if search:
            pattern = f"%{search}%"
            filters.append(
                or_(
                    PatchDeviceState.device_name.ilike(pattern),
                    PatchDeviceState.discovery_id.ilike(pattern),
                )
            )
        with SessionLocal() as db:
            query = select(PatchDeviceState).where(*filters)
            if patch_query:
                pattern = f"%{patch_query.strip()}%"
                query = query.where(
                    select(PatchFinding.finding_id)
                    .where(
                        PatchFinding.discovery_id == PatchDeviceState.discovery_id,
                        PatchFinding.scan_date == PatchDeviceState.last_seen_date,
                        PatchFinding.evidence_type == "CONFIRMED_MISSING",
                        or_(
                            PatchFinding.patch_name.ilike(pattern),
                            PatchFinding.kb_number.ilike(pattern),
                        ),
                    )
                    .exists()
                )
            total = int(
                db.scalar(
                    select(func.count()).select_from(
                        query.order_by(None).subquery()
                    )
                )
                or 0
            )
            states = list(
                db.scalars(
                    query.order_by(
                        PatchDeviceState.resolved_at.desc().nullslast(),
                        PatchDeviceState.device_name.asc(),
                    )
                    .offset(offset)
                    .limit(page_size)
                ).all()
            )
            observations = {}
            if states:
                ids = [state.discovery_id for state in states]
                dates = [state.last_seen_date for state in states]
                observations = {
                    observation.discovery_id: observation
                    for observation in db.scalars(
                        select(PatchDeviceObservation).where(
                            PatchDeviceObservation.discovery_id.in_(ids),
                            PatchDeviceObservation.scan_date.in_(dates),
                        )
                    ).all()
                }
        references = self._ticket_references(states)
        rows = []
        for state in states:
            observation = observations.get(state.discovery_id)
            rows.append(
                {
                    "device_name": state.device_name,
                    "discovery_id": state.discovery_id,
                    "ip_address": observation.ip_address if observation else None,
                    "os_name": observation.os_name if observation else None,
                    "missing_patch_count": int(state.missing_patch_count or 0),
                    "risk_score": state.risk_score,
                    "consecutive_days": int(state.consecutive_days or 0),
                    "active": False,
                    "resolved_at": (
                        state.resolved_at.isoformat() if state.resolved_at else None
                    ),
                    "ticket_eligible": False,
                    "ticket_status": state.ticket_status,
                    "ticket_reference": references.get(state.discovery_id),
                }
            )
        pages = max(1, (total + page_size - 1) // page_size)
        return {
            "date": report_date.isoformat(),
            "status": "resolved",
            "total": total,
            "page": min(page, pages),
            "page_size": page_size,
            "pages": pages,
            "rows": rows,
        }

    def device_details(self, device_name: str) -> dict[str, Any]:
        normalized = str(device_name or "").strip()
        if not normalized:
            raise ValueError("Device name is required.")
        with SessionLocal() as db:
            state = db.scalar(
                select(PatchDeviceState)
                .where(PatchDeviceState.device_name.ilike(normalized))
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
                    .where(PatchDeviceObservation.discovery_id == state.discovery_id)
                    .order_by(PatchDeviceObservation.scan_date.desc())
                ).all()
            )
            findings = list(
                db.scalars(
                    select(PatchFinding)
                    .where(
                        PatchFinding.discovery_id == state.discovery_id,
                        PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    )
                    .order_by(
                        PatchFinding.scan_date.desc(),
                        PatchFinding.patch_name.asc().nullslast(),
                    )
                ).all()
            )
        by_date: dict[str, list[dict[str, Any]]] = {}
        for finding in findings:
            day = finding.scan_date.isoformat()
            by_date.setdefault(day, []).append(
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
        history = []
        for observation in observations:
            day = observation.scan_date.isoformat()
            history.append(
                {
                    "scan_date": day,
                    "missing_patch_count": int(
                        observation.missing_patch_count or 0
                    ),
                    "risk_score": observation.risk_score,
                    "ip_address": observation.ip_address,
                    "os_name": observation.os_name,
                    "last_scanned_at": (
                        observation.last_scanned_at.isoformat()
                        if observation.last_scanned_at
                        else None
                    ),
                    "patches": by_date.get(day, []),
                }
            )
        return {
            "device_name": state.device_name,
            "discovery_id": state.discovery_id,
            "active": state.is_active,
            "first_seen_date": state.first_seen_date.isoformat(),
            "last_seen_date": state.last_seen_date.isoformat(),
            "days_open": int(state.consecutive_days or 0),
            "resolved_at": state.resolved_at.isoformat() if state.resolved_at else None,
            "ticket_status": state.ticket_status,
            "ticket_reference": state.ticket_reference,
            "history": history,
        }

    def fleet_report_evidence(self, report_date: date) -> dict[str, Any]:
        """Build evidence for exactly the same snapshot population as list_devices."""
        snapshot_filters = (
            PatchDeviceObservation.scan_date == report_date,
            PatchDeviceObservation.missing_patch_count > 0,
        )
        with SessionLocal() as db:
            summary = db.execute(
                select(
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    ),
                    func.coalesce(
                        func.sum(PatchDeviceObservation.missing_patch_count), 0
                    ),
                ).where(*snapshot_filters)
            ).one()

            ticket_eligible = db.scalar(
                select(
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    )
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id
                    == PatchDeviceObservation.discovery_id,
                )
                .where(
                    *snapshot_filters,
                    PatchDeviceState.is_active.is_(True),
                    PatchDeviceState.consecutive_days >= settings.days,
                )
            ) or 0

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
                    PatchDeviceState.discovery_id
                    == PatchDeviceObservation.discovery_id,
                )
                .where(*snapshot_filters)
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
                    func.count(func.distinct(PatchFinding.discovery_id)).label(
                        "affected_devices"
                    ),
                )
                .where(
                    PatchFinding.scan_date == report_date,
                    PatchFinding.evidence_type == "CONFIRMED_MISSING",
                )
                .group_by(patch_name)
                .order_by(
                    func.count(func.distinct(PatchFinding.discovery_id)).desc()
                )
                .limit(30)
            ).all()

            severity_rows = db.execute(
                select(PatchFinding.severity, func.count(PatchFinding.finding_id))
                .where(
                    PatchFinding.scan_date == report_date,
                    PatchFinding.evidence_type == "CONFIRMED_MISSING",
                )
                .group_by(PatchFinding.severity)
            ).all()

            os_rows = db.execute(
                select(
                    PatchDeviceObservation.os_name,
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    ),
                )
                .where(*snapshot_filters)
                .group_by(PatchDeviceObservation.os_name)
                .order_by(
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    ).desc()
                )
                .limit(15)
            ).all()

            trend_rows = db.execute(
                select(
                    PatchDeviceObservation.scan_date,
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    ),
                    func.coalesce(
                        func.sum(PatchDeviceObservation.missing_patch_count), 0
                    ),
                    func.avg(PatchDeviceObservation.risk_score),
                )
                .where(
                    PatchDeviceObservation.scan_date.between(
                        report_date - timedelta(days=13), report_date
                    ),
                    PatchDeviceObservation.missing_patch_count > 0,
                )
                .group_by(PatchDeviceObservation.scan_date)
                .order_by(PatchDeviceObservation.scan_date)
            ).all()

            high_risk = db.scalar(
                select(
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    )
                ).where(
                    *snapshot_filters,
                    PatchDeviceObservation.risk_score >= 80,
                )
            ) or 0

            persistent_14 = db.scalar(
                select(
                    func.count(
                        func.distinct(PatchDeviceObservation.discovery_id)
                    )
                )
                .join(
                    PatchDeviceState,
                    PatchDeviceState.discovery_id
                    == PatchDeviceObservation.discovery_id,
                )
                .where(
                    *snapshot_filters,
                    PatchDeviceState.consecutive_days >= 14,
                )
            ) or 0

            resolved = db.scalar(
                select(func.count(PatchDeviceState.discovery_id)).where(
                    PatchDeviceState.is_active.is_(False),
                    PatchDeviceState.resolved_at.is_not(None),
                    cast(PatchDeviceState.resolved_at, Date) <= report_date,
                )
            ) or 0

        devices = [
            {
                "device_name": row[0],
                "missing_patch_count": int(row[1] or 0),
                "risk_score": float(row[2]) if row[2] is not None else None,
                "consecutive_days": int(row[3] or 0),
                "ticket_status": row[4],
                "ticket_reference": row[5],
                "ip_address": row[6],
                "operating_system": row[7],
            }
            for row in priority_rows
        ]
        device_count = int(summary[0] or 0)
        missing_count = int(summary[1] or 0)
        return {
            "scope": "active_non_compliant_snapshot",
            "snapshot": report_date.isoformat(),
            "summary": {
                "devices": device_count,
                "active_non_compliant_devices": device_count,
                "total_missing_instances": missing_count,
                "ticket_eligible": int(ticket_eligible),
                "high_risk_devices": int(high_risk),
                "persistent_14_day_devices": int(persistent_14),
                "resolved_devices": int(resolved),
            },
            "trend": [
                {
                    "date": row[0].isoformat(),
                    "devices": int(row[1] or 0),
                    "missing_instances": int(row[2] or 0),
                    "average_risk": (
                        round(float(row[3]), 2) if row[3] is not None else None
                    ),
                }
                for row in trend_rows
            ],
            "top_missing_patches": [
                {"patch": row[0], "affected_devices": int(row[1] or 0)}
                for row in patch_rows
            ],
            "priority_devices": devices,
            "severity": {
                "Unknown" if severity is None else str(severity): int(count or 0)
                for severity, count in severity_rows
            },
            "operating_systems": [
                {"operating_system": name or "Unknown", "devices": int(count or 0)}
                for name, count in os_rows
            ],
            "data_limitations": [
                "Fleet totals represent devices with a stored observation on the selected date and missing_patch_count greater than zero.",
                "Resolved-device totals are archived device states resolved on or before the selected date and are not included in the non-compliant device total.",
                "Priority devices and patch exposure tables are limited to 30 rows for readability.",
                "The report does not infer reboot state, deployment results, disk space, maintenance windows, or root cause without explicit evidence.",
            ],
        }

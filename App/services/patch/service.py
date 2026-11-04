from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

from loguru import logger
from sqlalchemy import delete, func, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchDeviceObservation,
    PatchDeviceState,
    PatchFinding,
    PatchScanRun,
    PatchTicket,
)
from App.integration.ivanti.client import IvantiPatchClient
from App.services.patch.classification import (
    ACTIVE_FRESH,
    PERSISTENT,
    STALE,
    UNKNOWN,
    classify,
    management_sources,
)
from App.services.patch.config import settings
from App.services.patch.ticket_service import PatchTicketService


class PatchScanCancelled(RuntimeError):
    """A scan stopped cooperatively after an operator request."""


def parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except (TypeError, ValueError):
        return None


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _refresh_persistence(db: Any, day: date) -> tuple[int, list[PatchDeviceState]]:
    successful_dates = list(
        db.scalars(
            select(PatchScanRun.scan_date)
            .where(
                PatchScanRun.status == "SUCCEEDED",
                PatchScanRun.scan_date <= day,
            )
            .distinct()
            .order_by(PatchScanRun.scan_date.desc())
            .limit(14)
        ).all()
    )
    required = 14
    persistent_count = 0

    active_states = list(
        db.scalars(select(PatchDeviceState).where(PatchDeviceState.is_active.is_(True))).all()
    )
    for state in active_states:
        observed = 0
        if successful_dates:
            observed = int(
                db.scalar(
                    select(func.count(func.distinct(PatchDeviceObservation.scan_date))).where(
                        PatchDeviceObservation.discovery_id == state.discovery_id,
                        PatchDeviceObservation.scan_date.in_(successful_dates),
                    )
                )
                or 0
            )
        state.successful_snapshot_days_14 = observed
        state.required_snapshot_days_14 = required
        state.persistent_14_days = (
            len(successful_dates) == required
            and observed == required
            and state.compliance_category == ACTIVE_FRESH
        )
        if state.persistent_14_days:
            state.compliance_category = PERSISTENT
            state.inclusion_reason = (
                "The endpoint was actively reporting and non-compliant in all "
                "14 latest successful daily snapshots."
            )
            persistent_count += 1
        elif state.compliance_category == PERSISTENT:
            state.compliance_category = ACTIVE_FRESH

    active_ticket = select(PatchTicket.ticket_row_id).where(
        PatchTicket.discovery_id == PatchDeviceState.discovery_id,
        PatchTicket.episode_first_seen == PatchDeviceState.first_seen_date,
        PatchTicket.status.in_(("CREATED", "ACCEPTED", "CREATING", "REVIEW_REQUIRED")),
    ).exists()
    eligible = list(
        db.scalars(
            select(PatchDeviceState)
            .where(
                PatchDeviceState.is_active.is_(True),
                PatchDeviceState.persistent_14_days.is_(True),
                PatchDeviceState.compliance_category == PERSISTENT,
                PatchDeviceState.missing_patch_count > 0,
                ~active_ticket,
            )
            .order_by(
                PatchDeviceState.risk_score.desc().nullslast(),
                PatchDeviceState.missing_patch_count.desc(),
                PatchDeviceState.device_name.asc(),
            )
        ).all()
    )
    return persistent_count, eligible


class PatchService:
    def scan(
        self,
        scan_date: date | None = None,
        source: str = "MANUAL",
        should_stop=None,
    ) -> dict[str, Any]:
        day = scan_date or date.today()
        client = IvantiPatchClient()
        seen: set[str] = set()
        errors: list[dict[str, Any]] = []
        processed = findings_count = 0
        category_counts = {ACTIVE_FRESH: 0, STALE: 0, UNKNOWN: 0}

        with SessionLocal() as db:
            run = PatchScanRun(scan_date=day, source=source, status="RUNNING")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.scan_id

        try:
            readiness = client.preflight()
            if not readiness.get("patch_scan_ready"):
                raise RuntimeError("Ivanti Patch Management preflight failed")

            for device in client.iter_vulnerable_devices():
                if should_stop and should_stop():
                    raise PatchScanCancelled("Operator requested the scan to stop.")

                discovery_id = str(device.get("discoveryId") or "").strip()
                device_name = str(device.get("machineName") or "").strip()
                missing_count = _integer(device.get("missingPatches"))
                if not discovery_id or not device_name or missing_count <= 0:
                    continue

                last_scanned = parse_datetime(device.get("lastScannedDate"))
                classification = classify(
                    scan_date=day,
                    last_scanned_at=last_scanned,
                    missing_patches=missing_count,
                )
                device_status = device.get("deviceStatus") or {}
                sources = management_sources(device_status)
                category_counts[classification["category"]] += 1
                seen.add(discovery_id)
                processed += 1

                confirmed_findings: list[tuple[str, dict[str, Any]]] = []
                for patch in device_status.get("devicePatchSummaries") or []:
                    if str(patch.get("patchStatus") or "").casefold() != "missing":
                        continue
                    key = str(
                        patch.get("patchId")
                        or patch.get("notificationId")
                        or patch.get("kbNumber")
                        or patch.get("patchName")
                        or ""
                    ).strip()
                    if key:
                        confirmed_findings.append((key, patch))

                try:
                    with SessionLocal() as db:
                        state = db.scalar(
                            select(PatchDeviceState).where(
                                PatchDeviceState.discovery_id == discovery_id
                            )
                        )
                        if state is None:
                            state = PatchDeviceState(
                                discovery_id=discovery_id,
                                device_name=device_name,
                                display_name=device_name,
                                first_seen_date=day,
                                last_seen_date=day,
                                consecutive_days=1,
                                total_observed_days=1,
                                is_active=True,
                            )
                            db.add(state)
                        else:
                            if state.last_seen_date != day:
                                state.total_observed_days += 1
                            if not state.is_active:
                                state.first_seen_date = day
                                state.ticket_status = "NOT_ELIGIBLE"
                                state.ticket_reference = None
                                state.ticket_created_at = None
                            state.last_seen_date = day
                            state.is_active = True
                            state.resolved_at = None
                            state.device_name = device_name
                            state.display_name = device_name
                            state.consecutive_days = (day - state.first_seen_date).days + 1

                        state.missing_patch_count = missing_count
                        state.risk_score = device.get("riskScore")
                        state.last_scanned_at = last_scanned
                        state.scan_age_days = classification["scan_age_days"]
                        state.freshness_status = classification["freshness"]
                        state.compliance_category = classification["category"]
                        state.inclusion_reason = classification["reason"]
                        state.assigned_policy = device.get("assignedPolicy")
                        state.platform = device.get("platform")
                        state.os_name = device.get("osName")
                        state.management_sources = sources
                        state.security_critical = _integer(device.get("securityCritical"))
                        state.security_important = _integer(device.get("securityImportant"))
                        state.security_moderate = _integer(device.get("securityModerate"))
                        state.security_low = _integer(device.get("securityLow"))
                        state.exploited_missing_patches = _integer(device.get("exploited"))
                        state.notifications = device.get("notificationsAffected") or []
                        state.last_scan_id = run_id

                        db.execute(
                            delete(PatchFinding).where(
                                PatchFinding.scan_date == day,
                                PatchFinding.discovery_id == discovery_id,
                            )
                        )
                        db.execute(
                            delete(PatchDeviceObservation).where(
                                PatchDeviceObservation.scan_date == day,
                                PatchDeviceObservation.discovery_id == discovery_id,
                            )
                        )
                        db.add(
                            PatchDeviceObservation(
                                scan_id=run_id,
                                scan_date=day,
                                discovery_id=discovery_id,
                                device_name=device_name,
                                missing_patch_count=missing_count,
                                risk_score=device.get("riskScore"),
                                last_scanned_at=last_scanned,
                                scan_age_days=classification["scan_age_days"],
                                freshness_status=classification["freshness"],
                                compliance_category=classification["category"],
                                inclusion_reason=classification["reason"],
                                ip_address=device.get("ipAddress"),
                                os_name=device.get("osName"),
                                assigned_policy=device.get("assignedPolicy"),
                                management_sources=sources,
                                notifications=state.notifications,
                                telemetry={
                                    "platform": device.get("platform"),
                                    "os_version": device.get("osVersion"),
                                    "security_critical": state.security_critical,
                                    "security_important": state.security_important,
                                    "security_moderate": state.security_moderate,
                                    "security_low": state.security_low,
                                    "exploited_missing_patches": state.exploited_missing_patches,
                                    "management_sources": sources,
                                    "assigned_policy": state.assigned_policy,
                                    "collection_mode": "endpoint_vulnerability_missing_only",
                                },
                            )
                        )
                        for key, patch in confirmed_findings:
                            db.add(
                                PatchFinding(
                                    scan_id=run_id,
                                    scan_date=day,
                                    discovery_id=discovery_id,
                                    device_name=device_name,
                                    evidence_key=key,
                                    evidence_type="CONFIRMED_MISSING",
                                    patch_name=patch.get("patchName"),
                                    patch_id=patch.get("patchId"),
                                    notification_id=patch.get("notificationId"),
                                    kb_number=patch.get("kbNumber"),
                                    vendor_name=patch.get("vendorName"),
                                    patch_status=patch.get("patchStatus"),
                                    severity=patch.get("patchSeverity"),
                                    released_at=parse_datetime(patch.get("released")),
                                    raw_evidence={"summary": patch},
                                )
                            )
                        db.commit()
                        findings_count += len(confirmed_findings)
                except Exception as exc:
                    errors.append(
                        {
                            "device": device_name,
                            "discovery_id": discovery_id,
                            "error": type(exc).__name__,
                            "message": str(exc)[:500],
                        }
                    )

                if processed % 100 == 0:
                    with SessionLocal() as progress_db:
                        progress = progress_db.get(PatchScanRun, run_id)
                        if progress:
                            progress.noncompliant_devices = processed
                            progress.vulnerable_devices = processed
                            progress.active_fresh_devices = category_counts[ACTIVE_FRESH]
                            progress.stale_devices = category_counts[STALE]
                            progress.unknown_freshness_devices = category_counts[UNKNOWN]
                            progress_db.commit()

            if should_stop and should_stop():
                raise PatchScanCancelled("Operator requested the scan to stop.")

            with SessionLocal() as db:
                resolved = 0
                for state in db.scalars(
                    select(PatchDeviceState).where(PatchDeviceState.is_active.is_(True))
                ).all():
                    if state.discovery_id not in seen:
                        state.is_active = False
                        state.resolved_at = datetime.now(timezone.utc)
                        state.compliance_category = "RESOLVED"
                        state.inclusion_reason = "Device was absent from the latest complete successful vulnerability snapshot."
                        state.persistent_14_days = False
                        resolved += 1

                # Temporarily mark this run successful so it participates in the
                # authoritative latest-14-successful-snapshot calculation.
                run = db.get(PatchScanRun, run_id)
                run.status = "SUCCEEDED"
                db.flush()
                persistent_count, eligible = _refresh_persistence(db, day)

                final_status = "PARTIAL" if errors else "SUCCEEDED"
                run.status = final_status
                run.completed_at = datetime.now(timezone.utc)
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.active_fresh_devices = category_counts[ACTIVE_FRESH]
                run.stale_devices = category_counts[STALE]
                run.unknown_freshness_devices = category_counts[UNKNOWN]
                run.persistent_14_devices = persistent_count
                run.resolved_devices = resolved
                run.eligible_devices = len(eligible)
                run.errors = errors or None
                db.commit()

            created = 0
            if settings.auto_ticket:
                for attempted, state in enumerate(eligible, start=1):
                    if attempted > settings.max_auto_per_run:
                        break
                    try:
                        response = PatchTicketService().raise_for_device(
                            state.device_name,
                            reason=(
                                "Automatic ticket after the endpoint was actively "
                                "reporting and non-compliant in all 14 latest successful daily snapshots."
                            ),
                            mode="AUTO",
                            requested_by="TechAdmin Patch Scheduler",
                        )
                        created += int(response.get("status") == "CREATED")
                    except Exception:
                        logger.exception("PATCH_AUTO_TICKET_FAILED | device={}", state.device_name)

            with SessionLocal() as db:
                db.get(PatchScanRun, run_id).tickets_created = created
                db.commit()

            return {
                "scan_id": str(run_id),
                "scan_date": day.isoformat(),
                "status": "PARTIAL" if errors else "SUCCEEDED",
                "raw_missing_patch_records": processed,
                "active_non_compliant": category_counts[ACTIVE_FRESH],
                "stale_reporting": category_counts[STALE],
                "unknown_freshness": category_counts[UNKNOWN],
                "persistent_14_days": persistent_count,
                "resolved_devices": resolved,
                "confirmed_missing_findings": findings_count,
                "eligible_devices": len(eligible),
                "tickets_created": created,
                "errors": errors,
            }
        except PatchScanCancelled as exc:
            with SessionLocal() as db:
                run = db.get(PatchScanRun, run_id)
                run.status = "CANCELLED"
                run.completed_at = datetime.now(timezone.utc)
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.errors = [{"error": type(exc).__name__, "message": str(exc)}]
                db.commit()
            return {
                "scan_id": str(run_id),
                "scan_date": day.isoformat(),
                "status": "CANCELLED",
                "devices_processed": processed,
                "message": str(exc),
                "tickets_created": 0,
            }
        except Exception as exc:
            with SessionLocal() as db:
                run = db.get(PatchScanRun, run_id)
                run.status = "FAILED"
                run.completed_at = datetime.now(timezone.utc)
                run.errors = [{"error": type(exc).__name__, "message": str(exc)[:1000]}]
                db.commit()
            raise
        finally:
            client.close()

    def raise_ticket(
        self,
        device_name: str,
        reason: str | None = None,
        mode: str = "USER",
        requested_by: str | None = None,
    ) -> dict[str, Any]:
        return PatchTicketService().raise_for_device(
            device_name,
            reason=reason,
            mode=mode,
            requested_by=requested_by,
        )

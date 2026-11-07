"""Ivanti patch scan service.

Raw Ivanti evidence is stored in the existing production tables. Derived
freshness and persistent-14 classifications are rebuilt in the sidecar tables
through ComplianceQueryService after a complete successful scan.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Callable

from loguru import logger
from sqlalchemy import delete, select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import (
    PatchComplianceClassification,
    PatchDeviceObservation,
    PatchDeviceState,
    PatchFinding,
    PatchScanRun,
    PatchTicket,
)
from App.integration.ivanti.client import IvantiPatchClient
from App.services.patch.compliance_query_service import ComplianceQueryService
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


def _eligible_states(report_date: date) -> list[PatchDeviceState]:
    """Return fresh persistent 14/14 states without an active episode ticket."""
    with SessionLocal() as db:
        persistent_ids = list(
            db.scalars(
                select(PatchComplianceClassification.discovery_id).where(
                    PatchComplianceClassification.scan_date == report_date,
                    PatchComplianceClassification.compliance_category
                    == "PERSISTENT_14_DAYS",
                    PatchComplianceClassification.persistent_14_days.is_(True),
                    PatchComplianceClassification.is_active.is_(True),
                    PatchComplianceClassification.missing_patch_count > 0,
                )
            ).all()
        )
        if not persistent_ids:
            return []

        active_ticket = (
            select(PatchTicket.ticket_row_id)
            .where(
                PatchTicket.discovery_id == PatchDeviceState.discovery_id,
                PatchTicket.episode_first_seen == PatchDeviceState.first_seen_date,
                PatchTicket.status.in_(
                    ("CREATED", "ACCEPTED", "CREATING", "REVIEW_REQUIRED")
                ),
            )
            .exists()
        )
        return list(
            db.scalars(
                select(PatchDeviceState)
                .where(
                    PatchDeviceState.discovery_id.in_(persistent_ids),
                    PatchDeviceState.is_active.is_(True),
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


class PatchService:
    def scan(
        self,
        scan_date: date | None = None,
        source: str = "MANUAL",
        should_stop: Callable[[], bool] | None = None,
    ) -> dict[str, Any]:
        day = scan_date or date.today()
        client = IvantiPatchClient()
        seen: set[str] = set()
        errors: list[dict[str, Any]] = []
        processed = 0
        findings_count = 0

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

                seen.add(discovery_id)
                processed += 1
                device_status = device.get("deviceStatus") or {}
                # Ivanti can return the same patch summary more than once for
                # one endpoint. patch_findings has a unique key on
                # (scan_date, discovery_id, evidence_key), so deduplicate before
                # adding SQLAlchemy objects to the transaction.
                confirmed_by_key: dict[str, dict[str, Any]] = {}
                for patch in device_status.get("devicePatchSummaries") or []:
                    if str(patch.get("patchStatus") or "").casefold() != "missing":
                        continue

                    patch_id = str(patch.get("patchId") or "").strip()
                    notification_id = str(
                        patch.get("notificationId") or ""
                    ).strip()
                    kb_number = str(patch.get("kbNumber") or "").strip()
                    patch_name = str(patch.get("patchName") or "").strip()

                    # Prefix the source field so values from different identifier
                    # namespaces cannot collide accidentally. Empty evidence is
                    # skipped rather than inserted as an empty unique key.
                    if patch_id:
                        evidence_key = f"PATCH_ID:{patch_id}"
                    elif notification_id:
                        evidence_key = f"NOTIFICATION_ID:{notification_id}"
                    elif kb_number:
                        evidence_key = f"KB:{kb_number.upper()}"
                    elif patch_name:
                        evidence_key = f"NAME:{patch_name.casefold()}"
                    else:
                        logger.warning(
                            "PATCH_FINDING_SKIPPED_NO_KEY | device={} | discovery_id={}",
                            device_name,
                            discovery_id,
                        )
                        continue

                    existing = confirmed_by_key.get(evidence_key)
                    if existing is None:
                        confirmed_by_key[evidence_key] = patch
                    else:
                        # Keep one deterministic representation. Prefer the row
                        # with more populated fields when duplicate summaries are
                        # returned by Ivanti.
                        existing_score = sum(
                            value not in (None, "") for value in existing.values()
                        )
                        candidate_score = sum(
                            value not in (None, "") for value in patch.values()
                        )
                        if candidate_score > existing_score:
                            confirmed_by_key[evidence_key] = patch

                confirmed = list(confirmed_by_key.items())

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
                                last_scanned_at=parse_datetime(
                                    device.get("lastScannedDate")
                                ),
                                ip_address=device.get("ipAddress"),
                                os_name=device.get("osName"),
                                notifications=state.notifications,
                                telemetry={
                                    "platform": device.get("platform"),
                                    "os_version": device.get("osVersion"),
                                    "assigned_policy": device.get("assignedPolicy"),
                                    "security_critical": _integer(
                                        device.get("securityCritical")
                                    ),
                                    "security_important": _integer(
                                        device.get("securityImportant")
                                    ),
                                    "security_moderate": _integer(
                                        device.get("securityModerate")
                                    ),
                                    "security_low": _integer(
                                        device.get("securityLow")
                                    ),
                                    "exploited_missing_patches": _integer(
                                        device.get("exploited")
                                    ),
                                    "managed_by_patch_cloud": bool(
                                        device_status.get("managedByPatchCloud")
                                    ),
                                    "managed_by_intune": bool(
                                        device_status.get("managedByIntune")
                                    ),
                                    "managed_by_sccm": bool(
                                        device_status.get("managedBySccm")
                                    ),
                                    "collection_mode": (
                                        "endpoint_vulnerability_missing_only"
                                    ),
                                },
                            )
                        )
                        for key, patch in confirmed:
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
                        findings_count += len(confirmed)
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
                            progress_db.commit()

            if should_stop and should_stop():
                raise PatchScanCancelled("Operator requested the scan to stop.")

            # An error-bearing scan is PARTIAL. It must not resolve endpoints,
            # rebuild authoritative classifications, or auto-create tickets.
            if errors:
                # Partial inventory cannot prove resolution and cannot safely
                # auto-ticket. Successfully stored observations are still
                # classified so the selected date does not show all zeroes.
                with SessionLocal() as db:
                    run = db.get(PatchScanRun, run_id)
                    run.status = "PARTIAL"
                    run.completed_at = datetime.now(timezone.utc)
                    run.noncompliant_devices = processed
                    run.vulnerable_devices = processed
                    run.resolved_devices = 0
                    run.eligible_devices = 0
                    run.tickets_created = 0
                    run.errors = errors
                    db.commit()

                classification = ComplianceQueryService().ensure_classified(
                    day,
                    force=True,
                )
                return {
                    "scan_id": str(run_id),
                    "scan_date": day.isoformat(),
                    "status": "PARTIAL",
                    "devices_with_missing_patches": processed,
                    "resolved_devices": 0,
                    "confirmed_missing_findings": findings_count,
                    "active_non_compliant": int(
                        classification.get("active") or 0
                    ),
                    "persistent_14_days": int(
                        classification.get("persistent_14") or 0
                    ),
                    "stale_reporting": int(
                        classification.get("stale") or 0
                    ),
                    "unknown_freshness": int(
                        classification.get("unknown") or 0
                    ),
                    "eligible_devices": 0,
                    "tickets_created": 0,
                    "errors": errors,
                }

            # Resolve only after complete pagination and zero processing errors.
            with SessionLocal() as db:
                resolved = 0
                active_states = list(
                    db.scalars(
                        select(PatchDeviceState).where(
                            PatchDeviceState.is_active.is_(True)
                        )
                    ).all()
                )
                for state in active_states:
                    if state.discovery_id not in seen:
                        state.is_active = False
                        state.resolved_at = datetime.now(timezone.utc)
                        state.consecutive_days = (
                            day - state.first_seen_date
                        ).days + 1
                        resolved += 1

                run = db.get(PatchScanRun, run_id)
                run.status = "SUCCEEDED"
                run.completed_at = datetime.now(timezone.utc)
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.resolved_devices = resolved
                run.eligible_devices = 0
                run.tickets_created = 0
                run.errors = None
                db.commit()

            # Sidecar classification uses raw observations. PatchDeviceState has
            # no compliance_category column by design.
            classification = ComplianceQueryService().ensure_classified(
                day,
                force=True,
            )
            eligible = _eligible_states(day)

            created = 0
            if settings.auto_ticket:
                for attempted, state in enumerate(eligible, start=1):
                    if attempted > settings.max_auto_per_run:
                        break
                    try:
                        response = PatchTicketService().raise_for_device(
                            state.device_name,
                            reason=(
                                "Automatic ticket after fresh non-compliance in "
                                "all 14 latest successful daily snapshots."
                            ),
                            mode="AUTO",
                            requested_by="TechAdmin Patch Scheduler",
                        )
                        created += int(response.get("status") == "CREATED")
                    except Exception:
                        logger.exception(
                            "PATCH_AUTO_TICKET_FAILED | device={}",
                            state.device_name,
                        )

            with SessionLocal() as db:
                run = db.get(PatchScanRun, run_id)
                run.eligible_devices = len(eligible)
                run.tickets_created = created
                db.commit()

            return {
                "scan_id": str(run_id),
                "scan_date": day.isoformat(),
                "status": "SUCCEEDED",
                "devices_with_missing_patches": processed,
                "resolved_devices": resolved,
                "confirmed_missing_findings": findings_count,
                "active_non_compliant": int(classification.get("active") or 0),
                "persistent_14_days": int(
                    classification.get("persistent_14") or 0
                ),
                "stale_reporting": int(classification.get("stale") or 0),
                "unknown_freshness": int(classification.get("unknown") or 0),
                "eligible_devices": len(eligible),
                "tickets_created": created,
                "errors": [],
            }

        except PatchScanCancelled as exc:
            with SessionLocal() as db:
                run = db.get(PatchScanRun, run_id)
                run.status = "CANCELLED"
                run.completed_at = datetime.now(timezone.utc)
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.resolved_devices = 0
                run.eligible_devices = 0
                run.tickets_created = 0
                run.errors = [
                    {"error": type(exc).__name__, "message": str(exc)}
                ]
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
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.resolved_devices = 0
                run.eligible_devices = 0
                run.tickets_created = 0
                run.errors = [
                    {
                        "error": type(exc).__name__,
                        "message": str(exc)[:1000],
                    }
                ]
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

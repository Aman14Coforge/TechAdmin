"""Compact Patch Compliance service.

The daily scan stores only Endpoint Vulnerability records where
missingPatches > 0. It does not download or store the full inventory.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx
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
from App.services.patch.config import settings

RETURN_CODES = {
    "3010": "Restart required",
    "1603": "Fatal installer error",
    "1618": "Another installation is running",
    "1619": "Package could not be opened",
    "2147942512": "Insufficient disk space",
}


def parse_datetime(value: Any) -> datetime | None:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None
    except (TypeError, ValueError):
        return None


class PatchService:
    """Daily compact persistence, reporting, on-demand details, and ticketing."""

    def scan(self, scan_date: date | None = None) -> dict[str, Any]:
        day = scan_date or date.today()
        client = IvantiPatchClient()
        errors: list[dict[str, Any]] = []
        seen: set[str] = set()
        processed = 0
        confirmed_findings = 0

        with SessionLocal() as db:
            run = PatchScanRun(scan_date=day, status="RUNNING")
            db.add(run)
            db.commit()
            db.refresh(run)
            run_id = run.scan_id

        try:
            readiness = client.preflight()
            if not readiness.get("patch_scan_ready"):
                raise RuntimeError(
                    "Patch Management preflight failed: "
                    + str(readiness.get("checks", {}).get("endpoint_vulnerability"))
                )

            logger.info(
                "PATCH_COMPACT_SCAN_STARTED | scan_id={} | strategy=missing_patches_only",
                run_id,
            )

            for vulnerability in client.iter_vulnerable_devices():
                discovery_id = str(vulnerability.get("discoveryId") or "").strip()
                device_name = str(vulnerability.get("machineName") or "").strip()
                missing_count = int(vulnerability.get("missingPatches") or 0)

                if not discovery_id or not device_name or missing_count <= 0:
                    continue

                seen.add(discovery_id)
                processed += 1

                # Compact evidence comes directly from Endpoint Vulnerability.
                # No per-device Patch, Notification, or Deployment API calls are
                # made here. Those calls are reserved for an individual machine.
                summaries = (
                    (vulnerability.get("deviceStatus") or {})
                    .get("devicePatchSummaries")
                    or []
                )
                findings: list[dict[str, Any]] = []

                for summary in summaries:
                    if str(summary.get("patchStatus") or "").casefold() != "missing":
                        continue
                    patch_id = str(summary.get("patchId") or "").strip()
                    notification_id = str(summary.get("notificationId") or "").strip()
                    evidence_key = str(
                        patch_id
                        or notification_id
                        or summary.get("kbNumber")
                        or summary.get("patchName")
                    ).strip()
                    if not evidence_key:
                        continue
                    findings.append({
                        "evidence_key": evidence_key,
                        "evidence_type": "CONFIRMED_MISSING",
                        "patch_name": summary.get("patchName"),
                        "patch_id": patch_id or None,
                        "notification_id": notification_id or None,
                        "kb_number": summary.get("kbNumber"),
                        "vendor_name": summary.get("vendorName"),
                        "patch_status": summary.get("patchStatus"),
                        "severity": summary.get("patchSeverity"),
                        "released_at": parse_datetime(summary.get("released")),
                        "deployment_started_at": None,
                        "deployment_status": None,
                        "return_code": None,
                        "failure_reason": None,
                        "raw_evidence": {"summary": summary},
                    })

                telemetry = {
                    "last_scanned_at": vulnerability.get("lastScannedDate"),
                    "domain_name": vulnerability.get("domainName"),
                    "platform": vulnerability.get("platform"),
                    "os_version": vulnerability.get("osVersion"),
                    "assigned_policy": (
                        vulnerability.get("assignedPolicy")
                        or vulnerability.get("policyName")
                    ),
                    "security_critical": vulnerability.get("securityCritical"),
                    "security_important": vulnerability.get("securityImportant"),
                    "security_moderate": vulnerability.get("securityModerate"),
                    "security_low": vulnerability.get("securityLow"),
                    "critical_exploits": vulnerability.get("criticalExploits"),
                    "exploited_missing_patches": vulnerability.get("exploited"),
                    "collection_mode": "compact_endpoint_vulnerability",
                    "deployment_details": "available_on_demand",
                }

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
                                adjacent = (
                                    state.is_active
                                    and state.last_seen_date == day - timedelta(days=1)
                                )
                                state.consecutive_days = (
                                    state.consecutive_days + 1 if adjacent else 1
                                )
                                state.total_observed_days += 1
                            state.last_seen_date = day
                            state.is_active = True
                            state.resolved_at = None
                            state.device_name = device_name
                            state.display_name = device_name

                        state.missing_patch_count = missing_count
                        state.risk_score = vulnerability.get("riskScore")
                        state.notifications = vulnerability.get("notificationsAffected") or []
                        state.last_scan_id = run_id

                        # Same-day reruns replace one compact daily snapshot.
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

                        db.add(PatchDeviceObservation(
                            scan_id=run_id,
                            scan_date=day,
                            discovery_id=discovery_id,
                            device_name=device_name,
                            missing_patch_count=missing_count,
                            risk_score=vulnerability.get("riskScore"),
                            last_scanned_at=parse_datetime(
                                vulnerability.get("lastScannedDate")
                            ),
                            ip_address=vulnerability.get("ipAddress"),
                            os_name=vulnerability.get("osName"),
                            notifications=state.notifications,
                            telemetry=telemetry,
                        ))

                        for finding in findings:
                            db.add(PatchFinding(
                                scan_id=run_id,
                                scan_date=day,
                                discovery_id=discovery_id,
                                device_name=device_name,
                                **finding,
                            ))
                        db.commit()
                        confirmed_findings += len(findings)

                except Exception as exc:
                    logger.exception(
                        "PATCH_DEVICE_SAVE_FAILED | device={} | discovery_id={}",
                        device_name,
                        discovery_id,
                    )
                    errors.append({
                        "device": device_name,
                        "discovery_id": discovery_id,
                        "error": type(exc).__name__,
                        "message": str(exc)[:500],
                    })

                if processed % 100 == 0:
                    logger.info(
                        "PATCH_COMPACT_SCAN_PROGRESS | devices={} | findings={} | errors={}",
                        processed,
                        confirmed_findings,
                        len(errors),
                    )

            # Absence means no longer returned by the complete missing-patches
            # traversal. Resolve only after the traversal finishes successfully.
            with SessionLocal() as db:
                for state in db.scalars(
                    select(PatchDeviceState).where(
                        PatchDeviceState.is_active.is_(True)
                    )
                ).all():
                    if state.discovery_id not in seen:
                        state.is_active = False
                        state.resolved_at = datetime.now(timezone.utc)
                        state.consecutive_days = 0
                        if state.ticket_status != "CREATED":
                            state.ticket_status = "NOT_ELIGIBLE"

                eligible = list(db.scalars(
                    select(PatchDeviceState).where(
                        PatchDeviceState.is_active.is_(True),
                        PatchDeviceState.consecutive_days >= settings.days,
                        PatchDeviceState.missing_patch_count > 0,
                    )
                ).all())

                run = db.get(PatchScanRun, run_id)
                run.status = "PARTIAL" if errors else "SUCCEEDED"
                run.completed_at = datetime.now(timezone.utc)
                run.noncompliant_devices = processed
                run.vulnerable_devices = processed
                run.eligible_devices = len(eligible)
                run.errors = errors or None
                db.commit()

            if settings.auto_ticket:
                for state in eligible:
                    try:
                        self.raise_ticket(
                            state.device_name,
                            "Automatic ticket after patch persistence threshold",
                            "AUTO",
                        )
                    except Exception:
                        logger.exception(
                            "PATCH_AUTO_TICKET_FAILED | device={}",
                            state.device_name,
                        )

            return {
                "scan_id": str(run_id),
                "scan_date": day.isoformat(),
                "status": "PARTIAL" if errors else "SUCCEEDED",
                "devices_with_missing_patches": processed,
                "confirmed_missing_findings": confirmed_findings,
                "eligible_devices": len(eligible),
                "error_count": len(errors),
                "errors": errors,
                "storage_mode": "compact_missing_patches_only",
            }

        except Exception as exc:
            with SessionLocal() as db:
                run = db.get(PatchScanRun, run_id)
                if run:
                    run.status = "FAILED"
                    run.completed_at = datetime.now(timezone.utc)
                    run.errors = [{
                        "error": type(exc).__name__,
                        "message": str(exc)[:1000],
                    }]
                    db.commit()
            logger.exception("PATCH_SCAN_FAILED | scan_id={}", run_id)
            raise
        finally:
            client.close()

    def report(
        self,
        as_of: date | None = None,
        device_name: str | None = None,
        minimum_days: int = 1,
        limit: int = 200,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Fast paginated report over compact tables."""
        day = as_of or date.today()
        limit = max(1, min(int(limit), 1000))
        offset = max(0, int(offset))

        with SessionLocal() as db:
            base_filters = [PatchDeviceObservation.scan_date == day]
            if device_name:
                base_filters.append(
                    PatchDeviceObservation.device_name.ilike(device_name)
                )

            total = db.scalar(
                select(func.count())
                .select_from(PatchDeviceObservation)
                .where(*base_filters)
            ) or 0

            observations = db.scalars(
                select(PatchDeviceObservation)
                .where(*base_filters)
                .order_by(
                    PatchDeviceObservation.missing_patch_count.desc(),
                    PatchDeviceObservation.device_name,
                )
                .offset(offset)
                .limit(limit)
            ).all()

            output = []
            for observation in observations:
                state = db.scalar(
                    select(PatchDeviceState).where(
                        PatchDeviceState.discovery_id == observation.discovery_id
                    )
                )
                if state and state.consecutive_days < minimum_days:
                    continue

                findings = db.scalars(
                    select(PatchFinding).where(
                        PatchFinding.scan_date == day,
                        PatchFinding.discovery_id == observation.discovery_id,
                        PatchFinding.evidence_type == "CONFIRMED_MISSING",
                    )
                ).all()
                output.append({
                    "device_name": observation.device_name,
                    "discovery_id": observation.discovery_id,
                    "ip_address": observation.ip_address,
                    "os_name": observation.os_name,
                    "missing_patch_count": observation.missing_patch_count,
                    "consecutive_days": state.consecutive_days if state else None,
                    "risk_score": observation.risk_score,
                    "ticket_status": state.ticket_status if state else None,
                    "ticket_eligible": bool(
                        state
                        and state.is_active
                        and state.consecutive_days >= settings.days
                        and state.missing_patch_count > 0
                    ),
                    "telemetry": observation.telemetry or {},
                    "missing_patches": [{
                        "patch_name": item.patch_name,
                        "patch_id": item.patch_id,
                        "kb_number": item.kb_number,
                        "notification_id": item.notification_id,
                        "vendor_name": item.vendor_name,
                        "severity": item.severity,
                        "released_at": (
                            item.released_at.isoformat()
                            if item.released_at else None
                        ),
                    } for item in findings],
                })

        return {
            "as_of": day.isoformat(),
            "total_matching_devices": total,
            "returned_devices": len(output),
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total,
            "devices": output,
            "storage_mode": "compact_missing_patches_only",
        }

    def machine_details(self, device_name: str) -> dict[str, Any]:
        """Fetch expensive deployment details only for one requested machine."""
        with SessionLocal() as db:
            state = db.scalar(
                select(PatchDeviceState).where(
                    PatchDeviceState.device_name.ilike(device_name),
                    PatchDeviceState.is_active.is_(True),
                )
            )
            if state is None:
                raise ValueError("No active non-compliant device was found")
            discovery_id = state.discovery_id
            actual_name = state.device_name

        client = IvantiPatchClient()
        try:
            vulnerability = client.vulnerability(discovery_id, actual_name) or {}
            try:
                deployments = client.deployments(actual_name)
            except Exception as exc:
                deployments = []
                deployment_error = f"{type(exc).__name__}: {exc}"
            else:
                deployment_error = None

            failed = []
            for row in deployments:
                status = str(
                    row.get("deploymentStatus")
                    or row.get("patchStatus")
                    or ""
                ).casefold()
                if status in {"failed", "timedout", "timed_out"}:
                    code_value = row.get("patchStatusReturnCode")
                    code = str(code_value) if code_value is not None else None
                    failed.append({
                        "patch_id": row.get("patchId"),
                        "status": row.get("deploymentStatus") or row.get("patchStatus"),
                        "return_code": code,
                        "failure_reason": RETURN_CODES.get(
                            code,
                            "Unmapped return code",
                        ) if code else None,
                        "deployment_started_at": (
                            row.get("deploymentStart")
                            or row.get("deploymentDate")
                        ),
                    })

            return {
                "device_name": actual_name,
                "discovery_id": discovery_id,
                "missing_patch_count": vulnerability.get("missingPatches"),
                "risk_score": vulnerability.get("riskScore"),
                "last_scanned_at": vulnerability.get("lastScannedDate"),
                "failed_deployments": failed,
                "deployment_record_count": len(deployments),
                "deployment_error": deployment_error,
            }
        finally:
            client.close()

    def raise_ticket(
        self,
        device_name: str,
        reason: str | None = None,
        mode: str = "USER",
    ) -> dict[str, Any]:
        with SessionLocal() as db:
            state = db.scalar(
                select(PatchDeviceState).where(
                    PatchDeviceState.is_active.is_(True),
                    PatchDeviceState.device_name.ilike(device_name),
                )
            )
            if state is None:
                raise ValueError("No active patch non-compliance state found")

            existing = db.scalar(
                select(PatchTicket).where(
                    PatchTicket.discovery_id == state.discovery_id,
                    PatchTicket.episode_first_seen == state.first_seen_date,
                )
            )
            if existing:
                return {
                    "status": "ALREADY_EXISTS",
                    "ticket_id": existing.external_ticket_id,
                }

            payload = {
                "short_description": f"Patch non-compliance: {state.device_name}",
                "description": reason or (
                    f"{state.missing_patch_count} missing patches; "
                    f"{state.consecutive_days} consecutive days."
                ),
                "device_name": state.device_name,
                "discovery_id": state.discovery_id,
                "assignment_group": settings.assignment_group,
            }
            status = "PENDING_CONFIGURATION"
            ticket_id = None
            summary = "Ticket API not configured"

            if not settings.ticket_dry_run and settings.ticket_url:
                headers = {"Content-Type": "application/json"}
                if settings.ticket_token:
                    headers["Authorization"] = f"Bearer {settings.ticket_token}"
                response = httpx.post(
                    settings.ticket_url,
                    json=payload,
                    headers=headers,
                    timeout=settings.timeout,
                )
                response.raise_for_status()
                body = response.json() if response.content else {}
                ticket_id = str(
                    body.get("id") or body.get("number") or ""
                ) or None
                status = "CREATED"
                summary = f"HTTP {response.status_code}"

            db.add(PatchTicket(
                discovery_id=state.discovery_id,
                device_name=state.device_name,
                episode_first_seen=state.first_seen_date,
                request_mode=mode,
                status=status,
                external_ticket_id=ticket_id,
                request_payload=payload,
                response_summary=summary,
            ))
            state.ticket_status = status
            state.ticket_reference = ticket_id
            db.commit()
            return {
                "status": status,
                "ticket_id": ticket_id,
                "summary": summary,
            }

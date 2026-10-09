from __future__ import annotations
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceState, PatchFinding, PatchTicket
from App.integration.iengage.client import IEngageClient
from App.integration.iengage.config import settings


class PatchTicketService:
    def __init__(self, client: IEngageClient | None = None) -> None:
        self.client=client or IEngageClient()

    @staticmethod
    def _description(state: PatchDeviceState, findings: list[PatchFinding], reason: str | None) -> str:
        confirmed=[f for f in findings if f.evidence_type == "CONFIRMED_MISSING"]
        lines=[
            reason or "Persistent Ivanti patch non-compliance detected by TechAdmin.",
            f"Device: {state.device_name}",
            f"Discovery ID: {state.discovery_id}",
            f"Missing patch count: {state.missing_patch_count}",
            f"Consecutive non-compliant days: {state.consecutive_days}",
            f"Risk score: {state.risk_score if state.risk_score is not None else 'Unavailable'}",
            "Confirmed missing patches:",
        ]
        for finding in confirmed[:50]:
            lines.append(f"- {finding.patch_name or 'Unnamed patch'} | {finding.kb_number or 'No KB'} | severity={finding.severity}")
        if len(confirmed) > 50:
            lines.append(f"- ... and {len(confirmed)-50} additional confirmed findings")
        return "\n".join(lines)[:12000]

    def raise_for_device(self, device_name: str, *, reason: str | None = None, mode: str = "USER") -> dict[str, Any]:
        normalized=(device_name or "").strip()
        if not normalized:
            raise ValueError("Device name is required.")
        with SessionLocal() as db:
            state=db.scalar(select(PatchDeviceState).where(
                PatchDeviceState.is_active.is_(True),
                PatchDeviceState.device_name.ilike(normalized),
            ))
            if state is None:
                raise ValueError("No active patch non-compliance state was found for this device.")
            existing=db.scalar(select(PatchTicket).where(
                PatchTicket.discovery_id == state.discovery_id,
                PatchTicket.episode_first_seen == state.first_seen_date,
            ))
            if existing is not None:
                return {"success": True, "status": "ALREADY_EXISTS", "ticket_id": existing.external_ticket_id}

            findings=list(db.scalars(select(PatchFinding).where(
                PatchFinding.discovery_id == state.discovery_id,
                PatchFinding.scan_date == state.last_seen_date,
            )).all())
            details={
                "RequestID": "",
                "RequesterCode": settings.requester_code,
                "EmpCode": settings.employee_code,
                "RequesterMobile": settings.requester_mobile,
                "RequesterProjectCode": settings.requester_project_code,
                "RequestType": settings.request_type,
                "RequestPriorityName": settings.priority_name,
                "RequesterLocationName": settings.location_name,
                "RequestCategoryId": settings.category_id,
                "RequestSubCategoryId": settings.subcategory_id,
                "RequestPriorityId": settings.priority_id,
                "RequesterLocationId": settings.location_id,
                "OtherLocation": "",
                "RequesterSeatNo": "",
                "RequesterIP": "",
                "RequesterAssetCode": state.device_name,
                "RequestDescription": self._description(state, findings, reason),
                "RequestDurationId": "",
                "DurationFromDate": "",
                "DurationToDate": "",
                "ManagerID": "",
                "ReviewingManagerID": "",
                "isMgrOnLeave": "",
                "isSave": True,
                "SmBand": "",
                "Witness": "",
                "ThirdWitness": "",
                "IncidentDate": datetime.now(timezone.utc).isoformat(),
                "SoftwareIds": "",
            }
            result=self.client.create_ticket(details)
            status=result["status"]
            ticket=PatchTicket(
                discovery_id=state.discovery_id,
                device_name=state.device_name,
                episode_first_seen=state.first_seen_date,
                request_mode=mode,
                status=status,
                external_ticket_id=result.get("ticket_id"),
                request_payload={
                    "RequesterAssetCode": state.device_name,
                    "RequestDescription": details["RequestDescription"],
                    "RequestType": settings.request_type,
                    "category_id": settings.category_id,
                    "subcategory_id": settings.subcategory_id,
                },
                response_summary=result.get("response_summary"),
            )
            db.add(ticket)
            state.ticket_status=status
            state.ticket_reference=result.get("ticket_id")
            db.commit()
            return result

    def raise_eligible_automatic_tickets(self, minimum_days: int) -> list[dict[str, Any]]:
        with SessionLocal() as db:
            names=list(db.scalars(select(PatchDeviceState.device_name).where(
                PatchDeviceState.is_active.is_(True),
                PatchDeviceState.missing_patch_count > 0,
                PatchDeviceState.consecutive_days >= minimum_days,
            )).all())
        results=[]
        for name in names:
            results.append({"device_name": name, **self.raise_for_device(
                name,
                reason=f"Automatic remediation ticket after {minimum_days} consecutive daily observations.",
                mode="AUTO",
            )})
        return results

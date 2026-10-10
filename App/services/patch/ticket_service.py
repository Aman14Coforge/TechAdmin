"""Patch ticket orchestration with safe retry and episode-level deduplication."""
from __future__ import annotations
import asyncio
import json
from datetime import datetime,timezone
from typing import Any
from sqlalchemy import select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceObservation,PatchDeviceState,PatchFinding,PatchTicket
from App.integration.iengage.config import IEngageConfig
from App.integration.iengage.models import PatchTicketInput
from App.integration.iengage.ticket_service import PatchTicketService as IEngagePatchTicketService

FINAL_LIVE_STATUSES={"CREATED","ACCEPTED"}
RETRYABLE_STATUSES={"FAILED","DRY_RUN"}

class PatchTicketService:
    def __init__(self)->None:
        self.config=IEngageConfig.from_env();self.integration=IEngagePatchTicketService(config=self.config)
    @staticmethod
    def _run(coro):
        try:asyncio.get_running_loop()
        except RuntimeError:return asyncio.run(coro)
        raise RuntimeError("Use the synchronous patch service outside an active event loop.")
    def raise_for_device(self,device_name:str,*,reason:str|None=None,mode:str="USER",requested_by:str|None=None)->dict[str,Any]:
        name=(device_name or "").strip()
        if not name:raise ValueError("Device name is required.")
        with SessionLocal() as db:
            state=db.scalar(select(PatchDeviceState).where(PatchDeviceState.is_active.is_(True),PatchDeviceState.device_name.ilike(name)))
            if state is None:raise ValueError("No active patch non-compliance state was found for this device.")
            existing=db.scalar(select(PatchTicket).where(PatchTicket.discovery_id==state.discovery_id,PatchTicket.episode_first_seen==state.first_seen_date).order_by(PatchTicket.ticket_row_id.desc()))
            if existing and existing.status in {"CREATING", "REVIEW_REQUIRED"}:
                return {"success":False,"status":existing.status,"ticket_id":existing.external_ticket_id,"message":"A ticket request is in progress or its outcome is uncertain. Check iEngage before retrying to avoid a duplicate.","device_name":state.device_name,"dry_run":False,"sent":True}
            if existing and existing.status in FINAL_LIVE_STATUSES:
                message = (f"An active remediation ticket already exists: {existing.external_ticket_id}."
                           if existing.external_ticket_id else
                           "iEngage already accepted this ticket request without returning a reference. Check iEngage before resubmitting.")
                return {"success":True,"status":"ALREADY_EXISTS","ticket_id":existing.external_ticket_id,"message":message,"device_name":state.device_name,"dry_run":False,"sent":True}
            # A historical dry-run must never block a current live request.
            if existing and existing.status=="DRY_RUN" and self.config.dry_run:
                return {"success":True,"status":"DRY_RUN","ticket_id":existing.external_ticket_id or "DRY-RUN","message":"A dry-run record already exists for this active episode.","device_name":state.device_name,"dry_run":True,"sent":False}
            findings=list(db.scalars(select(PatchFinding).where(PatchFinding.discovery_id==state.discovery_id,PatchFinding.scan_date==state.last_seen_date,PatchFinding.evidence_type=="CONFIRMED_MISSING")).all())
            obs=db.scalar(select(PatchDeviceObservation).where(PatchDeviceObservation.discovery_id==state.discovery_id,PatchDeviceObservation.scan_date==state.last_seen_date))
            if existing and existing.status in RETRYABLE_STATUSES:
                row=existing;row.status="CREATING";row.attempt_count=(row.attempt_count or 0)+1;row.requested_by=requested_by;row.request_mode=mode;row.request_payload={"reason":reason,"retry":True};row.external_ticket_id=None;row.error_message=None;row.response_summary=None
            else:
                row=PatchTicket(discovery_id=state.discovery_id,device_name=state.device_name,episode_first_seen=state.first_seen_date,request_mode=mode,requested_by=requested_by,status="CREATING",attempt_count=1,request_payload={"reason":reason})
                db.add(row)
            state.ticket_status="CREATING";state.ticket_reference=None;state.ticket_created_at=None;db.commit();db.refresh(row);row_id=row.ticket_row_id
            input_data=PatchTicketInput(device_name=state.device_name,missing_patch_count=state.missing_patch_count,missing_patch_names=[f.patch_name for f in findings if f.patch_name],consecutive_non_compliant_days=state.consecutive_days,discovery_id=state.discovery_id,operating_system=obs.os_name if obs else None,ip_address=obs.ip_address if obs else None,triggered_by=requested_by or "TechAdmin",trigger_type=mode,additional_description=reason)
        result=self._run(self.integration.create_patch_ticket(input_data))
        status="DRY_RUN" if result.dry_run else "CREATED" if result.success and result.ticket_id else "ACCEPTED" if result.success else "FAILED"
        if not result.success and result.sent and (
            result.status_code is None or (
                200 <= result.status_code < 300 and "application error" not in result.message
            )
        ):
            status = "REVIEW_REQUIRED"
        completed=datetime.now(timezone.utc)
        with SessionLocal() as db:
            row=db.get(PatchTicket,row_id);state=db.scalar(select(PatchDeviceState).where(PatchDeviceState.discovery_id==input_data.discovery_id))
            row.status=status;row.external_ticket_id=result.ticket_id;row.response_summary=json.dumps({"message":result.message,"status_code":result.status_code,"response_data":result.response_data},ensure_ascii=False,default=str)[:20000];row.error_message=None if result.success else result.message;row.completed_at=completed
            if state:
                state.ticket_status=status;state.ticket_reference=result.ticket_id;state.ticket_created_at=completed if result.success else None
            db.commit()
        return {"success":result.success,"status":status,"ticket_id":result.ticket_id,"message":result.message,"device_name":input_data.device_name,"dry_run":result.dry_run,"sent":result.sent,"status_code":result.status_code,"response_data":result.response_data}

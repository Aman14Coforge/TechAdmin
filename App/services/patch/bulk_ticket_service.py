from __future__ import annotations
import time, uuid
from datetime import datetime, timezone
from typing import Any
from sqlalchemy import select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceState, PatchTicketBatch, PatchTicketBatchItem
from App.services.patch.config import settings
from App.services.patch.ticket_service import PatchTicketService

class PatchBulkTicketService:
    def create_batch(self, *, device_names: list[str] | None=None, all_active: bool=False, eligible_only: bool=False, requested_by: str | None=None, reason: str | None=None) -> dict[str, Any]:
        if not settings.bulk_enabled: raise ValueError("Bulk patch ticketing is disabled.")
        with SessionLocal() as db:
            q=select(PatchDeviceState).where(PatchDeviceState.is_active.is_(True),PatchDeviceState.missing_patch_count>0)
            if device_names: q=q.where(PatchDeviceState.device_name.in_(device_names))
            if eligible_only: q=q.where(PatchDeviceState.consecutive_days>=settings.days)
            states=list(db.scalars(q.order_by(PatchDeviceState.risk_score.desc().nullslast(),PatchDeviceState.consecutive_days.desc())).all())
            if not all_active and not eligible_only and len(states)>settings.max_manual_batch: raise ValueError(f"A manual batch is limited to {settings.max_manual_batch} devices.")
            batch=PatchTicketBatch(scope="ELIGIBLE" if eligible_only else "ALL_ACTIVE" if all_active else "SELECTED",requested_by=requested_by,reason=reason,total_items=len(states))
            db.add(batch); db.flush()
            for s in states: db.add(PatchTicketBatchItem(batch_id=batch.batch_id,discovery_id=s.discovery_id,device_name=s.device_name))
            db.commit(); return {"batch_id":str(batch.batch_id),"status":"QUEUED","total_items":len(states)}
    def process_pass(self, batch_id: str) -> dict[str, Any]:
        bid=uuid.UUID(str(batch_id))
        with SessionLocal() as db:
            batch=db.get(PatchTicketBatch,bid)
            if not batch: raise ValueError("Batch not found.")
            batch.status="PROCESSING"; db.commit()
            items=list(db.scalars(select(PatchTicketBatchItem).where(PatchTicketBatchItem.batch_id==bid,PatchTicketBatchItem.status.in_(["QUEUED","RETRY"])).limit(settings.max_batch_pass)).all())
        svc=PatchTicketService()
        for item in items:
            try:
                result=svc.raise_for_device(item.device_name,reason=batch.reason,mode="BULK",requested_by=batch.requested_by)
                status="SKIPPED" if result["status"]=="ALREADY_EXISTS" else "CREATED" if result.get("success") else "FAILED"
                error=None if result.get("success") else result.get("message")
            except Exception as exc: status,error,result="FAILED",f"{type(exc).__name__}: {exc}",{}
            with SessionLocal() as db:
                row=db.get(PatchTicketBatchItem,item.item_id); row.status=status; row.ticket_id=result.get("ticket_id"); row.error_message=error; row.attempt_count+=1; db.commit()
            if settings.ticket_delay_seconds: time.sleep(settings.ticket_delay_seconds)
        with SessionLocal() as db:
            batch=db.get(PatchTicketBatch,bid); rows=list(db.scalars(select(PatchTicketBatchItem).where(PatchTicketBatchItem.batch_id==bid)).all())
            batch.processed_items=sum(r.status not in {"QUEUED","RETRY"} for r in rows); batch.created_count=sum(r.status=="CREATED" for r in rows); batch.skipped_count=sum(r.status=="SKIPPED" for r in rows); batch.failed_count=sum(r.status=="FAILED" for r in rows)
            if batch.processed_items>=batch.total_items: batch.status="COMPLETED_WITH_ERRORS" if batch.failed_count else "COMPLETED"; batch.completed_at=datetime.now(timezone.utc)
            db.commit(); return self.status(str(bid))
    def status(self,batch_id:str)->dict[str,Any]:
        with SessionLocal() as db:
            b=db.get(PatchTicketBatch,uuid.UUID(str(batch_id)))
            if not b: raise ValueError("Batch not found.")
            return {"batch_id":str(b.batch_id),"scope":b.scope,"status":b.status,"total_items":b.total_items,"processed_items":b.processed_items,"created_count":b.created_count,"skipped_count":b.skipped_count,"failed_count":b.failed_count}

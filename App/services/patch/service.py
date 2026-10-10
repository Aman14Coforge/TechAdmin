from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
from typing import Any
from loguru import logger
from sqlalchemy import delete, select
from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchDeviceObservation,PatchDeviceState,PatchFinding,PatchScanRun,PatchTicket
from App.integration.ivanti.client import IvantiPatchClient
from App.services.patch.config import settings
from App.services.patch.ticket_service import PatchTicketService

def parse_datetime(v:Any)->datetime|None:
    try:return datetime.fromisoformat(str(v).replace('Z','+00:00')) if v else None
    except (TypeError,ValueError):return None
class PatchService:
    def scan(self,scan_date:date|None=None,source:str='MANUAL')->dict[str,Any]:
        day=scan_date or date.today(); client=IvantiPatchClient(); seen:set[str]=set(); errors=[]; processed=findings_count=0
        with SessionLocal() as db:
            run=PatchScanRun(scan_date=day,source=source,status='RUNNING');db.add(run);db.commit();db.refresh(run);run_id=run.scan_id
        try:
            readiness=client.preflight()
            if not readiness.get('patch_scan_ready'):raise RuntimeError('Ivanti Patch Management preflight failed')
            for v in client.iter_vulnerable_devices():
                did=str(v.get('discoveryId') or '').strip(); name=str(v.get('machineName') or '').strip(); count=int(v.get('missingPatches') or 0)
                if not did or not name or count<=0:continue
                seen.add(did);processed+=1; found=[]
                for x in ((v.get('deviceStatus') or {}).get('devicePatchSummaries') or []):
                    if str(x.get('patchStatus') or '').casefold()!='missing':continue
                    key=str(x.get('patchId') or x.get('notificationId') or x.get('kbNumber') or x.get('patchName') or '').strip()
                    if key:found.append((key,x))
                try:
                    with SessionLocal() as db:
                        s=db.scalar(select(PatchDeviceState).where(PatchDeviceState.discovery_id==did))
                        if s is None:
                            s=PatchDeviceState(discovery_id=did,device_name=name,display_name=name,first_seen_date=day,last_seen_date=day,consecutive_days=1,total_observed_days=1,is_active=True);db.add(s)
                        else:
                            if s.last_seen_date!=day:s.total_observed_days+=1
                            if not s.is_active:s.first_seen_date=day;s.ticket_status='NOT_ELIGIBLE';s.ticket_reference=None;s.ticket_created_at=None
                            s.last_seen_date=day;s.is_active=True;s.resolved_at=None;s.device_name=name;s.display_name=name
                            # Calendar-duration policy: missed scans do not reset an unresolved episode.
                            s.consecutive_days=(day-s.first_seen_date).days+1
                        s.missing_patch_count=count;s.risk_score=v.get('riskScore');s.notifications=v.get('notificationsAffected') or [];s.last_scan_id=run_id
                        db.execute(delete(PatchFinding).where(PatchFinding.scan_date==day,PatchFinding.discovery_id==did));db.execute(delete(PatchDeviceObservation).where(PatchDeviceObservation.scan_date==day,PatchDeviceObservation.discovery_id==did))
                        db.add(PatchDeviceObservation(scan_id=run_id,scan_date=day,discovery_id=did,device_name=name,missing_patch_count=count,risk_score=v.get('riskScore'),last_scanned_at=parse_datetime(v.get('lastScannedDate')),ip_address=v.get('ipAddress'),os_name=v.get('osName'),notifications=s.notifications,telemetry={'platform':v.get('platform'),'os_version':v.get('osVersion'),'security_critical':v.get('securityCritical'),'security_important':v.get('securityImportant'),'exploited_missing_patches':v.get('exploited'),'collection_mode':'endpoint_vulnerability_missing_only'}))
                        for key,x in found:db.add(PatchFinding(scan_id=run_id,scan_date=day,discovery_id=did,device_name=name,evidence_key=key,evidence_type='CONFIRMED_MISSING',patch_name=x.get('patchName'),patch_id=x.get('patchId'),notification_id=x.get('notificationId'),kb_number=x.get('kbNumber'),vendor_name=x.get('vendorName'),patch_status=x.get('patchStatus'),severity=x.get('patchSeverity'),released_at=parse_datetime(x.get('released')),raw_evidence={'summary':x}))
                        db.commit();findings_count+=len(found)
                except Exception as exc:errors.append({'device':name,'discovery_id':did,'error':type(exc).__name__,'message':str(exc)[:500]})
            with SessionLocal() as db:
                resolved=0
                for s in db.scalars(select(PatchDeviceState).where(PatchDeviceState.is_active.is_(True))).all():
                    if s.discovery_id not in seen:s.is_active=False;s.resolved_at=datetime.now(timezone.utc);s.consecutive_days=(day-s.first_seen_date).days+1;resolved+=1
                active_ticket=select(PatchTicket.ticket_row_id).where(
                    PatchTicket.discovery_id==PatchDeviceState.discovery_id,
                    PatchTicket.episode_first_seen==PatchDeviceState.first_seen_date,
                    PatchTicket.status.in_(("CREATED","ACCEPTED","CREATING","REVIEW_REQUIRED")),
                ).exists()
                eligible=list(db.scalars(select(PatchDeviceState).where(
                    PatchDeviceState.is_active.is_(True),
                    PatchDeviceState.consecutive_days>=settings.days,
                    PatchDeviceState.missing_patch_count>0,
                    ~active_ticket,
                ).order_by(
                    PatchDeviceState.risk_score.desc().nullslast(),
                    PatchDeviceState.consecutive_days.desc(),
                    PatchDeviceState.device_name.asc(),
                )).all())
                run=db.get(PatchScanRun,run_id);run.status='PARTIAL' if errors else 'SUCCEEDED';run.completed_at=datetime.now(timezone.utc);run.noncompliant_devices=processed;run.vulnerable_devices=processed;run.resolved_devices=resolved;run.eligible_devices=len(eligible);run.errors=errors or None;db.commit()
            created=0
            if settings.auto_ticket:
                attempted=0
                for s in eligible:
                    if attempted>=settings.max_auto_per_run:break
                    attempted+=1
                    try:
                        r=PatchTicketService().raise_for_device(s.device_name,reason=f'Automatic ticket after {settings.days} calendar days of persistent non-compliance',mode='AUTO',requested_by='TechAdmin Patch Scheduler')
                        created+=int(r.get('status')=='CREATED')
                        if r.get('status') not in {'ALREADY_EXISTS','CREATED','ACCEPTED','DRY_RUN'}:
                            logger.warning('PATCH_AUTO_TICKET_NOT_CREATED | device={} | status={} | message={}',s.device_name,r.get('status'),r.get('message'))
                    except Exception:logger.exception('PATCH_AUTO_TICKET_FAILED | device={}',s.device_name)
            with SessionLocal() as db:
                r=db.get(PatchScanRun,run_id);r.tickets_created=created;db.commit()
            return {'scan_id':str(run_id),'scan_date':day.isoformat(),'status':'PARTIAL' if errors else 'SUCCEEDED','devices_with_missing_patches':processed,'resolved_devices':resolved,'confirmed_missing_findings':findings_count,'eligible_devices':len(eligible),'tickets_created':created,'errors':errors}
        except Exception as exc:
            with SessionLocal() as db:
                r=db.get(PatchScanRun,run_id);r.status='FAILED';r.completed_at=datetime.now(timezone.utc);r.errors=[{'error':type(exc).__name__,'message':str(exc)[:1000]}];db.commit()
            raise
        finally:client.close()
    def raise_ticket(self,device_name:str,reason:str|None=None,mode:str='USER',requested_by:str|None=None)->dict[str,Any]:return PatchTicketService().raise_for_device(device_name,reason=reason,mode=mode,requested_by=requested_by)

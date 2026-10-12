"""Embedded scheduler that refuses to scan until all Ivanti API families pass preflight."""
from __future__ import annotations
import atexit,threading
from datetime import datetime,timedelta
from typing import Any
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import select,text
from App.db.connection import SessionLocal,engine
from App.integration.ivanti.client import IvantiPatchClient
from App.db.models.patch_compliance import PatchScanRun
from App.services.patch.config import settings
from App.services.patch.service import PatchService

_LOCK=threading.RLock();_SCHEDULER=None;_LAST_RESULT=None;_LAST_ERROR=None
_STOP_REQUESTED=threading.Event();_SCAN_RUNNING=False

def _preflight():
    c=IvantiPatchClient()
    try:return c.preflight()
    finally:c.close()

def _run(source:str):
    global _LAST_RESULT,_LAST_ERROR,_SCAN_RUNNING
    with _LOCK:
        if _SCAN_RUNNING:
            return {"status":"SKIPPED_ALREADY_RUNNING","source":source}
        _SCAN_RUNNING=True
        _STOP_REQUESTED.clear()
        _LAST_RESULT={"status":"RUNNING","source":source,"started_at":datetime.now(ZoneInfo(settings.scheduler_timezone)).isoformat()}
        _LAST_ERROR=None
    try:
        preflight=_preflight()
        if settings.scheduler_require_preflight and not preflight["success"]:
            _LAST_ERROR="Ivanti preflight failed";_LAST_RESULT={"status":"BLOCKED_PREFLIGHT","source":source,"preflight":preflight}
            logger.error("PATCH_SCAN_BLOCKED_PREFLIGHT | result={}",preflight);return _LAST_RESULT
        with engine.connect() as connection:
            acquired=bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"),{"key":settings.scan_lock_key}).scalar_one())
            if not acquired:
                _LAST_RESULT={"status":"SKIPPED_LOCKED","source":source}
                return _LAST_RESULT
            try:
                if _STOP_REQUESTED.is_set():
                    _LAST_RESULT={"status":"CANCELLED","source":source,"message":"Stopped before requesting Ivanti pages."}
                    return _LAST_RESULT
                local_day=datetime.now(ZoneInfo(settings.scheduler_timezone)).date()
                result=PatchService().scan(scan_date=local_day,source=source,should_stop=_STOP_REQUESTED.is_set)
                result.update({"source":source,"preflight":preflight});_LAST_RESULT=result;_LAST_ERROR=None;return result
            except Exception as exc:_LAST_ERROR=f"{type(exc).__name__}: {exc}";logger.exception("PATCH_SCAN_FAILED");raise
            finally:connection.execute(text("SELECT pg_advisory_unlock(:key)"),{"key":settings.scan_lock_key})
    finally:
        with _LOCK:_SCAN_RUNNING=False

def request_patch_scan_stop():
    if not _SCAN_RUNNING:
        return {"success":False,"status":"NOT_RUNNING","message":"No Ivanti scan is currently running."}
    _STOP_REQUESTED.set()
    logger.warning("PATCH_SCAN_STOP_REQUESTED | scan will stop after the current Ivanti page request")
    return {"success":True,"status":"STOP_REQUESTED","message":"Stop requested. The scan will stop after its current Ivanti page request; partial results will not trigger automatic tickets."}

def patch_scan_is_running()->bool:
    return _SCAN_RUNNING

def trigger_patch_scan_now():
    if _SCAN_RUNNING:
        return {"success":False,"status":"SKIPPED_ALREADY_RUNNING","message":"An Ivanti scan is already running."}
    worker=threading.Thread(target=_run,args=("MANUAL_API",),name="techadmin-patch-manual-scan",daemon=True)
    worker.start()
    return {"success":True,"status":"QUEUED","message":"Manual Ivanti scan queued."}

def scheduled_patch_scan():_run("DAILY_SCHEDULER")
def startup_patch_scan():
    today=datetime.now(ZoneInfo(settings.scheduler_timezone)).date()
    with SessionLocal() as db:
        existing=db.scalar(select(PatchScanRun).where(
            PatchScanRun.scan_date==today,
            PatchScanRun.status=="RUNNING",
        ).order_by(PatchScanRun.started_at.desc()).limit(1))
    if existing:
        with engine.connect() as connection:
            acquired=bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"),{"key":settings.scan_lock_key}).scalar_one())
            if not acquired:
                result={"status":"SKIPPED_STARTUP_CATCHUP","scan_date":today.isoformat(),"existing_status":"RUNNING","message":"A scan is still active in another process."}
                logger.info("PATCH_STARTUP_SCAN_SKIPPED | result={}",result)
                return result
            connection.execute(text("SELECT pg_advisory_unlock(:key)"),{"key":settings.scan_lock_key})
        with SessionLocal() as db:
            stale=db.get(PatchScanRun,existing.scan_id)
            if stale and stale.status=="RUNNING":
                stale.status="CANCELLED";stale.completed_at=datetime.now(ZoneInfo(settings.scheduler_timezone));stale.errors=[{"error":"InterruptedScan","message":"Previous scheduler process stopped before the scan completed."}];db.commit()
                logger.warning("PATCH_STALE_SCAN_MARKED_CANCELLED | scan_id={}",existing.scan_id)
                return {"status":"SKIPPED_INTERRUPTED_SCAN","scan_date":today.isoformat(),"message":"The interrupted scan was marked cancelled. Startup will not immediately restart a scan that an operator may have stopped; the next scheduled daily run remains enabled."}
    with SessionLocal() as db:
        completed=db.scalar(select(PatchScanRun).where(
            PatchScanRun.scan_date==today,
            PatchScanRun.status.in_(("SUCCEEDED","PARTIAL")),
        ).order_by(PatchScanRun.started_at.desc()).limit(1))
    if completed:
        result={"status":"SKIPPED_STARTUP_CATCHUP","scan_date":today.isoformat(),"existing_status":completed.status,"message":"A completed scan already exists for the current local day."}
        logger.info("PATCH_STARTUP_SCAN_SKIPPED | result={}",result)
        return result
    return _run("APPLICATION_STARTUP")
def ensure_patch_scheduler_started():
    global _SCHEDULER
    if not settings.scheduler_enabled:return None
    with _LOCK:
        if _SCHEDULER and _SCHEDULER.running:return _SCHEDULER
        tz=ZoneInfo(settings.scheduler_timezone);s=BackgroundScheduler(timezone=tz,daemon=True,job_defaults={"coalesce":True,"max_instances":1,"misfire_grace_time":21600})
        s.add_job(scheduled_patch_scan,CronTrigger(hour=settings.scheduler_hour,minute=settings.scheduler_minute,timezone=tz),id="ivanti_daily_patch_scan",replace_existing=True)
        if settings.scheduler_run_on_startup:s.add_job(startup_patch_scan,"date",run_date=datetime.now(tz)+timedelta(seconds=settings.scheduler_startup_delay_seconds),id="ivanti_startup_patch_scan",replace_existing=True)
        s.start();_SCHEDULER=s;atexit.register(shutdown_patch_scheduler);logger.info("PATCH_SCHEDULER_STARTED | next_run={}",s.get_job("ivanti_daily_patch_scan").next_run_time);return s

def shutdown_patch_scheduler():
    global _SCHEDULER
    _STOP_REQUESTED.set()
    if _SCHEDULER and _SCHEDULER.running:_SCHEDULER.shutdown(wait=False)
    _SCHEDULER=None

def scheduler_status():
    job=_SCHEDULER.get_job("ivanti_daily_patch_scan") if _SCHEDULER else None
    return {"enabled":settings.scheduler_enabled,"running":bool(_SCHEDULER and _SCHEDULER.running),"scan_in_progress":_SCAN_RUNNING,"stop_requested":_STOP_REQUESTED.is_set(),"timezone":settings.scheduler_timezone,"scheduled_time":f"{settings.scheduler_hour:02d}:{settings.scheduler_minute:02d}","run_on_startup":settings.scheduler_run_on_startup,"auto_ticket_enabled":settings.auto_ticket,"ticket_eligibility_days":settings.days,"max_automatic_tickets_per_scan":settings.max_auto_per_run,"next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None,"last_result":_LAST_RESULT,"last_error":_LAST_ERROR,"preflight":_preflight()}

"""Embedded scheduler that refuses to scan until all Ivanti API families pass preflight."""
from __future__ import annotations
import atexit,threading
from datetime import datetime,timedelta
from typing import Any
from zoneinfo import ZoneInfo
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import text
from App.db.connection import engine
from App.integration.ivanti.client import IvantiPatchClient
from App.services.patch.config import settings
from App.services.patch.service import PatchService

_LOCK=threading.RLock();_SCHEDULER=None;_LAST_RESULT=None;_LAST_ERROR=None

def _preflight():
    c=IvantiPatchClient()
    try:return c.preflight()
    finally:c.close()

def _run(source:str):
    global _LAST_RESULT,_LAST_ERROR
    preflight=_preflight()
    if settings.scheduler_require_preflight and not preflight["success"]:
        _LAST_ERROR="Ivanti preflight failed";_LAST_RESULT={"status":"BLOCKED_PREFLIGHT","source":source,"preflight":preflight}
        logger.error("PATCH_SCAN_BLOCKED_PREFLIGHT | result={}",preflight);return _LAST_RESULT
    with engine.connect() as connection:
        acquired=bool(connection.execute(text("SELECT pg_try_advisory_lock(:key)"),{"key":settings.scan_lock_key}).scalar_one())
        if not acquired:return {"status":"SKIPPED_LOCKED","source":source}
        try:
            result=PatchService().scan();result.update({"status":"COMPLETED","source":source,"preflight":preflight});_LAST_RESULT=result;_LAST_ERROR=None;return result
        except Exception as exc:_LAST_ERROR=f"{type(exc).__name__}: {exc}";logger.exception("PATCH_SCAN_FAILED");raise
        finally:connection.execute(text("SELECT pg_advisory_unlock(:key)"),{"key":settings.scan_lock_key})

def scheduled_patch_scan():_run("DAILY_SCHEDULER")
def startup_patch_scan():_run("APPLICATION_STARTUP")
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
    if _SCHEDULER and _SCHEDULER.running:_SCHEDULER.shutdown(wait=False)
    _SCHEDULER=None

def scheduler_status():
    job=_SCHEDULER.get_job("ivanti_daily_patch_scan") if _SCHEDULER else None
    return {"enabled":settings.scheduler_enabled,"running":bool(_SCHEDULER and _SCHEDULER.running),"next_run_time":job.next_run_time.isoformat() if job and job.next_run_time else None,"last_result":_LAST_RESULT,"last_error":_LAST_ERROR,"preflight":_preflight()}

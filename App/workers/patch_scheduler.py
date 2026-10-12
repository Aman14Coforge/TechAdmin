from __future__ import annotations
import signal, time
from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger
from loguru import logger
from sqlalchemy import text
from App.db.connection import engine
from App.services.patch.config import settings
from App.services.patch.service import PatchService

def run_once()->dict:
    with engine.connect() as c:
        locked=bool(c.execute(text('SELECT pg_try_advisory_lock(:key)'),{'key':settings.scan_lock_key}).scalar_one())
        if not locked:return {'status':'SKIPPED_LOCKED'}
        try:return PatchService().scan(source='DAILY_SCHEDULER')
        finally:c.execute(text('SELECT pg_advisory_unlock(:key)'),{'key':settings.scan_lock_key})
def main()->None:
    if not settings.scheduler_enabled:raise SystemExit('PATCH_SCHEDULER_ENABLED is false')
    scheduler=BlockingScheduler(timezone=settings.scheduler_timezone,job_defaults={'coalesce':True,'max_instances':1,'misfire_grace_time':21600})
    scheduler.add_job(run_once,CronTrigger(hour=settings.scheduler_hour,minute=settings.scheduler_minute,timezone=settings.scheduler_timezone),id='ivanti_daily_patch_scan',replace_existing=True)
    signal.signal(signal.SIGTERM,lambda *_:scheduler.shutdown(wait=False));logger.info('PATCH_SCHEDULER_READY | next_run={}',scheduler.get_job('ivanti_daily_patch_scan').next_run_time);scheduler.start()
if __name__=='__main__':main()

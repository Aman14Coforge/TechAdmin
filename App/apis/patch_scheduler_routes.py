"""Operational endpoints for the embedded Patch Agent scheduler."""
from fastapi import APIRouter
from App.services.patch.scheduler import request_patch_scan_stop, scheduler_status, trigger_patch_scan_now

router = APIRouter(prefix="/api/v1/patch/scheduler", tags=["patch-scheduler"])

@router.get("/status")
def get_scheduler_status() -> dict:
    return scheduler_status()

@router.post("/trigger")
def trigger_scheduler_scan() -> dict:
    return trigger_patch_scan_now()

@router.post("/stop")
def stop_scheduler_scan() -> dict:
    return request_patch_scan_stop()

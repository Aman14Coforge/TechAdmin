"""TechAdmin daily patch scheduler with startup catch-up and stop controls.

This module preserves the public API used by existing StreamlitApp/app.py while
running scans through PatchService. A cooperative stop event is passed into the
scanner so the operator can stop safely between Ivanti devices/pages.
"""
from __future__ import annotations

import os
import threading
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from loguru import logger
from sqlalchemy import select

from App.db.connection import SessionLocal
from App.db.models.patch_compliance import PatchScanRun
from App.services.patch.service import PatchService

_LOCK = threading.RLock()
_SCHEDULER_WAKE = threading.Event()
_SCHEDULER_STOP = threading.Event()
_SCAN_STOP = threading.Event()
_SCHEDULER_THREAD: threading.Thread | None = None
_SCAN_THREAD: threading.Thread | None = None
_LAST_RESULT: dict[str, Any] | None = None
_LAST_ERROR: str | None = None
_CURRENT_SOURCE: str | None = None
_SCAN_STARTED_AT: datetime | None = None
_NEXT_RUN: datetime | None = None


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().casefold() in {"1", "true", "yes", "on"}


def _env(primary: str, legacy: str, default: str) -> str:
    """Read the current variable, then the original production variable."""
    current = os.getenv(primary)
    if current is not None and current.strip():
        return current.strip()
    previous = os.getenv(legacy)
    if previous is not None and previous.strip():
        return previous.strip()
    return default


def _timezone() -> ZoneInfo:
    configured = _env(
        "PATCH_SCAN_TIMEZONE",
        "PATCH_SCHEDULER_TIMEZONE",
        "Asia/Kolkata",
    )
    try:
        return ZoneInfo(configured)
    except Exception:
        logger.exception("PATCH_SCHEDULER_INVALID_TIMEZONE | value={}", configured)
        return ZoneInfo("Asia/Kolkata")


def _hour() -> int:
    try:
        return min(
            23,
            max(
                0,
                int(_env("PATCH_SCAN_HOUR", "PATCH_SCHEDULER_HOUR", "1")),
            ),
        )
    except ValueError:
        return 1


def _minute() -> int:
    try:
        return min(
            59,
            max(
                0,
                int(_env("PATCH_SCAN_MINUTE", "PATCH_SCHEDULER_MINUTE", "0")),
            ),
        )
    except ValueError:
        return 0


def _scheduled_time(now: datetime) -> datetime:
    return now.replace(hour=_hour(), minute=_minute(), second=0, microsecond=0)


def _calculate_next_run(now: datetime) -> datetime:
    target = _scheduled_time(now)
    return target if target > now else target + timedelta(days=1)


def _successful_scan_exists(scan_date: date) -> bool:
    with SessionLocal() as db:
        return bool(
            db.scalar(
                select(PatchScanRun.scan_id)
                .where(
                    PatchScanRun.scan_date == scan_date,
                    PatchScanRun.status == "SUCCEEDED",
                )
                .limit(1)
            )
        )


def patch_scan_is_running() -> bool:
    """Return True while the background PatchService scan thread is alive."""
    with _LOCK:
        return bool(_SCAN_THREAD and _SCAN_THREAD.is_alive())


def patch_scan_stop_requested() -> bool:
    """Return the cooperative stop state expected by UI/status code."""
    return _SCAN_STOP.is_set()


def clear_patch_scan_stop() -> None:
    """Clear a previous stop request before starting the next scan."""
    _SCAN_STOP.clear()


def request_patch_scan_stop() -> dict[str, Any]:
    """Request a cooperative stop for the current scan.

    PatchService checks this event throughout device processing. The method does
    not kill the thread or interrupt a database transaction.
    """
    if not patch_scan_is_running():
        _SCAN_STOP.clear()
        return {
            "requested": False,
            "running": False,
            "message": "No patch scan is currently running.",
        }
    _SCAN_STOP.set()
    logger.warning("PATCH_SCAN_STOP_REQUESTED")
    return {
        "requested": True,
        "running": True,
        "message": "Stop requested. The scan will stop safely after the current item.",
    }


def stop_patch_scan() -> dict[str, Any]:
    """Compatibility alias used by older controls."""
    return request_patch_scan_stop()


def _run_scan(source: str) -> None:
    global _LAST_RESULT, _LAST_ERROR, _CURRENT_SOURCE, _SCAN_STARTED_AT
    _SCAN_STOP.clear()
    with _LOCK:
        _CURRENT_SOURCE = source
        _SCAN_STARTED_AT = datetime.now(_timezone())
        _LAST_ERROR = None
    try:
        logger.info("PATCH_SCHEDULED_SCAN_STARTED | source={}", source)
        result = PatchService().scan(
            source=source,
            should_stop=_SCAN_STOP.is_set,
        )
        with _LOCK:
            _LAST_RESULT = result
        logger.info(
            "PATCH_SCHEDULED_SCAN_COMPLETED | source={} | status={} | devices={} | eligible={} | tickets={}",
            source,
            result.get("status"),
            result.get(
                "devices_with_missing_patches",
                result.get("devices_processed", 0),
            ),
            result.get("eligible_devices", 0),
            result.get("tickets_created", 0),
        )
    except Exception as exc:
        with _LOCK:
            _LAST_ERROR = f"{type(exc).__name__}: {exc}"
        logger.exception("PATCH_SCHEDULED_SCAN_FAILED | source={}", source)
    finally:
        with _LOCK:
            _CURRENT_SOURCE = None
            _SCAN_STARTED_AT = None
        _SCAN_STOP.clear()


def request_patch_scan(source: str = "MANUAL") -> dict[str, Any]:
    """Start one background scan unless another scan is active."""
    global _SCAN_THREAD
    with _LOCK:
        if _SCAN_THREAD and _SCAN_THREAD.is_alive():
            return {
                "started": False,
                "running": True,
                "reason": "A patch scan is already running.",
            }
        _SCAN_STOP.clear()
        _SCAN_THREAD = threading.Thread(
            target=_run_scan,
            args=(source,),
            daemon=True,
            name=f"techadmin-patch-scan-{source.casefold()}",
        )
        _SCAN_THREAD.start()
        return {"started": True, "running": True, "source": source}


def run_patch_scan_now(source: str = "MANUAL") -> dict[str, Any]:
    return request_patch_scan(source)


def trigger_patch_scan(source: str = "MANUAL") -> dict[str, Any]:
    return request_patch_scan(source)


def _startup_scan_if_needed() -> None:
    now = datetime.now(_timezone())
    if _successful_scan_exists(now.date()):
        logger.info("PATCH_STARTUP_SCAN_SKIPPED | reason=successful_scan_exists")
        return
    if now >= _scheduled_time(now):
        request_patch_scan("STARTUP_CATCHUP")
    elif _bool_env(
        "PATCH_SCAN_ON_STARTUP",
        _bool_env("PATCH_SCHEDULER_RUN_ON_STARTUP", True),
    ):
        request_patch_scan("STARTUP")
    else:
        logger.info("PATCH_STARTUP_SCAN_SKIPPED | reason=startup_scan_disabled")


def _scheduler_loop() -> None:
    global _NEXT_RUN
    _startup_scan_if_needed()
    while not _SCHEDULER_STOP.is_set():
        now = datetime.now(_timezone())
        target = _calculate_next_run(now)
        with _LOCK:
            _NEXT_RUN = target
        logger.info("PATCH_SCHEDULER_WAITING | next_run={}", target.isoformat())
        woke = _SCHEDULER_WAKE.wait(
            timeout=max(1.0, (target - now).total_seconds())
        )
        _SCHEDULER_WAKE.clear()
        if _SCHEDULER_STOP.is_set():
            break
        if woke:
            continue
        today = datetime.now(_timezone()).date()
        if _successful_scan_exists(today):
            logger.info("PATCH_DAILY_SCAN_SKIPPED | reason=successful_scan_exists")
        else:
            request_patch_scan("SCHEDULED")


def start_patch_scheduler() -> None:
    global _SCHEDULER_THREAD
    if not _bool_env("PATCH_SCHEDULER_ENABLED", True):
        logger.info("PATCH_SCHEDULER_DISABLED")
        return
    with _LOCK:
        if _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive():
            return
        _SCHEDULER_STOP.clear()
        _SCHEDULER_THREAD = threading.Thread(
            target=_scheduler_loop,
            daemon=True,
            name="techadmin-patch-scheduler",
        )
        startup_delay = max(
            0,
            int(os.getenv("PATCH_SCHEDULER_STARTUP_DELAY_SECONDS", "0")),
        )
        if startup_delay:
            logger.info(
                "PATCH_SCHEDULER_STARTUP_DELAY | seconds={}",
                startup_delay,
            )
            _SCHEDULER_WAKE.wait(timeout=startup_delay)
            _SCHEDULER_WAKE.clear()
        _SCHEDULER_THREAD.start()
        logger.info(
            "PATCH_SCHEDULER_STARTED | hour={} | minute={} | timezone={}",
            _hour(),
            _minute(),
            _timezone(),
        )


def stop_patch_scheduler() -> None:
    _SCHEDULER_STOP.set()
    _SCHEDULER_WAKE.set()


def scheduler_status() -> dict[str, Any]:
    with _LOCK:
        scheduler_running = bool(
            _SCHEDULER_THREAD and _SCHEDULER_THREAD.is_alive()
        )
        scan_running = bool(_SCAN_THREAD and _SCAN_THREAD.is_alive())
        return {
            "running": scheduler_running,
            "scheduler_running": scheduler_running,
            "scan_running": scan_running,
            "stop_requested": _SCAN_STOP.is_set(),
            "current_source": _CURRENT_SOURCE,
            "scan_started_at": (
                _SCAN_STARTED_AT.isoformat() if _SCAN_STARTED_AT else None
            ),
            "next_run_time": _NEXT_RUN.isoformat() if _NEXT_RUN else None,
            "next_run": _NEXT_RUN.isoformat() if _NEXT_RUN else None,
            "last_result": _LAST_RESULT,
            "last_error": _LAST_ERROR,
            "timezone": str(_timezone()),
            "hour": _hour(),
            "minute": _minute(),
            "enabled": _bool_env("PATCH_SCHEDULER_ENABLED", True),
        }


def patch_scheduler_status() -> dict[str, Any]:
    return scheduler_status()


def get_patch_scheduler_status() -> dict[str, Any]:
    return scheduler_status()


def next_patch_run_time() -> str | None:
    return scheduler_status().get("next_run_time")


def ensure_patch_scheduler_started() -> dict[str, Any]:
    start_patch_scheduler()
    return scheduler_status()


def ensure_scheduler_started() -> dict[str, Any]:
    return ensure_patch_scheduler_started()

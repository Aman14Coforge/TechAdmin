"""APScheduler lifecycle for the Infrastructure Agent polling process."""

from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Any

from apscheduler.schedulers.background import (
    BackgroundScheduler,
)
from apscheduler.triggers.interval import (
    IntervalTrigger,
)
from loguru import logger

from App.services.infrastructure.processor import (
    process_infrastructure_sites,
)


_LOCK = threading.Lock()
_SCHEDULER: BackgroundScheduler | None = None

POLL_JOB_ID = "techadmin_infrastructure_site_poll"


def _flag(
    name: str,
    default: str = "false",
) -> bool:
    return (
        os.getenv(name, default)
        .strip()
        .casefold()
        in {
            "1",
            "true",
            "yes",
            "on",
        }
    )


def _poll_interval_minutes() -> int:
    try:
        value = int(
            os.getenv(
                "INFRA_POLL_INTERVAL_MINUTES",
                "10",
            )
        )
    except ValueError:
        value = 10

    return max(1, value)


def _run_infrastructure_poll() -> None:
    """
    Execute one protected Infrastructure Agent polling cycle.

    Exceptions are logged instead of terminating the APScheduler worker.
    """
    logger.info(
        "INFRASTRUCTURE_SCHEDULED_POLL_STARTED | "
        "started_at={}",
        datetime.now().isoformat(
            timespec="seconds"
        ),
    )

    try:
        result = process_infrastructure_sites()

        logger.info(
            "INFRASTRUCTURE_SCHEDULED_POLL_COMPLETED | "
            "alerts={} | tickets_attempted={} | "
            "tickets_created={} | emails_sent={} | "
            "skipped={} | errors={}",
            result.get("alerts", 0),
            result.get("tickets_attempted", 0),
            result.get("tickets_created", 0),
            result.get("emails_sent", 0),
            result.get("skipped", 0),
            len(result.get("errors") or []),
        )

    except Exception as exc:
        logger.exception(
            "INFRASTRUCTURE_SCHEDULED_POLL_FAILED | "
            "error_type={} | error={}",
            type(exc).__name__,
            str(exc),
        )


def start_infrastructure_scheduler(
) -> BackgroundScheduler | None:
    """
    Start the Infrastructure Agent scheduler once per application process.
    """
    global _SCHEDULER

    if not _flag(
        "INFRA_SCHEDULER_ENABLED",
        "true",
    ):
        logger.info(
            "Infrastructure scheduler is disabled "
            "through INFRA_SCHEDULER_ENABLED."
        )
        return None

    with _LOCK:
        if (
            _SCHEDULER is not None
            and _SCHEDULER.running
        ):
            return _SCHEDULER

        interval_minutes = (
            _poll_interval_minutes()
        )

        timezone_name = os.getenv(
            "INFRA_SCHEDULER_TIMEZONE",
            "Asia/Kolkata",
        ).strip() or "Asia/Kolkata"

        scheduler = BackgroundScheduler(
            timezone=timezone_name,
            daemon=True,
        )

        scheduler.add_job(
            _run_infrastructure_poll,
            trigger=IntervalTrigger(
                minutes=interval_minutes,
                timezone=timezone_name,
            ),
            id=POLL_JOB_ID,
            name=(
                "TechAdmin Infrastructure Agent "
                "site-health poll"
            ),
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            misfire_grace_time=max(
                60,
                interval_minutes * 60,
            ),
        )

        scheduler.start()

        _SCHEDULER = scheduler

        logger.info(
            "INFRASTRUCTURE_SCHEDULER_STARTED | "
            "interval_minutes={} | timezone={}",
            interval_minutes,
            timezone_name,
        )

        if _flag(
            "INFRA_POLL_RUN_ON_STARTUP",
            "true",
        ):
            scheduler.add_job(
                _run_infrastructure_poll,
                id=(
                    "techadmin_infrastructure_"
                    "startup_poll"
                ),
                name=(
                    "TechAdmin Infrastructure Agent "
                    "startup poll"
                ),
                replace_existing=True,
                max_instances=1,
                coalesce=True,
            )

            logger.info(
                "Infrastructure startup poll queued."
            )

        return scheduler


def stop_infrastructure_scheduler() -> bool:
    """
    Stop the Infrastructure Agent scheduler in the current process.
    """
    global _SCHEDULER

    with _LOCK:
        if (
            _SCHEDULER is None
            or not _SCHEDULER.running
        ):
            return False

        _SCHEDULER.shutdown(
            wait=False
        )
        _SCHEDULER = None

        logger.info(
            "Infrastructure scheduler stopped."
        )

        return True


def scheduler_status() -> dict[str, Any]:
    """
    Return scheduler and polling-job status for the Streamlit page.
    """
    scheduler = _SCHEDULER

    job = (
        scheduler.get_job(POLL_JOB_ID)
        if scheduler is not None
        else None
    )

    next_run_time = (
        job.next_run_time
        if job is not None
        else None
    )

    return {
        "enabled": _flag(
            "INFRA_SCHEDULER_ENABLED",
            "true",
        ),
        "running": bool(
            scheduler is not None
            and scheduler.running
        ),
        "job_registered": job is not None,
        "next_run_time": (
            next_run_time.isoformat()
            if next_run_time is not None
            else None
        ),
        "interval_minutes": (
            _poll_interval_minutes()
        ),
    }
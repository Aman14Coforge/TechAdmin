"""Idempotent startup for TechAdmin patch background services."""
from __future__ import annotations

import threading
from typing import Any
from loguru import logger
from App.services.patch.scheduler import (
    ensure_patch_scheduler_started,
    scheduler_status,
)

_LOCK = threading.Lock()
_STARTED = False


def start_patch_background_services() -> dict[str, Any]:
    global _STARTED
    with _LOCK:
        if not _STARTED:
            ensure_patch_scheduler_started()
            _STARTED = True
            logger.info("PATCH_BACKGROUND_SERVICES_STARTED")
    return scheduler_status()


def ensure_patch_background_services_started() -> dict[str, Any]:
    return start_patch_background_services()

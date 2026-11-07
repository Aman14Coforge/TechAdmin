"""Idempotent Infrastructure Agent service bootstrap."""
from __future__ import annotations

import threading

from App.services.infrastructure.public_download import start_public_download_service
from App.services.infrastructure.scheduler import start_infrastructure_scheduler
from App.services.infrastructure.state_repository import InfrastructureStateRepository

_LOCK = threading.Lock()
_STARTED = False


def start_infrastructure_background_services() -> None:
    global _STARTED
    with _LOCK:
        if _STARTED:
            return
        InfrastructureStateRepository().ensure_schema()
        start_public_download_service()
        start_infrastructure_scheduler()
        _STARTED = True

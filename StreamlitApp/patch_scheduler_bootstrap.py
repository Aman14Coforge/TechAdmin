"""Start the patch scheduler once when imported by StreamlitApp/app.py."""
from __future__ import annotations

from loguru import logger

from App.services.patch.scheduler import start_patch_scheduler

try:
    start_patch_scheduler()
except Exception:
    logger.exception("PATCH_SCHEDULER_BOOTSTRAP_FAILED")

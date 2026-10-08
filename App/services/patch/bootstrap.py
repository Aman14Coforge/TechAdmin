"""Patch scheduler bootstrap imported by both FastAPI and Streamlit."""
from App.services.patch.scheduler import ensure_patch_scheduler_started

def start_patch_background_services() -> None:
    ensure_patch_scheduler_started()

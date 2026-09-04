"""
Streamlit Flow Service
Purpose: Thin service layer between the Streamlit UI and the existing TechAdmin flow.

This module contains NO business logic of its own. It reuses the same
DemoFlow class that `python Scripts/demo_flow.py` runs, so the UI and the
terminal always behave identically.
"""

from __future__ import annotations

import sys
import uuid
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------------
# Project bootstrap
# Streamlit is started from the project root, but we add the paths explicitly
# so the app also works if it is launched from somewhere else.
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "Scripts"

for path in (PROJECT_ROOT, SCRIPTS_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(PROJECT_ROOT / ".env")

from loguru import logger  # noqa: E402

from App.utils.config import Config  # noqa: E402

# Scripts/ is not a package, which is why SCRIPTS_DIR was added to sys.path above.
# Importing DemoFlow (instead of copying its logic) keeps the UI in step with
# the terminal demo automatically.
from demo_flow import DemoFlow  # noqa: E402


LOG_FILE = PROJECT_ROOT / "logs" / "techadmin.log"


class FlowService:
    """Runs a user query through the complete TechAdmin workflow."""

    def __init__(self) -> None:
        # Building DemoFlow creates the Ollama client and the Graph client,
        # so this should happen once per session, not once per query.
        self.demo = DemoFlow()

    def run_query(self, user_query: str) -> Dict[str, Any]:
        """
        Run one user query through the full pipeline.

        The pipeline is: unified intent + metadata extraction with Ollama,
        then routing, then the Identity Agent, then response formatting.
        This is exactly what `python Scripts/demo_flow.py` does.

        Args:
            user_query: The user's request in plain English, for example
                "Get details for amit.bhagat@coforge.com" or
                "Reset password for aman.gupta"

        Returns:
            The response dict produced by DemoFlow.execute_flow(), containing
            success, request_id, intent, message, metadata, result and error.
        """
        user_query = (user_query or "").strip()
        request_id = f"ui_{uuid.uuid4().hex[:8]}"

        if not user_query:
            return {
                "success": False,
                "request_id": request_id,
                "intent": None,
                "message": "Please enter a request.",
                "metadata": {},
                "result": None,
                "error": "Empty query",
            }

        logger.info(f"UI query | request_id={request_id} | query={user_query}")

        try:
            return self.demo.execute_flow(user_query, request_id=request_id)
        except Exception as exc:
            # DemoFlow already handles its own errors, so reaching here means
            # something unexpected happened. Show it rather than a blank screen.
            logger.error(f"UI query failed: {exc}", exc_info=True)
            return {
                "success": False,
                "request_id": request_id,
                "intent": None,
                "message": "An unexpected error occurred while processing the request.",
                "metadata": {},
                "result": None,
                "error": str(exc),
            }


# ---------------------------------------------------------------------------
# Environment helpers, used by the sidebar
# ---------------------------------------------------------------------------
def get_config_status() -> Dict[str, Any]:
    """Report which settings are present, without revealing any secret values."""
    return {
        "ollama_host": Config.OLLAMA_HOST,
        "model_name": Config.MODEL_NAME,
        "graph_client_id": bool(Config.GRAPH_CLIENT_ID),
        "graph_client_secret": bool(Config.GRAPH_CLIENT_SECRET),
        "graph_tenant_id": bool(Config.GRAPH_TENANT_ID),
        "config_valid": Config.validate(),
    }


def check_ollama() -> tuple[bool, str]:
    """
    Check that the Ollama server is reachable and that the model is present.

    Returns:
        Tuple of (is_ok, message).
    """
    import requests

    try:
        response = requests.get(f"{Config.OLLAMA_HOST}/api/tags", timeout=5)
        response.raise_for_status()

        models = [m.get("name", "") for m in response.json().get("models", [])]

        if any(m.startswith(Config.MODEL_NAME.split(":")[0]) for m in models):
            return True, f"Connected. Model '{Config.MODEL_NAME}' is available."

        return False, (
            f"Ollama is running, but '{Config.MODEL_NAME}' was not found. "
            f"Available: {', '.join(models) or 'none'}"
        )

    except Exception as exc:
        return False, f"Cannot reach Ollama at {Config.OLLAMA_HOST} ({exc})"

"""Streamlit service adapter for the TechAdmin DemoFlow."""
from __future__ import annotations

import copy
import getpass
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(PROJECT_ROOT / ".env", override=False)

from loguru import logger  # noqa: E402
from App.utils.config import Config, Logger  # noqa: E402
Logger.setup()
from Scripts.demo_flow import DemoFlow  # noqa: E402

LOG_FILE = PROJECT_ROOT / "logs" / "techadmin.log"


class FlowService:
    """Run UI requests through guardrails, extraction, MCP, and tools."""

    def __init__(self) -> None:
        self.demo = DemoFlow()
        self.requester_id = os.getenv("TECHADMIN_REQUESTER_ID") or self._windows_identity()
        self.requester_role = os.getenv(
            "TECHADMIN_REQUESTER_ROLE",
            os.getenv("GUARDRAIL_DEFAULT_ROLE", "helpdesk"),
        ).strip().casefold()
        logger.info(
            "FLOW_SERVICE_INITIALIZED | requester_id={} | requester_role={} | execution_identity={}",
            self.requester_id,
            self.requester_role,
            self._windows_identity(),
        )

    @staticmethod
    def _windows_identity() -> str:
        domain = os.getenv("USERDOMAIN", "").strip()
        username = getpass.getuser().strip()
        return f"{domain}\\{username}" if domain else username

    @staticmethod
    def _extract_dashboard_password(response: Dict[str, Any]) -> Dict[str, Any] | None:
        tool_result = response.get("tool_result")
        if not isinstance(tool_result, dict):
            return None
        result = tool_result.get("result")
        if not isinstance(result, dict):
            return None

        password = None
        for key in ("temporary_password", "new_password"):
            candidate = result.pop(key, None)
            if isinstance(candidate, str) and candidate and candidate != "[redacted]":
                password = candidate
                break
        if not password:
            return None

        result["temporary_password_redacted"] = True
        result["temporary_password_displayed_on_dashboard"] = True
        metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
        return {
            "password": password,
            "user": (
                result.get("user_principal_name")
                or result.get("user_principal")
                or result.get("user_name")
                or metadata.get("email")
                or metadata.get("username")
                or "Unknown user"
            ),
            "backend": result.get("backend"),
            "operation_id": tool_result.get("operation_id"),
        }

    def run_query(
        self,
        user_query: str,
        *,
        confirmed: bool = False,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> Dict[str, Any]:
        query = user_query.strip() if isinstance(user_query, str) else ""
        resolved_request_id = request_id or f"ui_{uuid.uuid4().hex[:8]}"
        if not query:
            return {
                "success": False, "request_id": resolved_request_id,
                "correlation_id": correlation_id, "intent": None,
                "message": "Please enter a request.", "metadata": {},
                "result": None, "error": "Empty query",
            }

        logger.info(
            "UI_QUERY_RECEIVED | request_id={} | confirmed={} | requester_id={} | requester_role={}",
            resolved_request_id, confirmed, self.requester_id, self.requester_role,
        )
        try:
            response = self.demo.execute_flow(
                user_input=query,
                request_id=resolved_request_id,
                correlation_id=correlation_id,
                confirmed=confirmed,
                requester_id=self.requester_id,
                requester_role=self.requester_role,
            )
            if not isinstance(response, dict):
                raise TypeError("DemoFlow returned a non-dictionary response")

            safe_response = copy.deepcopy(response)
            dashboard_secret = self._extract_dashboard_password(safe_response)
            if dashboard_secret:
                safe_response["_dashboard_secret"] = dashboard_secret
            safe_response["execution_context"] = {
                "windows_identity": self._windows_identity(),
                "requester_id": self.requester_id,
                "requester_role": self.requester_role,
            }
            return safe_response
        except Exception as exc:
            logger.exception("UI_QUERY_FAILED | request_id={} | error_type={}", resolved_request_id, type(exc).__name__)
            return {
                "success": False, "request_id": resolved_request_id,
                "correlation_id": correlation_id, "intent": None,
                "message": "An unexpected error occurred while processing the request.",
                "metadata": {}, "result": None, "error": type(exc).__name__,
                "execution_context": {
                    "windows_identity": self._windows_identity(),
                    "requester_id": self.requester_id,
                    "requester_role": self.requester_role,
                },
            }


def get_config_status() -> Dict[str, Any]:
    domain = os.getenv("USERDOMAIN", "").strip()
    username = getpass.getuser().strip()
    identity = f"{domain}\\{username}" if domain else username
    env_true = lambda name: os.getenv(name, "false").strip().casefold() == "true"
    return {
        "ollama_host": Config.OLLAMA_HOST,
        "model_name": Config.MODEL_NAME,
        "graph_client_id": bool(Config.GRAPH_CLIENT_ID),
        "graph_client_secret": bool(Config.GRAPH_CLIENT_SECRET),
        "graph_tenant_id": bool(Config.GRAPH_TENANT_ID),
        "config_valid": Config.validate(),
        "execution_identity": identity,
        "execution_computer": os.getenv("COMPUTERNAME"),
        "requester_role": os.getenv("TECHADMIN_REQUESTER_ROLE", os.getenv("GUARDRAIL_DEFAULT_ROLE", "helpdesk")),
        "powershell_operations_enabled": env_true("ENABLE_POWERSHELL_OPERATIONS"),
        "destructive_operations_enabled": env_true("ENABLE_DESTRUCTIVE_OPERATIONS"),
    }


def check_ollama() -> tuple[bool, str]:
    import requests
    try:
        response = requests.get(f"{Config.OLLAMA_HOST}/api/tags", timeout=5)
        response.raise_for_status()
        models = [m.get("name", "") for m in response.json().get("models", [])]
        prefix = Config.MODEL_NAME.split(":", 1)[0]
        if any(name.startswith(prefix) for name in models):
            return True, f"Connected. Model '{Config.MODEL_NAME}' is available."
        return False, f"Ollama is running, but '{Config.MODEL_NAME}' was not found."
    except Exception as exc:
        return False, f"Cannot reach Ollama at {Config.OLLAMA_HOST} ({type(exc).__name__})"

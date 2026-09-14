"""
Streamlit Flow Service

Purpose:
    Connect the Streamlit UI to the existing TechAdmin DemoFlow while
    preserving guardrail confirmation, requester context, correlation IDs,
    MCP execution evidence, and temporary-password dashboard handling.
"""

from __future__ import annotations

import copy
import getpass
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Dict


# ---------------------------------------------------------------------------
# Project bootstrap
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "Scripts"

for path in (PROJECT_ROOT, SCRIPTS_DIR):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)


# ---------------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------------

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    PROJECT_ROOT / ".env",
    override=False,
)


# ---------------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------------

from loguru import logger  # noqa: E402

from App.utils.config import Config  # noqa: E402
from Scripts.demo_flow import DemoFlow  # noqa: E402


LOG_FILE = PROJECT_ROOT / "logs" / "techadmin.log"


class FlowService:
    """
    Run user requests through the complete TechAdmin workflow.

    The service passes trusted confirmation and caller context to DemoFlow.
    A generated temporary password is separated from the ordinary response
    so the Streamlit UI can display it in its dedicated dashboard section.
    """

    def __init__(self) -> None:
        self.demo = DemoFlow()

        self.requester_id = (
            os.getenv("TECHADMIN_REQUESTER_ID")
            or self._windows_identity()
        )

        self.requester_role = os.getenv(
            "TECHADMIN_REQUESTER_ROLE",
            os.getenv(
                "GUARDRAIL_DEFAULT_ROLE",
                "helpdesk",
            ),
        ).strip().casefold()

        logger.info(
            "FLOW_SERVICE_INITIALIZED | "
            "demo_flow={} | requester_id={} | requester_role={} | "
            "execution_identity={}",
            type(self.demo).__name__,
            self.requester_id,
            self.requester_role,
            self._windows_identity(),
        )

    @staticmethod
    def _windows_identity() -> str:
        """Return the account that owns the current Streamlit process."""

        domain = os.getenv("USERDOMAIN", "").strip()
        username = getpass.getuser().strip()

        if domain:
            return f"{domain}\\{username}"

        return username

    @staticmethod
    def _extract_dashboard_password(
        response: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """
        Remove a generated password from the normal response and return it
        through a transient dashboard-only object.

        Both `new_password` and `temporary_password` are supported so this
        works with the guardrail-compatible and earlier hybrid tools.
        """

        tool_result = response.get("tool_result")

        if not isinstance(tool_result, dict):
            return None

        result = tool_result.get("result")

        if not isinstance(result, dict):
            return None

        temporary_password: str | None = None

        for password_key in (
            "new_password",
            "temporary_password",
        ):
            candidate = result.pop(
                password_key,
                None,
            )

            if (
                isinstance(candidate, str)
                and candidate
                and candidate.casefold() != "[redacted]"
            ):
                temporary_password = candidate
                break

        if temporary_password is None:
            return None

        result["temporary_password_redacted"] = True
        result["temporary_password_displayed_on_dashboard"] = True

        metadata = response.get("metadata")

        if not isinstance(metadata, dict):
            metadata = {}

        user_identifier = (
            result.get("user_principal_name")
            or result.get("user_principal")
            or result.get("user_name")
            or metadata.get("email")
            or metadata.get("username")
            or "Unknown user"
        )

        return {
            "password": temporary_password,
            "backend": result.get("backend"),
            "user": user_identifier,
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
        """
        Run one user request through DemoFlow.

        `confirmed=True` must come only from the Streamlit confirmation
        control. The same request and correlation IDs are reused for the
        confirmed retry.
        """

        normalized_query = (
            user_query.strip()
            if isinstance(user_query, str)
            else ""
        )

        resolved_request_id = (
            request_id
            or f"ui_{uuid.uuid4().hex[:8]}"
        )

        if not normalized_query:
            return {
                "success": False,
                "request_id": resolved_request_id,
                "correlation_id": correlation_id,
                "intent": None,
                "message": "Please enter a request.",
                "metadata": {},
                "result": None,
                "error": "Empty query",
            }

        logger.info(
            "UI_QUERY_RECEIVED | request_id={} | correlation_id={} | "
            "query_length={} | confirmed={} | requester_id={} | "
            "requester_role={} | execution_identity={}",
            resolved_request_id,
            correlation_id,
            len(normalized_query),
            confirmed,
            self.requester_id,
            self.requester_role,
            self._windows_identity(),
        )

        try:
            workflow_response = self.demo.execute_flow(
                user_input=normalized_query,
                request_id=resolved_request_id,
                correlation_id=correlation_id,
                confirmed=bool(confirmed),
                requester_id=self.requester_id,
                requester_role=self.requester_role,
            )

            if not isinstance(workflow_response, dict):
                raise TypeError(
                    "DemoFlow.execute_flow() returned a non-dictionary response."
                )

            safe_response = copy.deepcopy(
                workflow_response
            )

            dashboard_secret = self._extract_dashboard_password(
                safe_response
            )

            if dashboard_secret is not None:
                safe_response["_dashboard_secret"] = dashboard_secret

            safe_response["execution_context"] = {
                "windows_identity": self._windows_identity(),
                "requester_id": self.requester_id,
                "requester_role": self.requester_role,
            }

            logger.info(
                "UI_QUERY_COMPLETED | request_id={} | correlation_id={} | "
                "intent={} | success={} | guardrail_action={} | "
                "confirmation_required={} | confirmed={} | "
                "dashboard_secret_present={}",
                safe_response.get("request_id"),
                safe_response.get("correlation_id"),
                safe_response.get("intent"),
                safe_response.get("success"),
                safe_response.get("guardrail_action"),
                safe_response.get("confirmation_required"),
                confirmed,
                dashboard_secret is not None,
            )

            return safe_response

        except Exception as exc:
            logger.exception(
                "UI_QUERY_FAILED | request_id={} | error_type={}",
                resolved_request_id,
                type(exc).__name__,
            )

            return {
                "success": False,
                "request_id": resolved_request_id,
                "correlation_id": correlation_id,
                "intent": None,
                "message": (
                    "An unexpected error occurred while processing the request."
                ),
                "metadata": {},
                "result": None,
                "error": type(exc).__name__,
                "execution_context": {
                    "windows_identity": self._windows_identity(),
                    "requester_id": self.requester_id,
                    "requester_role": self.requester_role,
                },
            }


# ---------------------------------------------------------------------------
# Sidebar helpers
# ---------------------------------------------------------------------------


def _environment_flag(name: str) -> bool:
    """Read a true/false environment flag."""

    return os.getenv(
        name,
        "false",
    ).strip().casefold() in {
        "true",
        "1",
        "yes",
        "on",
    }


def get_config_status() -> Dict[str, Any]:
    """Return environment status without exposing secret values."""

    domain = os.getenv("USERDOMAIN", "").strip()
    username = getpass.getuser().strip()

    execution_identity = (
        f"{domain}\\{username}"
        if domain
        else username
    )

    return {
        "ollama_host": Config.OLLAMA_HOST,
        "model_name": Config.MODEL_NAME,
        "graph_client_id": bool(Config.GRAPH_CLIENT_ID),
        "graph_client_secret": bool(Config.GRAPH_CLIENT_SECRET),
        "graph_tenant_id": bool(Config.GRAPH_TENANT_ID),
        "config_valid": Config.validate(),
        "execution_identity": execution_identity,
        "execution_computer": os.getenv("COMPUTERNAME"),
        "requester_id": (
            os.getenv("TECHADMIN_REQUESTER_ID")
            or execution_identity
        ),
        "requester_role": os.getenv(
            "TECHADMIN_REQUESTER_ROLE",
            os.getenv(
                "GUARDRAIL_DEFAULT_ROLE",
                "helpdesk",
            ),
        ),
        "powershell_operations_enabled": _environment_flag(
            "ENABLE_POWERSHELL_OPERATIONS"
        ),
        "destructive_operations_enabled": _environment_flag(
            "ENABLE_DESTRUCTIVE_OPERATIONS"
        ),
    }


def check_ollama() -> tuple[bool, str]:
    """Check whether Ollama and the configured model are available."""

    import requests

    try:
        response = requests.get(
            f"{Config.OLLAMA_HOST}/api/tags",
            timeout=5,
        )
        response.raise_for_status()

        models = [
            model.get("name", "")
            for model in response.json().get(
                "models",
                [],
            )
        ]

        model_prefix = Config.MODEL_NAME.split(
            ":",
            maxsplit=1,
        )[0]

        if any(
            model.startswith(model_prefix)
            for model in models
        ):
            return (
                True,
                f"Connected. Model '{Config.MODEL_NAME}' is available.",
            )

        return (
            False,
            (
                f"Ollama is running, but '{Config.MODEL_NAME}' was not found. "
                f"Available: {', '.join(models) or 'none'}"
            ),
        )

    except Exception as exc:
        return (
            False,
            (
                f"Cannot reach Ollama at {Config.OLLAMA_HOST} "
                f"({type(exc).__name__})"
            ),
        )

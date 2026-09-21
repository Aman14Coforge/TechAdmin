"""
Streamlit Flow Service backed by the TechAdmin LangGraph.

Preserves:
    - App-user login authorization in Streamlit app.py
    - Request and correlation ID reuse
    - Guardrail confirmation workflow
    - Operation-audit database lifecycle
    - Secure password vault, download, and explicit manager email
    - Existing UI helper contracts
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

from App.db.operation_audit import close_request, open_request  # noqa: E402
from App.services.email_service import EmailConfig, send_password_email  # noqa: E402
from App.services.password_file import generate_password_file  # noqa: E402
from App.services.password_vault import password_vault  # noqa: E402
from App.utils.config import Config  # noqa: E402
from App.workflow.graph import TechAdminWorkflow  # noqa: E402


LOG_FILE = PROJECT_ROOT / "logs" / "techadmin.log"


class FlowService:
    """
    Connect the Streamlit UI to the compiled TechAdmin LangGraph.

    FlowService remains a boundary adapter. Business orchestration is owned by
    App.workflow.graph.TechAdminWorkflow. This class owns UI-channel concerns:
    identity context, operation-audit lifecycle, exception containment, and
    non-sensitive execution context added to the response.
    """

    def __init__(self) -> None:
        self.workflow = TechAdminWorkflow()

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
            "orchestration=langgraph | workflow={} | "
            "requester_id={} | requester_role={} | "
            "execution_identity={}",
            type(self.workflow).__name__,
            self.requester_id,
            self.requester_role,
            self._windows_identity(),
        )

    @staticmethod
    def _windows_identity() -> str:
        """Return the operating-system account running Streamlit."""

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
        Retain the historical method contract as a secure no-op.

        Password reset now returns a masked password and opaque password token.
        The original password stays in the server-side password vault and must
        never be moved into Streamlit response state.
        """

        del response
        return None

    @staticmethod
    def _failure_response(
        *,
        request_id: str,
        correlation_id: str,
        error_type: str,
        execution_identity: str,
        requester_id: str,
        requester_role: str,
    ) -> Dict[str, Any]:
        """Build the stable UI response contract for an unexpected failure."""

        return {
            "success": False,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "intent": None,
            "message": (
                "An unexpected error occurred while processing the request."
            ),
            "metadata": {},
            "result": None,
            "error": error_type,
            "orchestration": {
                "engine": "langgraph",
                "graph": "TechAdminWorkflow",
                "compiled": True,
            },
            "execution_context": {
                "windows_identity": execution_identity,
                "requester_id": requester_id,
                "requester_role": requester_role,
            },
        }

    def run_query(
        self,
        user_query: str,
        *,
        confirmed: bool = False,
        request_id: str | None = None,
        correlation_id: str | None = None,
        requester_id: str | None = None,
    ) -> Dict[str, Any]:
        """
        Run one Streamlit request through the compiled LangGraph.

        A fresh request opens an operation-audit row. A confirmation retry uses
        the same request ID and updates the existing row. Every completed graph
        response and every controlled exception closes the audit lifecycle.
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
        resolved_correlation_id = (
            correlation_id
            or f"corr_{uuid.uuid4().hex}"
        )
        resolved_requester_id = requester_id or self.requester_id
        execution_identity = self._windows_identity()

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
            "requester_role={} | execution_identity={} | "
            "orchestration=langgraph",
            resolved_request_id,
            resolved_correlation_id,
            len(normalized_query),
            confirmed,
            resolved_requester_id,
            self.requester_role,
            execution_identity,
        )

        # Open only for the first submission. The trusted confirmation retry
        # reuses the same request ID and updates the already existing row.
        if not confirmed:
            open_request(
                request_id=resolved_request_id,
                user_query=normalized_query,
                requested_by=resolved_requester_id,
                source_channel="WEB",
            )
        # --- END ADDED FOR OPERATION AUDIT ---

        try:
            workflow_response = self.workflow.invoke(
                user_input=normalized_query,
                request_id=resolved_request_id,
                correlation_id=resolved_correlation_id,
                confirmed=bool(confirmed),
                requester_id=resolved_requester_id,
                requester_role=self.requester_role,
            )

            if not isinstance(workflow_response, dict):
                raise TypeError(
                    "TechAdminWorkflow.invoke() returned a "
                    "non-dictionary response."
                )

            safe_response = copy.deepcopy(workflow_response)

            # Kept for compatibility with app.py. Current secure password
            # handling always returns None here.
            dashboard_secret = self._extract_dashboard_password(
                safe_response
            )
            if dashboard_secret is not None:
                safe_response["_dashboard_secret"] = dashboard_secret

            safe_response["execution_context"] = {
                "windows_identity": execution_identity,
                "requester_id": resolved_requester_id,
                "requester_role": self.requester_role,
            }

            logger.info(
                "UI_QUERY_COMPLETED | request_id={} | correlation_id={} | "
                "intent={} | success={} | guardrail_action={} | "
                "confirmation_required={} | confirmed={} | "
                "dashboard_secret_present={} | orchestration=langgraph",
                safe_response.get("request_id"),
                safe_response.get("correlation_id"),
                safe_response.get("intent"),
                safe_response.get("success"),
                safe_response.get("guardrail_action"),
                safe_response.get("confirmation_required"),
                confirmed,
                dashboard_secret is not None,
            )

            try:
                # safe_response has already passed graph output sanitization.
                close_request(
                    resolved_request_id,
                    safe_response,
                )
            except Exception as exc:
                logger.exception(
                    "OPERATION_AUDIT_CLOSE_FAILED | request_id={} | "
                    "error_type={}",
                    resolved_request_id,
                    type(exc).__name__,
                )

            return safe_response

        except Exception as exc:
            logger.exception(
                "UI_QUERY_FAILED | request_id={} | correlation_id={} | "
                "error_type={}",
                resolved_request_id,
                resolved_correlation_id,
                type(exc).__name__,
            )

            # --- ADDED FOR OPERATION AUDIT (Amit Bhagat) ---
            # A crash is an outcome too. Without this the row would stay at
            # RECEIVED and look like an abandoned request.
            close_request(
                resolved_request_id,
                {
                    "success": False,
                    "user_input": normalized_query,
                    "error": type(exc).__name__,
                },
            )
            # --- END ADDED FOR OPERATION AUDIT ---

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
                    "windows_identity": execution_identity,
                    "requester_id": resolved_requester_id,
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
        "orchestration_engine": "langgraph",
        "operation_audit_enabled": True,
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


# ---------------------------------------------------------------------------
# Secure password-delivery helpers
# ---------------------------------------------------------------------------


def build_password_download(password_token: str):
    """Build a password TXT file from a valid server-side vault token."""

    entry = password_vault.get(password_token)

    if entry is None:
        return (
            False,
            None,
            None,
            "That password reset is no longer available. Run the reset again.",
        )

    return generate_password_file(
        username=entry.username,
        password=entry.password,
        manager_name=entry.manager_name,
        manager_email=entry.manager_email,
    )


def send_password_to_manager(password_token: str):
    """Send a temporary password only after an explicit UI action."""

    entry = password_vault.get(password_token)

    if entry is None:
        return (
            False,
            "That password reset is no longer available. Run the reset again.",
            "",
        )

    sent, message = send_password_email(
        manager_email=entry.manager_email,
        manager_name=entry.manager_name,
        username=entry.username,
        employee_name=entry.employee_name,
        password=entry.password,
    )

    return (
        sent,
        message,
        entry.manager_email if sent else "",
    )


def email_is_configured() -> bool:
    """Report whether SMTP settings are present."""

    return EmailConfig.is_configured()

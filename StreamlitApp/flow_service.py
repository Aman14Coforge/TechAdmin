"""
Streamlit Flow Service

Purpose:
    Provide a controlled service layer between the Streamlit dashboard
    and the existing TechAdmin DemoFlow.

The Streamlit UI and terminal workflow use the same DemoFlow
implementation.
"""

from __future__ import annotations

import copy
import sys
import uuid
from pathlib import Path
from typing import Any, Dict

# ---------------------------------------------------------------------
# Project path bootstrap
# ---------------------------------------------------------------------

PROJECT_ROOT = (
    Path(__file__)
    .resolve()
    .parent
    .parent
)

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(
        0,
        str(PROJECT_ROOT),
    )

# ---------------------------------------------------------------------
# Environment loading
# ---------------------------------------------------------------------

from dotenv import load_dotenv  # noqa: E402

load_dotenv(
    PROJECT_ROOT / ".env"
)

# ---------------------------------------------------------------------
# Application imports
# ---------------------------------------------------------------------

from loguru import logger  # noqa: E402

from App.utils.config import Config  # noqa: E402
from Scripts.demo_flow import DemoFlow  # noqa: E402


LOG_FILE = (
    PROJECT_ROOT
    / "logs"
    / "techadmin.log"
)


class FlowService:
    """
    Run user requests through the complete TechAdmin workflow.

    The pipeline includes:

    1. Unified intent and metadata extraction
    2. Agent routing
    3. Identity Agent validation
    4. MCP server and tool selection
    5. Microsoft Graph or PowerShell execution
    6. Structured response formatting
    """

    def __init__(
        self,
    ) -> None:
        self.demo = DemoFlow()

        logger.info(
            "FLOW_SERVICE_INITIALIZED | "
            "demo_flow_class={}",
            type(self.demo).__name__,
        )

    @staticmethod
    def _extract_dashboard_password(
        response: Dict[str, Any],
    ) -> Dict[str, Any] | None:
        """
        Extract a generated temporary password from a workflow response.

        The password is removed from the normal response before that
        response is stored in conversation history or displayed in the
        raw-response section.

        The password is returned separately for display in the current
        Streamlit session.
        """

        tool_result = response.get(
            "tool_result"
        )

        if not isinstance(
            tool_result,
            dict,
        ):
            return None

        result = tool_result.get(
            "result"
        )

        if not isinstance(
            result,
            dict,
        ):
            return None

        temporary_password = result.pop(
            "temporary_password",
            None,
        )

        if (
            not isinstance(
                temporary_password,
                str,
            )
            or not temporary_password
        ):
            return None

        result[
            "temporary_password_redacted"
        ] = True

        result[
            "temporary_password_displayed_on_dashboard"
        ] = True

        metadata = response.get(
            "metadata"
        )

        if not isinstance(
            metadata,
            dict,
        ):
            metadata = {}

        user_identifier = (
            result.get(
                "user_principal_name"
            )
            or result.get(
                "user_name"
            )
            or metadata.get(
                "email"
            )
            or metadata.get(
                "username"
            )
            or "Unknown user"
        )

        return {
            "password":
                temporary_password,

            "backend":
                result.get(
                    "backend"
                ),

            "user":
                user_identifier,

            "operation_id":
                tool_result.get(
                    "operation_id"
                ),
        }

    def run_query(
        self,
        user_query: str,
    ) -> Dict[str, Any]:
        """
        Run one user query through DemoFlow.

        Args:
            user_query:
                User request written in plain English.

        Returns:
            Structured TechAdmin workflow response.

            A generated temporary password, when present, is returned in
            the transient `_dashboard_secret` key. Streamlit must remove
            this key before adding the response to conversation history.
        """

        normalized_query = (
            user_query.strip()
            if isinstance(
                user_query,
                str,
            )
            else ""
        )

        request_id = (
            f"ui_{uuid.uuid4().hex[:8]}"
        )

        if not normalized_query:
            return {
                "success": False,
                "request_id": request_id,
                "intent": None,
                "message": (
                    "Please enter a request."
                ),
                "metadata": {},
                "result": None,
                "error": "Empty query",
            }

        logger.info(
            "UI_QUERY_RECEIVED | "
            "request_id={} | "
            "query_length={}",
            request_id,
            len(normalized_query),
        )

        try:
            workflow_response = (
                self.demo.execute_flow(
                    normalized_query,
                    request_id=request_id,
                )
            )

            if not isinstance(
                workflow_response,
                dict,
            ):
                raise TypeError(
                    "DemoFlow.execute_flow() returned "
                    "a non-dictionary response."
                )

            # Work on a separate response dictionary so the password can
            # be removed before Streamlit stores or downloads it.
            safe_response = copy.deepcopy(
                workflow_response
            )

            dashboard_secret = (
                self._extract_dashboard_password(
                    safe_response
                )
            )

            if dashboard_secret:
                safe_response[
                    "_dashboard_secret"
                ] = dashboard_secret

            logger.info(
                "UI_QUERY_COMPLETED | "
                "request_id={} | "
                "success={} | "
                "intent={} | "
                "dashboard_secret_present={}",
                request_id,
                safe_response.get(
                    "success"
                ),
                safe_response.get(
                    "intent"
                ),
                dashboard_secret is not None,
            )

            return safe_response

        except Exception as exc:
            logger.exception(
                "UI_QUERY_FAILED | "
                "request_id={} | "
                "error_type={}",
                request_id,
                type(exc).__name__,
            )

            return {
                "success": False,
                "request_id": request_id,
                "intent": None,
                "message": (
                    "An unexpected error occurred "
                    "while processing the request."
                ),
                "metadata": {},
                "result": None,
                "error": type(exc).__name__,
            }


# ---------------------------------------------------------------------
# Environment helpers used by the Streamlit sidebar
# ---------------------------------------------------------------------


def get_config_status() -> Dict[str, Any]:
    """
    Report configuration availability without exposing credentials.
    """

    return {
        "ollama_host":
            Config.OLLAMA_HOST,

        "model_name":
            Config.MODEL_NAME,

        "graph_client_id":
            bool(
                Config.GRAPH_CLIENT_ID
            ),

        "graph_client_secret":
            bool(
                Config.GRAPH_CLIENT_SECRET
            ),

        "graph_tenant_id":
            bool(
                Config.GRAPH_TENANT_ID
            ),

        "config_valid":
            Config.validate(),
    }


def check_ollama() -> tuple[
    bool,
    str,
]:
    """
    Check the Ollama server and configured model.
    """

    import requests

    try:
        response = requests.get(
            (
                f"{Config.OLLAMA_HOST}"
                "/api/tags"
            ),
            timeout=5,
        )

        response.raise_for_status()

        models = [
            model.get(
                "name",
                "",
            )
            for model
            in response.json().get(
                "models",
                [],
            )
        ]

        model_prefix = (
            Config.MODEL_NAME.split(
                ":",
                maxsplit=1,
            )[0]
        )

        if any(
            model_name.startswith(
                model_prefix
            )
            for model_name in models
        ):
            return (
                True,
                (
                    "Connected. Model "
                    f"'{Config.MODEL_NAME}' "
                    "is available."
                ),
            )

        return (
            False,
            (
                "Ollama is running, but "
                f"'{Config.MODEL_NAME}' "
                "was not found. Available: "
                f"{', '.join(models) or 'none'}"
            ),
        )

    except Exception as exc:
        return (
            False,
            (
                "Cannot reach Ollama at "
                f"{Config.OLLAMA_HOST} "
                f"({type(exc).__name__})"
            ),
        )
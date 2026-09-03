"""
Complete TechAdmin MCP Flow Demo

Purpose:
    Demonstrate unified extraction, agent routing, Identity Agent
    validation, clarification handling, MCP server selection, MCP tool
    invocation, application-tool execution, and query-history storage.

Flow:
    1. Extract intent and metadata.
    2. Validate intent confidence.
    3. Route intent to the Identity Agent.
    4. Let the Identity Agent validate required fields.
    5. Ask for missing fields when necessary.
    6. Dispatch the request through the selected MCP server.
    7. Invoke the selected MCP tool.
    8. Invoke the existing application tool and API integration.
    9. Save latest result and complete interaction history.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from loguru import logger


# ---------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------

PROJECT_ROOT = Path(
    __file__
).resolve().parent.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

load_dotenv(
    PROJECT_ROOT / ".env",
)


# Imports are intentionally placed after PROJECT_ROOT is added to
# sys.path and after the .env file is loaded.
from App.agents.identity_agent import IdentityAgent
from App.intent.unified_extractor import (
    UnifiedIntentMetadataExtractor,
)
from App.utils.config import Config, Logger
from App.workflow.router import AgentRouter
from App.workflow.state import (
    IdentityMetadata,
    IntentType,
)


OUTPUT_DIRECTORY = (
    PROJECT_ROOT / "output"
)

LATEST_RESULT_PATH = (
    OUTPUT_DIRECTORY
    / "extraction_result.json"
)

ALL_QUERIES_PATH = (
    OUTPUT_DIRECTORY
    / "all_queries.json"
)

LOG_PATH = (
    PROJECT_ROOT
    / "logs"
    / "techadmin.log"
)


# ---------------------------------------------------------------------
# Demo workflow
# ---------------------------------------------------------------------


class DemoFlow:
    """
    End-to-end TechAdmin MCP demonstration.

    The DemoFlow does not select an MCP server or MCP tool. It only:

    1. Extracts intent and metadata.
    2. Routes the intent to an agent.
    3. Calls the Identity Agent.

    The Identity Agent is responsible for:

    - Required-field validation
    - Clarification questions
    - MCP server selection
    - MCP tool selection
    - MCP tool invocation
    """

    MINIMUM_INTENT_CONFIDENCE = 0.70

    def __init__(self) -> None:
        self.extractor = (
            UnifiedIntentMetadataExtractor()
        )

        self.router = AgentRouter()

        self.identity_agent = (
            IdentityAgent()
        )

        logger.info(
            "DEMO_FLOW_INITIALIZED | "
            "extractor={} | router={} | agent={}",
            type(self.extractor).__name__,
            type(self.router).__name__,
            type(self.identity_agent).__name__,
        )

    def execute_flow(
        self,
        user_input: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Execute one complete workflow interaction.

        Args:
            user_input:
                The complete user request. When clarification is in
                progress, this value contains the original request and
                all follow-up information.

            request_id:
                Optional existing request ID. The same request ID is
                preserved during clarification.

            correlation_id:
                Optional existing correlation ID. The same correlation
                ID is preserved during clarification.

        Returns:
            Dictionary containing extraction, routing, agent, MCP, tool,
            validation, and execution information.
        """

        normalized_input = (
            user_input.strip()
            if isinstance(
                user_input,
                str,
            )
            else ""
        )

        request_id = (
            request_id
            or f"demo_{uuid4().hex[:12]}"
        )

        correlation_id = (
            correlation_id
            or f"corr_{uuid4().hex}"
        )

        logger.info(
            "FLOW_STARTED | "
            "request_id={} | "
            "correlation_id={} | "
            "user_input={}",
            request_id,
            correlation_id,
            normalized_input,
        )

        if not normalized_input:
            return self._build_failure_response(
                request_id=request_id,
                correlation_id=correlation_id,
                message="User input cannot be empty.",
                error="Empty user input",
            )

        # -------------------------------------------------------------
        # Step 1: Unified intent and metadata extraction
        # -------------------------------------------------------------

        extraction = (
            self.extractor.extract_all(
                normalized_input
            )
        )

        logger.info(
            "FLOW_EXTRACTION_RESULT | "
            "request_id={} | "
            "correlation_id={} | "
            "success={} | "
            "intent={} | "
            "confidence={}",
            request_id,
            correlation_id,
            extraction.success,
            extraction.intent.value,
            extraction.confidence,
        )

        if not extraction.success:
            return {
                "success": False,
                "request_id": request_id,
                "correlation_id":
                    correlation_id,
                "user_input":
                    normalized_input,
                "intent":
                    extraction.intent.value,
                "confidence":
                    extraction.confidence,
                "explanation":
                    extraction.explanation,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "validation": None,
                "selected_agent": None,
                "selected_mcp_server": None,
                "selected_mcp_tool": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required":
                    False,
                "clarification_question":
                    None,
                "message":
                    extraction.explanation,
                "error":
                    extraction.error,
            }

        # -------------------------------------------------------------
        # Step 2: Confidence check
        # -------------------------------------------------------------

        if (
            extraction.confidence
            < self.MINIMUM_INTENT_CONFIDENCE
        ):
            logger.warning(
                "FLOW_BLOCKED_LOW_CONFIDENCE | "
                "request_id={} | "
                "correlation_id={} | "
                "intent={} | "
                "confidence={} | "
                "required_confidence={}",
                request_id,
                correlation_id,
                extraction.intent.value,
                extraction.confidence,
                self.MINIMUM_INTENT_CONFIDENCE,
            )

            return {
                "success": False,
                "request_id": request_id,
                "correlation_id":
                    correlation_id,
                "user_input":
                    normalized_input,
                "intent":
                    extraction.intent.value,
                "confidence":
                    extraction.confidence,
                "explanation":
                    extraction.explanation,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "validation": None,
                "selected_agent": None,
                "selected_mcp_server": None,
                "selected_mcp_tool": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required":
                    False,
                "clarification_question":
                    None,
                "message": (
                    "The intent confidence is too low "
                    "to continue safely."
                ),
                "error":
                    "Low intent confidence",
            }

        # -------------------------------------------------------------
        # Step 3: Agent routing
        # -------------------------------------------------------------

        try:
            routing = self.router.route(
                extraction.intent,
                extraction.metadata.model_dump(
                    mode="json",
                ),
            )

        except ValueError as exc:
            logger.warning(
                "FLOW_ROUTING_FAILED | "
                "request_id={} | "
                "correlation_id={} | "
                "intent={} | "
                "error={}",
                request_id,
                correlation_id,
                extraction.intent.value,
                str(exc),
            )

            return {
                "success": False,
                "request_id":
                    request_id,
                "correlation_id":
                    correlation_id,
                "user_input":
                    normalized_input,
                "intent":
                    extraction.intent.value,
                "confidence":
                    extraction.confidence,
                "explanation":
                    extraction.explanation,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "validation": None,
                "selected_agent": None,
                "selected_mcp_server": None,
                "selected_mcp_tool": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required":
                    False,
                "clarification_question":
                    None,
                "message":
                    str(exc),
                "error":
                    type(exc).__name__,
            }

        logger.info(
            "FLOW_AGENT_ROUTED | "
            "request_id={} | "
            "correlation_id={} | "
            "intent={} | "
            "selected_agent={}",
            request_id,
            correlation_id,
            extraction.intent.value,
            routing.agent_name,
        )

        if routing.agent_type.value != "identity":
            return {
                "success": False,
                "request_id":
                    request_id,
                "correlation_id":
                    correlation_id,
                "user_input":
                    normalized_input,
                "intent":
                    extraction.intent.value,
                "confidence":
                    extraction.confidence,
                "explanation":
                    extraction.explanation,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "validation": None,
                "selected_agent":
                    routing.agent_name,
                "selected_mcp_server": None,
                "selected_mcp_tool": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required":
                    False,
                "clarification_question":
                    None,
                "message": (
                    "Only the Identity Agent is "
                    "implemented in this demo."
                ),
                "error":
                    "Agent unavailable",
            }

        # -------------------------------------------------------------
        # Step 4: Identity Agent execution
        #
        # IdentityAgent.execute() performs:
        #
        # - Required-field validation
        # - Clarification handling
        # - Username derivation
        # - MCP server selection
        # - MCP tool selection
        # - MCP tool execution
        # -------------------------------------------------------------

        try:
            agent_result = (
                self.identity_agent.execute(
                    operation=
                        extraction.intent,
                    metadata=
                        extraction.metadata,
                    request_id=
                        request_id,
                    correlation_id=
                        correlation_id,
                )
            )

        except Exception as exc:
            logger.exception(
                "FLOW_AGENT_EXECUTION_FAILED | "
                "request_id={} | "
                "correlation_id={} | "
                "intent={} | "
                "error_type={}",
                request_id,
                correlation_id,
                extraction.intent.value,
                type(exc).__name__,
            )

            return {
                "success": False,
                "request_id":
                    request_id,
                "correlation_id":
                    correlation_id,
                "user_input":
                    normalized_input,
                "intent":
                    extraction.intent.value,
                "confidence":
                    extraction.confidence,
                "explanation":
                    extraction.explanation,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "validation": None,
                "selected_agent":
                    routing.agent_name,
                "selected_mcp_server":
                    self._get_mcp_server_name(
                        extraction.intent
                    ),
                "selected_mcp_tool":
                    self._get_mcp_protocol_tool_name(
                        extraction.intent
                    ),
                "selected_tool":
                    self._get_application_tool_name(
                        extraction.intent
                    ),
                "tool_result": None,
                "clarification_required":
                    False,
                "clarification_question":
                    None,
                "message": (
                    "Identity Agent execution failed."
                ),
                "error":
                    type(exc).__name__,
            }

        # -------------------------------------------------------------
        # Step 5: Build response with MCP evidence
        # -------------------------------------------------------------

        selected_mcp_server = (
            self._get_mcp_server_name(
                extraction.intent
            )
            if not agent_result.clarification_required
            else None
        )

        selected_mcp_tool = (
            self._get_mcp_protocol_tool_name(
                extraction.intent
            )
            if not agent_result.clarification_required
            else None
        )

        selected_application_tool = (
            agent_result.selected_tool.value
            if agent_result.selected_tool
            else None
        )

        tool_result = (
            agent_result.tool_result.model_dump(
                mode="json",
            )
            if agent_result.tool_result
            else None
        )

        response = {
            "success":
                agent_result.success,

            "request_id":
                request_id,

            "correlation_id":
                correlation_id,

            "user_input":
                normalized_input,

            "intent":
                extraction.intent.value,

            "confidence":
                extraction.confidence,

            "explanation":
                extraction.explanation,

            "metadata":
                agent_result.metadata.model_dump(
                    mode="json",
                ),

            "validation":
                agent_result.validation.model_dump(
                    mode="json",
                ),

            "selected_agent":
                agent_result.selected_agent,

            "selected_mcp_server":
                selected_mcp_server,

            "selected_mcp_tool":
                selected_mcp_tool,

            "selected_tool":
                selected_application_tool,

            "tool_result":
                tool_result,

            "clarification_required":
                agent_result.clarification_required,

            "clarification_question":
                agent_result.clarification_question,

            "message":
                agent_result.message,

            "error":
                agent_result.error,
        }

        logger.info(
            "FLOW_COMPLETED | "
            "request_id={} | "
            "correlation_id={} | "
            "intent={} | "
            "selected_agent={} | "
            "selected_mcp_server={} | "
            "selected_mcp_tool={} | "
            "selected_tool={} | "
            "tool_status={} | "
            "success={}",
            request_id,
            correlation_id,
            extraction.intent.value,
            agent_result.selected_agent,
            selected_mcp_server,
            selected_mcp_tool,
            selected_application_tool,
            (
                tool_result.get("status")
                if tool_result
                else None
            ),
            agent_result.success,
        )

        return response

    def _get_mcp_server_name(
        self,
        intent: IntentType,
    ) -> str | None:
        """
        Return the deterministically selected MCP server module.
        """

        return (
            self.identity_agent
            .mcp_client
            .SERVER_MODULES
            .get(
                intent.value
            )
        )

    def _get_mcp_protocol_tool_name(
        self,
        intent: IntentType,
    ) -> str | None:
        """
        Return the actual MCP protocol tool name.

        Example:
            password_reset intent
            -> reset_password MCP tool
        """

        return (
            self.identity_agent
            .mcp_client
            .TOOL_NAMES
            .get(
                intent.value
            )
        )

    def _get_application_tool_name(
        self,
        intent: IntentType,
    ) -> str | None:
        """
        Return the existing application-tool name.

        Example:
            password_reset
            -> reset_password_tool
        """

        selected_tool = (
            self.identity_agent
            .TOOL_NAMES
            .get(
                intent
            )
        )

        return (
            selected_tool.value
            if selected_tool
            else None
        )

    @staticmethod
    def _build_failure_response(
        *,
        request_id: str,
        correlation_id: str,
        message: str,
        error: str,
    ) -> dict[str, Any]:
        return {
            "success": False,
            "request_id":
                request_id,
            "correlation_id":
                correlation_id,
            "user_input": None,
            "intent": None,
            "confidence": 0.0,
            "explanation": None,
            "metadata": None,
            "validation": None,
            "selected_agent": None,
            "selected_mcp_server": None,
            "selected_mcp_tool": None,
            "selected_tool": None,
            "tool_result": None,
            "clarification_required": False,
            "clarification_question": None,
            "message": message,
            "error": error,
        }


# ---------------------------------------------------------------------
# History persistence
# ---------------------------------------------------------------------


def _read_history() -> list[dict[str, Any]]:
    """
    Read all previously stored interactions.

    If the file does not exist, return an empty list. If the file is
    corrupted, preserve the application flow and start a new list after
    logging the failure.
    """

    if not ALL_QUERIES_PATH.exists():
        return []

    try:
        parsed = json.loads(
            ALL_QUERIES_PATH.read_text(
                encoding="utf-8",
            )
        )

        if isinstance(
            parsed,
            list,
        ):
            return parsed

        logger.warning(
            "QUERY_HISTORY_INVALID | "
            "reason=root_value_is_not_list"
        )

        return []

    except (
        OSError,
        json.JSONDecodeError,
    ):
        logger.exception(
            "QUERY_HISTORY_READ_FAILED | "
            "path={}",
            ALL_QUERIES_PATH,
        )

        return []


def save_result(
    *,
    original_input: str,
    complete_input: str,
    response: dict[str, Any],
) -> None:
    """
    Save the latest interaction and append the interaction to history.

    Files:

        output/extraction_result.json
            Latest workflow response only.

        output/all_queries.json
            Complete interaction history.
    """

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized_response = json.dumps(
        response,
        indent=2,
        ensure_ascii=False,
    )

    LATEST_RESULT_PATH.write_text(
        serialized_response,
        encoding="utf-8",
    )

    history = _read_history()

    history_entry = {
        "recorded_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "original_user_input":
            original_input,
        "complete_user_input":
            complete_input,
        "request_id":
            response.get(
                "request_id"
            ),
        "correlation_id":
            response.get(
                "correlation_id"
            ),
        "intent":
            response.get(
                "intent"
            ),
        "selected_agent":
            response.get(
                "selected_agent"
            ),
        "selected_mcp_server":
            response.get(
                "selected_mcp_server"
            ),
        "selected_mcp_tool":
            response.get(
                "selected_mcp_tool"
            ),
        "selected_tool":
            response.get(
                "selected_tool"
            ),
        "response":
            response,
    }

    history.append(
        history_entry
    )

    temporary_path = (
        ALL_QUERIES_PATH.with_suffix(
            ".tmp"
        )
    )

    temporary_path.write_text(
        json.dumps(
            history,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        ALL_QUERIES_PATH
    )

    logger.info(
        "FLOW_RESULT_SAVED | "
        "latest_result_path={} | "
        "history_path={} | "
        "history_count={}",
        LATEST_RESULT_PATH,
        ALL_QUERIES_PATH,
        len(history),
    )


# ---------------------------------------------------------------------
# Terminal display
# ---------------------------------------------------------------------


def print_response(
    response: dict[str, Any],
) -> None:
    """
    Print the complete workflow response and a concise MCP execution
    proof section.
    """

    print()
    print("=" * 80)
    print("TECHADMIN MCP WORKFLOW RESULT")
    print("=" * 80)

    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print("INTENT AND IDENTITY EXTRACTION")
    print("-" * 80)

    metadata = (
        response.get("metadata")
        or {}
    )

    validation = (
        response.get("validation")
        or {}
    )

    print(
        f"Intent              : "
        f"{response.get('intent')}"
    )

    print(
        f"Confidence          : "
        f"{response.get('confidence')}"
    )

    print(
        f"Username            : "
        f"{metadata.get('username')}"
    )

    print(
        f"Username source     : "
        f"{metadata.get('username_source')}"
    )

    print(
        f"Email               : "
        f"{metadata.get('email')}"
    )

    print(
        f"User ID             : "
        f"{metadata.get('user_id')}"
    )

    print(
        f"Employee number     : "
        f"{metadata.get('employee_number')}"
    )

    print(
        f"Group name          : "
        f"{metadata.get('group_name')}"
    )

    print(
        f"Time window         : "
        f"{metadata.get('time_window')}"
    )

    print(
        f"Metadata valid      : "
        f"{validation.get('is_valid')}"
    )

    print(
        f"Missing fields      : "
        f"{validation.get('missing_fields', [])}"
    )

    print(
        f"Derived fields      : "
        f"{validation.get('derived_fields', [])}"
    )

    print()
    print("MCP EXECUTION PROOF")
    print("-" * 80)

    print(
        f"Selected agent      : "
        f"{response.get('selected_agent')}"
    )

    print(
        f"Selected MCP server : "
        f"{response.get('selected_mcp_server')}"
    )

    print(
        f"Selected MCP tool   : "
        f"{response.get('selected_mcp_tool')}"
    )

    print(
        f"Application tool    : "
        f"{response.get('selected_tool')}"
    )

    tool_result = response.get(
        "tool_result"
    )

    if tool_result:
        print(
            f"Tool status         : "
            f"{tool_result.get('status')}"
        )

        print(
            f"Tool success        : "
            f"{tool_result.get('success')}"
        )

        print(
            f"Operation ID        : "
            f"{tool_result.get('operation_id')}"
        )

        print(
            f"API pending         : "
            f"{tool_result.get('api_integration_pending')}"
        )

        print()
        print(
            "[MCP PROOF] The Identity Agent selected an MCP "
            "server and invoked the registered MCP tool."
        )

        print(
            "[TOOL PROOF] The MCP server invoked the existing "
            "application tool and returned a structured result."
        )

    elif response.get(
        "clarification_required"
    ):
        print(
            "Tool status         : not_called"
        )

        print(
            f"Agent question      : "
            f"{response.get('clarification_question')}"
        )

        print()
        print(
            "[BLOCKED] No MCP server or MCP tool was called "
            "because mandatory information is missing."
        )

    else:
        print(
            "Tool status         : not_called"
        )

        print()
        print(
            "[NOT CALLED] The workflow did not invoke an MCP "
            "tool."
        )

    print()
    print(
        f"Message             : "
        f"{response.get('message')}"
    )

    if response.get("error"):
        print(
            f"Error               : "
            f"{response.get('error')}"
        )

    print("=" * 80)
    print()


# ---------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------


def main() -> None:
    """
    Run the interactive TechAdmin MCP demonstration.
    """

    Logger.setup()

    demo = DemoFlow()

    print()
    print("=" * 80)
    print("TECHADMIN IDENTITY MCP TOOL ROUTING DEMO")
    print("=" * 80)

    print(
        f"Latest result : "
        f"{LATEST_RESULT_PATH}"
    )

    print(
        f"All queries   : "
        f"{ALL_QUERIES_PATH}"
    )

    print(
        f"Runtime logs  : "
        f"{LOG_PATH}"
    )

    print()
    print(
        "Type 'exit' or 'quit' to stop."
    )
    print()

    pending_query: str | None = None
    pending_request_id: str | None = None
    pending_correlation_id: str | None = None

    while True:
        prompt = (
            "Provide missing information: "
            if pending_query
            else "Enter user query: "
        )

        user_input = input(
            prompt
        ).strip()

        if user_input.casefold() in {
            "exit",
            "quit",
        }:
            print(
                "TechAdmin MCP demo stopped."
            )
            break

        if not user_input:
            print(
                "Please enter a request."
            )
            continue

        if pending_query:
            complete_input = (
                f"{pending_query}. "
                f"Additional information: "
                f"{user_input}"
            )
        else:
            complete_input = user_input

        response = demo.execute_flow(
            user_input=complete_input,
            request_id=pending_request_id,
            correlation_id=(
                pending_correlation_id
            ),
        )

        print_response(
            response
        )

        save_result(
            original_input=user_input,
            complete_input=complete_input,
            response=response,
        )

        if response.get(
            "clarification_required"
        ):
            pending_query = (
                complete_input
            )

            pending_request_id = (
                response["request_id"]
            )

            pending_correlation_id = (
                response["correlation_id"]
            )

            print(
                response.get(
                    "clarification_question"
                )
            )

            print()

        else:
            pending_query = None
            pending_request_id = None
            pending_correlation_id = None


if __name__ == "__main__":
    if not Config.validate():
        logger.error(
            "Configuration validation failed"
        )

        sys.exit(1)

    try:
        main()

    except KeyboardInterrupt:
        print(
            "\nDemo interrupted."
        )

        sys.exit(0)
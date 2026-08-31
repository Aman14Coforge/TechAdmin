"""
Complete TechAdmin Flow Demo

Purpose:
    Demonstrate unified extraction, routing, Identity Agent validation,
    clarification handling and correct tool execution.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from dotenv import load_dotenv
from loguru import logger


PROJECT_ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(
    0,
    str(PROJECT_ROOT),
)

load_dotenv(
    PROJECT_ROOT / ".env",
)

from App.agents.identity_agent import IdentityAgent
from App.intent.unified_extractor import (
    UnifiedIntentMetadataExtractor,
)
from App.utils.config import Config, Logger
from App.workflow.router import AgentRouter


OUTPUT_DIRECTORY = PROJECT_ROOT / "output"

LATEST_RESULT_PATH = (
    OUTPUT_DIRECTORY / "extraction_result.json"
)

ALL_QUERIES_PATH = (
    OUTPUT_DIRECTORY / "all_queries.json"
)


class DemoFlow:
    def __init__(self) -> None:
        self.extractor = (
            UnifiedIntentMetadataExtractor()
        )

        self.router = AgentRouter()
        self.identity_agent = IdentityAgent()

    def execute_flow(
        self,
        user_input: str,
        request_id: str | None = None,
        correlation_id: str | None = None,
    ) -> dict:
        request_id = (
            request_id
            or f"demo_{uuid4().hex[:12]}"
        )

        correlation_id = (
            correlation_id
            or f"corr_{uuid4().hex}"
        )

        logger.info(
            "FLOW_STARTED | request_id={} | "
            "correlation_id={} | user_input={}",
            request_id,
            correlation_id,
            user_input,
        )

        extraction = self.extractor.extract_all(
            user_input,
        )

        if not extraction.success:
            return {
                "success": False,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "intent": extraction.intent.value,
                "confidence": extraction.confidence,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "selected_agent": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required": False,
                "clarification_question": None,
                "message": extraction.explanation,
                "error": extraction.error,
            }

        if extraction.confidence < 0.70:
            return {
                "success": False,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "intent": extraction.intent.value,
                "confidence": extraction.confidence,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "selected_agent": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required": False,
                "clarification_question": None,
                "message": (
                    "The intent confidence is too low "
                    "to continue safely."
                ),
                "error": "Low intent confidence",
            }

        try:
            routing = self.router.route(
                extraction.intent,
                extraction.metadata.model_dump(
                    mode="json",
                ),
            )

        except ValueError as exc:
            return {
                "success": False,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "intent": extraction.intent.value,
                "confidence": extraction.confidence,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "selected_agent": None,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required": False,
                "clarification_question": None,
                "message": str(exc),
                "error": type(exc).__name__,
            }

        if routing.agent_type.value != "identity":
            return {
                "success": False,
                "request_id": request_id,
                "correlation_id": correlation_id,
                "intent": extraction.intent.value,
                "confidence": extraction.confidence,
                "metadata":
                    extraction.metadata.model_dump(
                        mode="json",
                    ),
                "selected_agent":
                    routing.agent_name,
                "selected_tool": None,
                "tool_result": None,
                "clarification_required": False,
                "clarification_question": None,
                "message": (
                    "Only the Identity Agent is "
                    "implemented in this demo."
                ),
                "error": "Agent unavailable",
            }

        agent_result = self.identity_agent.execute(
            operation=extraction.intent,
            metadata=extraction.metadata,
            request_id=request_id,
            correlation_id=correlation_id,
        )

        return {
            "success": agent_result.success,
            "request_id": request_id,
            "correlation_id": correlation_id,
            "intent": extraction.intent.value,
            "confidence": extraction.confidence,
            "explanation": extraction.explanation,
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
            "selected_tool": (
                agent_result.selected_tool.value
                if agent_result.selected_tool
                else None
            ),
            "tool_result": (
                agent_result.tool_result.model_dump(
                    mode="json",
                )
                if agent_result.tool_result
                else None
            ),
            "clarification_required":
                agent_result.clarification_required,
            "clarification_question":
                agent_result.clarification_question,
            "message": agent_result.message,
            "error": agent_result.error,
        }


def _read_history() -> list:
    if not ALL_QUERIES_PATH.exists():
        return []

    try:
        parsed = json.loads(
            ALL_QUERIES_PATH.read_text(
                encoding="utf-8",
            )
        )

        return (
            parsed
            if isinstance(parsed, list)
            else []
        )

    except (
        OSError,
        json.JSONDecodeError,
    ):
        logger.exception(
            "Unable to read query history"
        )

        return []


def save_result(
    *,
    original_input: str,
    complete_input: str,
    response: dict,
) -> None:
    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    LATEST_RESULT_PATH.write_text(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    history = _read_history()

    history.append(
        {
            "recorded_at": (
                datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            "original_user_input":
                original_input,
            "complete_user_input":
                complete_input,
            "response": response,
        }
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
        ALL_QUERIES_PATH,
    )


def print_response(
    response: dict,
) -> None:
    print()
    print("=" * 80)
    print("TECHADMIN WORKFLOW RESULT")
    print("=" * 80)

    print(
        json.dumps(
            response,
            indent=2,
            ensure_ascii=False,
        )
    )

    print()
    print("EXECUTION PROOF")
    print("-" * 80)

    print(
        f"Intent         : "
        f"{response.get('intent')}"
    )

    print(
        f"Selected agent : "
        f"{response.get('selected_agent')}"
    )

    print(
        f"Selected tool  : "
        f"{response.get('selected_tool')}"
    )

    tool_result = response.get(
        "tool_result"
    )

    print(
        f"Tool status    : "
        f"{tool_result.get('status') if tool_result else None}"
    )

    if tool_result:
        print(
            f"Operation ID   : "
            f"{tool_result.get('operation_id')}"
        )

    if response.get(
        "clarification_required"
    ):
        print(
            f"Agent question : "
            f"{response.get('clarification_question')}"
        )

    print("=" * 80)
    print()


def main() -> None:
    Logger.setup()

    demo = DemoFlow()

    print()
    print("=" * 80)
    print("TECHADMIN IDENTITY TOOL ROUTING DEMO")
    print("=" * 80)
    print(
        f"Latest result: {LATEST_RESULT_PATH}"
    )
    print(
        f"All queries: {ALL_QUERIES_PATH}"
    )
    print(
        f"Logs: "
        f"{PROJECT_ROOT / 'logs' / 'techadmin.log'}"
    )
    print("Type 'exit' to stop.")
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
            prompt,
        ).strip()

        if user_input.casefold() in {
            "exit",
            "quit",
        }:
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
            response,
        )

        save_result(
            original_input=user_input,
            complete_input=complete_input,
            response=response,
        )

        if response.get(
            "clarification_required"
        ):
            pending_query = complete_input
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
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any
from uuid import UUID

from App.core.llm_client import build_llm
from App.core.settings import get_settings
from App.intent.analyzer import IntentAnalyzer
from App.schemas.models import WorkflowState
from App.workflows.graph import build_graph


PROJECT_ROOT = Path(__file__).resolve().parents[1]

OUTPUT_DIRECTORY = PROJECT_ROOT / "output"
LOG_DIRECTORY = PROJECT_ROOT / "logs"

LATEST_RESULT_PATH = (
    OUTPUT_DIRECTORY / "extraction_result.json"
)

ALL_QUERIES_PATH = (
    OUTPUT_DIRECTORY / "all_queries.json"
)

RESULT_PATH = PROJECT_ROOT / "result.json"

LOG_PATH = LOG_DIRECTORY / "techadmin.log"


def configure_logging(
    log_level: str,
) -> None:
    LOG_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    formatter = logging.Formatter(
        "%(asctime)s "
        "%(levelname)s "
        "%(name)s "
        "%(message)s"
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(
        formatter,
    )

    file_handler = RotatingFileHandler(
        LOG_PATH,
        maxBytes=5_000_000,
        backupCount=5,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        formatter,
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(
        log_level.upper(),
    )
    root_logger.addHandler(
        console_handler,
    )
    root_logger.addHandler(
        file_handler,
    )

    logging.getLogger(
        "google_genai.models"
    ).setLevel(
        logging.ERROR
    )

    logging.getLogger(
        "httpx"
    ).setLevel(
        logging.WARNING
    )

    logging.getLogger(
        "httpcore"
    ).setLevel(
        logging.WARNING
    )


def write_latest_result(
    state: WorkflowState,
) -> None:
    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    serialized_state = (
        state.model_dump_json(
            indent=2,
        )
    )

    LATEST_RESULT_PATH.write_text(
        serialized_state,
        encoding="utf-8",
    )

    RESULT_PATH.write_text(
        serialized_state,
        encoding="utf-8",
    )


def _json_default(
    value: Any,
) -> str:
    if isinstance(value, UUID):
        return str(value)

    raise TypeError(
        f"Unsupported JSON type: "
        f"{type(value).__name__}"
    )


def read_history() -> list[dict[str, Any]]:
    if not ALL_QUERIES_PATH.exists():
        return []

    try:
        raw_content = (
            ALL_QUERIES_PATH.read_text(
                encoding="utf-8",
            )
        )

        parsed_content = json.loads(
            raw_content,
        )

        if isinstance(
            parsed_content,
            list,
        ):
            return parsed_content

    except (
        OSError,
        json.JSONDecodeError,
    ):
        logging.getLogger(
            __name__
        ).exception(
            "Unable to read query-history file."
        )

    return []


def append_history(
    original_user_input: str,
    complete_query_used: str,
    state: WorkflowState,
) -> None:
    """
    Stores every interaction instead of overwriting older results.
    """

    OUTPUT_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    history = read_history()

    history_entry = {
        "recorded_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),
        "original_user_input":
            original_user_input,
        "complete_query_used":
            complete_query_used,
        "result":
            state.model_dump(
                mode="json",
            ),
    }

    history.append(
        history_entry,
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
            default=_json_default,
        ),
        encoding="utf-8",
    )

    temporary_path.replace(
        ALL_QUERIES_PATH,
    )


def print_result(
    state: WorkflowState,
) -> None:
    print()
    print("=" * 72)
    print("INTENT AND IDENTITY EXTRACTION")
    print("=" * 72)

    print(
        "Intent          : "
        f"{state.intent.value if state.intent else None}"
    )

    print(
        "Confidence      : "
        f"{state.confidence}"
    )

    print(
        "Username        : "
        f"{state.fields.username}"
    )

    print(
        "Username source : "
        f"{state.fields.username_source}"
    )

    print(
        "Email           : "
        f"{state.fields.email}"
    )

    print(
        "Employee ID     : "
        f"{state.fields.employee_id}"
    )

    print(
        "Group name      : "
        f"{state.fields.group_name}"
    )

    print(
        "Time window     : "
        f"{state.fields.time_window}"
    )

    if state.validation:
        print(
            "Missing fields : "
            f"{state.validation.missing_fields}"
        )

        print(
            "Rejected fields: "
            f"{state.validation.rejected_fields}"
        )

        print(
            "Derived fields : "
            f"{state.validation.derived_fields}"
        )

        print(
            "Valid           : "
            f"{state.validation.is_valid}"
        )

    print()
    print("=" * 72)
    print("AGENT AND TOOL RESULT")
    print("=" * 72)

    print(
        "Workflow status : "
        f"{state.workflow_status.value}"
    )

    print(
        "Selected agent  : "
        f"{state.selected_agent}"
    )

    print(
        "Tool called     : "
        f"{state.tool_called.value if state.tool_called else None}"
    )

    if state.tool_result:
        print(
            "Tool status     : "
            f"{state.tool_result.status.value}"
        )

        print(
            "Operation ID    : "
            f"{state.tool_result.operation_id}"
        )

        print(
            "API pending     : "
            f"{state.tool_result.api_integration_pending}"
        )

        print()
        print(
            "[SUCCESS] Correct placeholder tool "
            "was called."
        )

    elif state.clarification_required:
        print(
            "Tool status     : not_called"
        )

        print()
        print(
            "Agent question  : "
            f"{state.clarification_question}"
        )

    else:
        print(
            "Tool status     : not_called"
        )

    print("=" * 72)
    print()


def main() -> None:
    settings = get_settings()

    configure_logging(
        settings.log_level,
    )

    graph = build_graph(
        IntentAnalyzer(
            build_llm(
                settings
            )
        )
    )

    print("TechAdmin Identity Tool Dispatch")
    print(
        f"LLM provider: "
        f"{settings.llm_provider}"
    )
    print(
        "Identity APIs: placeholder only"
    )
    print(
        f"Latest result: "
        f"{LATEST_RESULT_PATH}"
    )
    print(
        f"All queries: "
        f"{ALL_QUERIES_PATH}"
    )
    print(
        f"Logs: "
        f"{LOG_PATH}"
    )
    print(
        "Type 'exit' to stop."
    )
    print()

    pending_query: str | None = None
    pending_correlation_id: UUID | None = None

    while True:
        if pending_query:
            prompt_text = (
                "Provide missing information: "
            )
        else:
            prompt_text = (
                "Enter user query: "
            )

        user_input = input(
            prompt_text
        ).strip()

        if user_input.casefold() in {
            "exit",
            "quit",
        }:
            print(
                "TechAdmin CLI stopped."
            )
            break

        if not user_input:
            print(
                "Enter a request or type 'exit'."
            )
            continue

        if pending_query:
            complete_query = (
                f"{pending_query}. "
                f"Additional information: "
                f"{user_input}"
            )
        else:
            complete_query = user_input

        initial_state_arguments: dict[
            str,
            Any,
        ] = {
            "user_query": complete_query,
        }

        if pending_correlation_id:
            initial_state_arguments[
                "correlation_id"
            ] = pending_correlation_id

        initial_state = WorkflowState(
            **initial_state_arguments,
        )

        raw_result = graph.invoke(
            initial_state,
        )

        final_state = (
            WorkflowState.model_validate(
                raw_result,
            )
        )

        print_result(
            final_state,
        )

        write_latest_result(
            final_state,
        )

        append_history(
            original_user_input=user_input,
            complete_query_used=complete_query,
            state=final_state,
        )

        print(
            f"Latest result saved to: "
            f"{LATEST_RESULT_PATH}"
        )

        print(
            f"Complete history saved to: "
            f"{ALL_QUERIES_PATH}"
        )

        print(
            f"Logs saved to: "
            f"{LOG_PATH}"
        )

        if (
            final_state.clarification_required
            and final_state.clarification_question
        ):
            pending_query = complete_query
            pending_correlation_id = (
                final_state.correlation_id
            )

            print()
            print(
                final_state.clarification_question
            )
            print()

        else:
            pending_query = None
            pending_correlation_id = None


if __name__ == "__main__":
    main()
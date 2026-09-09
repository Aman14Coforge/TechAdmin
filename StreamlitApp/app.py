"""
TechAdmin Streamlit UI

Purpose:
    Browser interface for the TechAdmin workflow.

Display behavior:
    - Shows structured tables for summary, metadata, routing, execution,
      and operation results.
    - Shows generated temporary passwords in a dedicated dashboard
      section for the current Streamlit session.
    - Does not render st.success(), st.error(), or st.info() result boxes.
    - Does not use standalone conditional expressions with Streamlit
      methods, preventing DeltaGenerator objects from appearing in UI.

Run from the project root:
    python -m streamlit run StreamlitApp/app.py
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from flow_service import (
    LOG_FILE,
    FlowService,
    check_ollama,
    get_config_status,
)


# ---------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------

st.set_page_config(
    page_title="TechAdmin IT Support",
    page_icon="🛠️",
    layout="centered",
)


EXAMPLE_QUERIES = [
    "Get user details for Shreesanyog.Rath@Coforge.com",
    "Get user details for Shreesanyog.Rath@Coforge.com via script",
    "Get user details for Shreesanyog.Rath@Coforge.com via API",
    "Reset password for MigrationTest2@Coforge.com",
]


USER_DETAIL_FIELDS = [
    ("displayName", "Display name"),
    ("Name", "Name"),
    ("userPrincipalName", "User principal name"),
    ("UserPrincipalName", "User principal name"),
    ("mail", "Mail"),
    ("Mail", "Mail"),
    ("id", "User ID"),
    ("userType", "User type"),
    ("accountEnabled", "Account enabled"),
    ("Enabled", "Account enabled"),
    ("LockedOut", "Locked out"),
    ("SamAccountName", "SAM account name"),
    ("Department", "Department"),
    ("DistinguishedName", "Distinguished name"),
    ("DomainController", "Domain controller"),
    ("Domain", "Domain"),
    ("Site", "AD site"),
]


PASSWORD_RESET_FIELDS = [
    ("user_principal_name", "User principal name"),
    ("user_principal", "User principal name"),
    ("user_name", "Username"),
    ("user_id", "User ID"),
    (
        "temporary_password_generated",
        "Temporary password generated",
    ),
    (
        "temporary_password_redacted",
        "Password removed from audit response",
    ),
    (
        "temporary_password_displayed_on_dashboard",
        "Password displayed on dashboard",
    ),
]


ROUTING_FIELDS = [
    ("selected_agent", "Agent"),
    ("selected_mcp_server", "MCP server"),
    ("selected_mcp_tool", "MCP tool"),
    ("selected_tool", "Application tool"),
]


# ---------------------------------------------------------------------
# Service and session state
# ---------------------------------------------------------------------


@st.cache_resource(
    show_spinner="Starting TechAdmin..."
)
def get_service() -> FlowService:
    """Create and cache the workflow service."""

    return FlowService()


def init_state() -> None:
    """Initialize all Streamlit session keys."""

    if "conversation" not in st.session_state:
        st.session_state.conversation = []

    if "queued_query" not in st.session_state:
        st.session_state.queued_query = None

    if "password_cards" not in st.session_state:
        st.session_state.password_cards = []

    if "ollama_check_result" not in st.session_state:
        st.session_state.ollama_check_result = None


# ---------------------------------------------------------------------
# Generic table helpers
# ---------------------------------------------------------------------


def as_text(value: Any) -> str:
    """Convert values to readable table-cell strings."""

    if value is None or value == "":
        return "—"

    if isinstance(value, bool):
        return "Yes" if value else "No"

    return str(value)


def show_table(
    rows: List[tuple[str, Any]],
    caption: str = "",
) -> None:
    """Render a two-column Field/Value dataframe."""

    if not rows:
        return

    if caption:
        st.markdown(f"**{caption}**")

    frame = pd.DataFrame(
        [
            {
                "Field": label,
                "Value": as_text(value),
            }
            for label, value in rows
        ]
    )

    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
    )


def pick_fields(
    data: Dict[str, Any],
    fields: List[tuple[str, str]],
    exclude: set[str] | None = None,
) -> List[tuple[str, Any]]:
    """Build ordered table rows from known and additional scalar fields."""

    excluded = exclude or set()

    rows = [
        (label, data.get(key))
        for key, label in fields
        if key in data and key not in excluded
    ]

    known = {
        key
        for key, _ in fields
    } | excluded

    for key, value in data.items():
        if key in known:
            continue

        if isinstance(value, (dict, list)):
            continue

        rows.append(
            (
                key.replace("_", " ").capitalize(),
                value,
            )
        )

    return rows


# ---------------------------------------------------------------------
# Dashboard password handling
# ---------------------------------------------------------------------


def register_dashboard_secret(
    response: Dict[str, Any],
) -> None:
    """
    Move a transient generated password into current session state.

    The `_dashboard_secret` key is removed before the normal response is
    placed into conversation history or rendered in raw JSON.
    """

    secret = response.pop(
        "_dashboard_secret",
        None,
    )

    if not isinstance(secret, dict):
        return

    password = secret.get("password")

    if not isinstance(password, str) or not password:
        return

    card = {
        "password": password,
        "user": secret.get("user") or "Unknown user",
        "backend": secret.get("backend") or "unknown",
        "operation_id": secret.get("operation_id"),
        "created_at": datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        ),
    }

    st.session_state.password_cards.insert(
        0,
        card,
    )


def render_password_cards() -> None:
    """Render session-scoped generated-password cards."""

    if not st.session_state.password_cards:
        return

    st.markdown("### Generated temporary passwords")

    for index, card in enumerate(
        list(st.session_state.password_cards)
    ):
        with st.container(border=True):
            show_table(
                [
                    ("Account", card.get("user")),
                    ("Backend", card.get("backend")),
                    ("Generated", card.get("created_at")),
                    (
                        "Operation ID",
                        card.get("operation_id"),
                    ),
                ]
            )

            st.code(
                card.get("password") or "",
                language=None,
            )

            if st.button(
                "Remove password from dashboard",
                key=f"remove_password_{index}",
                width="content",
            ):
                st.session_state.password_cards.pop(
                    index
                )
                st.rerun()

    if st.button(
        "Clear all displayed passwords",
        type="secondary",
        width="content",
    ):
        st.session_state.password_cards = []
        st.rerun()

    st.divider()


# ---------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------


def render_script_execution(
    execution: Dict[str, Any],
) -> None:
    """Render PowerShell execution evidence."""

    rows = [
        ("Operation", execution.get("operation")),
        ("Script", execution.get("script_name")),
        ("Exit code", execution.get("exit_code")),
        (
            "Duration seconds",
            execution.get("duration_seconds"),
        ),
        ("Dry run", execution.get("dry_run")),
        ("Succeeded", execution.get("success")),
        ("Error", execution.get("error")),
    ]

    show_table(
        rows,
        "Script execution",
    )


def render_result_table(
    intent: str,
    result: Dict[str, Any],
) -> None:
    """Render the operation result without success or error callouts."""

    backend = result.get("backend")

    if intent == "password_reset":
        rows = pick_fields(
            result,
            PASSWORD_RESET_FIELDS,
            exclude={
                "temporary_password",
                "execution",
                "backend",
            },
        )

        if backend is not None:
            rows.insert(
                0,
                ("Execution backend", backend),
            )

        show_table(
            rows,
            "Result",
        )

        execution = result.get("execution")

        if isinstance(execution, dict):
            render_script_execution(execution)

        return

    user_data = result.get("user")

    if not isinstance(user_data, dict):
        user_data = result

    rows = pick_fields(
        user_data,
        USER_DETAIL_FIELDS,
        exclude={
            "backend",
            "execution",
            "user",
        },
    )

    if backend is not None:
        rows.insert(
            0,
            ("Execution backend", backend),
        )

    show_table(
        rows,
        "Result",
    )

    execution = result.get("execution")

    if isinstance(execution, dict):
        render_script_execution(execution)


def render_response(
    response: Dict[str, Any],
) -> None:
    """
    Render only structured tables and raw JSON.

    No st.success(), st.error(), or st.info() calls are used here.
    Therefore Streamlit DeltaGenerator objects cannot be rendered by a
    standalone conditional expression.
    """

    confidence = response.get("confidence")

    summary_rows = [
        ("Succeeded", response.get("success")),
        ("Intent", response.get("intent")),
        (
            "Confidence",
            (
                f"{confidence:.0%}"
                if isinstance(confidence, (int, float))
                else None
            ),
        ),
        ("Request ID", response.get("request_id")),
        (
            "Correlation ID",
            response.get("correlation_id"),
        ),
        ("Explanation", response.get("explanation")),
        ("Message", response.get("message")),
        ("Error", response.get("error")),
        (
            "Clarification required",
            response.get("clarification_required"),
        ),
        (
            "Clarification question",
            response.get("clarification_question"),
        ),
    ]

    show_table(
        summary_rows,
        "Summary",
    )

    metadata = response.get("metadata")

    if not isinstance(metadata, dict):
        metadata = {}

    metadata_rows = [
        (
            key.replace("_", " ").capitalize(),
            value,
        )
        for key, value in metadata.items()
        if value not in (None, "")
    ]

    show_table(
        metadata_rows,
        "Extracted metadata",
    )

    routing_rows = [
        (
            label,
            response.get(key),
        )
        for key, label in ROUTING_FIELDS
        if response.get(key)
    ]

    show_table(
        routing_rows,
        "Routing",
    )

    tool_result = response.get("tool_result")

    if not isinstance(tool_result, dict):
        tool_result = {}

    if tool_result:
        execution_rows = [
            (
                "Tool name",
                tool_result.get("tool_name"),
            ),
            (
                "Status",
                tool_result.get("status"),
            ),
            (
                "Operation ID",
                tool_result.get("operation_id"),
            ),
            (
                "Succeeded",
                tool_result.get("success"),
            ),
            (
                "Message",
                tool_result.get("message"),
            ),
            (
                "Error",
                tool_result.get("error"),
            ),
        ]

        show_table(
            execution_rows,
            "Tool execution",
        )

    result = tool_result.get("result")

    if not isinstance(result, dict):
        fallback_result = response.get("result")

        if isinstance(fallback_result, dict):
            result = fallback_result
        else:
            result = {}

    if result:
        render_result_table(
            response.get("intent") or "",
            result,
        )

    with st.expander(
        "Raw response (JSON)"
    ):
        st.json(response)


# ---------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------


def safe_conversation_for_download() -> list[dict[str, Any]]:
    """Return a copy of password-free conversation history."""

    return copy.deepcopy(
        st.session_state.conversation
    )


def render_sidebar() -> None:
    """Render environment and session controls without status boxes."""

    with st.sidebar:
        st.header("Environment")

        status = get_config_status()

        show_table(
            [
                ("Ollama host", status.get("ollama_host")),
                ("Model", status.get("model_name")),
                (
                    "Graph client ID configured",
                    status.get("graph_client_id"),
                ),
                (
                    "Graph client secret configured",
                    status.get("graph_client_secret"),
                ),
                (
                    "Graph tenant ID configured",
                    status.get("graph_tenant_id"),
                ),
                (
                    "Configuration valid",
                    status.get("config_valid"),
                ),
            ]
        )

        if st.button(
            "Test Ollama connection",
            width="stretch",
        ):
            is_ok, message = check_ollama()

            st.session_state.ollama_check_result = {
                "connected": is_ok,
                "message": message,
            }

        ollama_result = st.session_state.get(
            "ollama_check_result"
        )

        if isinstance(ollama_result, dict):
            show_table(
                [
                    (
                        "Ollama connected",
                        ollama_result.get("connected"),
                    ),
                    (
                        "Connection result",
                        ollama_result.get("message"),
                    ),
                ]
            )

        st.divider()
        st.caption("Example queries")

        for example in EXAMPLE_QUERIES:
            if st.button(
                example,
                width="stretch",
                key=f"example_{example}",
            ):
                st.session_state.queued_query = example
                st.rerun()

        st.divider()
        st.caption(f"Logs: {LOG_FILE}")

        if st.session_state.conversation:
            if st.button(
                "Clear conversation",
                width="stretch",
            ):
                st.session_state.conversation = []
                st.rerun()

            st.download_button(
                "Download as JSON",
                data=json.dumps(
                    safe_conversation_for_download(),
                    indent=2,
                    default=str,
                ),
                file_name="techadmin_session.json",
                mime="application/json",
                width="stretch",
            )


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------


def main() -> None:
    """Run the Streamlit application."""

    init_state()

    st.title("🛠️ TechAdmin IT Support")
    st.caption(
        "Type your request in plain English. "
        "Supported: get user details, reset password."
    )

    service = get_service()

    render_password_cards()

    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.write(turn["content"])
            else:
                render_response(turn["content"])

    query = (
        st.session_state.queued_query
        or st.chat_input(
            "e.g. Get user details for derhant"
        )
    )

    st.session_state.queued_query = None

    if query:
        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner(
                "Classifying intent and running the operation..."
            ):
                response = service.run_query(query)

            register_dashboard_secret(response)
            render_response(response)

        timestamp = datetime.now().strftime(
            "%H:%M:%S"
        )

        st.session_state.conversation.append(
            {
                "role": "user",
                "content": query,
                "time": timestamp,
            }
        )

        st.session_state.conversation.append(
            {
                "role": "assistant",
                "content": response,
                "time": timestamp,
            }
        )

        # A rerun redraws the new password card above the conversation.
        if st.session_state.password_cards:
            st.rerun()

    render_sidebar()


if __name__ == "__main__":
    main()

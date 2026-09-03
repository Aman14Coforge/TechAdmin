"""
TechAdmin Streamlit UI

Purpose:
    Provide a browser-based interface for the existing TechAdmin flow:

    Unified extraction -> Agent routing -> Identity Agent validation ->
    MCP server selection -> MCP tool call -> application tool -> API.

Run:
    streamlit run app.py
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import streamlit as st
from loguru import logger

from App.utils.config import Config, Logger
from Scripts.demo_flow import DemoFlow, save_result


PROJECT_ROOT = Path(__file__).resolve().parent
LOG_PATH = PROJECT_ROOT / "logs" / "techadmin.log"
LATEST_RESULT_PATH = PROJECT_ROOT / "output" / "extraction_result.json"
ALL_QUERIES_PATH = PROJECT_ROOT / "output" / "all_queries.json"

PAGE_TITLE = "TechAdmin Identity Operations"
PAGE_ICON = "🛡️"

SENSITIVE_KEYS = {
    "new_password",
    "password",
    "access_token",
    "refresh_token",
    "client_secret",
    "graph_password",
    "authorization",
}


st.set_page_config(
    page_title=PAGE_TITLE,
    page_icon=PAGE_ICON,
    layout="wide",
    initial_sidebar_state="expanded",
)


st.markdown(
    """
    <style>
        .block-container {padding-top: 1.6rem; padding-bottom: 2rem;}
        [data-testid="stMetric"] {
            background: rgba(120, 120, 120, 0.08);
            border: 1px solid rgba(120, 120, 120, 0.18);
            border-radius: 14px;
            padding: 12px;
        }
        .status-panel {
            border: 1px solid rgba(120, 120, 120, 0.22);
            border-radius: 14px;
            padding: 14px 16px;
            margin: 8px 0 14px 0;
        }
        .small-muted {opacity: 0.72; font-size: 0.88rem;}
    </style>
    """,
    unsafe_allow_html=True,
)


def configure_logging_once() -> None:
    """Configure the existing Loguru file sink only once per UI process."""
    if not st.session_state.get("logging_configured"):
        Logger.setup()
        st.session_state.logging_configured = True


@st.cache_resource(show_spinner=False)
def get_demo_flow() -> DemoFlow:
    """Create one reusable workflow object for the Streamlit process."""
    return DemoFlow()


def initialize_state() -> None:
    defaults: dict[str, Any] = {
        "messages": [],
        "last_response": None,
        "pending_query": None,
        "pending_request_id": None,
        "pending_correlation_id": None,
        "logging_configured": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def redact_sensitive_data(value: Any) -> Any:
    """Create a deep redacted copy before UI display or JSON persistence."""
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if key.casefold() in SENSITIVE_KEYS:
                output[key] = "[REDACTED]" if item is not None else None
            else:
                output[key] = redact_sensitive_data(item)
        return output

    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]

    return value


def status_label(response: dict[str, Any]) -> str:
    if response.get("clarification_required"):
        return "Needs information"
    tool_result = response.get("tool_result") or {}
    if tool_result.get("status") == "completed":
        return "Completed"
    if tool_result.get("status") == "not_implemented":
        return "Tool reached"
    if response.get("error"):
        return "Failed"
    return "Processed"


def status_icon(response: dict[str, Any]) -> str:
    status = status_label(response)
    return {
        "Completed": "✅",
        "Tool reached": "🧩",
        "Needs information": "❓",
        "Failed": "❌",
        "Processed": "ℹ️",
    }.get(status, "ℹ️")


def render_response_summary(response: dict[str, Any]) -> None:
    metadata = response.get("metadata") or {}
    validation = response.get("validation") or {}
    tool_result = response.get("tool_result") or {}

    st.markdown(
        f"""
        <div class="status-panel">
            <strong>{status_icon(response)} {status_label(response)}</strong><br>
            <span class="small-muted">{response.get('message') or 'No response message.'}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    metric_columns = st.columns(4)
    metric_columns[0].metric("Intent", response.get("intent") or "Not identified")
    metric_columns[1].metric("Agent", response.get("selected_agent") or "Not selected")
    metric_columns[2].metric("MCP tool", response.get("selected_mcp_tool") or "Not called")
    metric_columns[3].metric("Tool status", tool_result.get("status") or "Not called")

    extraction_tab, mcp_tab, result_tab, json_tab = st.tabs(
        ["Identity extraction", "MCP evidence", "Operation result", "Full JSON"]
    )

    with extraction_tab:
        left, right = st.columns(2)
        with left:
            st.write("**Username:**", metadata.get("username") or "Not provided")
            st.write("**Username source:**", metadata.get("username_source") or "Not available")
            st.write("**Email:**", metadata.get("email") or "Not provided")
            st.write("**User ID:**", metadata.get("user_id") or "Not provided")
        with right:
            st.write("**Employee number:**", metadata.get("employee_number") or "Not provided")
            st.write("**Group name:**", metadata.get("group_name") or "Not provided")
            st.write("**Time window:**", metadata.get("time_window") or "Not provided")
            st.write("**Confidence:**", response.get("confidence"))

        missing = validation.get("missing_fields") or []
        derived = validation.get("derived_fields") or []
        if missing:
            st.warning("Missing fields: " + ", ".join(missing))
        else:
            st.success("Required metadata validation passed.")
        if derived:
            st.info("Derived fields: " + ", ".join(derived))

    with mcp_tab:
        st.write("**MCP server module:**", response.get("selected_mcp_server") or "Not started")
        st.write("**MCP protocol tool:**", response.get("selected_mcp_tool") or "Not called")
        st.write("**Application tool:**", response.get("selected_tool") or "Not called")
        st.write("**Request ID:**", response.get("request_id"))
        st.write("**Correlation ID:**", response.get("correlation_id"))
        if tool_result:
            st.success(
                "MCP dispatch returned a structured tool result with operation ID "
                f"{tool_result.get('operation_id')}."
            )
        elif response.get("clarification_required"):
            st.info("MCP was not called because required information is missing.")
        else:
            st.warning("No MCP tool result is available.")

    with result_tab:
        if tool_result:
            st.write("**Success:**", tool_result.get("success"))
            st.write("**Status:**", tool_result.get("status"))
            st.write("**Operation ID:**", tool_result.get("operation_id"))
            st.write("**Message:**", tool_result.get("message"))
            if tool_result.get("result") is not None:
                st.json(redact_sensitive_data(tool_result.get("result")), expanded=True)
            if tool_result.get("error"):
                st.error(tool_result.get("error"))
        elif response.get("clarification_required"):
            st.info(response.get("clarification_question"))
        else:
            st.info("No operation result was returned.")

    with json_tab:
        st.json(redact_sensitive_data(response), expanded=False)


def render_sidebar() -> None:
    st.sidebar.title("TechAdmin")
    st.sidebar.caption("Identity operations through MCP")

    st.sidebar.subheader("Runtime configuration")
    st.sidebar.write("**Model:**", Config.MODEL_NAME)
    st.sidebar.write("**Ollama:**", Config.OLLAMA_HOST)
    st.sidebar.write("**Graph auth mode:**", Config.GRAPH_AUTH_MODE)

    st.sidebar.subheader("Output files")
    st.sidebar.code(str(LATEST_RESULT_PATH), language=None)
    st.sidebar.code(str(ALL_QUERIES_PATH), language=None)
    st.sidebar.code(str(LOG_PATH), language=None)

    if st.sidebar.button("Clear conversation", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_response = None
        st.session_state.pending_query = None
        st.session_state.pending_request_id = None
        st.session_state.pending_correlation_id = None
        st.rerun()

    if st.sidebar.button("Cancel pending request", use_container_width=True):
        st.session_state.pending_query = None
        st.session_state.pending_request_id = None
        st.session_state.pending_correlation_id = None
        st.rerun()

    with st.sidebar.expander("Recent logs", expanded=False):
        if LOG_PATH.exists():
            try:
                lines = LOG_PATH.read_text(encoding="utf-8", errors="replace").splitlines()
                st.code("\n".join(lines[-40:]), language="text")
            except OSError as exc:
                st.error(f"Unable to read log file: {type(exc).__name__}")
        else:
            st.info("The log file has not been created yet.")


def process_user_input(user_input: str) -> None:
    demo = get_demo_flow()

    if st.session_state.pending_query:
        complete_input = (
            f"{st.session_state.pending_query}. "
            f"Additional information: {user_input}"
        )
    else:
        complete_input = user_input

    with st.status("Processing TechAdmin request...", expanded=True) as status:
        st.write("Extracting intent and identity metadata")
        st.write("Validating mandatory information")
        st.write("Routing to the Identity Agent")
        st.write("Calling MCP only when validation passes")

        try:
            response = demo.execute_flow(
                user_input=complete_input,
                request_id=st.session_state.pending_request_id,
                correlation_id=st.session_state.pending_correlation_id,
            )
            response = redact_sensitive_data(response)
            status.update(
                label=status_label(response),
                state="complete" if not response.get("error") else "error",
                expanded=False,
            )
        except Exception as exc:
            logger.exception("STREAMLIT_FLOW_FAILED | error_type={}", type(exc).__name__)
            response = {
                "success": False,
                "message": "The TechAdmin workflow could not complete the request.",
                "error": type(exc).__name__,
                "clarification_required": False,
            }
            status.update(label="Request failed", state="error", expanded=True)

    try:
        save_result(
            original_input=user_input,
            complete_input=complete_input,
            response=response,
        )
    except Exception as exc:
        logger.exception("STREAMLIT_RESULT_SAVE_FAILED | error_type={}", type(exc).__name__)
        st.warning("The request was processed, but its JSON history could not be saved.")

    st.session_state.messages.append({"role": "user", "content": user_input})
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": response.get("message") or "Request processed.",
            "response": response,
        }
    )
    st.session_state.last_response = response

    if response.get("clarification_required"):
        st.session_state.pending_query = complete_input
        st.session_state.pending_request_id = response.get("request_id")
        st.session_state.pending_correlation_id = response.get("correlation_id")
    else:
        st.session_state.pending_query = None
        st.session_state.pending_request_id = None
        st.session_state.pending_correlation_id = None

    st.rerun()


def main() -> None:
    initialize_state()
    configure_logging_once()
    render_sidebar()

    st.title(f"{PAGE_ICON} {PAGE_TITLE}")
    st.caption(
        "Enter an identity-operation request. The workflow extracts metadata, "
        "asks for missing details, routes through MCP, and displays tool evidence."
    )

    if st.session_state.pending_query:
        st.info(
            "A request is waiting for additional information. "
            "Answer the Identity Agent's question below."
        )

    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message["role"] == "assistant" and message.get("response"):
                render_response_summary(message["response"])

    placeholder = (
        "Provide the missing information..."
        if st.session_state.pending_query
        else "Example: Get details for email user@coforge.com"
    )

    user_input = st.chat_input(placeholder)
    if user_input:
        process_user_input(user_input.strip())


if __name__ == "__main__":
    main()

# """
# TechAdmin Streamlit UI
# Purpose: Browser UI for the TechAdmin IT support workflow.

# The user types a request in plain English, exactly as they would in the
# terminal demo. Ollama classifies the intent and extracts the metadata, the
# router picks the agent, and the Identity Agent runs the tool.

# Supported today: get user details, reset password.

# Run from the project root:
#     streamlit run StreamlitApp/app.py
# """

# from __future__ import annotations

# import json
# from datetime import datetime
# from typing import Any, Dict

# import streamlit as st

# from flow_service import LOG_FILE, FlowService, check_ollama, get_config_status

# # ---------------------------------------------------------------------------
# # Page setup
# # ---------------------------------------------------------------------------
# st.set_page_config(
#     page_title="TechAdmin IT Support",
#     page_icon="🛠️",
#     layout="centered",
# )

# EXAMPLE_QUERIES = [
#     "Get details for amit.bhagat@coforge.com",
#     "Find user details for derhant",
#     "Reset password for aman.gupta",
# ]


# @st.cache_resource(show_spinner="Starting TechAdmin (loading Ollama and Graph clients)...")
# def get_service() -> FlowService:
#     """
#     Build the FlowService once per Streamlit session.

#     cache_resource matters here: without it Streamlit would rebuild the Ollama
#     and Microsoft Graph clients on every interaction, which is slow and throws
#     away the cached Graph access token.
#     """
#     return FlowService()


# def init_state() -> None:
#     """Create the session keys the app relies on."""
#     if "conversation" not in st.session_state:
#         st.session_state.conversation = []
#     if "queued_query" not in st.session_state:
#         st.session_state.queued_query = None


# # ---------------------------------------------------------------------------
# # Result rendering
# # ---------------------------------------------------------------------------
# def render_user_details(user_data: Dict[str, Any]) -> None:
#     """Show the fields returned by Microsoft Graph in a readable layout."""
#     left, right = st.columns(2)

#     with left:
#         st.markdown("**Display name**")
#         st.write(user_data.get("displayName") or "—")
#         st.markdown("**User principal name**")
#         st.write(user_data.get("userPrincipalName") or "—")
#         st.markdown("**Mail**")
#         st.write(user_data.get("mail") or "—")

#     with right:
#         st.markdown("**User ID**")
#         st.code(user_data.get("id") or "—", language=None)
#         st.markdown("**User type**")
#         st.write(user_data.get("userType") or "—")
#         st.markdown("**AD sync enabled**")
#         st.write(user_data.get("onPremisesSyncEnabled"))

#     enabled = user_data.get("accountEnabled")
#     if enabled is True:
#         st.success("Account is enabled")
#     elif enabled is False:
#         st.warning("Account is disabled")


# def render_password_result(result: Dict[str, Any]) -> None:
#     """Show the outcome of a password reset."""
#     st.markdown("**User principal name**")
#     st.write(result.get("user_principal") or "—")

#     temp_password = result.get("new_password")
#     if temp_password:
#         # Demo behaviour only. In production the temporary password is delivered
#         # out of band and should never be rendered in a browser.
#         st.warning("Temporary password — demo only, deliver this securely in production.")
#         st.code(temp_password, language=None)


# def render_response(response: Dict[str, Any]) -> None:
#     """Render one workflow response."""
#     message = response.get("message") or (
#         "Completed successfully." if response.get("success") else "The request could not be completed."
#     )

#     if response.get("success"):
#         st.success(message)
#     else:
#         st.error(message)
#         if response.get("error"):
#             st.caption(f"Error: {response['error']}")

#     # What the LLM decided, so the classification step is visible and debuggable.
#     columns = st.columns(3)
#     columns[0].metric("Intent", response.get("intent") or "—")

#     confidence = response.get("confidence")
#     columns[1].metric(
#         "Confidence",
#         f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—",
#     )
#     columns[2].metric("Request ID", response.get("request_id") or "—")

#     metadata = response.get("metadata") or {}
#     if any(metadata.values()):
#         with st.expander("Extracted metadata"):
#             st.json({key: value for key, value in metadata.items() if value})

#     result = response.get("result")
#     if response.get("success") and isinstance(result, dict):
#         st.divider()
#         if response.get("intent") == "password_reset":
#             render_password_result(result)
#         else:
#             render_user_details(result)

#     with st.expander("Raw response (JSON)"):
#         st.json(response)


# # ---------------------------------------------------------------------------
# # Sidebar
# # ---------------------------------------------------------------------------
# def render_sidebar() -> None:
#     """Environment status, example queries and session controls."""
#     with st.sidebar:
#         st.header("Environment")

#         status = get_config_status()

#         st.caption("Ollama")
#         st.text(f"Host  : {status['ollama_host']}")
#         st.text(f"Model : {status['model_name']}")

#         if st.button("Test Ollama connection", use_container_width=True):
#             is_ok, message = check_ollama()
#             st.success(message) if is_ok else st.error(message)

#         st.divider()
#         st.caption("Microsoft Graph credentials")

#         for label, key in (
#             ("Client ID", "graph_client_id"),
#             ("Client secret", "graph_client_secret"),
#             ("Tenant ID", "graph_tenant_id"),
#         ):
#             st.text(f"{'✅' if status[key] else '❌'} {label}")

#         if not all(
#             status[key]
#             for key in ("graph_client_id", "graph_client_secret", "graph_tenant_id")
#         ):
#             st.warning("Graph credentials are missing. Add them to your .env file.")

#         st.divider()
#         st.caption("Example queries")

#         # Clicking an example queues it and reruns, so it flows through exactly
#         # the same path as a typed query.
#         for example in EXAMPLE_QUERIES:
#             if st.button(example, use_container_width=True, key=f"example_{example}"):
#                 st.session_state.queued_query = example
#                 st.rerun()

#         st.divider()
#         st.caption(f"Logs: {LOG_FILE}")

#         if st.session_state.conversation:
#             if st.button("Clear conversation", use_container_width=True):
#                 st.session_state.conversation = []
#                 st.rerun()

#             st.download_button(
#                 "Download as JSON",
#                 data=json.dumps(st.session_state.conversation, indent=2, default=str),
#                 file_name="techadmin_session.json",
#                 mime="application/json",
#                 use_container_width=True,
#             )


# # ---------------------------------------------------------------------------
# # Main
# # ---------------------------------------------------------------------------
# def main() -> None:
#     init_state()

#     st.title("🛠️ TechAdmin IT Support")
#     st.caption(
#         "Type your request in plain English. Supported: get user details, reset password."
#     )

#     service = get_service()

#     # Replay the conversation so far. Only the query text is stored for the user
#     # turns; the assistant turns keep the full response dict so the expanders
#     # still work after a rerun.
#     for turn in st.session_state.conversation:
#         with st.chat_message(turn["role"]):
#             if turn["role"] == "user":
#                 st.write(turn["content"])
#             else:
#                 render_response(turn["content"])

#     # A queued example takes priority, otherwise use whatever was typed.
#     query = st.session_state.queued_query or st.chat_input(
#         "e.g. Get details for amit.bhagat@coforge.com"
#     )
#     st.session_state.queued_query = None

#     if query:
#         with st.chat_message("user"):
#             st.write(query)

#         with st.chat_message("assistant"):
#             with st.spinner("Classifying intent and running the operation..."):
#                 response = service.run_query(query)

#             render_response(response)

#         timestamp = datetime.now().strftime("%H:%M:%S")
#         st.session_state.conversation.append(
#             {"role": "user", "content": query, "time": timestamp}
#         )
#         st.session_state.conversation.append(
#             {"role": "assistant", "content": response, "time": timestamp}
#         )

#     elif not st.session_state.conversation:
#         st.info(
#             "Enter a request below, or pick an example from the sidebar.\n\n"
#             "Examples:\n"
#             "- Get details for amit.bhagat@coforge.com\n"
#             "- Reset password for aman.gupta"
#         )

#     # The sidebar is rendered last, after the conversation has been updated, so
#     # the Clear and Download controls appear on the same run as the first query
#     # rather than only after the next interaction. Streamlit places this content
#     # in the sidebar regardless of when it is called.
#     render_sidebar()


# if __name__ == "__main__":
#     main()


"""
TechAdmin Streamlit UI
Purpose: Browser UI for the TechAdmin IT support workflow.

The user types a request in plain English, exactly as they would in the
terminal demo. Ollama classifies the intent and extracts the metadata, the
router picks the agent, and the Identity Agent runs the tool.

Supported today: get user details, reset password.

Run from the project root:
    streamlit run StreamlitApp/app.py
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from flow_service import LOG_FILE, FlowService, check_ollama, get_config_status

# ---------------------------------------------------------------------------
# Page setup
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="TechAdmin IT Support",
    page_icon="🛠️",
    layout="centered",
)

EXAMPLE_QUERIES = [
    "Get details for amit.bhagat@coforge.com",
    "Find user details for derhant",
    "Reset password for aman.gupta",
]


@st.cache_resource(show_spinner="Starting TechAdmin (loading Ollama and Graph clients)...")
def get_service() -> FlowService:
    """
    Build the FlowService once per Streamlit session.

    cache_resource matters here: without it Streamlit would rebuild the Ollama
    and Microsoft Graph clients on every interaction, which is slow and throws
    away the cached Graph access token.
    """
    return FlowService()


def init_state() -> None:
    """Create the session keys the app relies on."""
    if "conversation" not in st.session_state:
        st.session_state.conversation = []
    if "queued_query" not in st.session_state:
        st.session_state.queued_query = None


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------
# Graph returns camelCase keys. These are the labels shown in the table, in the
# order they should appear.
USER_DETAIL_FIELDS = [
    ("displayName", "Display name"),
    ("userPrincipalName", "User principal name"),
    ("mail", "Mail"),
    ("id", "User ID"),
    ("userType", "User type"),
    ("accountEnabled", "Account enabled"),
    ("onPremisesSyncEnabled", "On-prem sync enabled"),
]

PASSWORD_RESET_FIELDS = [
    ("user_principal", "User principal name"),
    ("user_id", "User ID"),
]

# Where the request went. Useful in a demo, because it shows the MCP hop.
ROUTING_FIELDS = [
    ("selected_agent", "Agent"),
    ("selected_mcp_server", "MCP server"),
    ("selected_mcp_tool", "MCP tool"),
    ("selected_tool", "Application tool"),
]


def as_text(value: Any) -> str:
    """
    Render a value for a table cell.

    Streamlit tables are string-based, so booleans and None need to be turned
    into something readable rather than shown as "True" and "None".
    """
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def show_table(rows: List[tuple], caption: str = "") -> None:
    """
    Draw a two-column Field/Value table.

    Args:
        rows: Pairs of (label, value).
        caption: Optional heading shown above the table.
    """
    if not rows:
        return

    if caption:
        st.markdown(f"**{caption}**")

    frame = pd.DataFrame(
        [{"Field": label, "Value": as_text(value)} for label, value in rows]
    )

    # hide_index keeps the table clean; 0..n row numbers add nothing here.
    st.dataframe(frame, hide_index=True, use_container_width=True)


def pick_fields(
    data: Dict[str, Any],
    fields: List[tuple],
    exclude: set = None,
) -> List[tuple]:
    """
    Build table rows from a known field list, then append anything unexpected.

    Listing the known fields keeps the important ones in a sensible order, and
    the sweep at the end means a new field added to a tool still shows up
    instead of being silently dropped.

    Args:
        data: The payload to turn into rows.
        fields: Ordered (key, label) pairs for the fields that are known.
        exclude: Keys to keep out of the table entirely, for values that are
            rendered separately or should not be shown in a copyable grid.
    """
    exclude = exclude or set()

    rows = [
        (label, data.get(key))
        for key, label in fields
        if key in data and key not in exclude
    ]

    known = {key for key, _ in fields} | exclude
    for key, value in data.items():
        if key not in known and not isinstance(value, (dict, list)):
            rows.append((key.replace("_", " ").capitalize(), value))

    return rows


def render_result_table(intent: str, result: Dict[str, Any]) -> None:
    """Render the tool's result payload as a table."""
    if intent == "password_reset":
        # new_password is excluded from the table and shown on its own below,
        # so it is not sitting in a grid that is easy to copy or screenshot.
        show_table(
            pick_fields(result, PASSWORD_RESET_FIELDS, exclude={"new_password"}),
            "Result",
        )

        temp_password = result.get("new_password")
        if temp_password:
            # Kept out of the table on purpose, so it is not casually copied or
            # screenshotted. Demo behaviour only; in production a temporary
            # password is delivered out of band.
            st.warning(
                "Temporary password — demo only, deliver this securely in production."
            )
            st.code(temp_password, language=None)
        return

    show_table(pick_fields(result, USER_DETAIL_FIELDS), "Result")


def render_response(response: Dict[str, Any]) -> None:
    """Render one workflow response as a set of tables."""
    message = response.get("message") or (
        "Completed successfully."
        if response.get("success")
        else "The request could not be completed."
    )

    if response.get("success"):
        st.success(message)
    else:
        st.error(message)
        if response.get("error"):
            st.caption(f"Error: {response['error']}")

    # A clarification is not a failure; the flow is waiting on the user.
    if response.get("clarification_required"):
        st.info(response.get("clarification_question") or "More information is needed.")

    # --- Summary of what the LLM decided ---
    confidence = response.get("confidence")
    summary_rows = [
        ("Intent", response.get("intent")),
        (
            "Confidence",
            f"{confidence:.0%}" if isinstance(confidence, (int, float)) else None,
        ),
        ("Request ID", response.get("request_id")),
        ("Correlation ID", response.get("correlation_id")),
        ("Explanation", response.get("explanation")),
    ]
    show_table(summary_rows, "Summary")

    # --- Extracted metadata ---
    metadata = response.get("metadata") or {}
    metadata_rows = [
        (key.replace("_", " ").capitalize(), value)
        for key, value in metadata.items()
        if value not in (None, "")
    ]
    show_table(metadata_rows, "Extracted metadata")

    # --- Routing, including the MCP hop ---
    routing_rows = [
        (label, response.get(key))
        for key, label in ROUTING_FIELDS
        if response.get(key)
    ]
    show_table(routing_rows, "Routing")

    # --- Tool execution ---
    # The result now lives under tool_result, not at the top level. The fallback
    # to response["result"] keeps this working with the older flat shape.
    tool_result = response.get("tool_result") or {}

    if tool_result:
        execution_rows = [
            ("Tool name", tool_result.get("tool_name")),
            ("Status", tool_result.get("status")),
            ("Operation ID", tool_result.get("operation_id")),
            ("Succeeded", tool_result.get("success")),
            ("Error", tool_result.get("error")),
        ]
        show_table(execution_rows, "Tool execution")

    result = tool_result.get("result") or response.get("result")
    if isinstance(result, dict) and result:
        render_result_table(response.get("intent") or "", result)

    with st.expander("Raw response (JSON)"):
        st.json(response)


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------
def render_sidebar() -> None:
    """Environment status, example queries and session controls."""
    with st.sidebar:
        st.header("Environment")

        status = get_config_status()

        st.caption("Ollama")
        st.text(f"Host  : {status['ollama_host']}")
        st.text(f"Model : {status['model_name']}")

        if st.button("Test Ollama connection", use_container_width=True):
            is_ok, message = check_ollama()
            st.success(message) if is_ok else st.error(message)

        st.divider()
        st.caption("Microsoft Graph credentials")

        for label, key in (
            ("Client ID", "graph_client_id"),
            ("Client secret", "graph_client_secret"),
            ("Tenant ID", "graph_tenant_id"),
        ):
            st.text(f"{'✅' if status[key] else '❌'} {label}")

        if not all(
            status[key]
            for key in ("graph_client_id", "graph_client_secret", "graph_tenant_id")
        ):
            st.warning("Graph credentials are missing. Add them to your .env file.")

        st.divider()
        st.caption("Example queries")

        # Clicking an example queues it and reruns, so it flows through exactly
        # the same path as a typed query.
        for example in EXAMPLE_QUERIES:
            if st.button(example, use_container_width=True, key=f"example_{example}"):
                st.session_state.queued_query = example
                st.rerun()

        st.divider()
        st.caption(f"Logs: {LOG_FILE}")

        if st.session_state.conversation:
            if st.button("Clear conversation", use_container_width=True):
                st.session_state.conversation = []
                st.rerun()

            st.download_button(
                "Download as JSON",
                data=json.dumps(st.session_state.conversation, indent=2, default=str),
                file_name="techadmin_session.json",
                mime="application/json",
                use_container_width=True,
            )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    init_state()

    st.title("🛠️ TechAdmin IT Support")
    st.caption(
        "Type your request in plain English. Supported: get user details, reset password."
    )

    service = get_service()

    # Replay the conversation so far. Only the query text is stored for the user
    # turns; the assistant turns keep the full response dict so the expanders
    # still work after a rerun.
    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.write(turn["content"])
            else:
                render_response(turn["content"])

    # A queued example takes priority, otherwise use whatever was typed.
    query = st.session_state.queued_query or st.chat_input(
        "e.g. Get details for amit.bhagat@coforge.com"
    )
    st.session_state.queued_query = None

    if query:
        with st.chat_message("user"):
            st.write(query)

        with st.chat_message("assistant"):
            with st.spinner("Classifying intent and running the operation..."):
                response = service.run_query(query)

            render_response(response)

        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.conversation.append(
            {"role": "user", "content": query, "time": timestamp}
        )
        st.session_state.conversation.append(
            {"role": "assistant", "content": response, "time": timestamp}
        )

    elif not st.session_state.conversation:
        st.info(
            "Enter a request below, or pick an example from the sidebar.\n\n"
            "Examples:\n"
            "- Get details for amit.bhagat@coforge.com\n"
            "- Reset password for aman.gupta"
        )

    # The sidebar is rendered last, after the conversation has been updated, so
    # the Clear and Download controls appear on the same run as the first query
    # rather than only after the next interaction. Streamlit places this content
    # in the sidebar regardless of when it is called.
    render_sidebar()


if __name__ == "__main__":
    main()

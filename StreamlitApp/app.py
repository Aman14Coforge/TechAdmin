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
from typing import Any, Dict

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
def render_user_details(user_data: Dict[str, Any]) -> None:
    """Show the fields returned by Microsoft Graph in a readable layout."""
    left, right = st.columns(2)

    with left:
        st.markdown("**Display name**")
        st.write(user_data.get("displayName") or "—")
        st.markdown("**User principal name**")
        st.write(user_data.get("userPrincipalName") or "—")
        st.markdown("**Mail**")
        st.write(user_data.get("mail") or "—")

    with right:
        st.markdown("**User ID**")
        st.code(user_data.get("id") or "—", language=None)
        st.markdown("**User type**")
        st.write(user_data.get("userType") or "—")
        st.markdown("**AD sync enabled**")
        st.write(user_data.get("onPremisesSyncEnabled"))

    enabled = user_data.get("accountEnabled")
    if enabled is True:
        st.success("Account is enabled")
    elif enabled is False:
        st.warning("Account is disabled")


def render_password_result(result: Dict[str, Any]) -> None:
    """Show the outcome of a password reset."""
    st.markdown("**User principal name**")
    st.write(result.get("user_principal") or "—")

    temp_password = result.get("new_password")
    if temp_password:
        # Demo behaviour only. In production the temporary password is delivered
        # out of band and should never be rendered in a browser.
        st.warning("Temporary password — demo only, deliver this securely in production.")
        st.code(temp_password, language=None)


def render_response(response: Dict[str, Any]) -> None:
    """Render one workflow response."""
    message = response.get("message") or (
        "Completed successfully." if response.get("success") else "The request could not be completed."
    )

    if response.get("success"):
        st.success(message)
    else:
        st.error(message)
        if response.get("error"):
            st.caption(f"Error: {response['error']}")

    # What the LLM decided, so the classification step is visible and debuggable.
    columns = st.columns(3)
    columns[0].metric("Intent", response.get("intent") or "—")

    confidence = response.get("confidence")
    columns[1].metric(
        "Confidence",
        f"{confidence:.0%}" if isinstance(confidence, (int, float)) else "—",
    )
    columns[2].metric("Request ID", response.get("request_id") or "—")

    metadata = response.get("metadata") or {}
    if any(metadata.values()):
        with st.expander("Extracted metadata"):
            st.json({key: value for key, value in metadata.items() if value})

    result = response.get("result")
    if response.get("success") and isinstance(result, dict):
        st.divider()
        if response.get("intent") == "password_reset":
            render_password_result(result)
        else:
            render_user_details(result)

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

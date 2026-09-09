"""TechAdmin Streamlit UI."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict, List

import pandas as pd
import streamlit as st

from flow_service import LOG_FILE, FlowService, check_ollama, get_config_status

st.set_page_config(page_title="TechAdmin IT Support", page_icon="🛠️", layout="centered")

EXAMPLE_QUERIES = [
    "Get user details for Shreesanyog.Rath@Coforge.com",
    "Get user details for Shreesanyog.Rath@Coforge.com via script",
    "Reset password for MigrationTest2@Coforge.com",
]

USER_DETAIL_FIELDS = [
    ("displayName", "Display name"), ("Name", "Name"),
    ("userPrincipalName", "User principal name"), ("UserPrincipalName", "User principal name"),
    ("mail", "Mail"), ("Mail", "Mail"), ("id", "User ID"),
    ("userType", "User type"), ("accountEnabled", "Account enabled"),
    ("Enabled", "Account enabled"), ("LockedOut", "Locked out"),
    ("SamAccountName", "SAM account name"), ("Department", "Department"),
    ("DistinguishedName", "Distinguished name"),
]
ROUTING_FIELDS = [
    ("selected_agent", "Agent"), ("selected_mcp_server", "MCP server"),
    ("selected_mcp_tool", "MCP tool"), ("selected_tool", "Application tool"),
]


@st.cache_resource(show_spinner="Starting TechAdmin...")
def get_service() -> FlowService:
    return FlowService()


def init_state() -> None:
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    # Session-persistent dashboard cards. They are intentionally excluded
    # from conversation JSON and downloads.
    st.session_state.setdefault("password_cards", [])


def as_text(value: Any) -> str:
    if value is None or value == "": return "—"
    if isinstance(value, bool): return "Yes" if value else "No"
    return str(value)


def show_table(rows: List[tuple], caption: str = "") -> None:
    if not rows: return
    if caption: st.markdown(f"**{caption}**")
    frame = pd.DataFrame([{"Field": label, "Value": as_text(value)} for label, value in rows])
    st.dataframe(frame, hide_index=True, width="stretch")


def pick_fields(data: Dict[str, Any], fields: List[tuple], exclude: set | None = None) -> List[tuple]:
    exclude = exclude or set()
    rows = [(label, data.get(key)) for key, label in fields if key in data and key not in exclude]
    known = {key for key, _ in fields} | exclude
    for key, value in data.items():
        if key not in known and not isinstance(value, (dict, list)):
            rows.append((key.replace("_", " ").capitalize(), value))
    return rows


def register_dashboard_secret(response: Dict[str, Any]) -> None:
    secret = response.pop("_dashboard_secret", None)
    if not isinstance(secret, dict) or not secret.get("password"):
        return

    card = {
        "password": secret["password"],
        "user": secret.get("user") or "Unknown user",
        "backend": secret.get("backend") or "unknown",
        "operation_id": secret.get("operation_id"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    st.session_state.password_cards.insert(0, card)


def render_password_cards() -> None:
    if not st.session_state.password_cards:
        return

    st.subheader("Generated temporary passwords")
    st.warning(
        "These passwords remain visible only in this active Streamlit session. "
        "They are excluded from conversation history and JSON downloads."
    )

    for index, card in enumerate(list(st.session_state.password_cards)):
        with st.container(border=True):
            left, right = st.columns([3, 1])
            with left:
                st.markdown(f"**Account:** {card['user']}")
                st.caption(
                    f"Backend: {card['backend']} | Generated: {card['created_at']} | "
                    f"Operation: {card.get('operation_id') or '—'}"
                )
                st.code(card["password"], language=None)
            with right:
                if st.button("Remove", key=f"remove_password_{index}", width="stretch"):
                    st.session_state.password_cards.pop(index)
                    st.rerun()

    if st.button("Clear all displayed passwords", type="secondary", width="content"):
        st.session_state.password_cards = []
        st.rerun()


def render_result_table(intent: str, result: Dict[str, Any]) -> None:
    backend = result.get("backend")
    if backend:
        show_table([("Execution backend", backend)], "Result")

    if intent == "password_reset":
        rows = pick_fields(
            result,
            [
                ("user_principal_name", "User principal name"),
                ("user_name", "Username"),
                ("temporary_password_generated", "Temporary password generated"),
                ("temporary_password_redacted", "Password removed from audit response"),
            ],
            exclude={"temporary_password", "execution", "backend"},
        )
        show_table(rows)
        execution = result.get("execution")
        if isinstance(execution, dict):
            show_table(
                [("Script", execution.get("script_name")), ("Exit code", execution.get("exit_code")),
                 ("Duration", execution.get("duration_seconds")), ("Dry run", execution.get("dry_run"))],
                "Script execution",
            )
        return

    user = result.get("user") if isinstance(result.get("user"), dict) else result
    show_table(pick_fields(user, USER_DETAIL_FIELDS, exclude={"backend", "execution", "user"}))


def render_response(response: Dict[str, Any]) -> None:
    message = response.get("message") or ("Completed successfully." if response.get("success") else "Request failed.")
    st.success(message) if response.get("success") else st.error(message)
    if response.get("error"): st.caption(f"Error: {response['error']}")
    if response.get("clarification_required"):
        st.info(response.get("clarification_question") or "More information is needed.")

    confidence = response.get("confidence")
    show_table([
        ("Intent", response.get("intent")),
        ("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else None),
        ("Request ID", response.get("request_id")),
        ("Correlation ID", response.get("correlation_id")),
        ("Explanation", response.get("explanation")),
    ], "Summary")

    metadata = response.get("metadata") or {}
    show_table([(k.replace("_", " ").capitalize(), v) for k, v in metadata.items() if v not in (None, "")], "Extracted metadata")
    show_table([(label, response.get(key)) for key, label in ROUTING_FIELDS if response.get(key)], "Routing")

    tool_result = response.get("tool_result") or {}
    if tool_result:
        show_table([
            ("Tool name", tool_result.get("tool_name")), ("Status", tool_result.get("status")),
            ("Operation ID", tool_result.get("operation_id")), ("Succeeded", tool_result.get("success")),
            ("Error", tool_result.get("error")),
        ], "Tool execution")

    result = tool_result.get("result") or response.get("result")
    if isinstance(result, dict) and result:
        render_result_table(response.get("intent") or "", result)

    with st.expander("Raw response (JSON)"):
        st.json(response)


def safe_conversation_for_download() -> list[dict[str, Any]]:
    return copy.deepcopy(st.session_state.conversation)


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Environment")
        status = get_config_status()
        st.caption("Ollama")
        st.text(f"Host  : {status['ollama_host']}")
        st.text(f"Model : {status['model_name']}")
        if st.button("Test Ollama connection", width="stretch"):
            ok, message = check_ollama()
            st.success(message) if ok else st.error(message)

        st.divider(); st.caption("Microsoft Graph credentials")
        for label, key in (("Client ID", "graph_client_id"), ("Client secret", "graph_client_secret"), ("Tenant ID", "graph_tenant_id")):
            st.text(f"{'✅' if status[key] else '❌'} {label}")

        st.divider(); st.caption("Example queries")
        for example in EXAMPLE_QUERIES:
            if st.button(example, width="stretch", key=f"example_{example}"):
                st.session_state.queued_query = example
                st.rerun()

        st.divider(); st.caption(f"Logs: {LOG_FILE}")
        if st.session_state.conversation:
            if st.button("Clear conversation", width="stretch"):
                st.session_state.conversation = []
                st.rerun()
            st.download_button(
                "Download as JSON",
                data=json.dumps(safe_conversation_for_download(), indent=2, default=str),
                file_name="techadmin_session.json",
                mime="application/json",
                width="stretch",
            )


def main() -> None:
    init_state()
    st.title("🛠️ TechAdmin IT Support")
    st.caption("Type your request in plain English. Supported: get user details, reset password.")

    service = get_service()
    render_password_cards()

    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            st.write(turn["content"]) if turn["role"] == "user" else render_response(turn["content"])

    query = st.session_state.queued_query or st.chat_input("e.g. Get user details for derhant")
    st.session_state.queued_query = None

    if query:
        with st.chat_message("user"): st.write(query)
        with st.chat_message("assistant"):
            with st.spinner("Classifying intent and running the operation..."):
                response = service.run_query(query)
            register_dashboard_secret(response)
            render_response(response)

        timestamp = datetime.now().strftime("%H:%M:%S")
        st.session_state.conversation.append({"role": "user", "content": query, "time": timestamp})
        st.session_state.conversation.append({"role": "assistant", "content": response, "time": timestamp})
        if st.session_state.password_cards:
            st.rerun()
    elif not st.session_state.conversation:
        st.info("Enter a request below, or pick an example from the sidebar.")

    render_sidebar()


if __name__ == "__main__":
    main()

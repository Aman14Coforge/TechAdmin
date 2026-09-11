"""TechAdmin Streamlit UI with guardrail confirmation and session password display."""
from __future__ import annotations

import copy
import json
from datetime import datetime
from typing import Any, Dict

import pandas as pd
import streamlit as st
from flow_service import LOG_FILE, FlowService, check_ollama, get_config_status

st.set_page_config(page_title="TechAdmin IT Support", page_icon="🛠️", layout="centered")

EXAMPLES = [
    "Get user details for Shreesanyog.Rath@Coforge.com",
    "Get user details for Shreesanyog.Rath@Coforge.com via script",
    "Reset password for MigrationTest2@Coforge.com",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
]
YES_WORDS = {"yes", "y", "confirm", "confirmed", "proceed", "approve", "approved", "ok", "okay"}
NO_WORDS = {"no", "n", "cancel", "stop", "abort"}


@st.cache_resource(show_spinner="Starting TechAdmin...")
def get_service() -> FlowService:
    return FlowService()


def init_state() -> None:
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    st.session_state.setdefault("pending_confirmation", None)
    st.session_state.setdefault("password_cards", [])
    st.session_state.setdefault("ollama_check_result", None)


def text(value: Any) -> str:
    if value is None or value == "": return "—"
    if isinstance(value, bool): return "Yes" if value else "No"
    return str(value)


def table(rows, caption="") -> None:
    rows = [(a, b) for a, b in rows if b not in (None, "")]
    if not rows: return
    if caption: st.markdown(f"**{caption}**")
    st.dataframe(pd.DataFrame([{"Field": a, "Value": text(b)} for a, b in rows]), hide_index=True, width="stretch")


def flatten_rows(data: Dict[str, Any], excluded=None):
    excluded = excluded or set()
    rows = []
    for key, value in data.items():
        if key in excluded or value in (None, ""): continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, default=str)
        rows.append((key.replace("_", " ").capitalize(), value))
    return rows


def register_secret(response: Dict[str, Any]) -> None:
    secret = response.pop("_dashboard_secret", None)
    if not isinstance(secret, dict) or not secret.get("password"): return
    st.session_state.password_cards.insert(0, {
        **secret,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })


def render_passwords() -> None:
    if not st.session_state.password_cards: return
    st.markdown("### Generated temporary passwords")
    for index, card in enumerate(list(st.session_state.password_cards)):
        with st.container(border=True):
            table([
                ("Account", card.get("user")), ("Backend", card.get("backend")),
                ("Generated", card.get("created_at")), ("Operation ID", card.get("operation_id")),
            ])
            st.code(card.get("password", ""), language=None)
            if st.button("Remove password", key=f"remove_password_{index}"):
                st.session_state.password_cards.pop(index)
                st.rerun()


def render_response(response: Dict[str, Any]) -> None:
    confidence = response.get("confidence")
    table([
        ("Succeeded", response.get("success")), ("Intent", response.get("intent")),
        ("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else None),
        ("Request ID", response.get("request_id")), ("Correlation ID", response.get("correlation_id")),
        ("Explanation", response.get("explanation")), ("Message", response.get("message")),
        ("Error", response.get("error")),
    ], "Summary")
    table(flatten_rows(response.get("metadata") or {}), "Extracted metadata")
    table([
        ("Action", response.get("guardrail_action")), ("Blocked", response.get("guardrail_blocked")),
        ("Confirmation required", response.get("confirmation_required")),
        ("Confirmation prompt", response.get("confirmation_prompt")),
    ], "Guardrails")
    for i, violation in enumerate(response.get("guardrail_violations") or [], 1):
        if isinstance(violation, dict):
            table(flatten_rows(violation), f"Guardrail violation {i}")
    table([
        ("Agent", response.get("selected_agent")), ("MCP server", response.get("selected_mcp_server")),
        ("MCP tool", response.get("selected_mcp_tool")), ("Application tool", response.get("selected_tool")),
    ], "Routing")
    context = response.get("execution_context") or {}
    table(flatten_rows(context), "Execution context")
    tool = response.get("tool_result") or {}
    if isinstance(tool, dict) and tool:
        table([
            ("Tool name", tool.get("tool_name")), ("Status", tool.get("status")),
            ("Operation ID", tool.get("operation_id")), ("Succeeded", tool.get("success")),
            ("Message", tool.get("message")), ("Error", tool.get("error")),
        ], "Tool execution")
        result = tool.get("result")
        if isinstance(result, dict):
            execution = result.get("execution")
            user = result.get("user")
            table(flatten_rows(user if isinstance(user, dict) else result, {"execution", "user", "new_password", "temporary_password"}), "Result")
            if isinstance(execution, dict):
                table(flatten_rows(execution), "Script execution")
    with st.expander("Raw response (JSON)"):
        st.json(response)


def set_pending(response: Dict[str, Any], query: str) -> None:
    if response.get("confirmation_required"):
        st.session_state.pending_confirmation = {
            "query": query,
            "request_id": response.get("request_id"),
            "correlation_id": response.get("correlation_id"),
            "prompt": response.get("confirmation_prompt"),
        }
    else:
        st.session_state.pending_confirmation = None


def run_query(query: str, *, confirmed=False, request_id=None, correlation_id=None, add_user=True) -> None:
    stamp = datetime.now().strftime("%H:%M:%S")
    if add_user:
        with st.chat_message("user"): st.write(query)
        st.session_state.conversation.append({"role": "user", "content": query, "time": stamp})
    with st.chat_message("assistant"):
        with st.spinner("Checking and running the operation..."):
            response = get_service().run_query(query, confirmed=confirmed, request_id=request_id, correlation_id=correlation_id)
        register_secret(response)
        render_response(response)
    st.session_state.conversation.append({"role": "assistant", "content": response, "time": stamp})
    set_pending(response, query)


def render_confirmation() -> None:
    pending = st.session_state.pending_confirmation
    if not isinstance(pending, dict): return
    with st.container(border=True):
        st.markdown("**Approval required**")
        st.write(pending.get("prompt") or "Confirm this operation before continuing.")
        left, right = st.columns(2)
        if left.button("Confirm and proceed", type="primary", width="stretch"):
            st.session_state.pending_confirmation = None
            run_query(pending["query"], confirmed=True, request_id=pending.get("request_id"), correlation_id=pending.get("correlation_id"), add_user=False)
            st.rerun()
        if right.button("Cancel", width="stretch"):
            st.session_state.pending_confirmation = None
            st.rerun()


def render_sidebar() -> None:
    with st.sidebar:
        st.header("Environment")
        status = get_config_status()
        table(flatten_rows(status))
        if st.button("Test Ollama connection", width="stretch"):
            ok, message = check_ollama()
            st.session_state.ollama_check_result = {"connected": ok, "message": message}
        if st.session_state.ollama_check_result:
            table(flatten_rows(st.session_state.ollama_check_result))
        st.divider()
        for example in EXAMPLES:
            if st.button(example, key=example, width="stretch"):
                st.session_state.queued_query = example
                st.rerun()
        st.caption(f"Logs: {LOG_FILE}")
        if st.session_state.conversation:
            if st.button("Clear conversation", width="stretch"):
                st.session_state.conversation = []
                st.session_state.pending_confirmation = None
                st.rerun()
            st.download_button("Download as JSON", json.dumps(copy.deepcopy(st.session_state.conversation), indent=2, default=str), "techadmin_session.json", "application/json", width="stretch")


def main() -> None:
    init_state()
    st.title("🛠️ TechAdmin IT Support")
    st.caption("Guardrailed identity operations through Microsoft Graph and PowerShell.")
    render_passwords()
    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user": st.write(turn["content"])
            elif isinstance(turn["content"], dict): render_response(turn["content"])

    query = st.session_state.queued_query or st.chat_input("Type an identity operation...")
    st.session_state.queued_query = None
    if query:
        pending = st.session_state.pending_confirmation
        answer = query.strip().casefold().rstrip(".!")
        if isinstance(pending, dict) and answer in YES_WORDS:
            st.session_state.pending_confirmation = None
            run_query(pending["query"], confirmed=True, request_id=pending.get("request_id"), correlation_id=pending.get("correlation_id"), add_user=False)
        elif isinstance(pending, dict) and answer in NO_WORDS:
            st.session_state.pending_confirmation = None
        else:
            run_query(query)
        st.rerun()

    render_confirmation()
    render_sidebar()


if __name__ == "__main__":
    main()

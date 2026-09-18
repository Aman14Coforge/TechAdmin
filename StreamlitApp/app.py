"""
TechAdmin Streamlit UI with Microsoft authentication, app_users authorization,
LangGraph workflow execution, operation auditing, secure password delivery,
and CrowdStrike failed-login/account-lockout investigation reporting.
"""
from __future__ import annotations

import copy
import html
import hmac
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable

import pandas as pd
import streamlit as st

from flow_service import (
    LOG_FILE,
    FlowService,
    build_password_download,
    check_ollama,
    email_is_configured,
    get_config_status,
    send_password_to_manager,
)
from App.db.login_authorization import authorize_claims, extract_display_name
from investigation_report_ui import render_investigation_report


# ---------------------------------------------------------------------------
# Page configuration and styling
# ---------------------------------------------------------------------------

st.set_page_config(page_title="TechAdmin", page_icon="🛠️", layout="wide")
st.markdown(
    """
    <style>
    :root {
        --tech-ink:#18212f; --tech-muted:#667085; --tech-blue:#1769aa;
        --tech-blue-soft:#eaf4fb; --tech-line:#d9e2ec;
    }
    [data-testid="stSidebar"] {border-right:1px solid var(--tech-line)}
    [data-testid="stSidebar"]>div:first-child {padding-top:2rem}
    .sidebar-brand {border-bottom:1px solid var(--tech-line);margin:0 0 1.5rem;padding:0 0 1.25rem}
    .company-name {color:#0d4f87;font-size:1.25rem;font-weight:800;letter-spacing:.08em;text-transform:uppercase}
    .sidebar-brand h1 {color:var(--tech-ink);font-size:1.8rem;line-height:1;margin:.45rem 0 0}
    .tech-kicker {color:var(--tech-blue);font-size:.75rem;font-weight:700;letter-spacing:.12em;text-transform:uppercase}
    .tech-panel {background:linear-gradient(135deg,var(--tech-blue-soft),#fff);border:1px solid #cfe3f2;border-radius:.75rem;padding:1.25rem 1.35rem;margin:.5rem 0 1.25rem}
    .tech-panel strong {color:var(--tech-ink);display:block;font-size:1.05rem;margin-bottom:.3rem}
    .tech-panel span {color:var(--tech-muted)}
    .operation-card {border:1px solid var(--tech-line);border-left:4px solid var(--tech-blue);border-radius:.55rem;padding:1rem 1.15rem;margin:1rem 0 1.25rem;background:#fff}
    .operation-card.success {border-left-color:#18864b}
    .operation-card.warning {border-left-color:#b7791f}
    .operation-card.failure {border-left-color:#c53030}
    .operation-label {color:var(--tech-muted);font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
    .operation-title {color:var(--tech-ink);font-size:1.2rem;font-weight:700;margin-top:.25rem}
    .operation-meta {color:var(--tech-muted);margin-top:.45rem}
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Authentication and app_users authorization
# ---------------------------------------------------------------------------

def enforce_app_user_access(claims: dict[str, Any]) -> None:
    """Authorize an authenticated identity against the app_users database."""
    display_name = extract_display_name(claims)

    if not display_name:
        st.session_state.app_user_access = {
            "display_name": "",
            "allowed": True,
            "reason": "legacy_sso_login",
            "message": "",
            "user_principal_name": "",
            "user_id": "",
            "department": "",
        }
        return

    cached = st.session_state.get("app_user_access")
    if not (isinstance(cached, dict) and cached.get("display_name") == display_name):
        decision = authorize_claims(claims)
        cached = {
            "display_name": display_name,
            "allowed": decision.allowed,
            "reason": decision.reason,
            "message": decision.message,
            "user_principal_name": decision.user_principal_name,
            "user_id": decision.user_id,
            "department": decision.department,
        }
        st.session_state.app_user_access = cached

    if cached["allowed"]:
        return

    st.title("TechAdmin")
    st.error(cached["message"])
    st.caption(
        f"Signed in as: {display_name or 'unknown'}. Access is granted only "
        "to active users registered in the TechAdmin app_users directory."
    )
    if st.button("Sign out", key="denied_sign_out"):
        st.session_state.pop("app_user_access", None)
        st.session_state.pop("local_authenticated_user", None)
        if claims.get("auth_source") != "local_test_account":
            st.logout()
        st.rerun()
    st.stop()


def require_authentication() -> dict[str, Any]:
    """Require Microsoft Entra authentication or configured local test login."""
    local_user = st.session_state.get("local_authenticated_user")
    if isinstance(local_user, dict):
        enforce_app_user_access(local_user)
        render_authenticated_user(local_user)
        return local_user

    if not st.user:
        st.title("TechAdmin")
        st.subheader("Sign in to TechAdmin")
        microsoft_tab, local_tab = st.tabs(["Microsoft SSO", "Test account"])
        with microsoft_tab:
            st.write("Use your Coforge Microsoft account.")
            if st.button("Sign in with Microsoft", type="primary", width="stretch"):
                st.login()
        with local_tab:
            render_local_login()
        st.stop()

    claims = dict(st.user)
    if not extract_display_name(claims):
        st.title("TechAdmin")
        st.warning("The current Microsoft session does not contain a usable identity.")
        if st.button("Restart Microsoft sign-in", type="primary"):
            st.logout()
            st.login()
        st.stop()

    # Tenant restriction can be re-enabled after production tenant alignment.
    # expected_tenant = str(st.secrets.get("entra", {}).get("allowed_tenant_id", "")).strip()
    # actual_tenant = str(claims.get("tid", "")).strip()
    # if expected_tenant and actual_tenant != expected_tenant:
    #     st.error("This Microsoft tenant is not authorized for TechAdmin.")
    #     if st.button("Sign out"):
    #         st.logout()
    #     st.stop()

    enforce_app_user_access(claims)
    render_authenticated_user(claims)
    return claims


def render_local_login() -> None:
    """Authenticate the explicitly configured local development account."""
    if os.getenv("TECHADMIN_LOCAL_LOGIN_ENABLED", "false").casefold() != "true":
        st.info("The local test account is disabled.")
        return

    with st.form("local_login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", width="stretch")

    if not submitted:
        return

    expected_username = os.getenv("TECHADMIN_LOCAL_LOGIN_USERNAME", "TechAdminTestUser")
    expected_password = os.getenv("TECHADMIN_LOCAL_LOGIN_PASSWORD", "")
    valid_username = hmac.compare_digest(username.strip().casefold(), expected_username.strip().casefold())
    valid_password = bool(expected_password) and hmac.compare_digest(password, expected_password)
    if not (valid_username and valid_password):
        st.error("Invalid username or password.")
        return

    st.session_state.local_authenticated_user = {
        "name": expected_username,
        "preferred_username": expected_username,
        "auth_source": "local_test_account",
    }
    st.session_state.pop("app_user_access", None)
    st.rerun()


def render_authenticated_user(claims: dict[str, Any]) -> None:
    """Render authenticated identity and logout action."""
    with st.sidebar:
        st.markdown(
            '<div class="sidebar-brand"><div class="company-name">Coforge</div>'
            '<h1>TechAdmin</h1><div class="tech-kicker">IT Operations</div></div>',
            unsafe_allow_html=True,
        )
        display_name = claims.get("name") or claims.get("preferred_username") or "Authenticated user"
        st.caption(f"Signed in as {display_name}")
        if claims.get("auth_source") == "local_test_account":
            if st.button("Sign out", key="local_sign_out", width="stretch"):
                st.session_state.pop("local_authenticated_user", None)
                st.session_state.pop("app_user_access", None)
                st.rerun()
        elif st.button("Sign out", key="sign_out", width="stretch"):
            st.session_state.pop("app_user_access", None)
            st.logout()


# ---------------------------------------------------------------------------
# Constants and session state
# ---------------------------------------------------------------------------

EXAMPLES = [
    "Get user details for MigrationTest2@Coforge.com",
    "Get user details for MigrationTest2@Coforge.com via script",
    "Get user details for MigrationTest2@Coforge.com via API",
    "Reset password for MigrationTest2@Coforge.com",
    "Reset password for MigrationTest2@Coforge.com via script",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
    "Investigate failed logins for MigrationTest2@Coforge.com in the last 24 hours",
    "Investigate account lockout for MigrationTest3@Coforge.com in the last 7 days",
]
YES_WORDS = {"yes", "y", "confirm", "confirmed", "proceed", "approve", "approved", "ok", "okay"}
NO_WORDS = {"no", "n", "cancel", "stop", "abort", "nevermind"}
SENSITIVE_HISTORY_KEYS = {
    "new_password", "temporary_password", "password", "initial_password", "domain_password",
    "admin_password", "client_secret", "access_token", "refresh_token", "_dashboard_secret",
    "_transient_password",
}


@st.cache_resource(show_spinner="Starting TechAdmin...")
def get_service() -> FlowService:
    """Create and cache the LangGraph-backed workflow service."""
    return FlowService()


def init_state() -> None:
    """Initialize Streamlit session state."""
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    st.session_state.setdefault("pending_confirmation", None)
    st.session_state.setdefault("password_cards", [])
    st.session_state.setdefault("ollama_check_result", None)


# ---------------------------------------------------------------------------
# Generic formatting and redaction
# ---------------------------------------------------------------------------

def display_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def show_table(rows: Iterable[tuple[str, Any]], caption: str = "") -> None:
    prepared = [(label, value) for label, value in rows if value not in (None, "")]
    if not prepared:
        return
    if caption:
        st.markdown(f"**{caption}**")
    frame = pd.DataFrame([{"Field": label, "Value": display_text(value)} for label, value in prepared])
    st.dataframe(frame, hide_index=True, width="stretch")


def flatten_rows(data: Dict[str, Any], excluded: set[str] | None = None) -> list[tuple[str, Any]]:
    rows: list[tuple[str, Any]] = []
    for key, value in data.items():
        if key in (excluded or set()) or value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        rows.append((key.replace("_", " ").capitalize(), value))
    return rows


def redact_sensitive_history(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
        for key, item in value.items():
            normalized = key.strip().casefold()
            if normalized in SENSITIVE_HISTORY_KEYS:
                if normalized != "_dashboard_secret":
                    cleaned[key] = "[redacted]"
                continue
            cleaned[key] = redact_sensitive_history(item)
        return cleaned
    if isinstance(value, list):
        return [redact_sensitive_history(item) for item in value]
    return value


def register_dashboard_secret(response: Dict[str, Any]) -> bool:
    """Discard any legacy plaintext dashboard secret before history storage."""
    response.pop("_dashboard_secret", None)
    return False


# ---------------------------------------------------------------------------
# Result renderers
# ---------------------------------------------------------------------------

def render_script_execution(execution: Dict[str, Any]) -> None:
    show_table([
        ("Success", execution.get("success")), ("Operation", execution.get("operation")),
        ("Script", execution.get("script_name")), ("Exit code", execution.get("exit_code")),
        ("Duration seconds", execution.get("duration_seconds")), ("Dry run", execution.get("dry_run")),
        ("Standard output", execution.get("stdout")), ("Standard error", execution.get("stderr")),
        ("Error", execution.get("error")),
    ], "Script execution")


def render_guardrails(response: Dict[str, Any]) -> None:
    show_table([
        ("Action", response.get("guardrail_action")), ("Blocked", response.get("guardrail_blocked")),
        ("Confirmation required", response.get("confirmation_required")),
        ("Confirmation prompt", response.get("confirmation_prompt")),
        ("Output filtered fields", response.get("guardrails_output_filtered")),
    ], "Guardrails")
    violations = response.get("guardrail_violations")
    if isinstance(violations, list):
        for index, violation in enumerate(violations, 1):
            if isinstance(violation, dict):
                show_table(flatten_rows(violation), f"Guardrail violation {index}")


def render_password_actions(token: str, manager_email: str) -> None:
    status_key = f"email_status_{token}"
    st.session_state.setdefault(status_key, None)
    can_email = bool(manager_email) and manager_email != "Not Available" and email_is_configured()
    left, right = st.columns(2)
    if left.button("Send Email To Manager", key=f"send_{token}", disabled=not can_email, width="stretch"):
        with st.spinner("Sending email..."):
            sent, message, recipient = send_password_to_manager(token)
        st.session_state[status_key] = {"sent": sent, "message": message, "recipient": recipient}

    ok, filename, content, message = build_password_download(token)
    if ok:
        right.download_button(
            "Download Password TXT", data=content, file_name=filename, mime="text/plain",
            key=f"dl_{token}", width="stretch",
        )
    else:
        right.button("Download Password TXT", key=f"dl_disabled_{token}", disabled=True, width="stretch")
        st.caption(message)

    status = st.session_state.get(status_key)
    if status is None:
        st.caption("Email status: Not Sent")
    elif status["sent"]:
        st.success(f"Email status: Sent Successfully to {status['recipient']}")
    else:
        st.error(f"Email status: Failed. {status['message']}")


def render_password_reset_actions(result: Dict[str, Any]) -> None:
    st.success("Password Reset Successful")
    manager_name = result.get("manager_name") or "Not Available"
    manager_email = result.get("manager_email") or "Not Available"
    show_table([
        ("Username", result.get("user_name") or result.get("user_principal_name")),
        ("Employee name", result.get("employee_name")),
        ("Temporary password", result.get("masked_password") or "Not Available"),
        ("Manager", manager_name), ("Manager email", manager_email), ("Backend", result.get("backend")),
    ], "Result")
    if isinstance(result.get("execution"), dict):
        render_script_execution(result["execution"])
    if manager_name == "Not Available":
        st.info("No manager is assigned. The password file can still be downloaded.")
    token = result.get("password_token")
    if not token:
        st.warning("The password is no longer retrievable for this reset. Run the reset again.")
        return
    render_password_actions(token, manager_email)


def render_result(intent: str, result: Dict[str, Any]) -> None:
    """Render generic results or specialized password/investigation reports."""
    if intent == "failed_login_investigation":
        report = result.get("report")
        if isinstance(report, dict):
            render_investigation_report(report)
            return
        st.warning("The investigation completed without a structured report payload.")
        show_table([
            ("Source", result.get("source")),
            ("Allowed event IDs", result.get("allowed_event_ids")),
            ("Message", result.get("message")),
        ], "Investigation result")
        return

    if intent == "password_reset" and result.get("password_token"):
        render_password_reset_actions(result)
        return

    execution = result.get("execution")
    user_record = result.get("user")
    excluded = {
        "execution", "user", "new_password", "temporary_password", "_transient_password",
        "report", "report_markdown",
    }
    if isinstance(user_record, dict):
        rows = [("Backend", result.get("backend"))]
        rows.extend(flatten_rows(user_record))
    else:
        rows = flatten_rows(result, excluded)
    show_table(rows, "Result")
    if isinstance(execution, dict):
        render_script_execution(execution)


def render_operation_summary(response: Dict[str, Any]) -> None:
    intent = str(response.get("intent") or "Identity operation")
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    target = metadata.get("email") or metadata.get("username") or metadata.get("user_id") or "Unknown target"
    if response.get("confirmation_required"):
        status, css = "Confirmation required", "warning"
    elif response.get("success") is True:
        status, css = "Completed", "success"
    elif response.get("success") is False:
        status, css = "Failed", "failure"
    else:
        status, css = "Submitted", ""
    st.markdown(
        f'<div class="operation-card {css}"><div class="operation-label">Current operation</div>'
        f'<div class="operation-title">{html.escape(intent.replace("_", " ").title())}</div>'
        f'<div class="operation-meta"><strong>Target:</strong> {html.escape(str(target))} &nbsp; | &nbsp; '
        f'<strong>Status:</strong> {html.escape(status)}</div></div>',
        unsafe_allow_html=True,
    )


def render_response(response: Dict[str, Any]) -> None:
    render_operation_summary(response)
    confidence = response.get("confidence")
    show_table([
        ("Succeeded", response.get("success")), ("Intent", response.get("intent")),
        ("Confidence", f"{confidence:.0%}" if isinstance(confidence, (int, float)) else None),
        ("Request ID", response.get("request_id")), ("Correlation ID", response.get("correlation_id")),
        ("Explanation", response.get("explanation")), ("Message", response.get("message")),
        ("Error", response.get("error")),
    ], "Summary")

    metadata = response.get("metadata")
    if isinstance(metadata, dict):
        show_table(flatten_rows(metadata, SENSITIVE_HISTORY_KEYS), "Extracted metadata")
    render_guardrails(response)
    show_table([
        ("Agent", response.get("selected_agent")), ("MCP server", response.get("selected_mcp_server")),
        ("MCP tool", response.get("selected_mcp_tool")), ("Application tool", response.get("selected_tool")),
    ], "Routing")

    if isinstance(response.get("orchestration"), dict):
        show_table(flatten_rows(response["orchestration"]), "Orchestration")
    if isinstance(response.get("execution_context"), dict):
        show_table(flatten_rows(response["execution_context"]), "Execution context")

    tool_result = response.get("tool_result")
    if isinstance(tool_result, dict) and tool_result:
        show_table([
            ("Tool name", tool_result.get("tool_name")), ("Status", tool_result.get("status")),
            ("Operation ID", tool_result.get("operation_id")), ("Succeeded", tool_result.get("success")),
            ("Message", tool_result.get("message")), ("Error", tool_result.get("error")),
            ("API integration pending", tool_result.get("api_integration_pending")),
        ], "Tool execution")
        if isinstance(tool_result.get("result"), dict):
            render_result(response.get("intent") or "", tool_result["result"])

    label = "Technical investigation details" if response.get("intent") == "failed_login_investigation" else "Raw response (JSON)"
    with st.expander(label, expanded=False):
        st.json(redact_sensitive_history(copy.deepcopy(response)))


# ---------------------------------------------------------------------------
# Confirmation and conversation workflow
# ---------------------------------------------------------------------------

def set_pending_confirmation(response: Dict[str, Any], query: str) -> None:
    if response.get("confirmation_required"):
        st.session_state.pending_confirmation = {
            "query": query,
            "request_id": response.get("request_id"),
            "correlation_id": response.get("correlation_id"),
            "intent": response.get("intent"),
            "prompt": response.get("confirmation_prompt"),
        }
    else:
        st.session_state.pending_confirmation = None


def append_conversation(role: str, content: Any, timestamp: str) -> None:
    st.session_state.conversation.append({
        "role": role,
        "content": redact_sensitive_history(copy.deepcopy(content)),
        "time": timestamp,
    })


def execute_and_render(
    query: str,
    *,
    confirmed: bool = False,
    request_id: str | None = None,
    correlation_id: str | None = None,
    add_user_turn: bool = True,
) -> Dict[str, Any]:
    timestamp = datetime.now().strftime("%H:%M:%S")
    if add_user_turn:
        with st.chat_message("user"):
            st.write(query)
        append_conversation("user", query, timestamp)

    with st.chat_message("assistant"):
        with st.spinner("Checking and running the operation..."):
            response = get_service().run_query(
                query,
                confirmed=confirmed,
                request_id=request_id,
                correlation_id=correlation_id,
            )
        register_dashboard_secret(response)
        render_response(response)

    append_conversation("assistant", response, timestamp)
    set_pending_confirmation(response, query)
    return response


def cancel_pending_confirmation() -> None:
    pending = st.session_state.pending_confirmation
    st.session_state.pending_confirmation = None
    response = {
        "success": False,
        "cancelled": True,
        "request_id": pending.get("request_id") if isinstance(pending, dict) else None,
        "correlation_id": pending.get("correlation_id") if isinstance(pending, dict) else None,
        "intent": pending.get("intent") if isinstance(pending, dict) else None,
        "message": "Operation cancelled. No changes were made.",
        "error": None,
    }
    append_conversation("assistant", response, datetime.now().strftime("%H:%M:%S"))
    st.rerun()


def render_confirmation_controls() -> None:
    pending = st.session_state.pending_confirmation
    if not isinstance(pending, dict):
        return
    with st.container(border=True):
        st.markdown("**Approval required**")
        st.write(pending.get("prompt") or "Confirm this operation before continuing.")
        left, right = st.columns(2)
        if left.button("Confirm and proceed", type="primary", width="stretch"):
            st.session_state.pending_confirmation = None
            execute_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending.get("request_id"),
                correlation_id=pending.get("correlation_id"),
                add_user_turn=False,
            )
            st.rerun()
        if right.button("Cancel", width="stretch"):
            cancel_pending_confirmation()


# ---------------------------------------------------------------------------
# Sidebar and main application
# ---------------------------------------------------------------------------

def safe_conversation_download() -> str:
    return json.dumps(
        redact_sensitive_history(copy.deepcopy(st.session_state.conversation)),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def render_sidebar() -> None:
    with st.sidebar:
        st.header("System status")
        status = get_config_status()
        show_table([
            ("Microsoft Graph", "Configured" if status.get("graph_client_id") and status.get("graph_client_secret") and status.get("graph_tenant_id") else "Incomplete"),
            ("PowerShell", "Enabled" if status.get("powershell_operations_enabled") else "Disabled"),
            ("Destructive actions", "Enabled" if status.get("destructive_operations_enabled") else "Disabled"),
            ("LangGraph", "Active" if status.get("orchestration_engine") == "langgraph" else "Unavailable"),
            ("Operation audit", "Enabled" if status.get("operation_audit_enabled") else "Unknown"),
            ("Configuration", "Valid" if status.get("config_valid") else "Invalid"),
        ])

        if st.button("Test Ollama connection", width="stretch"):
            connected, message = check_ollama()
            st.session_state.ollama_check_result = {"connected": connected, "message": message}
        if isinstance(st.session_state.ollama_check_result, dict):
            show_table(flatten_rows(st.session_state.ollama_check_result))

        with st.expander("Environment details"):
            show_table(flatten_rows(status, {"graph_client_secret"}))

        st.divider()
        st.caption("Example queries")
        for index, example in enumerate(EXAMPLES):
            if st.button(example, key=f"example_{index}", width="stretch"):
                st.session_state.queued_query = example
                st.rerun()

        st.divider()
        st.caption(f"Logs: {LOG_FILE}")
        if st.session_state.conversation:
            if st.button("Clear conversation", width="stretch"):
                st.session_state.conversation = []
                st.session_state.pending_confirmation = None
                st.rerun()
            st.download_button(
                "Download as JSON",
                data=safe_conversation_download(),
                file_name="techadmin_session.json",
                mime="application/json",
                width="stretch",
            )


def render_recent_operations() -> None:
    operations = []
    for turn in reversed(st.session_state.conversation):
        if turn.get("role") != "assistant" or not isinstance(turn.get("content"), dict):
            continue
        response = turn["content"]
        metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
        if response.get("confirmation_required"):
            status = "Awaiting confirmation"
        elif response.get("cancelled"):
            status = "Cancelled"
        elif response.get("success") is True:
            status = "Completed"
        else:
            status = "Failed"
        operations.append({
            "Operation": str(response.get("intent") or "Identity operation").replace("_", " ").title(),
            "Target": metadata.get("email") or metadata.get("username") or "Unknown target",
            "Status": status,
            "Time": turn.get("time", ""),
        })
        if len(operations) == 5:
            break
    if operations:
        st.markdown("#### Recent operations")
        st.dataframe(pd.DataFrame(operations), hide_index=True, width="stretch")


def render_command_center() -> None:
    if st.session_state.conversation:
        return
    st.markdown(
        '<div class="tech-panel"><strong>What do you need to take care of?</strong>'
        '<span>Ask for a user lookup, password reset, access change, or failed-login/account-lockout investigation. Sensitive actions pause for confirmation.</span></div>',
        unsafe_allow_html=True,
    )


def main() -> None:
    require_authentication()
    init_state()
    render_command_center()

    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.write(turn["content"])
            elif isinstance(turn["content"], dict):
                render_response(turn["content"])

    query = st.session_state.queued_query or st.chat_input("Type an identity operation...")
    st.session_state.queued_query = None
    if query:
        pending = st.session_state.pending_confirmation
        answer = query.strip().casefold().rstrip(".!")
        if isinstance(pending, dict) and answer in YES_WORDS:
            append_conversation("user", query, datetime.now().strftime("%H:%M:%S"))
            st.session_state.pending_confirmation = None
            execute_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending.get("request_id"),
                correlation_id=pending.get("correlation_id"),
                add_user_turn=False,
            )
        elif isinstance(pending, dict) and answer in NO_WORDS:
            append_conversation("user", query, datetime.now().strftime("%H:%M:%S"))
            cancel_pending_confirmation()
        else:
            execute_and_render(query)
        st.rerun()

    render_confirmation_controls()
    render_recent_operations()
    render_sidebar()


if __name__ == "__main__":
    main()

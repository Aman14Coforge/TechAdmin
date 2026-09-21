"""
TechAdmin Streamlit UI with Microsoft authentication, app_users authorization,
LangGraph workflow execution, operation auditing, secure password delivery,
and CrowdStrike failed-login/account-lockout investigation reporting.
 
Features:
    - Microsoft Entra sign-in through Streamlit OIDC.
    - Configured local Test account sign-in.
    - app_users database authorization for Microsoft and Test identities.
    - Structured workflow-result tables.
    - Dedicated CrowdStrike failed-login and account-lockout report.
    - Guardrail confirmation controls for sensitive operations.
    - Request ID and correlation ID reuse after confirmation.
    - Secure password TXT download and explicit manager email.
    - Password-safe conversation history and JSON download.
    - Microsoft Graph, PowerShell, MCP, and LangGraph result support.
 
Run from the project root:
    python -m streamlit run StreamlitApp/app.py
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
 
st.set_page_config(
    page_title="TechAdmin",
    page_icon="🛠️",
    layout="wide",
)


def enforce_https_origin() -> None:
    """Redirect insecure browser access to the public HTTPS origin."""

    public_url = (
        os.getenv("TECHADMIN_PUBLIC_URL", "https://techadmin.coforge.com")
        .strip()
    )
    if not public_url:
        return

    st.markdown(
        f"""
        <script>
        (() => {{
            try {{
                const publicUrl = new URL("{public_url}");
                const current = new URL(window.location.href);
                const sameHost = current.hostname === publicUrl.hostname;
                const needsHttps = current.protocol === "http:" && sameHost;
                if (needsHttps) {{
                    const target = new URL(window.location.href);
                    target.protocol = "https:";
                    target.port = publicUrl.port || "";
                    window.location.replace(target.toString());
                }}
            }} catch (e) {{}}
        }})();
        </script>
        """,
        unsafe_allow_html=True,
    )


enforce_https_origin()

st.markdown(
    """
    <style>
    :root {
        --tech-ink: #18212f;
        --tech-muted: #667085;
        --tech-blue: #1769aa;
        --tech-blue-soft: #eaf4fb;
        --tech-line: #d9e2ec;
        --tech-warm: #f7f4ee;
    }
 
    [data-testid="stSidebar"] {
        border-right: 1px solid var(--tech-line);
    }
 
    [data-testid="stSidebar"] > div:first-child {
        padding-top: 2rem;
    }
 
    .sidebar-brand {
        border-bottom: 1px solid var(--tech-line);
        margin: 0 0 1.5rem;
        padding: 0 0 1.25rem;
    }
 
    .sidebar-brand .company-name {
        color: #0d4f87;
        font-size: 1.25rem;
        font-weight: 800;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
 
    .sidebar-brand h1 {
        color: var(--tech-ink);
        font-size: 1.8rem;
        line-height: 1;
        margin: 0.45rem 0 0;
    }
 
    .tech-kicker {
        color: var(--tech-blue);
        font-size: 0.75rem;
        font-weight: 700;
        letter-spacing: 0.12em;
        text-transform: uppercase;
    }
 
    .tech-panel {
        background: linear-gradient(135deg, var(--tech-blue-soft), #fff);
        border: 1px solid #cfe3f2;
        border-radius: 0.75rem;
        padding: 1.25rem 1.35rem;
        margin: 0.5rem 0 1.25rem;
    }
 
    .tech-panel strong {
        color: var(--tech-ink);
        display: block;
        font-size: 1.05rem;
        margin-bottom: 0.3rem;
    }
 
    .tech-panel span {
        color: var(--tech-muted);
    }
 
    div[data-testid="stChatInput"] {
        margin-top: 1rem;
    }
 
    .operation-card {
        border: 1px solid var(--tech-line);
        border-left: 4px solid var(--tech-blue);
        border-radius: 0.55rem;
        padding: 1rem 1.15rem;
        margin: 1rem 0 1.25rem;
        background: #fff;
    }
 
    .operation-card.success {
        border-left-color: #18864b;
    }
 
    .operation-card.warning {
        border-left-color: #b7791f;
    }
 
    .operation-card.failure {
        border-left-color: #c53030;
    }
 
    .operation-label {
        color: var(--tech-muted);
        font-size: 0.72rem;
        font-weight: 700;
        letter-spacing: 0.08em;
        text-transform: uppercase;
    }
 
    .operation-title {
        color: var(--tech-ink);
        font-size: 1.2rem;
        font-weight: 700;
        margin-top: 0.25rem;
    }
 
    .operation-meta {
        color: var(--tech-muted);
        margin-top: 0.45rem;
    }
    </style>
    """,
    unsafe_allow_html=True,
)
 
 
# ---------------------------------------------------------------------------
# Authentication and app_users authorization
# ---------------------------------------------------------------------------
 
 
def microsoft_user_is_logged_in() -> bool:
    """Safely determine whether Streamlit has a Microsoft login session."""
 
    try:
        return bool(st.user.is_logged_in)
    except (AttributeError, RuntimeError, TypeError):
        return False
 
 
def clear_local_authentication_state() -> None:
    """Clear cached local identity and app_users authorization state."""
 
    st.session_state.pop("local_authenticated_user", None)
    st.session_state.pop("app_user_access", None)
 
 
def render_sign_in_screen(
    *,
    microsoft_message: str | None = None,
) -> None:
    """Render both Microsoft SSO and Test account sign-in choices."""
 
    st.title("TechAdmin")
    st.subheader("Sign in to TechAdmin")
 
    if microsoft_message:
        st.warning(microsoft_message)
 
    microsoft_tab, local_tab = st.tabs(
        ["Microsoft SSO", "Test account"]
    )
 
    with microsoft_tab:
        st.write("Use your Coforge Microsoft account.")
 
        if st.button(
            "Sign in with Microsoft",
            type="primary",
            width="stretch",
            key="microsoft_sign_in",
        ):
            st.login()
 
    with local_tab:
        render_local_login()
 
    st.stop()
 
 
def enforce_app_user_access(claims: dict[str, Any]) -> None:
    """Authorize an authenticated identity against the app_users database."""
 
    display_name = extract_display_name(claims)
 
    # Preserve legacy claim-shape compatibility. Microsoft sessions with no
    # usable identity are intercepted in require_authentication() before here.
    if not display_name:
        st.session_state.app_user_access = {
            "display_name": "",
            "allowed": True,
            "reason": "legacy_identity_without_display_name",
            "message": "",
            "user_principal_name": "",
            "user_id": "",
            "department": "",
        }
        return
 
    cached = st.session_state.get("app_user_access")
 
    if not (
        isinstance(cached, dict)
        and cached.get("display_name") == display_name
    ):
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
 
    if cached.get("allowed") is True:
        return
 
    st.title("TechAdmin")
    st.error(
        cached.get("message")
        or "This identity is not authorized to use TechAdmin."
    )
    st.caption(
        f"Signed in as: {display_name or 'unknown'}. "
        "Access is granted only to active users registered in the "
        "TechAdmin app_users directory."
    )
 
    if claims.get("auth_source") == "local_test_account":
        if st.button(
            "Return to sign in",
            key="denied_local_sign_out",
            width="content",
        ):
            clear_local_authentication_state()
            st.rerun()
    else:
        if st.button(
            "Sign out",
            key="denied_microsoft_sign_out",
            width="content",
        ):
            clear_local_authentication_state()
            st.logout()
 
    st.stop()
 
 
def require_authentication() -> dict[str, Any]:
    """Require Microsoft Entra or configured Test account authentication."""
 
    local_user = st.session_state.get("local_authenticated_user")
 
    if isinstance(local_user, dict):
        enforce_app_user_access(local_user)
        render_authenticated_user(local_user)
        return local_user
 
    # Do not use `if not st.user`. st.user is a proxy object and can exist even
    # when the browser has no usable authenticated identity.
    if not microsoft_user_is_logged_in():
        render_sign_in_screen()
 
    claims = dict(st.user)
    claims.pop("is_logged_in", None)
 
    if not extract_display_name(claims):
        # Keep Test account available if the Microsoft cookie is stale or its
        # identity token does not contain the application's expected claims.
        st.title("TechAdmin")
        st.warning(
            "The current Microsoft session does not contain a usable identity."
        )
 
        microsoft_tab, local_tab = st.tabs(
            ["Microsoft SSO", "Test account"]
        )
 
        with microsoft_tab:
            st.write(
                "Sign out of the incomplete Microsoft session, then start "
                "Microsoft sign-in again."
            )
 
            if st.button(
                "Sign out and restart",
                type="primary",
                width="stretch",
                key="restart_microsoft_sign_in",
            ):
                clear_local_authentication_state()
                # Do not call st.login immediately afterward. st.logout removes
                # the identity cookie and redirects/reruns the app.
                st.logout()
 
        with local_tab:
            render_local_login()
 
        st.stop()
 
    # Tenant restriction can be re-enabled after production alignment.
    # expected_tenant = str(
    #     st.secrets.get("entra", {}).get("allowed_tenant_id", "")
    # ).strip()
    # actual_tenant = str(claims.get("tid", "")).strip()
    # if expected_tenant and actual_tenant != expected_tenant:
    #     st.error("This Microsoft tenant is not authorized for TechAdmin.")
    #     if st.button("Sign out", key="unauthorized_tenant_sign_out"):
    #         clear_local_authentication_state()
    #         st.logout()
    #     st.stop()
 
    enforce_app_user_access(claims)
    render_authenticated_user(claims)
    return claims
 
 
def render_local_login() -> None:
    """Authenticate the explicitly configured Test account."""
 
    local_login_enabled = (
        os.getenv("TECHADMIN_LOCAL_LOGIN_ENABLED", "false")
        .strip()
        .casefold()
        in {"1", "true", "yes", "on"}
    )
 
    if not local_login_enabled:
        st.info("The local test account is disabled.")
        return
 
    with st.form("local_login_form", clear_on_submit=False):
        username = st.text_input(
            "Username",
            key="local_login_username",
        )
        password = st.text_input(
            "Password",
            type="password",
            key="local_login_password",
        )
        submitted = st.form_submit_button(
            "Sign in",
            type="primary",
            width="stretch",
        )
 
    if not submitted:
        return
 
    expected_username = os.getenv(
        "TECHADMIN_LOCAL_LOGIN_USERNAME",
        "TechAdminTestUser",
    ).strip()
    expected_password = os.getenv(
        "TECHADMIN_LOCAL_LOGIN_PASSWORD",
        "",
    )
 
    valid_username = hmac.compare_digest(
        username.strip().casefold(),
        expected_username.casefold(),
    )
    valid_password = (
        bool(expected_password)
        and hmac.compare_digest(password, expected_password)
    )
 
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
    """Render authenticated identity and the appropriate logout action."""
 
    with st.sidebar:
        st.markdown(
            """
            <div class="sidebar-brand">
                <div class="company-name">Coforge</div>
                <h1>TechAdmin</h1>
                <div class="tech-kicker">IT Operations</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
 
        display_name = (
            claims.get("name")
            or claims.get("preferred_username")
            or claims.get("email")
            or "Authenticated user"
        )
        st.caption(f"Signed in as {display_name}")
 
        if claims.get("auth_source") == "local_test_account":
            if st.button(
                "Sign out",
                key="local_sign_out",
                width="stretch",
            ):
                clear_local_authentication_state()
                st.rerun()
        elif st.button(
            "Sign out",
            key="microsoft_sign_out",
            width="stretch",
        ):
            clear_local_authentication_state()
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
    "Unlock account for MigrationTest2@Coforge.com",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
    (
        "Investigate failed logins for "
        "MigrationTest2@Coforge.com in the last 24 hours"
    ),
    (
        "Investigate account lockout for "
        "MigrationTest3@Coforge.com in the last 7 days"
    ),
]
 
YES_WORDS = {
    "yes",
    "y",
    "confirm",
    "confirmed",
    "proceed",
    "approve",
    "approved",
    "ok",
    "okay",
}
 
NO_WORDS = {
    "no",
    "n",
    "cancel",
    "stop",
    "abort",
    "nevermind",
}
 
SENSITIVE_HISTORY_KEYS = {
    "new_password",
    "temporary_password",
    "password",
    "initial_password",
    "domain_password",
    "admin_password",
    "client_secret",
    "access_token",
    "refresh_token",
    "_dashboard_secret",
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
# Generic formatting and redaction helpers
# ---------------------------------------------------------------------------
 
 
def display_text(value: Any) -> str:
    """Convert one value into readable table text."""
 
    if value is None or value == "":
        return "—"
 
    if isinstance(value, bool):
        return "Yes" if value else "No"
 
    return str(value)
 
 
def show_table(
    rows: Iterable[tuple[str, Any]],
    caption: str = "",
) -> None:
    """Render a two-column Field/Value table."""
 
    prepared_rows = [
        (label, value)
        for label, value in rows
        if value not in (None, "")
    ]
 
    if not prepared_rows:
        return
 
    if caption:
        st.markdown(f"**{caption}**")
 
    frame = pd.DataFrame(
        [
            {
                "Field": label,
                "Value": display_text(value),
            }
            for label, value in prepared_rows
        ]
    )
 
    st.dataframe(
        frame,
        hide_index=True,
        width="stretch",
    )
 
 
def flatten_rows(
    data: Dict[str, Any],
    excluded: set[str] | None = None,
) -> list[tuple[str, Any]]:
    """Convert a dictionary into readable rows."""
 
    excluded_keys = excluded or set()
    rows: list[tuple[str, Any]] = []
 
    for key, value in data.items():
        if key in excluded_keys or value in (None, ""):
            continue
 
        if isinstance(value, (dict, list)):
            value = json.dumps(
                value,
                ensure_ascii=False,
                default=str,
            )
 
        rows.append(
            (
                key.replace("_", " ").capitalize(),
                value,
            )
        )
 
    return rows
 
 
def redact_sensitive_history(value: Any) -> Any:
    """Remove plaintext credentials from history, JSON, and downloads."""
 
    if isinstance(value, dict):
        cleaned: dict[str, Any] = {}
 
        for key, item in value.items():
            normalized_key = key.strip().casefold()
 
            if normalized_key in SENSITIVE_HISTORY_KEYS:
                if normalized_key != "_dashboard_secret":
                    cleaned[key] = "[redacted]"
                continue
 
            cleaned[key] = redact_sensitive_history(item)
 
        return cleaned
 
    if isinstance(value, list):
        return [
            redact_sensitive_history(item)
            for item in value
        ]
 
    return value
 
 
def register_dashboard_secret(response: Dict[str, Any]) -> bool:
    """Discard any legacy plaintext dashboard secret before storage."""
 
    response.pop("_dashboard_secret", None)
    return False
 
 
def render_password_cards() -> None:
    """Legacy compatibility function. Plaintext password cards stay disabled."""
 
    return
 
 
# ---------------------------------------------------------------------------
# Workflow result renderers
# ---------------------------------------------------------------------------
 
 
def render_script_execution(execution: Dict[str, Any]) -> None:
    """Render PowerShell execution evidence."""
 
    show_table(
        [
            ("Success", execution.get("success")),
            ("Operation", execution.get("operation")),
            ("Script", execution.get("script_name")),
            ("Exit code", execution.get("exit_code")),
            ("Duration seconds", execution.get("duration_seconds")),
            ("Dry run", execution.get("dry_run")),
            ("Standard output", execution.get("stdout")),
            ("Standard error", execution.get("stderr")),
            ("Error", execution.get("error")),
        ],
        "Script execution",
    )
 
 
def render_guardrails(response: Dict[str, Any]) -> None:
    """Render guardrail decisions and violations."""
 
    show_table(
        [
            ("Action", response.get("guardrail_action")),
            ("Blocked", response.get("guardrail_blocked")),
            (
                "Confirmation required",
                response.get("confirmation_required"),
            ),
            (
                "Confirmation prompt",
                response.get("confirmation_prompt"),
            ),
            (
                "Output filtered fields",
                response.get("guardrails_output_filtered"),
            ),
        ],
        "Guardrails",
    )
 
    violations = response.get("guardrail_violations")
 
    if isinstance(violations, list):
        for index, violation in enumerate(violations, start=1):
            if isinstance(violation, dict):
                show_table(
                    flatten_rows(violation),
                    f"Guardrail violation {index}",
                )
 
 
def render_password_actions(
    token: str,
    manager_email: str,
) -> None:
    """Render explicit manager-email and secure TXT-download actions."""
 
    status_key = f"email_status_{token}"
    st.session_state.setdefault(status_key, None)
 
    can_email = (
        bool(manager_email)
        and manager_email != "Not Available"
        and email_is_configured()
    )
 
    left, right = st.columns(2)
 
    if left.button(
        "Send Email To Manager",
        key=f"send_{token}",
        disabled=not can_email,
        width="stretch",
    ):
        with st.spinner("Sending email..."):
            sent, message, recipient = send_password_to_manager(token)
 
        st.session_state[status_key] = {
            "sent": sent,
            "message": message,
            "recipient": recipient,
        }
 
    ok, filename, content, message = build_password_download(token)
 
    if ok:
        right.download_button(
            "Download Password TXT",
            data=content,
            file_name=filename,
            mime="text/plain",
            key=f"dl_{token}",
            width="stretch",
        )
    else:
        right.button(
            "Download Password TXT",
            key=f"dl_disabled_{token}",
            disabled=True,
            width="stretch",
        )
        st.caption(message)
 
    status = st.session_state.get(status_key)
 
    if status is None:
        st.caption("Email status: Not Sent")
    elif status["sent"]:
        st.success(
            "Email status: Sent Successfully to "
            f"{status['recipient']}"
        )
    else:
        st.error(
            f"Email status: Failed. {status['message']}"
        )
 
 
def render_password_reset_actions(result: Dict[str, Any]) -> None:
    """Render a successful secure password-reset result."""
 
    st.success("Password Reset Successful")
 
    manager_name = result.get("manager_name") or "Not Available"
    manager_email = result.get("manager_email") or "Not Available"
 
    show_table(
        [
            (
                "Username",
                result.get("user_name")
                or result.get("user_principal_name"),
            ),
            ("Employee name", result.get("employee_name")),
            (
                "Temporary password",
                result.get("masked_password") or "Not Available",
            ),
            ("Manager", manager_name),
            ("Manager email", manager_email),
            ("Backend", result.get("backend")),
        ],
        "Result",
    )
 
    execution = result.get("execution")
 
    if isinstance(execution, dict):
        render_script_execution(execution)
 
    if manager_name == "Not Available":
        st.info(
            "No manager is assigned. The password file can still be "
            "downloaded."
        )
 
    token = result.get("password_token")
 
    if not token:
        st.warning(
            "The password is no longer retrievable for this reset. "
            "Run the reset again."
        )
        return
 
    render_password_actions(token, manager_email)
 
 
def render_result(intent: str, result: Dict[str, Any]) -> None:
    """Render generic, password-reset, or investigation tool results."""
 
    if intent == "failed_login_investigation":
        report = result.get("report")
 
        if isinstance(report, dict):
            render_investigation_report(report)
            return
 
        st.warning(
            "The investigation completed without a structured report payload."
        )
        show_table(
            [
                ("Source", result.get("source")),
                (
                    "Allowed event IDs",
                    result.get("allowed_event_ids"),
                ),
                ("Message", result.get("message")),
            ],
            "Investigation result",
        )
        return
 
    if (
        intent == "password_reset"
        and result.get("password_token")
    ):
        render_password_reset_actions(result)
        return
 
    execution = result.get("execution")
    user_record = result.get("user")
 
    excluded = {
        "execution",
        "user",
        "new_password",
        "temporary_password",
        "_transient_password",
        "report",
        "report_markdown",
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
    """Render a visual summary of the current workflow operation."""
 
    intent = str(response.get("intent") or "Identity operation")
    metadata = (
        response.get("metadata")
        if isinstance(response.get("metadata"), dict)
        else {}
    )
    target = (
        metadata.get("email")
        or metadata.get("username")
        or metadata.get("user_id")
        or "Unknown target"
    )
 
    if response.get("confirmation_required"):
        status = "Confirmation required"
        status_class = "warning"
    elif response.get("success") is True:
        status = "Completed"
        status_class = "success"
    elif response.get("success") is False:
        status = "Failed"
        status_class = "failure"
    else:
        status = "Submitted"
        status_class = ""
 
    st.markdown(
        f"""
        <div class="operation-card {status_class}">
            <div class="operation-label">Current operation</div>
            <div class="operation-title">
                {html.escape(intent.replace('_', ' ').title())}
            </div>
            <div class="operation-meta">
                <strong>Target:</strong> {html.escape(str(target))}
                &nbsp; | &nbsp;
                <strong>Status:</strong> {html.escape(status)}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )
 
    timeline = [
        ("Request received", True),
        ("Request analyzed", True),
        ("Target validated", not bool(response.get("error"))),
    ]
 
    if response.get("confirmation_required"):
        timeline.append(("Confirmation required", True))
    else:
        timeline.append(
            ("Operation completed", response.get("success") is True)
        )
 
    st.markdown("**Operation timeline**")
    st.caption(
        "  ·  ".join(
            f"{'✓' if complete else '○'} {label}"
            for label, complete in timeline
        )
    )
 
 
def render_response(response: Dict[str, Any]) -> None:
    """Render one complete LangGraph workflow response."""
 
    render_operation_summary(response)
    confidence = response.get("confidence")
 
    show_table(
        [
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
            ("Correlation ID", response.get("correlation_id")),
            ("Explanation", response.get("explanation")),
            ("Message", response.get("message")),
            ("Error", response.get("error")),
        ],
        "Summary",
    )
 
    metadata = response.get("metadata")
 
    if isinstance(metadata, dict):
        show_table(
            flatten_rows(metadata, SENSITIVE_HISTORY_KEYS),
            "Extracted metadata",
        )
 
    render_guardrails(response)
 
    show_table(
        [
            ("Agent", response.get("selected_agent")),
            ("MCP server", response.get("selected_mcp_server")),
            ("MCP tool", response.get("selected_mcp_tool")),
            ("Application tool", response.get("selected_tool")),
        ],
        "Routing",
    )
 
    orchestration = response.get("orchestration")
 
    if isinstance(orchestration, dict):
        show_table(
            flatten_rows(orchestration),
            "Orchestration",
        )
 
    execution_context = response.get("execution_context")
 
    if isinstance(execution_context, dict):
        show_table(
            flatten_rows(execution_context),
            "Execution context",
        )
 
    tool_result = response.get("tool_result")
 
    if isinstance(tool_result, dict) and tool_result:
        show_table(
            [
                ("Tool name", tool_result.get("tool_name")),
                ("Status", tool_result.get("status")),
                ("Operation ID", tool_result.get("operation_id")),
                ("Succeeded", tool_result.get("success")),
                ("Message", tool_result.get("message")),
                ("Error", tool_result.get("error")),
                (
                    "API integration pending",
                    tool_result.get("api_integration_pending"),
                ),
            ],
            "Tool execution",
        )
 
        result = tool_result.get("result")
 
        if isinstance(result, dict):
            render_result(
                response.get("intent") or "",
                result,
            )
 
    expander_label = (
        "Technical investigation details"
        if response.get("intent") == "failed_login_investigation"
        else "Raw response (JSON)"
    )
 
    with st.expander(expander_label, expanded=False):
        st.json(
            redact_sensitive_history(
                copy.deepcopy(response)
            )
        )
 
 
# ---------------------------------------------------------------------------
# Confirmation and conversation workflow
# ---------------------------------------------------------------------------
 
 
def set_pending_confirmation(
    response: Dict[str, Any],
    query: str,
) -> None:
    """Persist a request awaiting trusted operator confirmation."""
 
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
 
 
def append_conversation(
    role: str,
    content: Any,
    timestamp: str,
) -> None:
    """Append one redacted conversation turn."""
 
    st.session_state.conversation.append(
        {
            "role": role,
            "content": redact_sensitive_history(
                copy.deepcopy(content)
            ),
            "time": timestamp,
        }
    )
 
 
def execute_and_render(
    query: str,
    *,
    confirmed: bool = False,
    request_id: str | None = None,
    correlation_id: str | None = None,
    add_user_turn: bool = True,
) -> Dict[str, Any]:
    """Execute one workflow request and save its redacted result."""
 
    timestamp = datetime.now().strftime("%H:%M:%S")
 
    if add_user_turn:
        with st.chat_message("user"):
            st.write(query)
 
        append_conversation(
            "user",
            query,
            timestamp,
        )
 
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
 
    append_conversation(
        "assistant",
        response,
        timestamp,
    )
    set_pending_confirmation(response, query)
    return response
 
 
def cancel_pending_confirmation() -> None:
    """Cancel a pending operation without invoking its tool."""
 
    pending = st.session_state.pending_confirmation
    st.session_state.pending_confirmation = None
 
    response = {
        "success": False,
        "cancelled": True,
        "request_id": (
            pending.get("request_id")
            if isinstance(pending, dict)
            else None
        ),
        "correlation_id": (
            pending.get("correlation_id")
            if isinstance(pending, dict)
            else None
        ),
        "intent": (
            pending.get("intent")
            if isinstance(pending, dict)
            else None
        ),
        "message": "Operation cancelled. No changes were made.",
        "error": None,
    }
 
    append_conversation(
        "assistant",
        response,
        datetime.now().strftime("%H:%M:%S"),
    )
    st.rerun()
 
 
def render_confirmation_controls() -> None:
    """Render approval controls for a pending sensitive operation."""
 
    pending = st.session_state.pending_confirmation
 
    if not isinstance(pending, dict):
        return
 
    with st.container(border=True):
        st.markdown("**Approval required**")
        st.write(
            pending.get("prompt")
            or "Confirm this operation before continuing."
        )
 
        confirm_column, cancel_column = st.columns(2)
 
        if confirm_column.button(
            "Confirm and proceed",
            type="primary",
            width="stretch",
        ):
            st.session_state.pending_confirmation = None
 
            execute_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending.get("request_id"),
                correlation_id=pending.get("correlation_id"),
                add_user_turn=False,
            )
            st.rerun()
 
        if cancel_column.button(
            "Cancel",
            width="stretch",
        ):
            cancel_pending_confirmation()
 
 
# ---------------------------------------------------------------------------
# Sidebar and application shell
# ---------------------------------------------------------------------------
 
 
def safe_conversation_download() -> str:
    """Serialize a password-safe copy of conversation history."""
 
    return json.dumps(
        redact_sensitive_history(
            copy.deepcopy(st.session_state.conversation)
        ),
        indent=2,
        ensure_ascii=False,
        default=str,
    )
 
 
def render_sidebar() -> None:
    """Render status, examples, diagnostics, and session controls."""
 
    with st.sidebar:
        st.header("System status")
        status = get_config_status()
 
        show_table(
            [
                (
                    "Microsoft Graph",
                    (
                        "Configured"
                        if status.get("graph_client_id")
                        and status.get("graph_client_secret")
                        and status.get("graph_tenant_id")
                        else "Incomplete"
                    ),
                ),
                (
                    "PowerShell",
                    (
                        "Enabled"
                        if status.get("powershell_operations_enabled")
                        else "Disabled"
                    ),
                ),
                (
                    "Destructive actions",
                    (
                        "Enabled"
                        if status.get("destructive_operations_enabled")
                        else "Disabled"
                    ),
                ),
                (
                    "LangGraph",
                    (
                        "Active"
                        if status.get("orchestration_engine") == "langgraph"
                        else "Unavailable"
                    ),
                ),
                (
                    "Operation audit",
                    (
                        "Enabled"
                        if status.get("operation_audit_enabled")
                        else "Unknown"
                    ),
                ),
                (
                    "Configuration",
                    (
                        "Valid"
                        if status.get("config_valid")
                        else "Invalid"
                    ),
                ),
            ]
        )
 
        if st.button(
            "Test Ollama connection",
            width="stretch",
        ):
            connected, message = check_ollama()
            st.session_state.ollama_check_result = {
                "connected": connected,
                "message": message,
            }
 
        ollama_result = st.session_state.ollama_check_result
 
        if isinstance(ollama_result, dict):
            show_table(
                [
                    (
                        "Ollama",
                        (
                            "Connected"
                            if ollama_result.get("connected")
                            else "Unavailable"
                        ),
                    ),
                    ("Details", ollama_result.get("message")),
                ]
            )
 
        with st.expander("Environment details"):
            show_table(
                flatten_rows(
                    status,
                    {
                        "graph_client_secret",
                        "client_secret",
                        "access_token",
                    },
                )
            )
 
        st.divider()
        st.caption("Example queries")
 
        for index, example in enumerate(EXAMPLES):
            if st.button(
                example,
                key=f"example_{index}",
                width="stretch",
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
    """Show the five most recent session operations."""
 
    operations: list[dict[str, Any]] = []
 
    for turn in reversed(st.session_state.conversation):
        if (
            turn.get("role") != "assistant"
            or not isinstance(turn.get("content"), dict)
        ):
            continue
 
        response = turn["content"]
        metadata = (
            response.get("metadata")
            if isinstance(response.get("metadata"), dict)
            else {}
        )
 
        if response.get("confirmation_required"):
            operation_status = "Awaiting confirmation"
        elif response.get("cancelled"):
            operation_status = "Cancelled"
        elif response.get("success") is True:
            operation_status = "Completed"
        else:
            operation_status = "Failed"
 
        operations.append(
            {
                "Operation": str(
                    response.get("intent")
                    or "Identity operation"
                ).replace("_", " ").title(),
                "Target": (
                    metadata.get("email")
                    or metadata.get("username")
                    or "Unknown target"
                ),
                "Status": operation_status,
                "Time": turn.get("time", ""),
            }
        )
 
        if len(operations) == 5:
            break
 
    if operations:
        st.markdown("#### Recent operations")
        st.dataframe(
            pd.DataFrame(operations),
            hide_index=True,
            width="stretch",
        )
 
 
def render_command_center() -> None:
    """Render the initial guidance panel before conversation begins."""
 
    if st.session_state.conversation:
        return
 
    st.markdown(
        """
        <div class="tech-panel">
            <strong>What do you need to take care of?</strong>
            <span>
                Ask for a user lookup, password reset, account unlock,
                access change, or failed-login/account-lockout investigation.
                Sensitive actions pause for confirmation.
            </span>
        </div>
        """,
        unsafe_allow_html=True,
    )
 
 
# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------
 
 
def main() -> None:
    """Run the TechAdmin Streamlit application."""
 
    init_state()
    require_authentication()
    render_command_center()
 
    # Plaintext password cards remain intentionally disabled. Password reset
    # results expose only a masked value plus secure delivery actions.
    # render_password_cards()
 
    for turn in st.session_state.conversation:
        with st.chat_message(turn["role"]):
            if turn["role"] == "user":
                st.write(turn["content"])
            elif isinstance(turn["content"], dict):
                render_response(turn["content"])
 
    query = (
        st.session_state.queued_query
        or st.chat_input("Type an identity operation...")
    )
    st.session_state.queued_query = None
 
    if query:
        pending = st.session_state.pending_confirmation
        normalized_answer = query.strip().casefold().rstrip(".!")
 
        if (
            isinstance(pending, dict)
            and normalized_answer in YES_WORDS
        ):
            append_conversation(
                "user",
                query,
                datetime.now().strftime("%H:%M:%S"),
            )
            st.session_state.pending_confirmation = None
 
            execute_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending.get("request_id"),
                correlation_id=pending.get("correlation_id"),
                add_user_turn=False,
            )
 
        elif (
            isinstance(pending, dict)
            and normalized_answer in NO_WORDS
        ):
            append_conversation(
                "user",
                query,
                datetime.now().strftime("%H:%M:%S"),
            )
            cancel_pending_confirmation()
 
        else:
            execute_and_render(query)
 
        st.rerun()
 
    render_confirmation_controls()
    render_recent_operations()
    render_sidebar()
 
 
if __name__ == "__main__":
    main()
 
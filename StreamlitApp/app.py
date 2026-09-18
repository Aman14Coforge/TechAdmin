"""
TechAdmin Streamlit UI with LangGraph orchestration, guardrail confirmation,
secure password delivery, database-backed application authorization, and
CrowdStrike failed-login investigation reporting.

Features:
    - Uses FlowService, which invokes the compiled TechAdmin LangGraph.
    - Structured tables for normal identity-operation results.
    - Dedicated visual report for failed-login/account-lockout investigations.
    - Guardrail confirmation controls for sensitive operations.
    - Reuses request ID and correlation ID after confirmation.
    - Keeps plaintext passwords out of the UI and conversation history.
    - Supports secure password TXT download and explicit manager email.
    - Authorizes signed-in users against the app_users database.
    - Supports Microsoft Graph, PowerShell, MCP, and CrowdStrike results.

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

from App.db.login_authorization import (
    authorize_claims,
    extract_display_name,
)

from investigation_report_ui import render_investigation_report


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="TechAdmin",
    page_icon="🛠️",
    layout="wide",
)

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

    .sidebar-brand .tech-kicker {
        font-size: 0.72rem;
        line-height: 1.4;
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
        margin-bottom: 0.5rem;
        text-align: left;
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


def enforce_app_user_access(claims: dict[str, Any]) -> None:
    """Allow only identities authorized by the app_users database."""

    display_name = extract_display_name(claims)

    # Preserve the latest behavior supplied by the project. A missing-display-
    # name identity is handled in require_authentication before this function
    # for Microsoft SSO. This fallback mainly protects legacy local sessions.
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

    if cached["allowed"]:
        return

    st.title("TechAdmin")
    st.error(cached["message"])
    st.caption(
        f"Signed in as: {display_name or 'unknown'}. "
        "Access is granted only to users registered in the TechAdmin "
        "app_users directory."
    )

    if st.button("Sign out", key="denied_sign_out"):
        st.session_state.pop("app_user_access", None)
        st.session_state.pop("local_authenticated_user", None)

        if claims.get("auth_source") != "local_test_account":
            st.logout()

        st.rerun()

    st.stop()


def require_authentication() -> dict[str, Any]:
    """Require Microsoft Entra or local-development authentication."""

    local_user = st.session_state.get("local_authenticated_user")

    if isinstance(local_user, dict):
        enforce_app_user_access(local_user)
        render_authenticated_user(local_user)
        return local_user

    # -----------------------------------------------------------------------
    # ORIGINAL LOGIN IMPLEMENTATION KEPT COMMENTED AS REQUESTED
    # -----------------------------------------------------------------------
    if not st.user.is_logged_in:
        st.title("TechAdmin")
        st.subheader("Sign in to TechAdmin")
    
        microsoft_tab, local_tab = st.tabs(
            ["Microsoft SSO", "Test account"]
        )
    
        with microsoft_tab:
            st.write("Use your Coforge Microsoft account.")
            if st.button(
                "Sign in with Microsoft",
                type="primary",
                width="stretch",
            ):
                st.login()
    
        with local_tab:
            render_local_login()
    
        st.stop()

    # if not st.user:
    #     if (
    #         os.getenv(
    #             "TECHADMIN_LOCAL_LOGIN_ENABLED",
    #             "false",
    #         ).casefold()
    #         == "true"
    #     ):
    #         st.title("TechAdmin")
    #         st.subheader("Local Development Login")
    #         render_local_login()
    #         st.stop()

    #     st.title("TechAdmin")
    #     st.subheader("Sign in to TechAdmin")

    #     microsoft_tab, local_tab = st.tabs(
    #         ["Microsoft SSO", "Test account"]
    #     )

    #     with microsoft_tab:
    #         st.write("Use your Coforge Microsoft account.")

    #         if st.button(
    #             "Sign in with Microsoft",
    #             type="primary",
    #             width="stretch",
    #         ):
    #             st.login()

    #     with local_tab:
    #         render_local_login()

    #     st.stop()

    claims = dict(st.user)

    if not extract_display_name(claims):
        st.title("TechAdmin")
        st.subheader("Sign in to TechAdmin")

        microsoft_tab, local_tab = st.tabs(
            ["Microsoft SSO", "Test account"]
        )

        with microsoft_tab:
            st.write("Use your Coforge Microsoft account.")

            if st.button(
                "Sign in with Microsoft",
                type="primary",
                width="stretch",
            ):
                st.logout()
                st.login()

        with local_tab:
            render_local_login()

        st.stop()

    # Tenant restriction remains commented while tenant configuration is
    # aligned. This preserves the latest supplied application behavior.
    # expected_tenant = str(
    #     st.secrets.get("entra", {}).get("allowed_tenant_id", "")
    # ).strip()
    # actual_tenant = str(claims.get("tid", "")).strip()
    #
    # if expected_tenant and actual_tenant != expected_tenant:
    #     st.error("This Microsoft tenant is not authorized for TechAdmin.")
    #     if st.button("Sign out", width="content"):
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
    )
    expected_password = os.getenv(
        "TECHADMIN_LOCAL_LOGIN_PASSWORD",
        "",
    )

    valid_username = hmac.compare_digest(
        username.strip().casefold(),
        expected_username.strip().casefold(),
    )
    valid_password = bool(expected_password) and hmac.compare_digest(
        password,
        expected_password,
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
    """Render identity and a logout action for either auth method."""

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
            or "Authenticated user"
        )
        st.caption(f"Signed in as {display_name}")

        if claims.get("auth_source") == "local_test_account":
            if st.button(
                "Sign out",
                key="local_sign_out",
                width="stretch",
            ):
                st.session_state.pop("local_authenticated_user", None)
                st.session_state.pop("app_user_access", None)
                st.rerun()

        elif st.button(
            "Sign out",
            key="sign_out",
            width="stretch",
        ):
            st.session_state.pop("app_user_access", None)
            st.logout()


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

EXAMPLES = [
    "Get user details for MigrationTest2@Coforge.com",
    "Get user details for MigrationTest2@Coforge.com via script",
    "Get user details for MigrationTest2@Coforge.com via API",
    "Reset password for MigrationTest2@Coforge.com",
    "Reset password for MigrationTest2@Coforge.com via script",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
    (
        "Investigate failed logins for "
        "Amit.Bhagat@Coforge.com in the last 24 hours"
    ),
    (
        "Investigate account lockout for "
        "MigrationTest3@Coforge.com in the last 24 hours"
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


# ---------------------------------------------------------------------------
# Service and session state
# ---------------------------------------------------------------------------


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
# Generic formatting helpers
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
    """Remove plaintext credentials from history and downloads."""

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


# ---------------------------------------------------------------------------
# Legacy dashboard-password interface
# ---------------------------------------------------------------------------


def register_dashboard_secret(response: Dict[str, Any]) -> bool:
    """
    Remove any legacy dashboard secret from a response.

    Current FlowService never creates this field. The method remains for
    compatibility and defensively prevents a secret from reaching history.
    """

    secret = response.pop("_dashboard_secret", None)

    if not isinstance(secret, dict):
        return False

    # Do not restore plaintext-password rendering. Discard the legacy payload.
    return False


def render_password_cards() -> None:
    """Legacy password-card renderer retained but intentionally unused."""

    return


# ---------------------------------------------------------------------------
# Workflow result rendering
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

    if not isinstance(violations, list):
        return

    for index, violation in enumerate(violations, start=1):
        if isinstance(violation, dict):
            show_table(
                flatten_rows(violation),
                f"Guardrail violation {index}",
            )


def render_password_reset_actions(result: Dict[str, Any]) -> None:
    """Render secure post-reset actions without exposing plaintext."""

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
            "No manager is assigned to this account, so the email option is "
            "unavailable. The password file can still be downloaded."
        )

    token = result.get("password_token")

    if not token:
        st.warning(
            "The password is no longer retrievable for this reset, so the "
            "download and email actions are unavailable."
        )
        return

    render_password_actions(token, manager_email)


def render_password_actions(
    token: str,
    manager_email: str,
) -> None:
    """Render explicit manager-email and secure-download actions."""

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


def render_result(intent: str, result: Dict[str, Any]) -> None:
    """Render generic, password-reset, or investigation results."""

    # CrowdStrike failed-login and account-lockout investigations must be
    # rendered before generic flattening. Otherwise the report dictionary and
    # event timeline become one unreadable JSON value in the Result table.
    if intent == "failed_login_investigation":
        report = result.get("report")

        if isinstance(report, dict):
            render_investigation_report(report)
            return

        st.warning(
            "The failed-login investigation completed, but the response did "
            "not contain a structured investigation report."
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
        result_rows = [
            ("Backend", result.get("backend"))
        ]
        result_rows.extend(
            flatten_rows(user_record)
        )
    else:
        result_rows = flatten_rows(
            result,
            excluded,
        )

    show_table(result_rows, "Result")

    if isinstance(execution, dict):
        render_script_execution(execution)

    if intent == "password_reset":
        redacted_value = (
            result.get("new_password")
            or result.get("temporary_password")
        )

        if redacted_value == "[redacted]":
            show_table(
                [
                    (
                        "Password display",
                        (
                            "The response password is redacted. Use the "
                            "secure password-token delivery workflow."
                        ),
                    )
                ],
                "Password status",
            )


def render_response(response: Dict[str, Any]) -> None:
    """Render one complete workflow response."""

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
            flatten_rows(
                metadata,
                SENSITIVE_HISTORY_KEYS,
            ),
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

    safe_raw_response = redact_sensitive_history(
        copy.deepcopy(response)
    )

    if response.get("intent") == "failed_login_investigation":
        with st.expander(
            "Technical investigation details",
            expanded=False,
        ):
            st.json(safe_raw_response)
    else:
        with st.expander(
            "Raw response (JSON)",
            expanded=False,
        ):
            st.json(safe_raw_response)


def render_operation_summary(response: Dict[str, Any]) -> None:
    """Show operation status before detailed tables."""

    intent = str(
        response.get("intent")
        or "Identity operation"
    )
    title = intent.replace("_", " ").title()
    metadata = response.get("metadata")
    target = "Unknown target"

    if isinstance(metadata, dict):
        target = (
            metadata.get("email")
            or metadata.get("username")
            or metadata.get("user_id")
            or target
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

    safe_title = html.escape(title)
    safe_target = html.escape(str(target))
    safe_status = html.escape(status)

    st.markdown(
        f"""
        <div class="operation-card {status_class}">
            <div class="operation-label">Current operation</div>
            <div class="operation-title">{safe_title}</div>
            <div class="operation-meta">
                <strong>Target:</strong> {safe_target}
                &nbsp; | &nbsp;
                <strong>Status:</strong> {safe_status}
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    timeline = [
        ("Request received", True),
        ("Request analyzed", True),
        (
            "Target validated",
            not bool(response.get("error")),
        ),
    ]

    if response.get("confirmation_required"):
        timeline.append(
            ("Confirmation required", True)
        )
    else:
        timeline.append(
            (
                "Operation completed",
                response.get("success") is True,
            )
        )

    st.markdown("**Operation timeline**")
    st.caption(
        "  ·  ".join(
            f"{'✓' if complete else '○'} {label}"
            for label, complete in timeline
        )
    )


# ---------------------------------------------------------------------------
# Confirmation workflow
# ---------------------------------------------------------------------------


def set_pending_confirmation(
    response: Dict[str, Any],
    query: str,
) -> None:
    """Persist the trusted confirmation context in Streamlit session state."""

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
    """Append one password-safe conversation item."""

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
    """Execute one LangGraph request and store a redacted response."""

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
    """Render trusted approval controls for a pending operation."""

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
# Sidebar and session summaries
# ---------------------------------------------------------------------------


def safe_conversation_download() -> str:
    """Serialize password-safe conversation history."""

    return json.dumps(
        redact_sensitive_history(
            copy.deepcopy(
                st.session_state.conversation
            )
        ),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def render_sidebar() -> None:
    """Render system status, examples, and session controls."""

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
                        "graph_client_id",
                        "graph_client_secret",
                        "graph_tenant_id",
                        "powershell_operations_enabled",
                        "destructive_operations_enabled",
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
    """Show recent operations without sensitive values."""

    operations: list[dict[str, Any]] = []

    for turn in reversed(st.session_state.conversation):
        if (
            turn.get("role") != "assistant"
            or not isinstance(turn.get("content"), dict)
        ):
            continue

        response = turn["content"]
        metadata = response.get("metadata")
        target = "Unknown target"

        if isinstance(metadata, dict):
            target = (
                metadata.get("email")
                or metadata.get("username")
                or target
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
                "Target": target,
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
    """Render guidance before the first conversation turn."""

    if st.session_state.conversation:
        return

    st.markdown(
        """
        <div class="tech-panel">
            <strong>What do you need to take care of?</strong>
            <span>
                Ask for a user lookup, password reset, account unlock,
                access change, directory operation, VM provisioning, or a
                failed-login and account-lockout investigation. Sensitive
                actions pause for confirmation.
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

    require_authentication()
    init_state()
    render_command_center()

    # Plaintext password display remains intentionally disabled. Passwords are
    # available only through the secure token-based download/email workflow.
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

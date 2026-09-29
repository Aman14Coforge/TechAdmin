"""Production TechAdmin Streamlit UI."""
from __future__ import annotations

import copy
import html
import hmac
import json
import os
from datetime import datetime
from typing import Any, Dict, Iterable

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
from App.db.operation_audit import get_user_request_history
from investigation_report_ui import render_investigation_report

st.set_page_config(
    page_title="TechAdmin",
    page_icon="🛠️",
    layout="wide",
    initial_sidebar_state="expanded",
)


def enforce_https_origin() -> None:
    """Redirect insecure browser access to the configured public HTTPS origin."""
    public_url = os.getenv(
        "TECHADMIN_PUBLIC_URL",
        "https://techadmin.coforge.com",
    ).strip()
    if not public_url:
        return
    st.markdown(
        f"""
        <script>
        (() => {{
            try {{
                const publicUrl = new URL("{public_url}");
                const current = new URL(window.location.href);
                if (
                    current.protocol === "http:" &&
                    current.hostname === publicUrl.hostname
                ) {{
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

# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

st.markdown(
    """
<style>
:root {
  --canvas:#f4f7fb; --surface:#ffffff; --surface-2:#f8fafc;
  --navy:#112a46; --navy-2:#173858; --blue:#1671b9; --cyan:#40a9df;
  --text:#172436; --muted:#68788c; --line:#dce5ee;
  --green:#15804a; --green-bg:#edf9f2; --red:#b42318; --red-bg:#fff1f0;
  --amber:#a55d00; --amber-bg:#fff8e8; --grey:#667085; --grey-bg:#f1f4f7;
  --shadow:0 12px 34px rgba(19,45,72,.08);
}
.stApp {background:var(--canvas); color:var(--text)}
.block-container {padding-top:1.5rem; padding-bottom:3rem; max-width:1480px}
[data-testid="stSidebar"] {
  background:linear-gradient(180deg,var(--navy),var(--navy-2)); border-right:0;
}
[data-testid="stSidebar"] p,[data-testid="stSidebar"] label,
[data-testid="stSidebar"] .stCaption {color:#c5d5e4 !important}
[data-testid="stSidebar"] button {
  background:rgba(255,255,255,.07); color:#fff; border:1px solid rgba(255,255,255,.14);
  border-radius:11px;
}
[data-testid="stSidebar"] button:hover {background:rgba(255,255,255,.13)}
[data-testid="stSidebar"] [data-testid="stExpander"] {
  border:1px solid rgba(255,255,255,.12); border-radius:14px;
  background:rgba(255,255,255,.05); overflow:hidden;
}
[data-testid="stSidebar"] [data-testid="stExpander"] summary {
  color:#f5f9fd !important; background:transparent !important; font-weight:750;
}
.brand {padding:.25rem .15rem 1.1rem; border-bottom:1px solid rgba(255,255,255,.13)}
.brand-company {color:#71caf6; font-size:.7rem; font-weight:850; letter-spacing:.16em; text-transform:uppercase}
.brand-title {color:#fff; font-size:1.9rem; font-weight:900; margin:.2rem 0 .1rem}
.brand-subtitle {color:#a9c0d4; font-size:.72rem; text-transform:uppercase; letter-spacing:.1em}
.sidebar-user {display:flex; gap:.7rem; align-items:center; padding:.75rem; margin:.8rem 0;
  border:1px solid rgba(255,255,255,.12); border-radius:14px; background:rgba(255,255,255,.05)}
.sidebar-avatar {width:40px;height:40px;display:flex;align-items:center;justify-content:center;
  border-radius:12px;background:linear-gradient(135deg,#2d92d1,#64c7ef);color:#fff;font-weight:900}
.sidebar-user-name {max-width:198px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#fff;font-size:.84rem;font-weight:850}
.sidebar-user-role {color:#9fb7ca;font-size:.67rem;margin-top:.15rem}
.sidebar-head {display:flex;align-items:center;justify-content:space-between;margin:1rem .1rem .55rem}
.sidebar-head-title {color:#f5f9fd;font-size:.69rem;font-weight:850;letter-spacing:.11em;text-transform:uppercase}
.sidebar-count {color:#a9e0ff;background:rgba(50,157,220,.16);border:1px solid rgba(100,195,245,.2);
  border-radius:999px;padding:.07rem .42rem;font-size:.63rem;font-weight:850}
.activity-card {padding:.68rem .72rem;margin-bottom:.48rem;border-radius:12px;
  border:1px solid rgba(255,255,255,.1);background:rgba(255,255,255,.045)}
.activity-title {color:#edf6fc;font-size:.76rem;font-weight:700;line-height:1.35;overflow-wrap:anywhere}
.activity-meta {display:flex;gap:.35rem;align-items:center;margin-top:.38rem;color:#9eb5c8;font-size:.65rem}
.dot {width:6px;height:6px;border-radius:50%;background:#61d29a;display:inline-block}.dot.bad{background:#ff8b83}
.hero {position:relative;overflow:hidden;border-radius:22px;padding:1.7rem 1.8rem;color:#fff;
  background:linear-gradient(120deg,#113755,#1671b9 58%,#30a0d8);box-shadow:var(--shadow);margin-bottom:1.1rem}
.hero:after {content:"";position:absolute;width:330px;height:330px;border-radius:50%;right:-110px;top:-160px;background:rgba(255,255,255,.09)}
.hero-kicker {color:#c4e9ff;font-size:.7rem;font-weight:850;letter-spacing:.12em;text-transform:uppercase}
.hero-title {font-size:1.55rem;font-weight:900;margin:.32rem 0 .2rem}.hero-copy{color:#def1fc;max-width:900px}
.operation {border:1px solid var(--line);border-left:5px solid var(--blue);border-radius:16px;background:#fff;
  padding:1rem 1.2rem;margin:.3rem 0 1rem;box-shadow:0 5px 17px rgba(19,45,72,.05)}
.operation.success{border-left-color:var(--green)}.operation.failure{border-left-color:var(--red)}.operation.warning{border-left-color:var(--amber)}
.operation-kicker{color:var(--muted);font-size:.66rem;font-weight:850;letter-spacing:.1em;text-transform:uppercase}
.operation-title{font-size:1.13rem;font-weight:900;margin-top:.18rem}.operation-meta{color:var(--muted);font-size:.86rem;margin-top:.28rem}
.profile {display:flex;gap:1rem;align-items:center;background:#fff;border:1px solid var(--line);border-radius:18px;
  padding:1.15rem 1.3rem;box-shadow:var(--shadow);margin:.5rem 0 1rem}
.avatar {width:60px;height:60px;border-radius:17px;background:linear-gradient(135deg,#1671b9,#52b7e8);
  display:flex;align-items:center;justify-content:center;color:#fff;font-size:1.35rem;font-weight:900}
.profile-name{font-size:1.24rem;font-weight:900}.profile-upn{color:var(--muted);font-size:.85rem;margin-top:.12rem}
.chip {display:inline-block;background:#e7f4fc;color:#12649d;font-size:.68rem;font-weight:850;border-radius:999px;padding:.24rem .62rem;margin-top:.4rem}
.section-title{font-size:1rem;font-weight:900;margin:1.1rem 0 .55rem;color:var(--text)}
.detail-card {background:#fff;border:1px solid var(--line);border-radius:17px;padding:.25rem 1rem .45rem;box-shadow:0 5px 17px rgba(19,45,72,.045)}
.detail-row {display:grid;grid-template-columns:minmax(145px,34%) 1fr;gap:1rem;padding:.76rem .1rem;border-bottom:1px solid #e8eef4}
.detail-row:last-child{border-bottom:0}.detail-label{color:#65758a;font-size:.76rem;font-weight:750}.detail-value{color:#1c2b3d;font-size:.82rem;font-weight:650;overflow-wrap:anywhere}
.detail-value.muted{color:#98a4b2;font-weight:550}
.status-card {height:118px;border-radius:16px;padding:1rem;border:1px solid var(--line);box-shadow:0 4px 14px rgba(19,45,72,.04)}
.status-card.healthy{border-top:4px solid var(--green);background:var(--green-bg)}
.status-card.unhealthy{border-top:4px solid var(--red);background:var(--red-bg)}
.status-card.unavailable{border-top:4px solid var(--grey);background:var(--grey-bg)}
.status-label{color:var(--muted);font-size:.68rem;font-weight:850;text-transform:uppercase;letter-spacing:.07em}
.status-value{font-size:1.15rem;font-weight:900;margin-top:.42rem}.healthy .status-value{color:var(--green)}.unhealthy .status-value{color:var(--red)}.unavailable .status-value{color:var(--grey)}
.status-note{color:var(--muted);font-size:.69rem;margin-top:.22rem}
.metric-grid {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;margin:.55rem 0 1rem}
.metric-card {background:linear-gradient(145deg,#fff,#f8fbfd);border:1px solid var(--line);border-radius:17px;padding:1rem 1.05rem;box-shadow:0 5px 17px rgba(19,45,72,.045)}
.metric-label{color:var(--muted);font-size:.72rem;font-weight:750}.metric-value{color:#202d3d;font-size:1.65rem;font-weight:900;margin-top:.25rem;overflow-wrap:anywhere}
.table-shell {background:#fff;border:1px solid var(--line);border-radius:17px;overflow:hidden;box-shadow:0 5px 17px rgba(19,45,72,.045)}
.rich-table {width:100%;border-collapse:separate;border-spacing:0;table-layout:fixed}
.rich-table thead th {background:linear-gradient(180deg,#f8fbfd,#f1f6fa);color:#526579;font-size:.68rem;font-weight:850;text-transform:uppercase;letter-spacing:.055em;text-align:left;padding:.82rem .85rem;border-bottom:1px solid var(--line)}
.rich-table tbody td {color:#223246;font-size:.78rem;padding:.82rem .85rem;border-bottom:1px solid #e8eef4;vertical-align:top;overflow-wrap:anywhere}
.rich-table tbody tr:last-child td{border-bottom:0}.rich-table tbody tr:hover td{background:#f5faff}
.pill {display:inline-block;border-radius:999px;padding:.18rem .48rem;background:#e9f5fc;color:#166b9f;font-size:.66rem;font-weight:850}
.empty {background:#fff;border:1px dashed #b8c9d8;border-radius:16px;color:var(--muted);text-align:center;padding:1.5rem}
[data-testid="stTabs"] [data-baseweb="tab-list"] {gap:.4rem;border-bottom:1px solid var(--line)}
[data-testid="stTabs"] button {border-radius:10px 10px 0 0;padding:.65rem .9rem;font-weight:750}
[data-testid="stExpander"]{background:#fff;border:1px solid var(--line);border-radius:14px}

.result-banner {position:relative;overflow:hidden;border-radius:18px;padding:1.15rem 1.3rem;margin:.35rem 0 1rem;border:1px solid var(--line);box-shadow:0 7px 22px rgba(19,45,72,.06)}
.result-banner.success {background:linear-gradient(120deg,#effaf4,#f8fffb);border-left:5px solid var(--green)}
.result-banner.warning {background:linear-gradient(120deg,#fff8e8,#fffdf7);border-left:5px solid var(--amber)}
.result-banner.failure {background:linear-gradient(120deg,#fff1f0,#fffafa);border-left:5px solid var(--red)}
.result-icon {float:left;width:42px;height:42px;border-radius:13px;display:flex;align-items:center;justify-content:center;margin-right:.85rem;font-size:1.1rem;font-weight:900}
.success .result-icon {background:#d8f2e4;color:var(--green)}.warning .result-icon{background:#ffedc5;color:var(--amber)}.failure .result-icon{background:#ffdcd8;color:var(--red)}
.result-heading {font-size:1rem;font-weight:900;color:var(--text)}.result-copy{color:var(--muted);font-size:.79rem;margin-top:.2rem}
.action-grid {display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:1rem;margin:.6rem 0 1rem}
.action-card {background:#fff;border:1px solid var(--line);border-radius:17px;padding:1rem;box-shadow:0 5px 17px rgba(19,45,72,.045)}
.action-card-icon {width:36px;height:36px;border-radius:11px;background:#e8f5fc;color:#1470a9;display:flex;align-items:center;justify-content:center;font-weight:900;margin-bottom:.65rem}
.action-card-title {font-size:.76rem;color:var(--muted);font-weight:750}.action-card-value{font-size:.94rem;color:var(--text);font-weight:850;margin-top:.22rem;overflow-wrap:anywhere}
.timeline {background:#fff;border:1px solid var(--line);border-radius:17px;padding:.45rem 1rem;box-shadow:0 5px 17px rgba(19,45,72,.04)}
.timeline-item {display:grid;grid-template-columns:22px 1fr;gap:.7rem;padding:.7rem .1rem;border-bottom:1px solid #e8eef4}.timeline-item:last-child{border-bottom:0}
.timeline-dot {width:10px;height:10px;border-radius:50%;background:#51b985;margin-top:.22rem;box-shadow:0 0 0 4px #e8f7ef}.timeline-dot.pending{background:#e4a03a;box-shadow:0 0 0 4px #fff4dc}.timeline-dot.failed{background:#db6258;box-shadow:0 0 0 4px #ffebe9}
.timeline-title{font-size:.78rem;font-weight:850;color:var(--text)}.timeline-copy{font-size:.7rem;color:var(--muted);margin-top:.12rem}
.confirm-panel {background:linear-gradient(120deg,#fff8e8,#fffdf7);border:1px solid #f1d9a8;border-left:5px solid var(--amber);border-radius:17px;padding:1rem 1.15rem;margin:.7rem 0;box-shadow:0 7px 22px rgba(19,45,72,.05)}
.secret-box {background:#122d47;color:#f7fbff;border-radius:15px;padding:1rem 1.15rem;margin:.6rem 0;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.08em;box-shadow:0 8px 22px rgba(18,45,71,.15)}
.evidence-summary {display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:1rem;margin:.6rem 0 1rem}
.evidence-card {background:#fff;border:1px solid var(--line);border-radius:16px;padding:.9rem 1rem;box-shadow:0 5px 17px rgba(19,45,72,.04)}
.evidence-label{color:var(--muted);font-size:.68rem;font-weight:800;text-transform:uppercase;letter-spacing:.05em}.evidence-value{color:var(--text);font-size:1.2rem;font-weight:900;margin-top:.25rem}
@media(max-width:980px){.metric-grid,.evidence-summary{grid-template-columns:repeat(2,minmax(0,1fr))}.action-grid{grid-template-columns:1fr}.detail-row{grid-template-columns:1fr}.status-card{height:auto}}
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# State, authentication, and helpers
# ---------------------------------------------------------------------------

EXAMPLES = [
    "Get user details for MigrationTest2@Coforge.com",
    "Get user details for MigrationTest2@Coforge.com on Entra",
    "Reset password for MigrationTest2@Coforge.com",
    "Unlock MigrationTest2@Coforge.com",
    "Add MigrationTest2@Coforge.com to TechAI_Group",
    "Investigate why MigrationTest2@Coforge.com keeps getting locked",
]
YES_WORDS = {"yes","y","confirm","confirmed","proceed","approve","approved","ok","okay"}
NO_WORDS = {"no","n","cancel","stop","abort","nevermind"}
SENSITIVE = {"new_password","temporary_password","password","initial_password","domain_password","admin_password","client_secret","access_token","refresh_token","_dashboard_secret","_transient_password"}


def init_state() -> None:
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    st.session_state.setdefault("pending_confirmation", None)
    st.session_state.setdefault("password_cards", [])
    st.session_state.setdefault("ollama_check_result", None)


@st.cache_resource(show_spinner="Starting TechAdmin services...")
def get_service() -> FlowService:
    return FlowService()


def _initials(name: Any) -> str:
    parts = [p for p in str(name or "User").split() if p]
    return "".join(p[0].upper() for p in parts[:2]) or "U"


def _ci_get(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    normalized = {str(k).replace("_", "").casefold(): v for k, v in data.items()} if isinstance(data, dict) else {}
    for name in names:
        key = name.replace("_", "").casefold()
        if key in normalized:
            return normalized[key]
    return default


def _optional_bool(data: dict[str, Any], *names: str) -> bool | None:
    value = _ci_get(data, *names)
    if isinstance(value, bool): return value
    if isinstance(value, int) and value in {0,1}: return bool(value)
    if isinstance(value, str):
        text = value.strip().casefold()
        if text in {"true","yes","1","enabled","locked"}: return True
        if text in {"false","no","0","disabled","not locked"}: return False
    return None


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: ("[redacted]" if k.strip().casefold() in SENSITIVE else redact(v)) for k,v in value.items() if k.strip().casefold() != "_dashboard_secret"}
    if isinstance(value, list): return [redact(v) for v in value]
    return value


def microsoft_user_is_logged_in() -> bool:
    """Safely determine whether Streamlit has a Microsoft login session."""
    try:
        return bool(st.user.is_logged_in)
    except (AttributeError, RuntimeError, TypeError):
        return False


def clear_local_authentication_state() -> None:
    """Clear local identity and cached app_users authorization state."""
    st.session_state.pop("local_authenticated_user", None)
    st.session_state.pop("app_user_access", None)


def render_sign_in_screen(*, microsoft_message: str | None = None) -> None:
    """Render the original working Microsoft SSO and test-account flows."""
    st.title("TechAdmin")
    st.subheader("Sign in to TechAdmin")
    if microsoft_message:
        st.warning(microsoft_message)

    microsoft_tab, local_tab = st.tabs(["Microsoft SSO", "Test account"])
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
    """Authorize an authenticated identity against app_users."""
    display_name = extract_display_name(claims)
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
        f"Signed in as: {display_name or 'unknown'}. Access is granted only "
        "to active users registered in the TechAdmin app_users directory."
    )
    if claims.get("auth_source") == "local_test_account":
        if st.button("Return to sign in", key="denied_local_sign_out"):
            clear_local_authentication_state()
            st.rerun()
    elif st.button("Sign out", key="denied_microsoft_sign_out"):
        clear_local_authentication_state()
        st.logout()
    st.stop()


def require_authentication() -> dict[str, Any]:
    """Require the original Microsoft Entra or local test authentication."""
    local_user = st.session_state.get("local_authenticated_user")
    if isinstance(local_user, dict):
        enforce_app_user_access(local_user)
        render_authenticated_user(local_user)
        return local_user

    if not microsoft_user_is_logged_in():
        render_sign_in_screen()

    claims = dict(st.user)
    claims.pop("is_logged_in", None)
    if not extract_display_name(claims):
        st.title("TechAdmin")
        st.warning(
            "The current Microsoft session does not contain a usable identity."
        )
        microsoft_tab, local_tab = st.tabs(["Microsoft SSO", "Test account"])
        with microsoft_tab:
            st.write(
                "Sign out of the incomplete Microsoft session, then sign in again."
            )
            if st.button(
                "Sign out and restart",
                type="primary",
                width="stretch",
                key="restart_microsoft_sign_in",
            ):
                clear_local_authentication_state()
                st.logout()
        with local_tab:
            render_local_login()
        st.stop()

    enforce_app_user_access(claims)
    render_authenticated_user(claims)
    return claims


def render_local_login() -> None:
    """Authenticate the configured test account exactly as in the stable app."""
    enabled = (
        os.getenv("TECHADMIN_LOCAL_LOGIN_ENABLED", "false")
        .strip()
        .casefold()
        in {"1", "true", "yes", "on"}
    )
    if not enabled:
        st.info("The local test account is disabled.")
        return

    with st.form("local_login_form", clear_on_submit=False):
        username = st.text_input("Username", key="local_login_username")
        password = st.text_input(
            "Password", type="password", key="local_login_password"
        )
        submitted = st.form_submit_button(
            "Sign in", type="primary", width="stretch"
        )
    if not submitted:
        return

    expected_username = os.getenv(
        "TECHADMIN_LOCAL_LOGIN_USERNAME", "TechAdminTestUser"
    ).strip()
    expected_password = os.getenv("TECHADMIN_LOCAL_LOGIN_PASSWORD", "")
    valid_username = hmac.compare_digest(
        username.strip().casefold(), expected_username.casefold()
    )
    valid_password = bool(expected_password) and hmac.compare_digest(
        password, expected_password
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
    """Render a styled identity card while preserving original logout behavior."""
    with st.sidebar:
        st.markdown(
            '<div class="brand"><div class="brand-company">Coforge</div>'
            '<div class="brand-title">TechAdmin</div>'
            '<div class="brand-subtitle">Agentic IT Operations</div></div>',
            unsafe_allow_html=True,
        )
        display_name = (
            claims.get("name")
            or claims.get("preferred_username")
            or claims.get("email")
            or "Authenticated user"
        )
        role = (
            "Test account"
            if claims.get("auth_source") == "local_test_account"
            else "Authorized operator"
        )
        st.markdown(
            f'<div class="sidebar-user">'
            f'<div class="sidebar-avatar">{html.escape(_initials(display_name))}</div>'
            f'<div><div class="sidebar-user-name">{html.escape(str(display_name))}</div>'
            f'<div class="sidebar-user-role">{html.escape(role)}</div></div></div>',
            unsafe_allow_html=True,
        )

        if claims.get("auth_source") == "local_test_account":
            if st.button("Sign out", key="local_sign_out", width="stretch"):
                clear_local_authentication_state()
                st.rerun()
        elif st.button(
            "Sign out", key="microsoft_sign_out", width="stretch"
        ):
            clear_local_authentication_state()
            st.logout()

# ---------------------------------------------------------------------------
# Rich UI components
# ---------------------------------------------------------------------------


def rich_details(rows: Iterable[tuple[str, Any]], title: str) -> None:
    visible=[(label,value) for label,value in rows if value not in (None,"")]
    if not visible: return
    body="".join(
        f'<div class="detail-row"><div class="detail-label">{html.escape(label)}</div><div class="detail-value{ " muted" if value is None else ""}">{html.escape(str(value if value not in (None,"") else "Not available"))}</div></div>'
        for label,value in visible
    )
    st.markdown(f'<div class="section-title">{html.escape(title)}</div><div class="detail-card">{body}</div>',unsafe_allow_html=True)


def status_card(label: str, value: str, state: str, note: str) -> None:
    st.markdown(f'<div class="status-card {state}"><div class="status-label">{html.escape(label)}</div><div class="status-value">{html.escape(value)}</div><div class="status-note">{html.escape(note)}</div></div>',unsafe_allow_html=True)


def metric_cards(primary: Any, direct: int, nested: int, effective: int) -> None:
    cards=[("Primary group",primary or "Not available"),("Direct",direct),("Nested",nested),("Effective",effective)]
    content="".join(f'<div class="metric-card"><div class="metric-label">{html.escape(str(k))}</div><div class="metric-value">{html.escape(str(v))}</div></div>' for k,v in cards)
    st.markdown(f'<div class="metric-grid">{content}</div>',unsafe_allow_html=True)


def rich_group_table(groups: list[dict[str, Any]], nested: bool=False) -> None:
    if not groups:
        st.markdown('<div class="empty">No group memberships were returned.</div>',unsafe_allow_html=True); return
    headers=["Group","SAM account","Type","Description","Mail"] + (["Level","Inherited from"] if nested else [])
    head="".join(f"<th>{html.escape(h)}</th>" for h in headers)
    rows=[]
    for g in groups:
        values=[
            _ci_get(g,"Name") or "Unnamed group",
            _ci_get(g,"SamAccountName") or "Not available",
            _ci_get(g,"GroupCategory") or "Not available",
            _ci_get(g,"Description") or "Not available",
            _ci_get(g,"Mail") or "Not available",
        ]
        if nested: values += [_ci_get(g,"NestingLevel") if _ci_get(g,"NestingLevel") is not None else "Not available", _ci_get(g,"InheritedFrom") or "Not available"]
        cells=[]
        for index,value in enumerate(values):
            content=html.escape(str(value))
            if index==2 and value!="Not available": content=f'<span class="pill">{content}</span>'
            cells.append(f"<td>{content}</td>")
        rows.append("<tr>"+"".join(cells)+"</tr>")
    st.markdown(f'<div class="table-shell"><table class="rich-table"><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>',unsafe_allow_html=True)


def render_user_details(user: dict[str, Any]) -> None:
    name=_ci_get(user,"DisplayName","Name") or "User"
    upn=_ci_get(user,"UserPrincipalName") or "Identity unavailable"
    department=_ci_get(user,"Department")
    chip=f'<span class="chip">{html.escape(str(department))}</span>' if department else ""
    st.markdown(f'<div class="profile"><div class="avatar">{html.escape(_initials(name))}</div><div><div class="profile-name">{html.escape(str(name))}</div><div class="profile-upn">{html.escape(str(upn))}</div>{chip}</div></div>',unsafe_allow_html=True)

    c1,c2=st.columns(2,gap="large")
    with c1: rich_details([("Name",_ci_get(user,"Name")),("Display name",_ci_get(user,"DisplayName")),("SAM account name",_ci_get(user,"SamAccountName")),("User principal name",upn)],"Identity")
    with c2: rich_details([("Mail",_ci_get(user,"Mail","Email")),("Mobile phone",_ci_get(user,"MobilePhone")),("Department",department),("Description",_ci_get(user,"Description"))],"Contact and organization")

    enabled=_optional_bool(user,"Enabled","AccountEnabled"); locked=_optional_bool(user,"LockedOut")
    expired=_optional_bool(user,"PasswordExpired"); never=_optional_bool(user,"PasswordNeverExpires")
    st.markdown('<div class="section-title">Account health</div>',unsafe_allow_html=True)
    cols=st.columns(4,gap="medium")
    values=[
        ("Account", "Not available" if enabled is None else "Enabled" if enabled else "Disabled", "unavailable" if enabled is None else "healthy" if enabled else "unhealthy", "Not returned" if enabled is None else "Sign-in is enabled" if enabled else "Sign-in is blocked"),
        ("Lockout", "Not available" if locked is None else "Locked" if locked else "Not locked", "unavailable" if locked is None else "unhealthy" if locked else "healthy", "Use script for current AD state" if locked is None else "Action required" if locked else "No active lockout"),
        ("Password expired", "Not available" if expired is None else "Yes" if expired else "No", "unavailable" if expired is None else "unhealthy" if expired else "healthy", "Use script for calculated state" if expired is None else "Password change required" if expired else "Within policy"),
        ("Never expires", "Not available" if never is None else "Yes" if never else "No", "unavailable" if never is None else "unhealthy" if never else "healthy", "Policy unavailable" if never is None else "Review exception" if never else "Expiration applies"),
    ]
    for col,args in zip(cols,values):
        with col: status_card(*args)

    a1,a2=st.columns(2,gap="large")
    with a1: rich_details([("Password last set",_ci_get(user,"PasswordLastSet")),("Bad password count",_ci_get(user,"BadPasswordCount")),("When created",_ci_get(user,"WhenCreated")),("Canonical name",_ci_get(user,"CanonicalName"))],"Account details")
    with a2: rich_details([("Manager name",_ci_get(user,"ManagerName","ManagerDisplayName")),("Manager email",_ci_get(user,"ManagerEmail","ManagerUserPrincipalName")),("Distinguished name",_ci_get(user,"DistinguishedName"))],"Manager and directory")

    direct=[x for x in (_ci_get(user,"DirectGroups",default=[]) or []) if isinstance(x,dict)]
    nested=[x for x in (_ci_get(user,"NestedGroups",default=[]) or []) if isinstance(x,dict)]
    effective=[x for x in (_ci_get(user,"EffectiveGroups",default=[]) or []) if isinstance(x,dict)]
    st.markdown('<div class="section-title">Group memberships</div>',unsafe_allow_html=True)
    metric_cards(_ci_get(user,"PrimaryGroupName"),len(direct),len(nested),len(effective) or len(direct)+len(nested))
    t1,t2,t3=st.tabs(["Direct memberships","Nested memberships","Effective access"])
    with t1: rich_group_table(direct)
    with t2: rich_group_table(nested,True)
    with t3: rich_group_table(effective)


def flatten_rows(data: Dict[str, Any], excluded: set[str] | None=None) -> list[tuple[str,Any]]:
    rows=[]
    for key,value in data.items():
        if key in (excluded or set()) or value in (None,""): continue
        if isinstance(value,(dict,list)): value=json.dumps(value,ensure_ascii=False,default=str)
        rows.append((key.replace("_"," ").capitalize(),value))
    return rows


def result_banner(
    heading: str,
    message: str,
    state: str = "success",
) -> None:
    icons = {"success": "✓", "warning": "!", "failure": "×"}
    safe_state = state if state in icons else "success"
    st.markdown(
        f'<div class="result-banner {safe_state}">'
        f'<div class="result-icon">{icons[safe_state]}</div>'
        f'<div class="result-heading">{html.escape(heading)}</div>'
        f'<div class="result-copy">{html.escape(message)}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def action_cards(items: Iterable[tuple[str, Any, str]]) -> None:
    cards = []
    for label, value, icon in items:
        display = "Not available" if value in (None, "") else str(value)
        cards.append(
            f'<div class="action-card"><div class="action-card-icon">{html.escape(icon)}</div>'
            f'<div class="action-card-title">{html.escape(label)}</div>'
            f'<div class="action-card-value">{html.escape(display)}</div></div>'
        )
    st.markdown(
        '<div class="action-grid">' + "".join(cards) + '</div>',
        unsafe_allow_html=True,
    )


def render_timeline(items: Iterable[tuple[str, str, str]]) -> None:
    rows = []
    for title, copy_text, state in items:
        css = state if state in {"pending", "failed"} else ""
        rows.append(
            f'<div class="timeline-item"><div class="timeline-dot {css}"></div>'
            f'<div><div class="timeline-title">{html.escape(title)}</div>'
            f'<div class="timeline-copy">{html.escape(copy_text)}</div></div></div>'
        )
    st.markdown(
        '<div class="timeline">' + "".join(rows) + '</div>',
        unsafe_allow_html=True,
    )


def render_password_result(result: dict[str, Any]) -> None:
    result_banner(
        "Password reset completed",
        "A new credential was generated and is available through controlled delivery actions.",
    )
    username = result.get("user_name") or result.get("user_principal_name")
    manager_name = result.get("manager_name") or "Not available"
    manager_email = result.get("manager_email") or "Not available"
    action_cards([
        ("Target account", username, "U"),
        ("Manager", manager_name, "M"),
        ("Delivery recipient", manager_email, "@"),
    ])

    masked = result.get("masked_password") or "Credential hidden"
    st.markdown(
        f'<div class="section-title">Temporary credential</div>'
        f'<div class="secret-box">{html.escape(str(masked))}</div>',
        unsafe_allow_html=True,
    )

    token = result.get("password_token")
    if not token:
        result_banner(
            "Secure delivery unavailable",
            "The password token is no longer available. Run the reset again if delivery is required.",
            "warning",
        )
        return

    can_email = manager_email != "Not available" and email_is_configured()
    left, right = st.columns(2)
    if left.button(
        "Send securely to manager",
        key=f"send_{token}",
        disabled=not can_email,
        width="stretch",
    ):
        sent, message, recipient = send_password_to_manager(token)
        if sent:
            result_banner("Delivery successful", f"The credential was sent to {recipient}.")
        else:
            result_banner("Delivery failed", message, "failure")

    ok, filename, content, message = build_password_download(token)
    if ok:
        right.download_button(
            "Download secure password file",
            content,
            filename,
            "text/plain",
            width="stretch",
            key=f"dl_{token}",
        )
    else:
        right.button(
            "Download secure password file",
            disabled=True,
            width="stretch",
            key=f"dl_disabled_{token}",
        )
        st.caption(message)


def render_access_result(intent: str, result: dict[str, Any]) -> None:
    granted = intent == "grant_access"
    heading = "Group access granted" if granted else "Group access revoked"
    message = (
        "The user was added to the requested group."
        if granted
        else "The user was removed from the requested group."
    )
    result_banner(heading, result.get("message") or message)
    action_cards([
        ("User", result.get("user_principal_name") or result.get("user_name") or result.get("username"), "U"),
        ("Group", result.get("group_name") or result.get("group"), "G"),
        ("Operation", "Access granted" if granted else "Access revoked", "+" if granted else "−"),
    ])
    render_timeline([
        ("Identity resolved", "The target user was validated.", "complete"),
        ("Group resolved", "The requested group was validated.", "complete"),
        ("Membership updated", message, "complete"),
    ])


def render_unlock_result(result: dict[str, Any]) -> None:
    result_banner(
        "Account unlocked",
        result.get("message") or "The account lockout was cleared successfully.",
    )
    action_cards([
        ("Account", result.get("user_principal_name") or result.get("user_name") or result.get("username"), "U"),
        ("Current state", "Unlocked", "✓"),
        ("Directory", result.get("domain") or result.get("backend") or "Active Directory", "D"),
    ])
    render_timeline([
        ("Account located", "The target identity was resolved.", "complete"),
        ("Lockout verified", "The current account state was checked.", "complete"),
        ("Unlock applied", "The account can attempt sign-in again.", "complete"),
    ])


def render_create_user_result(result: dict[str, Any]) -> None:
    result_banner(
        "User account created",
        result.get("message") or "The new identity was provisioned successfully.",
    )
    action_cards([
        ("Display name", result.get("display_name") or result.get("employee_name") or result.get("name"), "U"),
        ("User principal name", result.get("user_principal_name") or result.get("email"), "@"),
        ("Department", result.get("department"), "D"),
    ])
    rich_details([
        ("SAM account name", result.get("sam_account_name") or result.get("username")),
        ("Employee number", result.get("employee_number")),
        ("Target OU", result.get("target_ou")),
        ("Description", result.get("description")),
    ], "Provisioned identity")


def render_delete_user_result(result: dict[str, Any]) -> None:
    result_banner(
        "User account removed",
        result.get("message") or "The requested identity was deprovisioned.",
        "warning",
    )
    action_cards([
        ("Account", result.get("user_principal_name") or result.get("username"), "U"),
        ("Operation", "Deprovisioned", "×"),
        ("Audit reference", result.get("operation_id") or result.get("request_id"), "#"),
    ])


def render_create_group_result(result: dict[str, Any]) -> None:
    result_banner(
        "Group created",
        result.get("message") or "The new directory group was created successfully.",
    )
    action_cards([
        ("Group", result.get("group_name") or result.get("name"), "G"),
        ("Type", result.get("group_type") or result.get("group_category") or "Security group", "T"),
        ("Scope", result.get("group_scope") or "Not available", "S"),
    ])
    rich_details([
        ("Distinguished name", result.get("distinguished_name")),
        ("Description", result.get("description")),
        ("Target OU", result.get("target_ou")),
    ], "Directory group")


def render_vm_result(result: dict[str, Any]) -> None:
    result_banner(
        "Virtual machine provisioned",
        result.get("message") or "The virtual machine workflow completed successfully.",
    )
    action_cards([
        ("Virtual machine", result.get("vm_name") or result.get("hostname"), "V"),
        ("Compute", f"{result.get('cpu_count') or '—'} CPU / {result.get('ram_gb') or '—'} GB", "C"),
        ("Host", result.get("target_host"), "H"),
    ])
    rich_details([
        ("Virtual switch", result.get("vswitch_name")),
        ("IP address", result.get("ip_address")),
        ("Subnet", result.get("subnet")),
        ("Gateway", result.get("gateway")),
        ("DNS", result.get("dns")),
    ], "Network configuration")


def render_investigation_result(result: dict[str, Any]) -> None:
    report = result.get("report")
    if isinstance(report, dict):
        # Preserve the specialized evidence renderer, but add a consistent executive header.
        event_count = report.get("total_events") or report.get("event_count") or report.get("summary", {}).get("total_events") if isinstance(report.get("summary"), dict) else None
        result_banner(
            "Security investigation completed",
            result.get("message") or "Failed sign-in and lockout evidence was collected and normalized.",
        )
        if event_count is not None:
            action_cards([
                ("Evidence events", event_count, "E"),
                ("Target", report.get("user_principal_name") or report.get("username"), "U"),
                ("Time window", report.get("time_window"), "T"),
            ])
        render_investigation_report(report)
    else:
        result_banner(
            "Investigation completed without evidence",
            "No structured investigation report was returned.",
            "warning",
        )


def render_generic_result(result: dict[str, Any]) -> None:
    success = result.get("success") is not False
    result_banner(
        "Operation completed" if success else "Operation failed",
        result.get("message") or (
            "The requested administration workflow completed successfully."
            if success
            else "The requested administration workflow did not complete."
        ),
        "success" if success else "failure",
    )
    rows = flatten_rows(
        result,
        {
            "execution", "user", "new_password", "temporary_password",
            "_transient_password", "report", "report_markdown", "message",
            "success", "password_token",
        },
    )
    rich_details(rows, "Operation details")


def render_result(intent: str, result: dict[str, Any]) -> None:
    if intent == "get_user_details":
        user = result.get("user")
        render_user_details(user if isinstance(user, dict) else result)
    elif intent == "password_reset":
        render_password_result(result)
    elif intent == "account_unlock":
        render_unlock_result(result)
    elif intent in {"grant_access", "revoke_access"}:
        render_access_result(intent, result)
    elif intent == "create_user":
        render_create_user_result(result)
    elif intent == "delete_user":
        render_delete_user_result(result)
    elif intent == "create_group":
        render_create_group_result(result)
    elif intent == "create_vm":
        render_vm_result(result)
    elif intent == "failed_login_investigation":
        render_investigation_result(result)
    else:
        render_generic_result(result)


def render_response(response: dict[str,Any]) -> None:
    intent=str(response.get("intent") or "Identity operation"); meta=response.get("metadata") if isinstance(response.get("metadata"),dict) else {}
    target=meta.get("email") or meta.get("username") or "Unknown target"
    if response.get("confirmation_required"): status,css="Approval required","warning"
    elif response.get("success") is True: status,css="Completed","success"
    elif response.get("success") is False: status,css="Failed","failure"
    else: status,css="Submitted",""
    st.markdown(f'<div class="operation {css}"><div class="operation-kicker">Current operation</div><div class="operation-title">{html.escape(intent.replace("_"," ").title())}</div><div class="operation-meta"><b>Target:</b> {html.escape(str(target))} &nbsp; • &nbsp; <b>Status:</b> {status}</div></div>',unsafe_allow_html=True)
    tool=response.get("tool_result"); result=tool.get("result") if isinstance(tool,dict) else None
    if isinstance(result,dict): render_result(intent,result)
    elif response.get("confirmation_required"): st.info(response.get("confirmation_prompt") or "Approval required.")
    elif response.get("success") is False: st.error(response.get("message") or "Operation failed.")
    elif response.get("message"): st.info(response["message"])
    with st.expander("Raw response (JSON)",expanded=False): st.json(redact(copy.deepcopy(response)))

# ---------------------------------------------------------------------------
# Workflow and sidebar
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
        "content": redact(copy.deepcopy(content)),
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
    access = st.session_state.get("app_user_access")
    requester_id = access.get("user_id") if isinstance(access, dict) else None

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
                requester_id=requester_id,
            )
        response.pop("_dashboard_secret", None)
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
    append_conversation(
        "assistant", response, datetime.now().strftime("%H:%M:%S")
    )
    st.rerun()


def render_confirmation_controls() -> None:
    pending = st.session_state.pending_confirmation
    if not isinstance(pending, dict):
        return
    with st.container(border=True):
        st.markdown(
            '<div class="confirm-panel"><div class="result-heading">Approval required</div>'
            '<div class="result-copy">Review the target before authorizing this sensitive operation.</div></div>',
            unsafe_allow_html=True,
        )
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


def safe_conversation_download() -> str:
    return json.dumps(
        redact(copy.deepcopy(st.session_state.conversation)),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def render_sidebar() -> None:
    with st.sidebar:
        access=st.session_state.get("app_user_access"); user_id=access.get("user_id") if isinstance(access,dict) else None
        history=(get_user_request_history(user_id) if user_id else []) or []; history=history[:5]
        st.markdown(f'<div class="sidebar-head"><div class="sidebar-head-title">Recent activity</div><div class="sidebar-count">{len(history)}</div></div>',unsafe_allow_html=True)
        if history:
            for item in history:
                date=item.get("requested_at"); date=date.strftime("%d %b, %H:%M") if isinstance(date,datetime) else str(date or "Unknown")
                title=str(item.get("request") or item.get("operation") or "Operation"); title=title if len(title)<=85 else title[:82]+"..."
                status=str(item.get("status") or "Unknown").title(); bad=" bad" if status.casefold() in {"failed","cancelled"} else ""
                st.markdown(f'<div class="activity-card"><div class="activity-title">{html.escape(title)}</div><div class="activity-meta"><span class="dot{bad}"></span><span>{html.escape(status)}</span><span>•</span><span>{html.escape(date)}</span></div></div>',unsafe_allow_html=True)
        else: st.caption("No recent operations yet.")
        with st.expander("System health"):
            status=get_config_status(); st.caption(f"Microsoft Entra: {'Configured' if status.get('graph_client_id') and status.get('graph_client_secret') and status.get('graph_tenant_id') else 'Incomplete'}"); st.caption(f"PowerShell: {'Enabled' if status.get('powershell_operations_enabled') else 'Disabled'}"); st.caption(f"LangGraph: {'Active' if status.get('orchestration_engine')=='langgraph' else 'Unavailable'}")
            if st.button("Test Ollama",width="stretch"):
                connected,message=check_ollama(); st.session_state.ollama_check_result={"connected":connected,"message":message}
        with st.expander("Quick actions"):
            for index,example in enumerate(EXAMPLES):
                if st.button(example,key=f"example_{index}",width="stretch"): st.session_state.queued_query=example; st.rerun()
        st.caption(f"Audit log: {LOG_FILE}")
        if st.session_state.conversation:
            if st.button("Clear session",width="stretch"): st.session_state.conversation=[];st.session_state.pending_confirmation=None;st.rerun()
            st.download_button("Export session",json.dumps(redact(st.session_state.conversation),indent=2,default=str),"techadmin_session.json","application/json",width="stretch")


def render_command_center() -> None:
    if st.session_state.conversation:
        return
    st.markdown(
        '<div class="hero"><div class="hero-kicker">AI-assisted administration</div>'
        '<div class="hero-title">How can TechAdmin help?</div>'
        '<div class="hero-copy">Look up identities, reset passwords, manage access, '
        'or investigate failed sign-ins through governed workflows.</div></div>',
        unsafe_allow_html=True,
    )


def render_recent_operations() -> None:
    """Retained for compatibility; recent requests are displayed in the sidebar."""
    return


def main() -> None:
    init_state()
    require_authentication()
    render_command_center()

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
        answer = query.strip().casefold().rstrip(".!")
        if isinstance(pending, dict) and answer in YES_WORDS:
            append_conversation(
                "user", query, datetime.now().strftime("%H:%M:%S")
            )
            st.session_state.pending_confirmation = None
            execute_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending.get("request_id"),
                correlation_id=pending.get("correlation_id"),
                add_user_turn=False,
            )
        elif isinstance(pending, dict) and answer in NO_WORDS:
            append_conversation(
                "user", query, datetime.now().strftime("%H:%M:%S")
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

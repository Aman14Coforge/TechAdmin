# """TechAdmin Streamlit UI.

# Stable application shell with Microsoft SSO, local test authentication,
# app_users authorization, LangGraph execution, confirmation handling, secure
# password delivery, request history, and business-facing result rendering.

# Microsoft Entra values are handled as tri-state values. Missing values are
# shown as Unavailable rather than being incorrectly converted to False.
# """
# from __future__ import annotations

# import copy
# import html
# import hmac
# import json
# import os
# from datetime import datetime
# from typing import Any, Dict, Iterable

# import pandas as pd
# import streamlit as st
# # from patch_report_ui import (
#     initialize_patch_report_state,
#     render_patch_report,
# )

# from flow_service import (
#     LOG_FILE,
#     FlowService,
#     build_password_download,
#     check_ollama,
#     email_is_configured,
#     get_config_status,
#     send_password_to_manager,
# )
# from App.db.login_authorization import authorize_claims, extract_display_name
# from App.db.operation_audit import get_user_request_history
# from investigation_report_ui import render_investigation_report
# from patch_report_ui import initialize_patch_report_state, render_patch_report

# st.set_page_config(page_title="TechAdmin", page_icon="🛠️", layout="wide")


# def enforce_https_origin() -> None:
#     public_url = os.getenv(
#         "TECHADMIN_PUBLIC_URL", "https://techadmin.coforge.com"
#     ).strip()
#     if not public_url:
#         return
#     st.markdown(
#         f"""
#         <script>
#         (() => {{
#             try {{
#                 const publicUrl = new URL("{public_url}");
#                 const current = new URL(window.location.href);
#                 if (current.protocol === "http:" &&
#                     current.hostname === publicUrl.hostname) {{
#                     const target = new URL(window.location.href);
#                     target.protocol = "https:";
#                     target.port = publicUrl.port || "";
#                     window.location.replace(target.toString());
#                 }}
#             }} catch (e) {{}}
#         }})();
#         </script>
#         """,
#         unsafe_allow_html=True,
#     )


# enforce_https_origin()

# st.markdown(
#     """
#     <style>
#     :root {
#         --tech-ink:#10283f; --tech-muted:#71849a; --tech-blue:#1b5277;
#         --tech-blue-soft:#eaf4f8; --tech-line:#dce5eb;
#         --tech-navy:#0b2034; --tech-navy-light:#17334c;
#         --tech-coral:#f45a45; --ok:#168969; --bad:#d94e4e; --warn:#b7791f;
#     }
#     .stApp {background:#f7f9fb;color:var(--tech-ink)}
#     [data-testid="stSidebar"] {background:var(--tech-navy);border-right:1px solid #20394f}
#     [data-testid="stSidebar"] > div:first-child {padding:1.1rem .8rem 1rem}
#     [data-testid="stSidebar"] [data-testid="stMarkdownContainer"] {color:#d8e5f0}
#     [data-testid="stSidebar"] [data-testid="stCaptionContainer"] {color:#8ea6bc}
#     [data-testid="stSidebar"] hr {border-color:#294158}
#     [data-testid="stSidebar"] .stButton > button {background:transparent;border:1px solid transparent;color:#d3e0eb;text-align:left;justify-content:flex-start;min-height:2.35rem}
#     [data-testid="stSidebar"] .stButton > button:hover,[data-testid="stSidebar"] .stButton > button[kind="primary"] {background:#183a56;border-color:#244c6a;color:#fff}
#     [data-testid="stSidebar"] [data-testid="stExpander"] {background:#112c43;border:1px solid #27445d;border-radius:.65rem}
#     [data-testid="stSidebar"] [data-testid="stExpander"] summary {color:#e6eef5}
#     .sidebar-brand {border-bottom:1px solid #294158;margin:0 0 1rem;padding:0 0 1rem}
#     .company-name {color:#fff;font-size:1.55rem;font-weight:800;letter-spacing:-.045em}
#     .company-name span {color:var(--tech-coral)}
#     .sidebar-brand h1 {color:#fff;font-size:1rem;line-height:1;margin:.75rem 0 .15rem}
#     .tech-kicker {color:#8ea6bc;font-size:.68rem;letter-spacing:.02em}
#     .sidebar-section-label {color:#7892a9;font-size:.62rem;font-weight:800;letter-spacing:.13em;text-transform:uppercase;margin:1.35rem 0 .55rem}
#     .sidebar-request {border-left:2px solid var(--tech-coral);background:#132e46;border-radius:0 .5rem .5rem 0;padding:.55rem .6rem;margin:.35rem 0;color:#f2f6f9;font-size:.73rem;line-height:1.35}
#     .sidebar-request small {color:#8ea6bc;font-size:.63rem}
#     .user-footer {border-top:1px solid #294158;margin-top:1rem;padding-top:.9rem;color:#fff;font-size:.75rem}
#     .topbar {background:#fff;border-bottom:1px solid var(--tech-line);margin:-1rem -1rem 1.5rem;padding:.7rem 1.5rem;color:var(--tech-ink);font-size:.87rem;font-weight:650}
#     .topbar small {display:block;color:var(--tech-muted);font-size:.67rem;font-weight:400;margin-top:.15rem}
#     .assistant-content {max-width:950px;margin:0 auto}
#     .welcome-heading {font-size:1.65rem;font-weight:550;letter-spacing:-.035em;color:#102b44;margin:.15rem 0 .2rem}
#     .welcome-subtitle {color:var(--tech-muted);font-size:.82rem}
#     .tech-panel {background:linear-gradient(135deg,var(--tech-blue-soft),#fff);border:1px solid #cfe3f2;border-radius:.75rem;padding:1.25rem 1.35rem;margin:.5rem 0 1.25rem}
#     .tech-panel strong {color:var(--tech-ink);display:block;font-size:1.05rem;margin-bottom:.3rem}
#     .tech-panel span {color:var(--tech-muted)}
#     .operation-card {border:1px solid var(--tech-line);border-left:4px solid var(--tech-blue);border-radius:.55rem;padding:1rem 1.15rem;margin:1rem 0 1.25rem;background:#fff}
#     .operation-card.success {border-left-color:var(--ok)}
#     .operation-card.warning {border-left-color:var(--warn)}
#     .operation-card.failure {border-left-color:var(--bad)}
#     .operation-label {color:var(--tech-muted);font-size:.72rem;font-weight:700;letter-spacing:.08em;text-transform:uppercase}
#     .operation-title {color:var(--tech-ink);font-size:1.2rem;font-weight:700;margin-top:.25rem}
#     .operation-meta {color:var(--tech-muted);margin-top:.45rem}
#     .status-card {border:1px solid var(--tech-line);border-radius:.75rem;padding:1rem;background:#fff;min-height:128px}
#     .status-card.ok {border-left:5px solid var(--ok);background:#f1fbf5}
#     .status-card.bad {border-left:5px solid var(--bad);background:#fff5f5}
#     .status-card.unknown {border-left:5px solid var(--tech-muted);background:#f5f7fa}
#     .status-label {font-size:.72rem;color:var(--tech-muted);font-weight:700;text-transform:uppercase;letter-spacing:.06em}
#     .status-value {font-size:1.25rem;font-weight:800;margin-top:.35rem}
#     .status-value.ok {color:var(--ok)}
#     .status-value.bad {color:var(--bad)}
#     .status-value.unknown {color:var(--tech-muted)}
#     .status-note {color:var(--tech-muted);font-size:.72rem;line-height:1.35;margin-top:.35rem}
#     .directory-information {background:#f7fbfe;border:1px solid #cfe3f2;border-left:4px solid var(--tech-blue);border-radius:.65rem;color:var(--tech-muted);font-size:.85rem;line-height:1.5;margin:.75rem 0 1rem;padding:.85rem 1rem}
#     .directory-information strong {color:var(--tech-ink)}
#     .login-hero {position:relative;isolation:isolate;overflow:hidden;box-sizing:border-box;min-height:calc(100vh - 2rem);padding:2rem 2.25rem;background:var(--tech-navy);color:#fff;display:flex;flex-direction:column;justify-content:center}
#     .login-hero:before,.login-hero:after {content:"";position:absolute;z-index:-1;border:1px solid rgba(114,153,184,.08);border-radius:50%;width:560px;height:560px;right:-250px;top:10%}
#     .login-hero:after {width:420px;height:420px;right:-180px;top:19%;border-color:rgba(114,153,184,.11)}
#     .login-hero .company-name {position:absolute;top:2rem;left:2.25rem;font-size:2rem}
#     .hero-copy {max-width:540px;margin-top:1.5rem}
#     .hero-icon {display:flex;align-items:center;justify-content:center;width:2.8rem;height:2.8rem;border-radius:.7rem;background:var(--tech-coral);font-size:1.25rem;margin-bottom:1.25rem}
#     .hero-copy .tech-kicker {color:var(--tech-coral);font-weight:800;letter-spacing:.16em}
#     .hero-copy h1 {font-size:clamp(2.3rem,4vw,3.4rem);font-weight:500;line-height:1.08;letter-spacing:-.055em;color:white;margin:.85rem 0 1rem}
#     .hero-copy p {color:#b6c9d9;font-size:.95rem;line-height:1.65;max-width:390px}
#     .hero-foot {position:absolute;bottom:1.8rem;left:2.25rem;color:#8ea6bc;font-size:.72rem}
#     .login-panel {max-width:470px;margin:0 auto;padding:2rem 1rem}
#     .login-panel .tech-kicker {color:var(--tech-coral);font-size:.65rem;font-weight:800}
#     .login-panel h2 {font-size:1.8rem;font-weight:550;letter-spacing:-.04em;color:var(--tech-ink);margin:.6rem 0 .25rem}
#     .login-panel p {color:var(--tech-muted);font-size:.82rem}
#     .login-callout {border:1px solid var(--tech-line);border-radius:.65rem;background:#fafbfc;padding:.9rem 1rem;margin:.55rem 0 1rem;color:var(--tech-ink);font-size:.78rem}
#     .login-callout small {color:var(--tech-muted)}
#     .ms-mark {display:inline-grid;grid-template-columns:8px 8px;grid-template-rows:8px 8px;gap:2px;vertical-align:middle;margin-right:.5rem}
#     .ms-mark i:nth-child(1){background:#f25022}.ms-mark i:nth-child(2){background:#7fba00}.ms-mark i:nth-child(3){background:#00a4ef}.ms-mark i:nth-child(4){background:#ffb900}
#     .login-footnote {text-align:center;color:var(--tech-muted);font-size:.68rem;margin-top:1.2rem}
#     div.stButton > button[kind="primary"],div.stFormSubmitButton > button[kind="primary"] {background:var(--tech-coral);border-color:var(--tech-coral);color:#fff;font-weight:700}
#     div.stButton > button[kind="primary"]:hover,div.stFormSubmitButton > button[kind="primary"]:hover {background:#df4c3a;border-color:#df4c3a;color:#fff}
#     [data-testid="stChatInput"] {border-color:#d6e0e7;box-shadow:0 4px 14px rgba(16,40,63,.08)}
#     [data-testid="stChatMessage"] {border:0}
#     @media (max-width:800px) {.login-hero{min-height:370px;padding:1.5rem}.login-hero .company-name{top:1.5rem;left:1.5rem}.hero-foot{left:1.5rem}.login-panel{padding:1rem .25rem}.welcome-heading{font-size:1.4rem}}
#     </style>
#     """,
#     unsafe_allow_html=True,
# )

# # Authentication

# def microsoft_user_is_logged_in() -> bool:
#     try:
#         return bool(st.user.is_logged_in)
#     except (AttributeError, RuntimeError, TypeError):
#         return False


# def clear_local_authentication_state() -> None:
#     st.session_state.pop("local_authenticated_user", None)
#     st.session_state.pop("app_user_access", None)


# def render_sign_in_screen(*, microsoft_message: str | None = None) -> None:
#     st.markdown(
#         """<style>
#         [data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display:none !important}
#         [data-testid="stMain"] {margin-left:0 !important}
#         [data-testid="stMainBlockContainer"] {max-width:none !important;padding:1rem !important}
#         </style>""",
#         unsafe_allow_html=True,
#     )
#     hero, form = st.columns([1, 1], gap="small")
#     with hero:
#         st.markdown(
#             '<section class="login-hero"><div class="company-name"><span>Co</span>forge</div>'
#             '<div class="hero-copy"><div class="hero-icon">✣</div><div class="tech-kicker">TechAdmin AI</div>'
#             '<h1>Identity operations,<br>made effortless.</h1>'
#             '<p>Resolve access issues and manage employee identities with a secure, intelligent copilot.</p></div>'
#             '<div class="hero-foot">♧ &nbsp; Enterprise protected · Actions fully audited</div></section>',
#             unsafe_allow_html=True,
#         )
#     with form:
#         st.markdown('<div class="login-panel"><div class="tech-kicker">Welcome back</div><h2>Sign in to TechAdmin</h2><p>Access the secure identity operations workspace.</p></div>', unsafe_allow_html=True)
#         microsoft_tab, local_tab = st.tabs(["Microsoft SSO", "Test account"])
#         with microsoft_tab:
#             if microsoft_message:
#                 st.warning(microsoft_message)
#             st.markdown(
#                 '<div class="login-callout"><strong><span class="ms-mark"><i></i><i></i><i></i><i></i></span>Continue with your work account</strong><br>'
#                 '<small>Use your Coforge Microsoft credentials.</small></div>',
#                 unsafe_allow_html=True,
#             )
#             if st.button("▦  Sign in with Microsoft", type="primary", width="stretch", key="microsoft_sign_in"):
#                 st.login()
#         with local_tab:
#             st.markdown('<div class="login-callout"><strong>Test account</strong><br><small>Use your configured preview credentials.</small></div>', unsafe_allow_html=True)
#             render_local_login()
#         st.markdown('<div class="login-footnote">Need access? Contact your IT service desk.<br><br>Authorized users only · Coforge IT Operations</div>', unsafe_allow_html=True)
#     st.stop()


# def enforce_app_user_access(claims: dict[str, Any]) -> None:
#     display_name = extract_display_name(claims)
#     if not display_name:
#         st.session_state.app_user_access = {
#             "display_name": "", "allowed": True,
#             "reason": "legacy_identity_without_display_name", "message": "",
#             "user_principal_name": "", "user_id": "", "department": "",
#         }
#         return
#     cached = st.session_state.get("app_user_access")
#     if not (isinstance(cached, dict) and cached.get("display_name") == display_name):
#         decision = authorize_claims(claims)
#         cached = {
#             "display_name": display_name, "allowed": decision.allowed,
#             "reason": decision.reason, "message": decision.message,
#             "user_principal_name": decision.user_principal_name,
#             "user_id": decision.user_id, "department": decision.department,
#         }
#         st.session_state.app_user_access = cached
#     if cached.get("allowed") is True:
#         return
#     st.title("TechAdmin")
#     st.error(cached.get("message") or "This identity is not authorized to use TechAdmin.")
#     st.caption(f"Signed in as: {display_name or 'unknown'}. Access is granted only to active users registered in the TechAdmin app_users directory.")
#     if claims.get("auth_source") == "local_test_account":
#         if st.button("Return to sign in", key="denied_local_sign_out"):
#             clear_local_authentication_state(); st.rerun()
#     elif st.button("Sign out", key="denied_microsoft_sign_out"):
#         clear_local_authentication_state(); st.logout()
#     st.stop()


# def require_authentication() -> dict[str, Any]:
#     local_user = st.session_state.get("local_authenticated_user")
#     if isinstance(local_user, dict):
#         enforce_app_user_access(local_user); render_authenticated_user(local_user); return local_user
#     if not microsoft_user_is_logged_in():
#         render_sign_in_screen()
#     claims = dict(st.user)
#     claims.pop("is_logged_in", None)
#     if not extract_display_name(claims):
#         st.title("TechAdmin")
#         st.warning("The current Microsoft session does not contain a usable identity.")
#         microsoft_tab, local_tab = st.tabs(["Microsoft SSO", "Test account"])
#         with microsoft_tab:
#             st.write("Sign out of the incomplete Microsoft session, then sign in again.")
#             if st.button("Sign out and restart", type="primary", width="stretch", key="restart_microsoft_sign_in"):
#                 clear_local_authentication_state(); st.logout()
#         with local_tab:
#             render_local_login()
#         st.stop()
#     enforce_app_user_access(claims); render_authenticated_user(claims); return claims


# def render_local_login() -> None:
#     enabled = os.getenv("TECHADMIN_LOCAL_LOGIN_ENABLED", "false").strip().casefold() in {"1", "true", "yes", "on"}
#     if not enabled:
#         st.info("The local test account is disabled."); return
#     with st.form("local_login_form", clear_on_submit=False):
#         username = st.text_input("Username", key="local_login_username")
#         password = st.text_input("Password", type="password", key="local_login_password")
#         submitted = st.form_submit_button("Sign in", type="primary", width="stretch")
#     if not submitted:
#         return
#     expected_username = os.getenv("TECHADMIN_LOCAL_LOGIN_USERNAME", "TechAdminTestUser").strip()
#     expected_password = os.getenv("TECHADMIN_LOCAL_LOGIN_PASSWORD", "")
#     valid_username = hmac.compare_digest(username.strip().casefold(), expected_username.casefold())
#     valid_password = bool(expected_password) and hmac.compare_digest(password, expected_password)
#     if not (valid_username and valid_password):
#         st.error("Invalid username or password."); return
#     st.session_state.local_authenticated_user = {
#         "name": expected_username, "preferred_username": expected_username,
#         "auth_source": "local_test_account",
#     }
#     st.session_state.pop("app_user_access", None); st.rerun()


# def render_authenticated_user(claims: dict[str, Any]) -> None:
#     with st.sidebar:
#         st.markdown('<div class="sidebar-brand"><div class="company-name"><span>Co</span>forge</div><h1>TechAdmin AI</h1><div class="tech-kicker">IT operations copilot</div></div>', unsafe_allow_html=True)
#         st.markdown('<div class="sidebar-section-label">Workspace</div>', unsafe_allow_html=True)
#         current_page = st.session_state.get("active_page", "Assistant")
#         for label, icon in (("Assistant", "▱"), ("Request history", "◷"), ("Directory", "♙")):
#             if st.button(f"{icon}  {label}", key=f"nav_{label.casefold().replace(' ', '_')}", type="primary" if current_page == label else "secondary", width="stretch"):
#                 st.session_state.active_page = label
#                 st.rerun()
#         display_name = claims.get("name") or claims.get("preferred_username") or claims.get("email") or "Authenticated user"
#         st.markdown('<div class="user-footer">● &nbsp; ' + html.escape(str(display_name)) + '<br><small>Operations admin</small></div>', unsafe_allow_html=True)
#         if claims.get("auth_source") == "local_test_account":
#             if st.button("Sign out", key="local_sign_out", width="stretch"):
#                 clear_local_authentication_state(); st.rerun()
#         elif st.button("Sign out", key="microsoft_sign_out", width="stretch"):
#             clear_local_authentication_state(); st.logout()

# # Constants and helpers

# EXAMPLES = [
#     "Get user details for MigrationTest2@Coforge.com",
#     "Get user details for MigrationTest2@Coforge.com via script",
#     "Get user details for MigrationTest2@Coforge.com on Entra",
#     "Reset password for MigrationTest2@Coforge.com",
#     "Reset password for MigrationTest2@Coforge.com via script",
#     "Unlock account for MigrationTest2@Coforge.com",
#     "Add user MigrationTest2@Coforge.com to group TechAI_Group",
#     "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
#     "Investigate failed logins for MigrationTest2@Coforge.com in the last 24 hours",
#     "Investigate account lockout for MigrationTest3@Coforge.com in the last 7 days",
# ]
# YES_WORDS = {"yes", "y", "confirm", "confirmed", "proceed", "approve", "approved", "ok", "okay"}
# NO_WORDS = {"no", "n", "cancel", "stop", "abort", "nevermind"}
# SENSITIVE_HISTORY_KEYS = {
#     "new_password", "temporary_password", "password", "initial_password",
#     "domain_password", "admin_password", "client_secret", "access_token",
#     "refresh_token", "_dashboard_secret", "_transient_password",
# }


# @st.cache_resource(show_spinner="Starting TechAdmin...")
# def get_service() -> FlowService:
#     return FlowService()


# def init_state() -> None:
#     st.session_state.setdefault("conversation", [])
#     st.session_state.setdefault("queued_query", None)
#     st.session_state.setdefault("pending_confirmation", None)
#     st.session_state.setdefault("password_cards", [])
#     st.session_state.setdefault("ollama_check_result", None)
#     initialize_patch_report_state()
    


# def display_text(value: Any) -> str:
#     if value is None or value == "": return "—"
#     if isinstance(value, bool): return "Yes" if value else "No"
#     return str(value)


# def show_table(rows: Iterable[tuple[str, Any]], caption: str = "") -> None:
#     prepared = [(label, value) for label, value in rows if value not in (None, "")]
#     if not prepared: return
#     if caption: st.markdown(f"**{caption}**")
#     st.dataframe(pd.DataFrame([{"Field": label, "Value": display_text(value)} for label, value in prepared]), hide_index=True, width="stretch")


# def flatten_rows(data: Dict[str, Any], excluded: set[str] | None = None) -> list[tuple[str, Any]]:
#     rows = []
#     for key, value in data.items():
#         if key in (excluded or set()) or value in (None, ""): continue
#         if isinstance(value, (dict, list)): value = json.dumps(value, ensure_ascii=False, default=str)
#         rows.append((key.replace("_", " ").capitalize(), value))
#     return rows


# def redact_sensitive_history(value: Any) -> Any:
#     if isinstance(value, dict):
#         cleaned = {}
#         for key, item in value.items():
#             normalized = key.strip().casefold()
#             if normalized in SENSITIVE_HISTORY_KEYS:
#                 if normalized != "_dashboard_secret": cleaned[key] = "[redacted]"
#                 continue
#             cleaned[key] = redact_sensitive_history(item)
#         return cleaned
#     if isinstance(value, list): return [redact_sensitive_history(item) for item in value]
#     return value


# def register_dashboard_secret(response: Dict[str, Any]) -> bool:
#     response.pop("_dashboard_secret", None); return False


# def _ci_get(data: dict[str, Any], *names: str, default: Any = None) -> Any:
#     if not isinstance(data, dict): return default
#     normalized = {str(key).replace("_", "").casefold(): value for key, value in data.items()}
#     for name in names:
#         key = name.replace("_", "").casefold()
#         if key in normalized: return normalized[key]
#     return default


# def _optional_boolean(data: dict[str, Any], *field_names: str) -> bool | None:
#     value = _ci_get(data, *field_names, default=None)
#     if isinstance(value, bool): return value
#     if isinstance(value, int) and value in {0, 1}: return bool(value)
#     if isinstance(value, str):
#         normalized = value.strip().casefold()
#         if normalized in {"true", "yes", "1", "enabled", "locked", "expired"}: return True
#         if normalized in {"false", "no", "0", "disabled", "not locked", "not expired"}: return False
#     return None


# def _status_card(label: str, display_value: str, status: str, note: str | None = None) -> None:
#     css = status if status in {"ok", "bad", "unknown"} else "unknown"
#     note_html = f'<div class="status-note">{html.escape(note)}</div>' if note else ""
#     st.markdown(
#         f'<div class="status-card {css}"><div class="status-label">{html.escape(label)}</div>'
#         f'<div class="status-value {css}">{html.escape(display_value)}</div>{note_html}</div>',
#         unsafe_allow_html=True,
#     )


# def _normalise_group_rows(value: Any) -> list[dict[str, Any]]:
#     return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


# def _group_frame(groups: list[dict[str, Any]], *, nested: bool) -> pd.DataFrame:
#     rows = []
#     for group in groups:
#         row = {
#             "Group": _ci_get(group, "Name") or "Unresolved group",
#             "SAM account": _ci_get(group, "SamAccountName"),
#             "Category": _ci_get(group, "GroupCategory"),
#             "Scope": _ci_get(group, "GroupScope"),
#             "Description": _ci_get(group, "Description"),
#             "Distinguished name": _ci_get(group, "DistinguishedName"),
#         }
#         if nested:
#             row["Nesting level"] = _ci_get(group, "NestingLevel")
#             row["Inherited from"] = _ci_get(group, "InheritedFrom")
#         rows.append(row)
#     return pd.DataFrame(rows)

# # Business renderers

# def render_script_execution(execution: Dict[str, Any]) -> None:
#     show_table([
#         ("Success", execution.get("success")), ("Operation", execution.get("operation")),
#         ("Script", execution.get("script_name")), ("Exit code", execution.get("exit_code")),
#         ("Duration seconds", execution.get("duration_seconds")), ("Dry run", execution.get("dry_run")),
#         ("Standard output", execution.get("stdout")), ("Standard error", execution.get("stderr")),
#         ("Error", execution.get("error")),
#     ], "Script execution")


# def render_password_actions(token: str, manager_email: str) -> None:
#     status_key = f"email_status_{token}"
#     st.session_state.setdefault(status_key, None)
#     can_email = bool(manager_email) and manager_email != "Not Available" and email_is_configured()
#     left, right = st.columns(2)
#     if left.button("Send Email To Manager", key=f"send_{token}", disabled=not can_email, width="stretch"):
#         with st.spinner("Sending email..."):
#             sent, message, recipient = send_password_to_manager(token)
#         st.session_state[status_key] = {"sent": sent, "message": message, "recipient": recipient}
#     ok, filename, content, message = build_password_download(token)
#     if ok:
#         right.download_button("Download Password TXT", data=content, file_name=filename, mime="text/plain", key=f"dl_{token}", width="stretch")
#     else:
#         right.button("Download Password TXT", key=f"dl_disabled_{token}", disabled=True, width="stretch"); st.caption(message)
#     status = st.session_state.get(status_key)
#     if status is None: st.caption("Email status: Not Sent")
#     elif status["sent"]: st.success(f"Email status: Sent Successfully to {status['recipient']}")
#     else: st.error(f"Email status: Failed. {status['message']}")


# def render_password_reset_actions(result: Dict[str, Any]) -> None:
#     st.success("Password Reset Successful")
#     manager_name = result.get("manager_name") or "Not Available"
#     manager_email = result.get("manager_email") or "Not Available"
#     show_table([
#         ("Username", result.get("user_name") or result.get("user_principal_name")),
#         ("Employee name", result.get("employee_name")),
#         ("Temporary password", result.get("masked_password") or "Not Available"),
#         ("Manager", manager_name), ("Manager email", manager_email),
#     ], "Password reset result")
#     token = result.get("password_token")
#     if not token:
#         st.warning("The password is no longer retrievable for this reset. Run the reset again."); return
#     render_password_actions(token, manager_email)


# def render_user_details(user: dict[str, Any], backend: Any = None) -> None:
#     st.markdown("### User details")
#     show_table([
#         ("Name", _ci_get(user, "Name")), ("Display name", _ci_get(user, "DisplayName")),
#         ("SAM account name", _ci_get(user, "SamAccountName")),
#         ("Mail", _ci_get(user, "Mail", "Email")),
#         ("User principal name", _ci_get(user, "UserPrincipalName")),
#         ("Mobile phone", _ci_get(user, "MobilePhone")),
#         ("Description", _ci_get(user, "Description")),
#         ("Department", _ci_get(user, "Department")),
#     ], "Identity and contact")

#     enabled = _optional_boolean(user, "Enabled", "AccountEnabled")
#     locked = _optional_boolean(user, "LockedOut")
#     expired = _optional_boolean(user, "PasswordExpired")
#     never_expires = _optional_boolean(user, "PasswordNeverExpires")

#     c1, c2, c3, c4 = st.columns(4)
#     with c1:
#         if enabled is True: _status_card("Enabled", "Enabled", "ok", "Sign-in is enabled.")
#         elif enabled is False: _status_card("Enabled", "Disabled", "bad", "Sign-in is blocked.")
#         else: _status_card("Enabled", "Unavailable", "unknown", "Account status was not returned.")
#     with c2:
#         if locked is True: _status_card("Locked out", "Locked", "bad", "The account currently has a lockout.")
#         elif locked is False: _status_card("Locked out", "Not locked", "ok", "No current lockout was reported.")
#         else: _status_card("Locked out", "Unavailable", "unknown", "Use script for current AD lockout status.")
#     with c3:
#         if expired is True: _status_card("Password expired", "Yes", "bad", "A password change may be required.")
#         elif expired is False: _status_card("Password expired", "No", "ok", "The password was not reported as expired.")
#         else: _status_card("Password expired", "Unavailable", "unknown", "Use script for calculated AD status.")
#     with c4:
#         if never_expires is True: _status_card("Password never expires", "Yes", "bad", "Review this policy exception.")
#         elif never_expires is False: _status_card("Password never expires", "No", "ok", "Password expiration applies.")
#         else: _status_card("Password never expires", "Unavailable", "unknown", "Password policy was not returned.")

#     if locked is None or expired is None:
#         st.markdown(
#             '<div class="directory-information"><strong>Additional Active Directory details available</strong><br>'
#             'Some current on-premises values are not exposed by Microsoft Entra. Run the same lookup normally '
#             'or add <strong>using script</strong> to retrieve current lockout status, bad-password count, calculated '
#             'password-expired state, canonical name, primary group, and exact nested-group inheritance.</div>',
#             unsafe_allow_html=True,
#         )

#     show_table([
#         ("Password last set", _ci_get(user, "PasswordLastSet")),
#         ("Bad password count", _ci_get(user, "BadPasswordCount")),
#         ("Distinguished name", _ci_get(user, "DistinguishedName")),
#         ("Canonical name", _ci_get(user, "CanonicalName")),
#         ("When created", _ci_get(user, "WhenCreated")),
#         ("Manager name", _ci_get(user, "ManagerName", "ManagerDisplayName")),
#         ("Manager email", _ci_get(user, "ManagerEmail", "ManagerMail", "ManagerUserPrincipalName")),
#     ], "Account and manager")

#     primary = _ci_get(user, "PrimaryGroupName")
#     direct = _normalise_group_rows(_ci_get(user, "DirectGroups", default=[]))
#     nested = _normalise_group_rows(_ci_get(user, "NestedGroups", default=[]))
#     effective = _normalise_group_rows(_ci_get(user, "EffectiveGroups", default=[]))
#     st.markdown("### Group memberships")
#     m1, m2, m3, m4 = st.columns(4)
#     m1.metric("Primary group", primary or "Unavailable")
#     m2.metric("Direct groups", len(direct)); m3.metric("Nested groups", len(nested))
#     m4.metric("Effective groups", len(effective) if effective else len(direct) + len(nested))
#     direct_tab, nested_tab, effective_tab = st.tabs(["Direct groups", "Nested groups", "Effective groups"])
#     with direct_tab:
#         if direct:
#             st.dataframe(
#                 _group_frame(direct, nested=False),
#                 hide_index=True,
#                 width="stretch",
#             )
#         else:
#             st.info("No direct group memberships were returned.")

#     with nested_tab:
#         if nested:
#             st.dataframe(
#                 _group_frame(nested, nested=True),
#                 hide_index=True,
#                 width="stretch",
#             )
#             if str(backend).strip().casefold() == "api":
#                 st.caption(
#                     "Microsoft Entra returns transitive membership, but "
#                     "exact inheritance may require the script lookup."
#                 )
#         else:
#             st.info("No nested group memberships were returned.")

#     with effective_tab:
#         shown_groups = effective or direct + nested
#         if shown_groups:
#             st.dataframe(
#                 _group_frame(shown_groups, nested=False),
#                 hide_index=True,
#                 width="stretch",
#             )
#         else:
#             st.info("No effective group memberships were returned.")


# def render_generic_result(result: Dict[str, Any]) -> None:
#     execution = result.get("execution"); user_record = result.get("user")
#     excluded = {"execution", "user", "new_password", "temporary_password", "_transient_password", "report", "report_markdown", "backend"}
#     rows = flatten_rows(user_record if isinstance(user_record, dict) else result, excluded)
#     show_table(rows, "Result")
#     if isinstance(execution, dict):
#         with st.expander("Execution details", expanded=False): render_script_execution(execution)


# def render_result(intent: str, result: Dict[str, Any]) -> None:
#     if intent == "patch_report":
#         render_patch_report(result)
#         return
#     if intent == "failed_login_investigation":
#         report = result.get("report")
#         if isinstance(report, dict): render_investigation_report(report)
#         else: st.warning("The investigation completed without a structured report payload.")
#         return
#     if intent == "password_reset" and result.get("password_token"):
#         render_password_reset_actions(result); return
#     if intent == "get_user_details":
#         record = result.get("user")
#         render_user_details(record if isinstance(record, dict) else result, result.get("backend")); return
#     render_generic_result(result)


# def render_operation_summary(response: Dict[str, Any]) -> None:
#     intent = str(response.get("intent") or "Identity operation")
#     metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
#     if intent in {"patch_report", "patch_scan"}:
#         target = metadata.get("device_name") or "Ivanti patch fleet"
#     elif intent == "patch_ticket":
#         target = metadata.get("device_name") or "Patch remediation"
#     else:
#         target = metadata.get("email") or metadata.get("username") or metadata.get("user_id") or "Unknown target"
#     if response.get("confirmation_required"): status, css = "Confirmation required", "warning"
#     elif response.get("success") is True: status, css = "Completed", "success"
#     elif response.get("success") is False: status, css = "Failed", "failure"
#     else: status, css = "Submitted", ""
#     st.markdown(
#         f'<div class="operation-card {css}"><div class="operation-label">Current operation</div>'
#         f'<div class="operation-title">{html.escape(intent.replace("_", " ").title())}</div>'
#         f'<div class="operation-meta"><strong>Target:</strong> {html.escape(str(target))} &nbsp; | &nbsp; '
#         f'<strong>Status:</strong> {html.escape(status)}</div></div>', unsafe_allow_html=True)


# def render_response(response: Dict[str, Any]) -> None:
#     render_operation_summary(response)
#     intent = str(response.get("intent") or "")
#     tool_result = response.get("tool_result")
#     if isinstance(tool_result, dict):
#         result = tool_result.get("result")
#         if isinstance(result, dict): render_result(intent, result)
#         elif response.get("success") is False: st.error(response.get("error") or response.get("message") or "The operation failed.")
#         elif response.get("message"): st.info(response["message"])
#     elif response.get("confirmation_required"):
#         st.info(response.get("confirmation_prompt") or "Approval is required before this operation can continue.")
#     elif response.get("clarification_required"):
#         st.warning(response.get("clarification_question") or response.get("message") or "More information is required.")
#     elif response.get("success") is False:
#         st.error(response.get("error") or response.get("message") or "The operation failed.")
#     elif response.get("message"): st.info(response["message"])
#     with st.expander("Raw response (JSON)", expanded=False):
#         st.json(redact_sensitive_history(copy.deepcopy(response)))

# # Confirmation and conversation

# def set_pending_confirmation(response: Dict[str, Any], query: str) -> None:
#     if response.get("confirmation_required"):
#         st.session_state.pending_confirmation = {
#             "query": query, "request_id": response.get("request_id"),
#             "correlation_id": response.get("correlation_id"),
#             "intent": response.get("intent"), "prompt": response.get("confirmation_prompt"),
#         }
#     else: st.session_state.pending_confirmation = None


# def append_conversation(role: str, content: Any, timestamp: str) -> None:
#     st.session_state.conversation.append({"role": role, "content": redact_sensitive_history(copy.deepcopy(content)), "time": timestamp})


# def execute_and_render(query: str, *, confirmed: bool = False, request_id: str | None = None, correlation_id: str | None = None, add_user_turn: bool = True) -> Dict[str, Any]:
#     timestamp = datetime.now().strftime("%H:%M:%S")
#     access = st.session_state.get("app_user_access")
#     requester_id = access.get("user_id") if isinstance(access, dict) else None
#     if add_user_turn:
#         with st.chat_message("user"): st.write(query)
#         append_conversation("user", query, timestamp)
#     with st.chat_message("assistant"):
#         with st.spinner("Checking and running the operation..."):
#             response = get_service().run_query(query, confirmed=confirmed, request_id=request_id, correlation_id=correlation_id, requester_id=requester_id)
#         register_dashboard_secret(response); render_response(response)
#     append_conversation("assistant", response, timestamp); set_pending_confirmation(response, query); return response


# def cancel_pending_confirmation() -> None:
#     pending = st.session_state.pending_confirmation; st.session_state.pending_confirmation = None
#     response = {
#         "success": False, "cancelled": True,
#         "request_id": pending.get("request_id") if isinstance(pending, dict) else None,
#         "correlation_id": pending.get("correlation_id") if isinstance(pending, dict) else None,
#         "intent": pending.get("intent") if isinstance(pending, dict) else None,
#         "message": "Operation cancelled. No changes were made.", "error": None,
#     }
#     append_conversation("assistant", response, datetime.now().strftime("%H:%M:%S")); st.rerun()


# def render_confirmation_controls() -> None:
#     pending = st.session_state.pending_confirmation
#     if not isinstance(pending, dict): return
#     with st.container(border=True):
#         st.markdown("**Approval required**"); st.write(pending.get("prompt") or "Confirm this operation before continuing.")
#         left, right = st.columns(2)
#         if left.button("Confirm and proceed", type="primary", width="stretch"):
#             st.session_state.pending_confirmation = None
#             execute_and_render(pending["query"], confirmed=True, request_id=pending.get("request_id"), correlation_id=pending.get("correlation_id"), add_user_turn=False); st.rerun()
#         if right.button("Cancel", width="stretch"): cancel_pending_confirmation()

# # Sidebar

# def safe_conversation_download() -> str:
#     return json.dumps(redact_sensitive_history(copy.deepcopy(st.session_state.conversation)), indent=2, ensure_ascii=False, default=str)


# def render_sidebar() -> None:
#     with st.sidebar:
#         access = st.session_state.get("app_user_access")
#         user_id = access.get("user_id") if isinstance(access, dict) else None
#         st.markdown('<div class="sidebar-section-label">Recent requests</div>', unsafe_allow_html=True)
#         if user_id:
#             history = get_user_request_history(user_id)
#             if history:
#                 for item in history:
#                     requested_at = item.get("requested_at")
#                     if isinstance(requested_at, datetime): requested_at = requested_at.strftime("%b %d, %H:%M")
#                     label = item["request"].strip() or item["operation"]
#                     st.markdown(f'<div class="sidebar-request">{html.escape(label[:72])}<br><small>{html.escape(item["status"].title())} · {html.escape(str(requested_at or "Recently"))}</small></div>', unsafe_allow_html=True)
#             else: st.caption("No requests recorded yet.")
#         elif st.session_state.conversation:
#             recent = [turn for turn in reversed(st.session_state.conversation) if turn.get("role") == "user"][:4]
#             for turn in recent:
#                 st.markdown(f'<div class="sidebar-request">{html.escape(str(turn.get("content", ""))[:72])}<br><small>{html.escape(str(turn.get("time", "")))}</small></div>', unsafe_allow_html=True)
#         else:
#             st.caption("Your recent activity will appear here.")
#         with st.expander("Tools & examples"):
#             status = get_config_status()
#             st.caption("Example requests")
#             for index, example in enumerate(EXAMPLES):
#                 if st.button(example, key=f"example_{index}", width="stretch"):
#                     st.session_state.active_page = "Assistant"
#                     st.session_state.queued_query = example
#                     st.rerun()
#             st.divider()
#             st.caption("System status")
#             st.caption(f"LangGraph · {'Active' if status.get('orchestration_engine') == 'langgraph' else 'Unavailable'}")
#             st.caption(f"Operation audit · {'Enabled' if status.get('operation_audit_enabled') else 'Unknown'}")
#             if st.button("Test Ollama connection", width="stretch"):
#                 connected, message = check_ollama(); st.session_state.ollama_check_result = {"connected": connected, "message": message}
#             if isinstance(st.session_state.ollama_check_result, dict):
#                 st.caption(st.session_state.ollama_check_result.get("message", ""))
#             st.caption(f"Logs: {LOG_FILE}")
#         if st.session_state.conversation:
#             if st.button("＋  New conversation", width="stretch"):
#                 st.session_state.conversation = []; st.session_state.pending_confirmation = None; st.rerun()
#             st.download_button("Download as JSON", data=safe_conversation_download(), file_name="techadmin_session.json", mime="application/json", width="stretch")


# def render_recent_operations() -> None:
#     operations = []
#     for turn in reversed(st.session_state.conversation):
#         if turn.get("role") != "assistant" or not isinstance(turn.get("content"), dict): continue
#         response = turn["content"]
#         metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
#         status = "Awaiting confirmation" if response.get("confirmation_required") else "Cancelled" if response.get("cancelled") else "Completed" if response.get("success") is True else "Failed"
#         operations.append({
#             "Operation": str(response.get("intent") or "Identity operation").replace("_", " ").title(),
#             "Target": (metadata.get("device_name") or ("Ivanti patch fleet" if response.get("intent") in {"patch_report", "patch_scan"} else None) or metadata.get("email") or metadata.get("username") or "Unknown target"),
#             "Status": status, "Time": turn.get("time", ""),
#         })
#         if len(operations) == 5: break
#     if operations:
#         st.markdown("#### Recent operations"); st.dataframe(pd.DataFrame(operations), hide_index=True, width="stretch")


# def render_command_center(claims: dict[str, Any]) -> None:
#     if st.session_state.conversation: return
#     name = claims.get("name") or claims.get("preferred_username") or claims.get("email") or "TechAdmin"
#     hour = datetime.now().hour
#     greeting = "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
#     heading, new_chat = st.columns([5, 1.25], vertical_alignment="center")
#     heading.markdown(f'<div class="welcome-heading">{greeting}, {html.escape(str(name).split()[0])}</div><div class="welcome-subtitle">Here’s the result from your latest identity request.</div>', unsafe_allow_html=True)
#     if new_chat.button("＋  New conversation", key="new_conversation_main", width="stretch"):
#         st.session_state.conversation = []; st.session_state.pending_confirmation = None; st.rerun()
#     st.markdown("<hr>", unsafe_allow_html=True)
#     st.markdown('<div class="tech-panel"><strong>How can I help with identity operations?</strong><span>Look up an employee, reset a password, manage access, or investigate failed sign-ins. Sensitive actions pause for confirmation.</span></div>', unsafe_allow_html=True)
#     quick_queries = (EXAMPLES[0], EXAMPLES[3], EXAMPLES[8])
#     quick_buttons = st.columns(3)
#     for index, example in enumerate(quick_queries):
#         short_label = ("⌕  Look up a user", "↻  Reset a password", "◷  Investigate sign-ins")[index]
#         if quick_buttons[index].button(short_label, key=f"quick_action_{index}", width="stretch"):
#             st.session_state.queued_query = example
#             st.rerun()


# def render_history_page() -> None:
#     st.markdown('<div class="welcome-heading">Request history</div><div class="welcome-subtitle">Review your recent, fully audited identity operations.</div><hr>', unsafe_allow_html=True)
#     access = st.session_state.get("app_user_access")
#     user_id = access.get("user_id") if isinstance(access, dict) else None
#     history = get_user_request_history(user_id) if user_id else []
#     if not history:
#         st.info("No audited requests are available for this account yet.")
#         return
#     st.dataframe(pd.DataFrame([{
#         "Request": item.get("request"), "Operation": item.get("operation"),
#         "Target": item.get("target"), "Status": str(item.get("status", "")).replace("_", " ").title(),
#         "Requested": item.get("requested_at"),
#     } for item in history]), hide_index=True, width="stretch")


# def render_directory_page() -> None:
#     st.markdown('<div class="welcome-heading">Directory</div><div class="welcome-subtitle">Find a user profile and review account health and access.</div><hr>', unsafe_allow_html=True)
#     with st.container(border=True):
#         st.markdown("#### Search the identity directory")
#         with st.form("directory_search_form"):
#             target = st.text_input("Work email or username", placeholder="name@coforge.com")
#             submitted = st.form_submit_button("Search directory", type="primary", width="stretch")
#         if submitted:
#             if not target.strip():
#                 st.warning("Enter an email address or username to search.")
#             else:
#                 st.session_state.active_page = "Assistant"
#                 st.session_state.queued_query = f"Get user details for {target.strip()}"
#                 st.rerun()
#     st.caption("Directory lookups are read-only and are recorded in the operation audit.")


# def main() -> None:
#     init_state(); claims = require_authentication(); render_sidebar()
#     st.markdown('<div class="topbar">Identity assistant<small>● &nbsp; All systems operational</small></div>', unsafe_allow_html=True)
#     active_page = st.session_state.get("active_page", "Assistant")
#     if active_page == "Request history":
#         render_history_page()
#         return
#     if active_page == "Directory":
#         render_directory_page()
#         return
#     _, content, _ = st.columns([1, 5, 1], gap="small")
#     with content:
#         render_command_center(claims)
#         for turn in st.session_state.conversation:
#             with st.chat_message(turn["role"]):
#                 if turn["role"] == "user": st.write(turn["content"])
#                 elif isinstance(turn["content"], dict): render_response(turn["content"])
#         query = st.session_state.queued_query or st.chat_input("Ask TechAdmin to manage an identity…")
#         st.session_state.queued_query = None
#         if query:
#             pending = st.session_state.pending_confirmation
#             answer = query.strip().casefold().rstrip(".! ")
#             if isinstance(pending, dict) and answer in YES_WORDS:
#                 append_conversation("user", query, datetime.now().strftime("%H:%M:%S")); st.session_state.pending_confirmation = None
#                 execute_and_render(pending["query"], confirmed=True, request_id=pending.get("request_id"), correlation_id=pending.get("correlation_id"), add_user_turn=False)
#             elif isinstance(pending, dict) and answer in NO_WORDS:
#                 append_conversation("user", query, datetime.now().strftime("%H:%M:%S")); cancel_pending_confirmation()
#             else: execute_and_render(query)
#             st.rerun()
#         render_confirmation_controls()


# if __name__ == "__main__":
#     main()

"""TechAdmin Streamlit UI.

Identity-operations copilot with Microsoft SSO,
app_users authorization, LangGraph execution, confirmation handling, secure
password delivery and request history.

Layout
    * Split-screen sign-in (Microsoft SSO)
    * Navy sidebar: agent navigation, request history, signed-in user
    * Top bar: page title, system status, help / notifications popovers
    * Assistant: chat with rich result cards (directory record, password reset,
      approval, investigation report), contextual suggestion chips, composer

Run from the project root:
    streamlit run StreamlitApp/app.py

UI preview without Ollama / Graph / PostgreSQL (sample data, relaxed sign-in):
    TECHADMIN_UI_PREVIEW=true streamlit run StreamlitApp/app.py
"""
from __future__ import annotations

import copy
import hmac
import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from html import escape
from pathlib import Path
from typing import Any, Callable, Dict, Iterable

import streamlit as st

OPERATIONS_ICON_PATH = Path(__file__).resolve().parent.parent / "Logo" / "icons8-operations-60.png"

st.set_page_config(
    page_title="TechAdmin AI",
    page_icon=str(OPERATIONS_ICON_PATH),
    layout="wide",
    initial_sidebar_state="expanded",
)


def _env_flag(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().casefold() in {"1", "true", "yes", "on"}


PREVIEW_MODE = _env_flag("TECHADMIN_UI_PREVIEW")

if PREVIEW_MODE:
    import preview_backend as _preview

    FlowService = _preview.PreviewFlowService
    LOG_FILE = _preview.LOG_FILE
    build_password_download = _preview.build_password_download
    check_ollama = _preview.check_ollama
    email_is_configured = _preview.email_is_configured
    get_config_status = _preview.get_config_status
    send_password_to_manager = _preview.send_password_to_manager
    get_user_request_history = _preview.get_user_request_history
    authorize_claims = None

    def extract_display_name(claims: dict[str, Any]) -> str:
        return str(claims.get("name") or claims.get("preferred_username") or "").strip()
else:
    from flow_service import (  # noqa: E402
        LOG_FILE,
        FlowService,
        build_password_download,
        check_ollama,
        email_is_configured,
        get_config_status,
        send_password_to_manager,
    )
    from App.db.login_authorization import authorize_claims, extract_display_name  # noqa: E402
    from App.db.operation_audit import get_user_request_history  # noqa: E402
    from App.services.patch.security_history import get_security_query_history  # noqa: E402

from investigation_report_ui import (
    render_investigation_report,
)  # noqa: E402

if PREVIEW_MODE:
    render_patch_agent_page = None
    PatchSemanticInterpreter = None
else:
    from patch_agent_page import (
        render_patch_agent_page,
    )  # noqa: E402

    from App.services.patch.semantic import (
        PatchSemanticInterpreter,
    )  # noqa: E402
from ui_theme import (  # noqa: E402
    coforge_wordmark,
    icon_alert,
    icon_check_circle,
    icon_key,
    icon_shield,
    icon_shield_alert,
    icon_shield_check,
    icon_sparkle,
    icon_x_circle,
    inject_app_css,
    inject_base_css,
    inject_login_css,
    operations_icon,
)


def enforce_https_origin() -> None:
    public_url = os.getenv("TECHADMIN_PUBLIC_URL", "https://techadmin.coforge.com").strip()
    if not public_url:
        return
    st.markdown(
        f"""
        <script>
        (() => {{
            try {{
                const publicUrl = new URL("{public_url}");
                const current = new URL(window.location.href);
                if (current.protocol === "http:" && current.hostname === publicUrl.hostname) {{
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
inject_base_css()


def html_block(markup: str) -> None:
    st.markdown(markup, unsafe_allow_html=True)

def inject_workspace_layout_css() -> None:
    st.markdown(
        """
        <style>
            .st-key-content,
            .st-key-security_content {
                max-width: min(
                    1000px,
                    100%
                ) !important;
                width: 100%;
                margin-left: auto;
                margin-right: auto;
            }

            .st-key-history_sidebar_scroll,
            .st-key-history_page_scroll {
                overscroll-behavior: contain;
                scrollbar-gutter: stable;
            }

            .st-key-history_page_scroll {
                width: 100%;
            }

            .st-key-history_sidebar_scroll
           ::-webkit-scrollbar,
            .st-key-history_page_scroll
           ::-webkit-scrollbar {
                width: 7px;
            }

            .st-key-history_sidebar_scroll
           ::-webkit-scrollbar-thumb,
            .st-key-history_page_scroll
           ::-webkit-scrollbar-thumb {
                background:
                    rgba(120, 135, 155, .45);
                border-radius: 8px;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
# =============================================================================
# Constants
# =============================================================================

EXAMPLES = [
    "Get user details for MigrationTest2@Coforge.com",
    "Get user details for MigrationTest2@Coforge.com via script",
    "Get user details for MigrationTest2@Coforge.com on Entra",
    "Reset password for MigrationTest2@Coforge.com",
    "Unlock account for MigrationTest2@Coforge.com",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
    "Investigate failed logins for MigrationTest2@Coforge.com in the last 24 hours",
    "Investigate account lockout for MigrationTest3@Coforge.com in the last 7 days",
]
YES_WORDS = {"yes", "y", "confirm", "confirmed", "proceed", "approve", "approved", "ok", "okay"}
NO_WORDS = {"no", "n", "cancel", "stop", "abort", "nevermind"}
SENSITIVE_HISTORY_KEYS = {
    "new_password", "temporary_password", "password", "initial_password",
    "domain_password", "admin_password", "client_secret", "access_token",
    "refresh_token", "_dashboard_secret", "_transient_password",
}
INTENT_TITLES = {
    "get_user_details": "Get user details",
    "patch_report": "Patch report",
    "password_reset": "Reset password",
    "account_unlock": "Unlock account",
    "unlock_account": "Unlock account",
    "failed_login_investigation": "Failed sign-in investigation",
    "add_user_to_group": "Add to group",
    "remove_user_from_group": "Remove from group",
    "create_user": "Create user",
    "delete_user": "Delete user",
    "create_group": "Create group",
}
ROLE_TITLES = {"helpdesk": "Helpdesk operator", "admin": "Operations admin", "operations_admin": "Operations admin"}
PAGES = [
    ("assistant", "Identity Agent", ":material/smart_toy:"),
    ("security", "Security Agent", ":material/security:"),
    ("history", "Your History", ":material/history:"),
]


# =============================================================================
# Small helpers
# =============================================================================

def display_text(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def intent_title(intent: Any) -> str:
    key = str(intent or "").strip()
    return INTENT_TITLES.get(key) or (key.replace("_", " ").capitalize() if key else "Identity request")


def initials(name: str) -> str:
    text = str(name or "").split("@", 1)[0]
    text = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", text)
    parts = [p for p in re.split(r"[\s._\-]+", text) if p[:1].isalpha()]
    if not parts:
        return "TA"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def first_name(name: str) -> str:
    text = str(name or "").strip()
    if "@" in text:
        text = text.split("@", 1)[0].replace(".", " ")
    word = (text.split() or ["there"])[0] if text else "there"
    return word[:1].upper() + word[1:]


def time_ago(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return value
    if not isinstance(value, datetime):
        return str(value)
    if value.tzinfo is None:
        value = value.astimezone()  # naive values are treated as server-local time
    seconds = max(0, int((datetime.now(timezone.utc) - value.astimezone(timezone.utc)).total_seconds()))
    if seconds < 45:
        return "just now"
    if seconds < 3600:
        return f"{max(1, seconds // 60)} min ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 172800:
        return "Yesterday"
    return value.astimezone().strftime("%d %b")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def greeting() -> str:
    hour = datetime.now().hour
    return "Good morning" if hour < 11 else "Good afternoon" if hour < 17 else "Good evening"


def _ci_get(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    if not isinstance(data, dict):
        return default
    normalized = {str(key).replace("_", "").casefold(): value for key, value in data.items()}
    for name in names:
        key = name.replace("_", "").casefold()
        if key in normalized and normalized[key] not in (None, ""):
            return normalized[key]
    return default


def _optional_boolean(data: dict[str, Any], *field_names: str) -> bool | None:
    value = _ci_get(data, *field_names, default=None)
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in {0, 1}:
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "yes", "1", "enabled", "locked", "expired"}:
            return True
        if normalized in {"false", "no", "0", "disabled", "not locked", "not expired"}:
            return False
    return None


def redact_sensitive_history(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).strip().casefold()
            if normalized in SENSITIVE_HISTORY_KEYS:
                if normalized != "_dashboard_secret":
                    cleaned[key] = "[redacted]"
                continue
            cleaned[key] = redact_sensitive_history(item)
        return cleaned
    if isinstance(value, list):
        return [redact_sensitive_history(item) for item in value]
    return value


def response_target(response: Dict[str, Any]) -> str:
    metadata = response.get("metadata") if isinstance(response.get("metadata"), dict) else {}
    return str(metadata.get("device_name") or metadata.get("email") or metadata.get("username") or metadata.get("user_id") or "")


def kv_grid(rows: Iterable[tuple[str, Any]], *, single: bool = False, keep_empty: bool = False) -> str:
    cells = []
    for label, value in rows:
        if value in (None, "") and not keep_empty:
            continue
        if isinstance(value, (dict, list)):
            value = json.dumps(value, ensure_ascii=False, default=str)
        cells.append(
            f'<div class="row"><span class="k">{escape(str(label))}</span>'
            f'<span class="v">{escape(display_text(value))}</span></div>'
        )
    if not cells:
        return ""
    return f'<div class="ta-kv{" single" if single else ""}">{"".join(cells)}</div>'


def card_head(*, avatar: str, kicker: str, title: str, sub: str = "", tone: str = "ok", avatar_html: str | None = None) -> str:
    av = avatar_html or f'<div class="ta-avatar lg">{escape(avatar)}</div>'
    tone_cls = "" if tone == "ok" else tone
    return (
        f'<div class="ta-card-head">{av}<div style="min-width:0">'
        f'<div class="ta-kicker {tone_cls}"><span class="ta-dot"></span>{escape(kicker)}</div>'
        f'<div class="name">{escape(title)}</div>'
        + (f'<div class="sub">{escape(sub)}</div>' if sub else "")
        + "</div></div>"
    )


def card_foot(left: str, right: str = "", *, icon: str | None = None) -> str:
    return (
        f'<div class="ta-card-foot"><span class="l">{icon or icon_shield(14)}{escape(left)}</span>'
        f'<span>{escape(right)}</span></div>'
    )


def elapsed_text(response: Dict[str, Any]) -> str:
    elapsed = response.get("_ui_elapsed")
    return f"Completed in {elapsed:.1f}s" if isinstance(elapsed, (int, float)) else ""


# =============================================================================
# Authentication (behaviour unchanged from the previous UI)
# =============================================================================

def microsoft_user_is_logged_in() -> bool:
    try:
        return bool(st.user.is_logged_in)
    except (AttributeError, RuntimeError, TypeError):
        return False


def clear_local_authentication_state() -> None:
    st.session_state.pop("local_authenticated_user", None)
    st.session_state.pop("app_user_access", None)


HERO_HTML = f"""
<div class="ta-hero">
  <div class="ring r1"></div><div class="ring r2"></div><div class="ring r3"></div>
    <div class="ta-hero-brand">{coforge_wordmark(40)}</div>
  <div class="content">
        <div class="ta-hero-product">{operations_icon(42)}<div><div class="ta-hero-product-name"><span>Tech</span>Admin</div>
        <div class="ta-hero-product-subtitle">Autonomous Assistant</div></div></div>
        <h1>Intelligent operations,<br>made effortless.</h1>
        <p class="lead">We’re agentifying identity operations—taking the mundane, repetitive work off your plate with secure, auditable assistance.</p>
  </div>
    <div class="ta-hero-footer"><span>Plan</span><i></i><span>Secure</span><i></i><span>Implement</span><i></i><span>Deliver</span></div>
</div>
"""

MS_LOGO = '<span class="ta-ms-logo"><i style="background:#F25022"></i><i style="background:#7FBA00"></i><i style="background:#00A4EF"></i><i style="background:#FFB900"></i></span>'


def render_auth_shell(body: Callable[[], None]) -> None:
    """Split-screen frame shared by sign-in, denied and incomplete-session screens."""
    inject_login_css()
    st.markdown("""
        <style>
            .ta-hero-brand { position:relative; z-index:1; }
            .ta-hero .content { z-index:1; }
            .ta-hero-product { display:flex; align-items:center; gap:14px; }
            .ta-hero-product-name { color:#fff; font-size:24px; line-height:1.1; font-weight:600; letter-spacing:-.02em; }
            .ta-hero-product-name span { color:#EF5B3F; }
            .ta-hero-product-subtitle { color:#B9C3D1; font-size:13.5px; margin-top:3px; }
            .ta-hero h1 { margin-top:26px; }
            .ta-hero p.lead { max-width:460px; }
            .ta-hero-footer { position:relative; z-index:1; display:flex; flex-wrap:wrap; align-items:center; gap:12px;
                color:#C8D1DD; font-size:12.5px; font-weight:500; letter-spacing:.02em; }
            .ta-hero-footer i { width:1px; height:16px; background:#EF5B3F; display:inline-block; }
            .ta-login-head h2 { margin-top:0; }
        </style>
        """, unsafe_allow_html=True)
    with st.container(key="login_shell"):
        left, right = st.columns([0.44, 0.56], gap="small")
        with left:
            html_block(HERO_HTML)
        with right:
            with st.container(key="login_form"):
                body()
                html_block('<div class="ta-login-legal">Authorized users only · Coforge Global IT</div>')
    st.stop()


def _login_heading(title: str = "Sign in to TechAdmin", sub: str = "Please use your Coforge SSO ID.") -> None:
    html_block(
        f'<div class="ta-login-head"><h2>{escape(title)}</h2><p>{escape(sub)}</p></div>'
    )


def _microsoft_sign_in_button(key: str = "microsoft_sign_in", label: str = "Sign in with Microsoft") -> None:
    html_block(
        f'<div class="ta-sso-card">{MS_LOGO}<div><strong>Continue with your work account</strong>'
        f'<span>Use your Coforge Microsoft credentials.</span></div></div>'
    )
    if st.button(label, type="primary", width="stretch", key=key):
        try:
            st.login()
        except Exception as exc:  # missing [auth] secrets, provider errors
            st.error(f"Microsoft sign-in is not available on this server ({type(exc).__name__}). "
                     "Check the [auth] section of .streamlit/secrets.toml.")
    html_block('<div class="ta-login-note">Unable to access? Contact your IT service desk.</div>')


def render_sign_in_screen(*, microsoft_message: str | None = None) -> None:
    def body() -> None:
        _login_heading()
        if microsoft_message:
            st.warning(microsoft_message)
        sso_tab, local_tab = st.tabs(["Microsoft SSO", "Local authentication"])
        with sso_tab:
            _microsoft_sign_in_button()
        with local_tab:
            render_local_login()

    render_auth_shell(body)


def render_local_login() -> None:
    enabled = PREVIEW_MODE or _env_flag("TECHADMIN_LOCAL_LOGIN_ENABLED")
    if not enabled:
        html_block('<div class="ta-note" style="margin-top:8px">Local authentication is disabled on this server. '
                   'Use Microsoft SSO, or ask an administrator to enable it for local testing.</div>')
        return
    optional = " :gray[Optional for preview]" if PREVIEW_MODE else ""
    with st.form("local_login_form", clear_on_submit=False, border=False):
        username = st.text_input(
            f"Username{optional}", key="local_login_username",
            placeholder="No username required" if PREVIEW_MODE else "Enter your local username",
        )
        password = st.text_input(
            f"Password{optional}", type="password", key="local_login_password",
            placeholder="No password required" if PREVIEW_MODE else "Enter your password",
        )
        submitted = st.form_submit_button("Sign in securely", type="primary", width="stretch")
    html_block('<div class="ta-login-note">Unable to access? Contact your IT service desk.</div>')
    if not submitted:
        return
    if PREVIEW_MODE:
        name = username.strip() or "TechAdmin User"
        st.session_state.local_authenticated_user = {
            "name": name, "preferred_username": name, "auth_source": "local_test_account",
        }
        st.session_state.pop("app_user_access", None)
        st.rerun()
    expected_username = os.getenv("TECHADMIN_LOCAL_LOGIN_USERNAME", "TechAdminTestUser").strip()
    expected_password = os.getenv("TECHADMIN_LOCAL_LOGIN_PASSWORD", "")
    valid_username = hmac.compare_digest(username.strip().casefold(), expected_username.casefold())
    valid_password = bool(expected_password) and hmac.compare_digest(password, expected_password)
    if not (valid_username and valid_password):
        st.error("Invalid username or password.")
        return
    st.session_state.local_authenticated_user = {
        "name": expected_username, "preferred_username": expected_username,
        "auth_source": "local_test_account",
    }
    st.session_state.pop("app_user_access", None)
    st.rerun()


def enforce_app_user_access(claims: dict[str, Any]) -> None:
    if PREVIEW_MODE:
        st.session_state.app_user_access = _preview.authorize_preview(claims)
        return
    display_name = extract_display_name(claims)
    if not display_name:
        st.session_state.app_user_access = {
            "display_name": "", "allowed": True,
            "reason": "legacy_identity_without_display_name", "message": "",
            "user_principal_name": "", "user_id": "", "department": "",
        }
        return
    cached = st.session_state.get("app_user_access")
    if not (isinstance(cached, dict) and cached.get("display_name") == display_name):
        decision = authorize_claims(claims)
        cached = {
            "display_name": display_name, "allowed": decision.allowed,
            "reason": decision.reason, "message": decision.message,
            "user_principal_name": decision.user_principal_name,
            "user_id": decision.user_id, "department": decision.department,
        }
        st.session_state.app_user_access = cached
    if cached.get("allowed") is True:
        return

    def body() -> None:
        _login_heading("Access not granted", "Your identity was verified, but it isn't registered for TechAdmin.")
        html_block(
            f'<div class="ta-note bad">{escape(cached.get("message") or "This identity is not authorized to use TechAdmin.")}'
            f'<br><br>Signed in as <strong>{escape(display_name or "unknown")}</strong>. Access is granted only to active '
            f'users registered in the TechAdmin app_users directory.</div>'
        )
        st.write("")
        if claims.get("auth_source") == "local_test_account":
            if st.button("Return to sign in", key="denied_local_sign_out", width="stretch"):
                clear_local_authentication_state()
                st.rerun()
        elif st.button("Sign out", key="denied_microsoft_sign_out", width="stretch"):
            clear_local_authentication_state()
            st.logout()

    render_auth_shell(body)


def require_authentication() -> dict[str, Any]:
    local_user = st.session_state.get("local_authenticated_user")
    if isinstance(local_user, dict):
        enforce_app_user_access(local_user)
        return local_user
    if not microsoft_user_is_logged_in():
        render_sign_in_screen()
    claims = dict(st.user)
    claims.pop("is_logged_in", None)
    if not extract_display_name(claims):
        def body() -> None:
            _login_heading("Finish signing in", "The current Microsoft session does not contain a usable identity.")
            sso_tab, local_tab = st.tabs(["Microsoft SSO", "Local authentication"])
            with sso_tab:
                html_block('<div class="ta-note warn" style="margin:6px 0 16px">Sign out of the incomplete '
                           'Microsoft session, then sign in again.</div>')
                if st.button("Sign out and restart", type="primary", width="stretch", key="restart_microsoft_sign_in"):
                    clear_local_authentication_state()
                    st.logout()
            with local_tab:
                render_local_login()

        render_auth_shell(body)
    enforce_app_user_access(claims)
    return claims


# =============================================================================
# Service + state
# =============================================================================

@st.cache_resource(show_spinner="Starting TechAdmin...")
def get_service() -> Any:
    return FlowService()


def init_state() -> None:
    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    st.session_state.setdefault("pending_confirmation", None)
    st.session_state.setdefault("pending_run", None)
    st.session_state.setdefault("ollama_check_result", None)
    st.session_state.setdefault("page", "assistant")
    st.session_state.setdefault("history_filter", "")
    st.session_state.setdefault("quick_action", None)


def clear_conversation_state() -> None:
    """Reset conversation keys without leaving them absent on the next rerun."""
    st.session_state.conversation = []
    st.session_state.queued_query = None
    st.session_state.pending_confirmation = None
    st.session_state.pending_run = None
    st.session_state.quick_action = None


def access_info() -> dict[str, Any]:
    access = st.session_state.get("app_user_access")
    return access if isinstance(access, dict) else {}


def append_turn(role: str, content: Any, **extra: Any) -> None:
    turn = {"role": role, "content": redact_sensitive_history(copy.deepcopy(content)), "ts": now_iso()}
    turn.update(extra)
    st.session_state.conversation.append(turn)


def queue_run(query: str, *, confirmed: bool = False, request_id: str | None = None,
              correlation_id: str | None = None, add_user_turn: bool = True) -> None:
    """Record the user turn now; execute on the next script run so the UI updates first."""
    if add_user_turn:
        append_turn("user", query)
    st.session_state.pending_run = {
        "query": query, "confirmed": confirmed,
        "request_id": request_id, "correlation_id": correlation_id,
    }
    st.session_state.page = "assistant"


def execute_pending_run() -> None:
    run = st.session_state.pending_run
    if not isinstance(run, dict):
        return
    html_block(
        f'<div class="ta-asst-head"><div class="ta-icon-tile">{icon_sparkle(18, "#fff")}</div><div>'
        f'<div class="who">TechAdmin AI</div><div class="ta-working"><i></i><i></i><i></i>'
        f'<span>{"Running the approved operation" if run.get("confirmed") else "Checking and running your request"}…</span>'
        f'</div></div></div>'
    )
    requester_id = access_info().get("user_id") or None
    started = time.perf_counter()
    try:
        response = get_service().run_query(
            run["query"], confirmed=bool(run.get("confirmed")), request_id=run.get("request_id"),
            correlation_id=run.get("correlation_id"), requester_id=requester_id,
        )
    except Exception as exc:  # FlowService already contains errors; this is a last resort
        response = {"success": False, "intent": None, "metadata": {}, "error": type(exc).__name__,
                    "message": "An unexpected error occurred while processing the request."}
    response = response if isinstance(response, dict) else {"success": False, "message": "Invalid response."}
    response.pop("_dashboard_secret", None)
    response["_ui_elapsed"] = round(time.perf_counter() - started, 2)
    append_turn("assistant", response, query=run["query"])
    if response.get("confirmation_required"):
        st.session_state.pending_confirmation = {
            "query": run["query"], "request_id": response.get("request_id"),
            "correlation_id": response.get("correlation_id"), "intent": response.get("intent"),
            "prompt": response.get("confirmation_prompt"),
            "turn_index": len(st.session_state.conversation) - 1,
        }
    else:
        st.session_state.pending_confirmation = None
    st.session_state.pending_run = None
    st.rerun()


def _mark_approval(state: str) -> None:
    pending = st.session_state.pending_confirmation
    if isinstance(pending, dict):
        idx = pending.get("turn_index")
        conv = st.session_state.conversation
        if isinstance(idx, int) and 0 <= idx < len(conv):
            conv[idx]["approval_state"] = state


def approve_pending() -> None:
    pending = st.session_state.pending_confirmation
    if not isinstance(pending, dict):
        return
    _mark_approval("approved")
    st.session_state.pending_confirmation = None
    queue_run(pending["query"], confirmed=True, request_id=pending.get("request_id"),
              correlation_id=pending.get("correlation_id"), add_user_turn=False)


def cancel_pending_confirmation() -> None:
    pending = st.session_state.pending_confirmation
    _mark_approval("cancelled")
    st.session_state.pending_confirmation = None
    append_turn("assistant", {
        "success": False, "cancelled": True,
        "request_id": pending.get("request_id") if isinstance(pending, dict) else None,
        "correlation_id": pending.get("correlation_id") if isinstance(pending, dict) else None,
        "intent": pending.get("intent") if isinstance(pending, dict) else None,
        "message": "Operation cancelled. No changes were made.", "error": None,
    })
def handle_input(query: str) -> None:
    normalized_query = (
        query.strip()
        if isinstance(query, str)
        else ""
    )

    if not normalized_query:
        return

    current_page = st.session_state.get(
        "page",
        "assistant",
    )

    is_security_request = bool(
        not PREVIEW_MODE
        and PatchSemanticInterpreter is not None
        and PatchSemanticInterpreter.matches(
            normalized_query
        )
    )

    if (
        current_page == "assistant"
        and is_security_request
    ):
        st.session_state.security_redirect_query = (
            normalized_query
        )
        st.session_state.pending_run = None
        st.session_state.pending_confirmation = None
        st.session_state.page = "security"

        st.rerun()

    pending = st.session_state.pending_confirmation
    answer = normalized_query.casefold().rstrip(".!")

    if (
        isinstance(pending, dict)
        and answer in YES_WORDS
    ):
        append_turn(
            "user",
            normalized_query,
        )
        approve_pending()

    elif (
        isinstance(pending, dict)
        and answer in NO_WORDS
    ):
        append_turn(
            "user",
            normalized_query,
        )
        cancel_pending_confirmation()

    else:
        queue_run(normalized_query)

    st.rerun()
def new_conversation() -> None:
    st.session_state.conversation = []
    st.session_state.pending_confirmation = None
    st.session_state.pending_run = None
    st.session_state.page = "assistant"


# =============================================================================
# Result renderers
# =============================================================================

def _tile(label: str, value: str, tone: str, sub: str = "") -> str:
    icon = {"ok": icon_shield_check, "bad": icon_shield_alert, "warn": icon_shield_alert}.get(tone, icon_shield)(15)
    return (f'<div class="ta-tile {tone}"><div class="ic">{icon}</div><div style="min-width:0">'
            f'<div class="lb">{escape(label)}</div><div class="vl">{escape(value)}</div>'
            + (f'<div class="sb">{escape(sub)}</div>' if sub else "")
            + '</div></div>')


def _parse_datetime(value: Any) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone()  # naive script timestamps are server-local time


def _short_date(value: Any) -> str:
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).strftime("%d %b %Y")
    except ValueError:
        return str(value)


def password_expiry_label(user: dict[str, Any]) -> str:
    return "Password expired on" if _optional_boolean(user, "PasswordExpired") else "Password expires on"


def password_expiry_value(user: dict[str, Any]) -> str:
    if _optional_boolean(user, "PasswordNeverExpires"):
        return "Never expires"
    expiry = _ci_get(user, "PasswordExpiryDate")
    return _short_date(expiry) if expiry else "Not reported"


def user_status_tiles(user: dict[str, Any]) -> str:
    enabled = _optional_boolean(user, "Enabled", "AccountEnabled")
    locked = _optional_boolean(user, "LockedOut")
    expired = _optional_boolean(user, "PasswordExpired")
    password_never_expires = _optional_boolean(
        user, "PasswordNeverExpires", "password_never_expires"
    )
    expiry = _ci_get(user, "PasswordExpiryDate")
    expiry_at = _parse_datetime(expiry) if expiry else None
    if expiry_at and not expired and expiry_at <= datetime.now().astimezone():
        expired = True
    password_value = "Expired" if expired else "Active" if expired is False else "Unavailable"
    password_tone = "bad" if expired else "ok" if expired is False else "unk"
    password_sub = ""
    if expiry_at:
        days_left = (expiry_at - datetime.now().astimezone()).total_seconds() / 86400
        if expired:
            password_sub = f"Expired on {expiry_at.strftime('%d %b %Y')}"
        else:
            password_sub = f"Expires on {expiry_at.strftime('%d %b %Y')}"
            password_tone = "warn" if days_left <= 10 else "ok"
            if days_left <= 10:
                password_value = f"Expires in {max(0, int(days_left))} day{'s' if int(days_left) != 1 else ''}"

    tiles = [
        _tile("Account status", "Enabled" if enabled else "Disabled" if enabled is False else "Unavailable",
              "ok" if enabled else "bad" if enabled is False else "unk"),
        _tile("Lock status", "Locked" if locked else "Not locked" if locked is False else "Unavailable",
              "bad" if locked else "ok" if locked is False else "unk"),
        _tile("Password", password_value, password_tone, password_sub),
    ]
    if password_never_expires is True:
        tiles.append(_tile("Password never expires", "Yes", "warn"))
    elif password_never_expires is False:
        tiles.append(_tile("Password never expires", "No", "ok"))
    else:
        tiles.append(_tile("Password never expires", "Not reported", "unk"))
    return f'<div class="ta-tiles">{"".join(tiles)}</div>'


def _groups(user: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = _ci_get(user, key, default=[])
    return [g for g in value if isinstance(g, dict)] if isinstance(value, list) else []


def user_copy_text(user: dict[str, Any]) -> str:
    fields = [
        ("Full name", _ci_get(user, "Name", "displayName")), ("Display name", _ci_get(user, "DisplayName")),
        ("Email", _ci_get(user, "Mail", "Email", "userPrincipalName")), ("SAM account", _ci_get(user, "SamAccountName")),
        ("UPN", _ci_get(user, "UserPrincipalName")), ("Department", _ci_get(user, "Department")),
        ("Manager", _ci_get(user, "ManagerName", "ManagerDisplayName")),
        ("Enabled", _optional_boolean(user, "Enabled", "AccountEnabled")), ("Locked out", _optional_boolean(user, "LockedOut")),
        ("Password expired", _optional_boolean(user, "PasswordExpired")),
        (password_expiry_label(user), password_expiry_value(user)),
    ]
    return "\n".join(f"{k}: {display_text(v)}" for k, v in fields if v not in (None, ""))


def render_user_details(user: dict[str, Any], backend: Any, response: Dict[str, Any], idx: int) -> None:
    name = _ci_get(user, "DisplayName", "Name", "displayName") or "Unknown user"
    email = _ci_get(user, "Mail", "Email", "UserPrincipalName", "userPrincipalName") or response_target(response)
    direct = _groups(user, "DirectGroups")
    nested = _groups(user, "NestedGroups")
    effective = _groups(user, "EffectiveGroups")

    with st.container(key=f"card_user_{idx}"):
        head, action = st.columns([5, 1.25], vertical_alignment="center")
        with head:
            html_block(card_head(avatar=initials(name), kicker="Directory record", title=str(name), sub=str(email)))
        with action:
            with st.popover("Copy details", icon=":material/content_copy:", width="stretch"):
                st.caption("Use the copy icon in the corner of the box.")
                st.code(user_copy_text(user), language=None, wrap_lines=True)
        html_block(user_status_tiles(user))

        overview, groups_tab = st.tabs(["Overview", f"Group memberships :gray-badge[{len(direct) + len(nested)}]"])
        with overview:
            core = [
                ("Full name", _ci_get(user, "Name", "displayName")),
                ("Display name", _ci_get(user, "DisplayName", "displayName")),
                ("Email", _ci_get(user, "Mail", "Email", "mail")),
                ("SAM account", _ci_get(user, "SamAccountName")),
                ("Department", _ci_get(user, "Department")),
                ("Manager", _ci_get(user, "ManagerName", "ManagerDisplayName")),
            ]
            extra = [
                ("Job title", _ci_get(user, "JobTitle", "Title")),
                ("User principal name", _ci_get(user, "UserPrincipalName")),
                ("Manager email", _ci_get(user, "ManagerEmail", "ManagerMail", "ManagerUserPrincipalName")),
                ("Mobile phone", _ci_get(user, "MobilePhone")),
                ("Password last set", _ci_get(user, "PasswordLastSet")),
                (password_expiry_label(user), password_expiry_value(user)),
                ("Bad password count", _ci_get(user, "BadPasswordCount")),
                ("Last logon", _ci_get(user, "LastLogonDate")),
                ("Created", _ci_get(user, "WhenCreated")),
                ("User type", _ci_get(user, "UserType")),
                ("Description", _ci_get(user, "Description")),
            ]
            html_block(kv_grid(core, keep_empty=True) + kv_grid(extra))
            if _optional_boolean(user, "LockedOut") is None or _optional_boolean(user, "PasswordExpired") is None:
                html_block(
                    '<div class="ta-note" style="margin-top:12px"><strong>More Active Directory detail is available.</strong> '
                    'Microsoft Entra does not expose current on-premises lockout or password-expiry state. '
                    'Add <strong>“via script”</strong> to the request for lockout status, bad-password count, '
                    'primary group and exact nested-group inheritance.</div>'
                )
            dn = _ci_get(user, "DistinguishedName")
            if dn:
                with st.expander("Directory path"):
                    st.code(str(dn), language=None, wrap_lines=True)
        with groups_tab:
            primary = _ci_get(user, "PrimaryGroupName") or "Unavailable"
            effective_groups = effective or direct + nested
            html_block(
                '<div class="ta-stats">'
                f'<div class="ta-stat"><div class="lb">Primary group</div><div class="vl">{escape(str(primary))}</div></div>'
                f'<div class="ta-stat"><div class="lb">Direct groups</div><div class="vl">{len(direct)}</div></div>'
                f'<div class="ta-stat"><div class="lb">Nested groups</div><div class="vl">{len(nested)}</div></div>'
                f'<div class="ta-stat"><div class="lb">Effective groups</div><div class="vl">{len(effective_groups)}</div></div>'
                '</div>'
            )
            group_views = {
                "Direct groups": direct,
                "Nested groups": nested,
                "Effective groups": effective_groups,
            }
            selected_view = st.radio(
                "Group membership view",
                options=list(group_views),
                format_func=lambda label: f"{label}  {len(group_views[label])}",
                horizontal=True,
                label_visibility="collapsed",
                key=f"group_membership_view_{idx}",
            )
            selected_groups = group_views[selected_view]
            if selected_groups:
                group_rows = [{
                    "Group": _ci_get(group, "Name", "DisplayName", "SamAccountName") or "Unresolved group",
                    "SAM account": _ci_get(group, "SamAccountName"),
                    "Category": _ci_get(group, "GroupCategory", "Category"),
                    "Scope": _ci_get(group, "GroupScope", "Scope"),
                    "Description": _ci_get(group, "Description"),
                    "Distinguished name": _ci_get(group, "DistinguishedName", "DN"),
                    "Nesting level": _ci_get(group, "NestingLevel"),
                    "Inherited from": _ci_get(group, "InheritedFrom"),
                } for group in selected_groups]
                st.dataframe(group_rows, hide_index=True, width="stretch")
            else:
                st.info(f"No {selected_view.casefold()} were returned.")
            if nested and str(backend).strip().casefold() == "api":
                st.caption("Microsoft Entra returns transitive membership; exact inheritance may need the script lookup.")

        source = {"api": "Microsoft Entra", "script": "Active Directory"}.get(str(backend).casefold(), "")
        html_block(card_foot("Read-only directory lookup" + (f" · {source}" if source else ""), elapsed_text(response)))


def render_password_reset(result: Dict[str, Any], response: Dict[str, Any], idx: int) -> None:
    username = result.get("user_name") or result.get("user_principal_name") or result.get("user_principal") or response_target(response)
    employee = result.get("employee_name") or username
    manager_name = result.get("manager_name") or "Not available"
    manager_email = result.get("manager_email") or "Not available"
    token = result.get("password_token")

    with st.container(key=f"card_pwd_{idx}"):
        html_block(card_head(
            avatar="", kicker="Password reset complete", title=str(employee), sub=str(username),
            avatar_html=f'<div class="ta-avatar lg" style="background:var(--ta-ok-bg);color:var(--ta-ok)">{icon_key(20)}</div>',
        ))
        masked = escape(str(result.get("masked_password") or "Not available"))
        html_block(
            kv_grid([("Username", username), ("Employee", employee), ("Manager", manager_name),
                     ("Manager email", manager_email)], keep_empty=True)
            + f'<div class="ta-note ok" style="margin-top:12px;display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap">'
              f'<span>Temporary password</span><strong class="ta-secret">{masked}</strong></div>'
        )
        if not token:
            html_block('<div class="ta-note warn">The password is no longer retrievable for this reset. Run the reset again.</div>')
        else:
            status_key = f"email_status_{token}"
            st.session_state.setdefault(status_key, None)
            can_email = manager_email != "Not available" and email_is_configured()
            left, right = st.columns(2)
            if left.button("Send to manager", key=f"send_{token}", icon=":material/forward_to_inbox:",
                           disabled=not can_email, width="stretch", type="primary"):
                with st.spinner("Sending email..."):
                    sent, message, recipient = send_password_to_manager(token)
                st.session_state[status_key] = {"sent": sent, "message": message, "recipient": recipient}
            ok, filename, content, message = build_password_download(token)
            if ok:
                right.download_button("Download password (.txt)", data=content, file_name=filename, mime="text/plain",
                                      key=f"dl_{token}", width="stretch", icon=":material/download:")
            else:
                right.button("Download password (.txt)", key=f"dl_disabled_{token}", disabled=True, width="stretch",
                             icon=":material/download:")
                st.caption(message)
            status = st.session_state.get(status_key)
            if status is None:
                note = ("Email delivery is not configured on this server." if not email_is_configured()
                        else "Not sent yet. Nothing is emailed until you choose to send it.")
                st.caption(note)
            elif status["sent"]:
                html_block(f'<div class="ta-note ok">Sent to {escape(str(status["recipient"]))}.</div>')
            else:
                html_block(f'<div class="ta-note bad">Email failed. {escape(str(status["message"]))}</div>')
        html_block(card_foot("Password held in the secure vault, never stored in history", elapsed_text(response),
                             icon=icon_shield_check(14)))


def render_investigation(result: Dict[str, Any], response: Dict[str, Any], idx: int) -> None:
    report = result.get("report")
    with st.container(key=f"card_inv_{idx}"):
        target = (report or {}).get("target_user") if isinstance(report, dict) else None
        html_block(card_head(
            avatar="", kicker="Authentication investigation", title=str(target or response_target(response) or "Investigation"),
            sub=str((report or {}).get("requested_time_window") or "") if isinstance(report, dict) else "",
            avatar_html=f'<div class="ta-avatar lg">{icon_alert(20)}</div>',
        ))
        if isinstance(report, dict):
            render_investigation_report(report)
        else:
            html_block('<div class="ta-note warn">The investigation completed without a structured report payload.</div>')
        html_block(card_foot("Read-only CrowdStrike evidence", elapsed_text(response)))


def render_generic_result(intent: str, result: Dict[str, Any], response: Dict[str, Any], idx: int) -> None:
    excluded = {"execution", "user", "new_password", "temporary_password", "_transient_password",
                "report", "report_markdown", "backend", "password_token"}
    record = result.get("user") if isinstance(result.get("user"), dict) else result
    rows = [(str(k).replace("_", " ").capitalize(), v) for k, v in record.items()
            if k not in excluded and v not in (None, "")]
    success = response.get("success") is not False
    with st.container(key=f"card_gen_{idx}"):
        html_block(card_head(
            avatar="", kicker="Completed" if success else "Finished with issues", title=intent_title(intent),
            sub=response_target(response), tone="ok" if success else "bad",
            avatar_html=f'<div class="ta-avatar lg" style="background:var(--ta-ok-bg);color:var(--ta-ok)">{icon_check_circle(20)}</div>'
            if success else None,
        ))
        html_block(kv_grid(rows) or '<div class="ta-empty">No additional details were returned.</div>')
        execution = result.get("execution")
        if isinstance(execution, dict):
            with st.expander("Script execution"):
                html_block(kv_grid([
                    ("Success", execution.get("success")), ("Operation", execution.get("operation")),
                    ("Script", execution.get("script_name")), ("Exit code", execution.get("exit_code")),
                    ("Duration (s)", execution.get("duration_seconds")), ("Dry run", execution.get("dry_run")),
                    ("Error", execution.get("error")),
                ], single=True))
                if execution.get("stdout"):
                    st.code(str(execution["stdout"]), language=None)
                if execution.get("stderr"):
                    st.code(str(execution["stderr"]), language=None)
        html_block(card_foot("Change recorded in the operation audit log", elapsed_text(response)))


def render_error_card(response: Dict[str, Any], idx: int) -> None:
    detail = response.get("message") or response.get("error") or "The operation failed."
    tool_result = response.get("tool_result") if isinstance(response.get("tool_result"), dict) else {}
    if tool_result.get("message") and tool_result.get("message") != detail:
        detail = f"{detail} {tool_result['message']}"
    blocked = bool(response.get("guardrail_blocked"))
    with st.container(key=f"card_err_{idx}"):
        html_block(card_head(
            avatar="", kicker="Blocked by policy" if blocked else "Request failed", tone="bad",
            title=intent_title(response.get("intent")), sub=response_target(response),
            avatar_html=f'<div class="ta-avatar lg" style="background:var(--ta-bad-bg);color:var(--ta-bad)">{icon_x_circle(20)}</div>',
        ))
        html_block(f'<div class="ta-note bad">{escape(str(detail))}</div>')
        code = response.get("error")
        html_block(card_foot(f"Error: {code}" if code else "No changes were made", elapsed_text(response), icon=icon_alert(14)))


def render_approval_card(turn: dict[str, Any], response: Dict[str, Any], idx: int) -> None:
    pending = st.session_state.pending_confirmation
    active = isinstance(pending, dict) and pending.get("turn_index") == idx
    state = turn.get("approval_state")
    with st.container(key=f"card_approval_{idx}"):
        html_block(card_head(
            avatar="", kicker="Approval required", tone="warn", title=intent_title(response.get("intent")),
            sub=response_target(response),
            avatar_html=f'<div class="ta-avatar lg" style="background:var(--ta-warn-bg);color:var(--ta-warn)">{icon_shield_alert(20)}</div>',
        ))
        prompt = response.get("confirmation_prompt") or "Confirm this operation before continuing."
        html_block(f'<div class="ta-note warn">{escape(str(prompt))}</div>')
        if active:
            left, right = st.columns(2)
            if left.button("Approve and run", key=f"approve_{idx}", type="primary", width="stretch", icon=":material/check:"):
                approve_pending()
                st.rerun()
            if right.button("Cancel", key=f"cancel_{idx}", width="stretch"):
                cancel_pending_confirmation()
                st.rerun()
            st.caption("You can also reply “yes” or “no” in the chat.")
        else:
            label, tone = {"approved": ("Approved", "ok"), "cancelled": ("Cancelled", "bad")}.get(state, ("Expired", ""))
            html_block(f'<span class="ta-badge {tone}">{label}</span>')
        html_block(card_foot("Nothing changes until you approve", f"Request {response.get('request_id') or ''}".strip()))


def assistant_summary(response: Dict[str, Any]) -> str:
    intent = str(response.get("intent") or "")
    tool_result = response.get("tool_result") if isinstance(response.get("tool_result"), dict) else {}
    if response.get("cancelled"):
        return "Cancelled. No changes were made."
    if response.get("confirmation_required"):
        return "This changes a live account, so I need your approval before running it."
    if response.get("clarification_required"):
        return str(response.get("clarification_question") or response.get("message") or "I need a little more information.")
    if response.get("success") is False or tool_result.get("success") is False:
        return "I couldn't complete that request."
    if intent == "get_user_details":
        return "I found one matching directory profile. Account health and access details are shown below."
    if intent == "password_reset":
        return "The password has been reset. Choose how to deliver the temporary password."
    if intent == "failed_login_investigation":
        return "Here's what the authentication evidence shows."
    if intent == "patch_report":
        return "Here’s the latest Ivanti patch compliance snapshot. Adjust the date and filters to explore the fleet."
    return str(tool_result.get("message") or response.get("message") or "Done.")


def render_assistant_turn(turn: dict[str, Any], idx: int) -> None:
    response = turn.get("content") if isinstance(turn.get("content"), dict) else {}
    html_block(
        f'<div class="ta-asst-head"><div class="ta-icon-tile">{icon_sparkle(18, "#fff")}</div><div>'
        f'<div class="who">TechAdmin AI</div><div class="msg">{escape(assistant_summary(response))}</div></div></div>'
    )
    with st.container(key=f"amsg_{idx}"):
        intent = str(response.get("intent") or "")
        tool_result = response.get("tool_result")
        result = tool_result.get("result") if isinstance(tool_result, dict) else None
        if response.get("cancelled") or response.get("clarification_required"):
            pass
        elif response.get("confirmation_required"):
            render_approval_card(turn, response, idx)
        elif isinstance(result, dict) and response.get("success") is not False:
            if intent == "failed_login_investigation":
                render_investigation(result, response, idx)
            elif intent == "patch_report":
                from patch_report_ui import render_patch_report

                render_patch_report(result)
            elif intent == "password_reset" and result.get("password_token"):
                render_password_reset(result, response, idx)
            elif intent == "get_user_details":
                record = result.get("user")
                render_user_details(record if isinstance(record, dict) else result, result.get("backend"), response, idx)
            else:
                render_generic_result(intent, result, response, idx)
        elif response.get("success") is False:
            render_error_card(response, idx)
        elif response.get("message") and response.get("message") != assistant_summary(response):
            html_block(f'<div class="ta-note">{escape(str(response["message"]))}</div>')

        if response and not response.get("cancelled"):
            with st.expander("Technical details"):
                facts = [
                    ("Intent", intent or None), ("Confidence", response.get("confidence")),
                    ("Agent", response.get("selected_agent")), ("Tool", response.get("selected_tool")),
                    ("Request ID", response.get("request_id")), ("Correlation ID", response.get("correlation_id")),
                    ("Guardrail action", response.get("guardrail_action")),
                ]
                html_block(kv_grid(facts, single=True))
                st.json(redact_sensitive_history(copy.deepcopy(response)), expanded=False)


def render_user_turn(turn: dict[str, Any], claims: dict[str, Any]) -> None:
    who = claims.get("preferred_username") or claims.get("email") or claims.get("name") or ""
    meta = " · ".join(p for p in ("You", str(who), time_ago(turn.get("ts"))) if p)
    html_block(
        f'<div class="ta-user-row"><div class="ta-user-bubble"><div class="meta">{escape(meta)}</div>'
        f'<div class="txt">{escape(str(turn.get("content") or ""))}</div></div>'
        f'<div class="ta-avatar" style="width:32px;height:32px;font-size:11px">{escape(initials(claims.get("name") or who))}</div></div>'
    )


# =============================================================================
# Chrome: sidebar + top bar
# =============================================================================

def request_history(limit: int = 20) -> list[dict[str, Any]]:
    access = access_info()
    user_id = access.get("user_id")
    requester_id = user_id or access.get("user_principal_name")

    if requester_id:
        identity_items: list[dict[str, Any]] = []
        security_items: list[dict[str, Any]] = []

        if user_id:
            try:
                identity_items = get_user_request_history(
                    user_id,
                    limit=limit,
                )
            except Exception:
                identity_items = []

        if not PREVIEW_MODE:
            try:
                security_items = get_security_query_history(
                    str(requester_id),
                    limit=limit,
                )
            except Exception:
                security_items = []

        combined = identity_items + security_items
        combined.sort(
            key=lambda item: item.get("requested_at") or datetime.min,
            reverse=True,
        )
        return combined[:limit]
    # identities without an app_users row: fall back to this browser session
    items = []
    for turn in reversed(st.session_state.conversation):
        content = turn.get("content")
        if turn.get("role") != "assistant" or not isinstance(content, dict) or content.get("cancelled"):
            continue
        status = ("awaiting_approval" if content.get("confirmation_required") else
                  "completed" if content.get("success") is True else "failed")
        items.append({"request": turn.get("query") or "", "operation": content.get("intent") or "",
                      "target": response_target(content), "status": status, "requested_at": turn.get("ts")})
    return items[:limit]


def _history_title(item: dict[str, Any]) -> str:
    op = str(item.get("operation") or "").strip()
    key = op.casefold().replace(" ", "_")
    return INTENT_TITLES.get(key) or (op.replace("_", " ").capitalize() if op else (item.get("request") or "Identity request"))


def _status_badge(status: Any) -> str:
    text = str(status or "unknown").replace("_", " ")
    s = text.casefold()
    tone = "ok" if s in {"completed", "succeeded", "success"} else "warn" if "await" in s or "pending" in s else \
        "bad" if s in {"failed", "rejected", "error", "blocked"} else ""
    return f'<span class="ta-badge {tone}">{escape(text.capitalize())}</span>'


def sign_out(claims: dict[str, Any]) -> None:
    is_local = claims.get("auth_source") == "local_test_account"
    clear_local_authentication_state()
    clear_conversation_state()
    if is_local:
        st.rerun()
    else:
        st.logout()


def render_sidebar(
    history: list[dict[str, Any]],
) -> None:
    page = st.session_state.page

    agents_open = bool(
        st.session_state.get(
            "agents_open"
        )
    )

    with st.sidebar:
        html_block(
            f'<div class="ta-side-brand">'
            f'{coforge_wordmark(46)}'
            f'</div>'
        )

        with st.container(
            key=(
                "agents_toggle_open"
                if agents_open
                else "agents_toggle"
            )
        ):
            if st.button(
                "AI Agents",
                key="agents_toggle_btn",
                icon=":material/apps:",
                width="stretch",
            ):
                st.session_state.agents_open = (
                    not agents_open
                )
                st.rerun()

        if agents_open:
            with st.container(
                key="agent_list"
            ):
                # Identity Agent navigation
                with st.container(
                    key=(
                        "agent_identity_active"
                        if page == "assistant"
                        else "agent_identity"
                    )
                ):
                    if st.button(
                        "Identity Agent",
                        key="navbtn_assistant",
                        icon=":material/badge:",
                        width="stretch",
                    ):
                        st.session_state.page = (
                            "assistant"
                        )

                        # Do not carry an unapproved Security
                        # operation into Identity Agent.
                        st.session_state.security_pending = (
                            None
                        )

                        st.rerun()

                # Security Agent navigation
                with st.container(
                    key=(
                        "agent_security_active"
                        if page == "security"
                        else "agent_security"
                    )
                ):
                    if st.button(
                        "Security Agent",
                        key="navbtn_security",
                        icon=":material/security:",
                        width="stretch",
                    ):
                        st.session_state.page = (
                            "security"
                        )

                        # Do not carry an Identity Agent
                        # execution or approval into
                        # Security Agent.
                        st.session_state.pending_run = None
                        st.session_state.pending_confirmation = (
                            None
                        )

                        st.rerun()

                # Future Network Agent placeholder
                html_block(
                    '<div class="ta-agent-soon">'
                    '<span '
                    'class="material-symbols-rounded">'
                    'lan'
                    '</span>'
                    '<span class="nm">'
                    'Network Agent'
                    '</span>'
                    '<span class="pill">'
                    'Soon'
                    '</span>'
                    '</div>'
                )

        # Request history navigation
        with st.container(
            key=(
                "nav_active_history"
                if page == "history"
                else "nav_history"
            )
        ):
            if st.button(
                "Your History",
                key="navbtn_history",
                icon=":material/history:",
                width="stretch",
            ):
                st.session_state.page = "history"
                st.rerun()

        # Recent requests heading and filter
        head_left, head_right = st.columns(
            [5, 1],
            vertical_alignment="center",
        )

        head_left.markdown(
            '<div class="ta-side-label">'
            'Recent requests'
            '</div>',
            unsafe_allow_html=True,
        )

        with head_right:
            with st.container(
                key="side_search"
            ):
                with st.popover(
                    ":material/search:"
                ):
                    st.text_input(
                        "Filter your history",
                        key="history_filter",
                        placeholder=(
                            "Email or operation"
                        ),
                    )

        term = str(
            st.session_state.get(
                "history_filter"
            )
            or ""
        ).strip().casefold()

        shown = [
            item
            for item in history
            if (
                not term
                or term
                in json.dumps(
                    item,
                    default=str,
                ).casefold()
            )
        ]

        with st.container(
            border=False,
            key="history_sidebar_scroll",
        ):
            if not shown:
                if term:
                    html_block(
                        '<div class="ta-side-empty">'
                        'No matching requests.'
                        '</div>'
                    )
                else:
                    html_block(
                        '<div class="ta-side-empty">'
                        'No requests recorded yet.'
                        '</div>'
                    )

            request_items: list[str] = []

            for item in shown:
                subtitle = " · ".join(
                    part
                    for part in (
                        str(
                            item.get(
                                "target"
                            )
                            or ""
                        ),
                        time_ago(
                            item.get(
                                "requested_at"
                            )
                        ),
                    )
                    if part
                )

                request_items.append(
                    '<div '
                    'class="ta-recent" '
                    f'title="{escape(str(item.get("request") or ""))}">'
                    '<strong>'
                    f'{escape(_history_title(item))}'
                    '</strong>'
                    '<span>'
                    f'{escape(subtitle)}'
                    '</span>'
                    '</div>'
                )

            html_block(
                "".join(request_items)
            )


def system_health() -> tuple[bool, list[tuple[str, Any]]]:
    status = get_config_status()
    graph_ok = bool(status.get("graph_client_id") and status.get("graph_client_secret") and status.get("graph_tenant_id"))
    rows = [
        ("Mode", status.get("mode") or "Live"),
        ("Microsoft Entra", "Configured" if graph_ok else "Incomplete"),
        ("PowerShell", "Enabled" if status.get("powershell_operations_enabled") else "Disabled"),
        ("Destructive actions", "Enabled" if status.get("destructive_operations_enabled") else "Disabled"),
        ("Orchestration", "LangGraph" if status.get("orchestration_engine") == "langgraph" else "Unavailable"),
        ("Operation audit", "Enabled" if status.get("operation_audit_enabled") else "Unknown"),
        ("Configuration", "Valid" if status.get("config_valid") else "Invalid"),
        ("Model", status.get("model_name")),
    ]
    return graph_ok and bool(status.get("config_valid")), rows


def render_topbar(claims: dict[str, Any]) -> None:
    healthy, rows = system_health()
    with st.container(key="topbar"):
        left, right = st.columns([4, 1], vertical_alignment="center", gap="small")
        with left:
            badges = "" if healthy else ' <span class="ta-badge warn">Configuration needs attention</span>'
            if PREVIEW_MODE:
                badges += ' <span class="ta-badge warn">Preview · sample data</span>'
            html_block(
                f'<div class="ta-top-brand">{operations_icon(36)}<div><div class="ta-topbar-title">TechAdmin{badges}</div>'
                '<div class="ta-topbar-sub">Autonomous Assistant</div></div></div>'
            )
            # initials() only yields letters, so it is safe inside a CSS string
            html_block(f'<style>.st-key-me_menu {{ --ta-initials: "{initials(claims.get("name") or claims.get("preferred_username") or "")}"; }}</style>')
        actions = right.container(horizontal=True, horizontal_alignment="right", vertical_alignment="center",
                                  gap="small", wrap=False, key="top_actions")
        with actions:
            with st.popover(":material/help_outline:", help="Help and system status"):
                st.markdown("**Try asking**")
                for i, example in enumerate(EXAMPLES):
                    if st.button(example, key=f"example_{i}", width="stretch"):
                        queue_run(example)
                        st.rerun()
                st.markdown("**System status**")
                html_block(kv_grid(rows, single=True))
                if st.button("Test Ollama connection", width="stretch", key="test_ollama"):
                    connected, message = check_ollama()
                    st.session_state.ollama_check_result = {"connected": connected, "message": message}
                result = st.session_state.ollama_check_result
                if isinstance(result, dict):
                    (st.success if result["connected"] else st.error)(result["message"])
                st.caption(f"Logs: {LOG_FILE}")
            pending = st.session_state.get("pending_confirmation")
            with st.popover(":material/notifications:" if not pending else ":material/notifications_active:",
                            help="Notifications"):
                if isinstance(pending, dict):
                    st.markdown(f"**Awaiting your approval** — {intent_title(pending.get('intent'))}")
                    st.caption(pending.get("prompt") or "")
                    if st.button("Review", key="bell_review", width="stretch"):
                        st.session_state.page = "assistant"
                        st.rerun()
                else:
                    st.caption("You're all caught up. Approvals waiting on you will appear here.")
            name = claims.get("name") or claims.get("preferred_username") or "TechAdmin"
            email = claims.get("preferred_username") or claims.get("email") or ""
            role = ROLE_TITLES.get(str(get_config_status().get("requester_role") or "").casefold(), "Operations admin")
            dept = access_info().get("department")
            with st.container(key="me_menu", width="content"):
                with st.popover(":material/person:", help=str(name)):
                    html_block(
                        f'<div class="ta-me-pop"><div class="ta-avatar">{escape(initials(name))}</div><div style="min-width:0">'
                        f'<strong>{escape(str(name))}</strong><span>{escape(str(email))}</span>'
                        f'<span>{escape(str(dept or role))}</span></div></div>'
                    )
                    if st.button("Sign out", key="top_sign_out_btn", icon=":material/logout:", width="stretch"):
                        sign_out(claims)


# =============================================================================
# Pages
# =============================================================================

QUICK_ACTIONS = [
    ("lookup", "Look up a user", ":material/person_search:", "Get user details for {email}"),
    ("unlock", "Unlock an account", ":material/lock_open:", "Unlock account for {email}"),
    ("investigate", "Investigate account lockout", ":material/policy:",
     "Investigate account lockout for {email} in the last 24 hours"),
]


@st.dialog("Who is this for?")
def quick_action_dialog(title: str, template: str) -> None:
    st.caption(title)
    with st.form("qa_form", border=False):
        email = st.text_input("Work email or username", placeholder="name@coforge.com", key="qa_email")
        submitted = st.form_submit_button("Continue", type="primary", width="stretch")
    if submitted:
        if not email.strip():
            st.error("Enter the user's work email or username.")
            return
        queue_run(template.format(email=email.strip()))
        st.rerun()


def contextual_chips() -> list[tuple[str, str]]:
    if st.session_state.pending_confirmation or st.session_state.pending_run:
        return []
    for turn in reversed(st.session_state.conversation):
        response = turn.get("content")
        if turn.get("role") != "assistant" or not isinstance(response, dict):
            continue
        target = response_target(response)
        if not target:
            return []
        intent = response.get("intent")
        tool_result = response.get("tool_result") if isinstance(response.get("tool_result"), dict) else {}
        result = tool_result.get("result") if isinstance(tool_result.get("result"), dict) else {}
        user = result.get("user") if isinstance(result.get("user"), dict) else result
        name = first_name(_ci_get(user, "DisplayName", "Name", "displayName") or target)
        chips: list[tuple[str, str]] = []
        if intent == "get_user_details" and response.get("success") is not False:
            if _optional_boolean(user, "LockedOut"):
                chips.append((f"Unlock {name}'s account", f"Unlock account for {target}"))
            chips.append((f"Reset {name}'s password", f"Reset password for {target}"))
            chips.append(("Investigate failed sign-ins", f"Investigate failed logins for {target} in the last 24 hours"))
        else:
            chips.append((f"Show {name}'s profile", f"Get user details for {target}"))
            if intent != "failed_login_investigation":
                chips.append(("Investigate failed sign-ins", f"Investigate failed logins for {target} in the last 24 hours"))
        return chips
    return []


def page_assistant(claims: dict[str, Any]) -> None:
    conversation = st.session_state.conversation
    with st.container(key="content"):
        with st.container(key="greet_row"):
            left, right = st.columns([5, 1.4], vertical_alignment="center")
            with left:
                sub = ("Here's the result from your latest identity request." if conversation
                       else "What would you like to take care of today?")
                html_block(f'<div class="ta-greet"><h1>{greeting()}, {escape(first_name(claims.get("name") or "TechAdmin"))}</h1>'
                           f'<p>{sub}</p></div>')
            with right:
                with st.container(key="new_conversation"):
                    if st.button("New conversation", icon=":material/add_comment:", width="stretch", key="new_conv_btn"):
                        new_conversation()
                        st.rerun()

        if not conversation and not st.session_state.pending_run:
            html_block('<div class="ta-hello"><h3>Quick actions</h3>'
                       '<p>Pick a task, or describe what you need in the box below. Changes always pause for your approval.</p></div>')
            cols = st.columns(len(QUICK_ACTIONS))
            for col, (key, title, icon, template) in zip(cols, QUICK_ACTIONS):
                with col:
                    with st.container(key=f"qa_{key}"):
                        if st.button(title, key=f"qa_btn_{key}", icon=icon, width="stretch"):
                            quick_action_dialog(title, template)

        for idx, turn in enumerate(conversation):
            if turn.get("role") == "user":
                render_user_turn(turn, claims)
            else:
                render_assistant_turn(turn, idx)

        if st.session_state.pending_run:
            execute_pending_run()

        chips = contextual_chips()
        if chips:
            with st.container(key="chips"):
                cols = st.columns(len(chips), gap="small")
                for i, (col, (label, query)) in enumerate(zip(cols, chips)):
                    if col.button(label, key=f"chip_{len(conversation)}_{i}", icon=":material/chevron_right:"):
                        queue_run(query)
                        st.rerun()

    placeholder = ("Reply “yes” to approve or “no” to cancel…" if st.session_state.pending_confirmation
                   else "Ask TechAdmin to manage an identity…")
    query = st.session_state.queued_query or st.chat_input(placeholder)
    st.session_state.queued_query = None
    if query:
        handle_input(query)


def page_history(history: list[dict[str, Any]]) -> None:
    with st.container(key="content"):
        html_block('<div class="ta-page-head"><h1>Your History</h1>'
                   '<p>Your recent identity requests, as recorded in the operation audit log.</p></div>')
        with st.container(height=520, border=False, key="history_page_scroll"):
            with st.container(key="hist_card"):
                rows = ['<div class="ta-hist h"><span>Request</span><span>Target</span><span>Status</span><span>When</span></div>']
                for item in history:
                    when = item.get("requested_at")
                    when_text = when.astimezone().strftime("%d %b, %H:%M") if isinstance(when, datetime) else time_ago(when)
                    rows.append(
                        f'<div class="ta-hist"><span class="q" title="{escape(str(item.get("request") or ""))}">'
                        f'{escape(_history_title(item))}<br><span class="t">{escape(str(item.get("request") or ""))}</span></span>'
                        f'<span class="t">{escape(str(item.get("target") or "—"))}</span>'
                        f'<span>{_status_badge(item.get("status"))}</span><span class="t">{escape(when_text)}</span></div>'
                    )
                if not history:
                    rows.append('<div class="ta-empty" style="padding:22px 16px">No requests recorded yet.</div>')
                html_block("".join(rows))
        st.write("")
        if st.session_state.conversation:
            data = json.dumps(redact_sensitive_history(copy.deepcopy(st.session_state.conversation)),
                              indent=2, ensure_ascii=False, default=str)
            st.download_button("Download this session (JSON)", data=data, file_name="techadmin_session.json",
                               mime="application/json", icon=":material/download:")


# =============================================================================
# Main
# =============================================================================

def open_sidebar_once() -> None:
    """Expand the sidebar the first time the workspace renders after sign-in."""
    if st.session_state.get("sidebar_opened_once"):
        return
    st.session_state.sidebar_opened_once = True
    import streamlit.components.v1 as components

    with st.container(key="sidebar_opener"):
        components.html(
            """<script>
            (() => {
              const doc = window.parent.document;
              let tries = 0;
              const timer = setInterval(() => {
                const side = doc.querySelector('section[data-testid="stSidebar"]');
                const btn = doc.querySelector('[data-testid="stExpandSidebarButton"]');
                if (side && side.getAttribute('aria-expanded') === 'true') { clearInterval(timer); return; }
                if (btn) { btn.click(); clearInterval(timer); return; }
                if (++tries > 40) clearInterval(timer);
              }, 100);
            })();
            </script>""",
            height=0,
        )
def main() -> None:
    init_state()

    if not PREVIEW_MODE:
        try:
            from App.services.patch.bootstrap import start_patch_background_services

            start_patch_background_services()
        except Exception:
            logging.getLogger(__name__).exception(
                "Could not start the embedded patch scheduler."
            )

    claims = require_authentication()

    inject_app_css()
    inject_workspace_layout_css()

    history = request_history()

    valid_pages = {
        key
        for key, _, _ in PAGES
    }

    current_page = st.session_state.get(
        "page",
        "assistant",
    )

    if current_page not in valid_pages:
        current_page = "assistant"
        st.session_state.page = "assistant"

    render_sidebar(history)
    render_topbar(claims)

    if not PREVIEW_MODE:
        try:
            from App.services.patch.scheduler import (
                patch_scan_is_running,
                request_patch_scan_stop,
            )
            if patch_scan_is_running():
                status_col, stop_col = st.columns([5, 1.2], vertical_alignment="center")
                status_col.warning(
                    "Ivanti compliance scan is running. A stop request takes effect after the current API page; partial scans will not resolve devices or raise automatic tickets."
                )
                if stop_col.button("Stop scan", key="global_stop_patch_scan", icon=":material/stop_circle:", width="stretch"):
                    result = request_patch_scan_stop()
                    st.toast(result.get("message") or "Stop requested.")
                    st.rerun()
        except Exception:
            logging.getLogger(__name__).exception("Could not read patch scheduler status.")

    # Keep this only if the automatic sidebar expansion
    # is required. It generates a Streamlit deprecation warning.
    open_sidebar_once()

    if current_page == "history":
        page_history(history)
        return

    if current_page == "security":
        if PREVIEW_MODE:
            with st.container(key="content"):
                html_block(
                    '<div class="ta-page-head">'
                    '<h1>Security Agent</h1>'
                    '<p>'
                    'Security Agent requires the live '
                    'PostgreSQL and Ivanti configuration.'
                    '</p>'
                    '</div>'
                )

                st.info(
                    "Security Agent is unavailable in "
                    "TECHADMIN_UI_PREVIEW mode."
                )

            return

        if render_patch_agent_page is None:
            with st.container(key="content"):
                st.error(
                    "Security Agent could not be loaded."
                )

            return

        redirected = st.session_state.pop(
            "security_redirect_query",
            None,
        )

        if redirected:
            st.session_state[
                "patch_query_prefill"
            ] = redirected

            st.session_state[
                "security_redirect_notice"
            ] = True

        render_patch_agent_page(
            claims,
            access_info(),
        )

        return

    # Identity Agent is the default page.
    page_assistant(claims)


if __name__ == "__main__":
    main()




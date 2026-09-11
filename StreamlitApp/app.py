# """
# TechAdmin Streamlit UI
# Author: Amit Bhagat
# Purpose: Browser UI for the TechAdmin IT support assistant.

# The user types a request in plain English. Guardrails validate it, Ollama
# classifies the intent and extracts the identifiers, and the Identity Agent runs
# the tool through MCP.

# The interface is written for the person raising the ticket, not for the person
# who built the pipeline. The answer comes first and in plain language; intent
# scores, MCP server names, operation IDs and the raw payload are all still
# available, but they sit behind a "Technical details" expander so they do not
# compete with the answer.

# Run from the project root:
#     streamlit run StreamlitApp/app.py
# """

# from __future__ import annotations

# import json
# from datetime import datetime
# from typing import Any, Dict, List

# import streamlit as st

# from flow_service import LOG_FILE, FlowService, check_ollama, get_config_status

# # ---------------------------------------------------------------------------
# # Page setup
# # ---------------------------------------------------------------------------
# st.set_page_config(
#     page_title="TechAdmin IT Support",
#     page_icon="🛡️",
#     layout="centered",
#     initial_sidebar_state="collapsed",
# )

# # Styling is kept in one block rather than scattered through the render
# # functions. Colours are semi-transparent greys where possible so the cards
# # read correctly in both light and dark themes.
# STYLES = """
# <style>
#     .block-container { padding-top: 2.5rem; max-width: 780px; }

#     .ta-card {
#         border: 1px solid rgba(128, 128, 128, 0.25);
#         border-radius: 12px;
#         padding: 1.1rem 1.3rem;
#         margin: 0.5rem 0 0.75rem 0;
#         background: rgba(128, 128, 128, 0.06);
#     }
#     .ta-card-accent-ok    { border-left: 4px solid #1a9f5a; }
#     .ta-card-accent-warn  { border-left: 4px solid #d99100; }
#     .ta-card-accent-block { border-left: 4px solid #c8442b; }

#     .ta-name {
#         font-size: 1.25rem;
#         font-weight: 650;
#         margin-bottom: 0.15rem;
#         line-height: 1.3;
#     }
#     .ta-sub {
#         font-size: 0.9rem;
#         opacity: 0.7;
#         margin-bottom: 0.9rem;
#     }

#     .ta-grid {
#         display: grid;
#         grid-template-columns: 34% 66%;
#         row-gap: 0.55rem;
#         font-size: 0.94rem;
#     }
#     .ta-label { opacity: 0.62; }
#     .ta-value { font-weight: 500; word-break: break-word; }

#     .ta-pill {
#         display: inline-block;
#         padding: 0.12rem 0.6rem;
#         border-radius: 999px;
#         font-size: 0.78rem;
#         font-weight: 600;
#     }
#     .ta-pill-ok  { background: rgba(26, 159, 90, 0.18); color: #1a9f5a; }
#     .ta-pill-off { background: rgba(200, 68, 43, 0.18); color: #c8442b; }

#     .ta-headline { font-size: 1.02rem; font-weight: 600; margin-bottom: 0.2rem; }
#     .ta-body     { font-size: 0.93rem; opacity: 0.85; }

#     div[data-testid="stExpander"] summary p { font-size: 0.86rem; opacity: 0.75; }
# </style>
# """


# # ---------------------------------------------------------------------------
# # Field definitions
# # ---------------------------------------------------------------------------
# # What an end user is shown for a person, in this order. Anything else Graph
# # returns stays in the technical details rather than the card.
# PROFILE_FIELDS = [
#     ("mail", "Email"),
#     ("userPrincipalName", "Sign-in name"),
#     ("department", "Department"),
#     ("jobTitle", "Job title"),
#     ("officeLocation", "Office"),
# ]

# # Developer-facing fields, shown only inside the expander.
# TECHNICAL_FIELDS = [
#     ("request_id", "Request ID"),
#     ("correlation_id", "Correlation ID"),
#     ("intent", "Detected intent"),
#     ("selected_agent", "Agent"),
#     ("selected_mcp_server", "MCP server"),
#     ("selected_mcp_tool", "MCP tool"),
#     ("selected_tool", "Application tool"),
# ]

# EXAMPLE_QUERIES = [
#     "Get details for amit.bhagat@coforge.com",
#     # "Reset password for aman.gupta",
#     "Find user details for derhant",
# ]

# GUARDRAIL_NAMES = [
#     "Intent allowlist",
#     "Identifier validation",
#     "Single user only",
#     "Prompt injection detection",
#     "Authorization check",
#     "Sensitive field filtering",
#     "Privileged account protection",
#     "Reset confirmation and audit",
# ]


# @st.cache_resource(show_spinner="Starting TechAdmin...")
# def get_service() -> FlowService:
#     """
#     Build the FlowService once per session.

#     Without cache_resource Streamlit rebuilds the Ollama and Graph clients on
#     every interaction, which is slow and discards the cached Graph token.
#     """
#     return FlowService()


# def init_state() -> None:
#     """Create the session keys the app relies on."""
#     st.session_state.setdefault("conversation", [])
#     st.session_state.setdefault("queued_query", None)
#     # Holds the query and request ID while the user answers a confirmation.
#     st.session_state.setdefault("pending_confirmation", None)


# def esc(value: Any) -> str:
#     """
#     Escape a value for the HTML cards.

#     Graph values are user-controlled, so a display name containing angle
#     brackets would otherwise break out of the markup.
#     """
#     if value is None or value == "":
#         return "—"

#     text = str(value)
#     return (
#         text.replace("&", "&amp;")
#         .replace("<", "&lt;")
#         .replace(">", "&gt;")
#         .replace('"', "&quot;")
#     )


# def grid_rows(pairs: List[tuple]) -> str:
#     """Build label/value rows for a card grid, skipping empty values."""
#     rows = []
#     for label, value in pairs:
#         if value in (None, "", "—"):
#             continue
#         rows.append(
#             f'<div class="ta-label">{esc(label)}</div>'
#             f'<div class="ta-value">{value}</div>'
#         )
#     return "".join(rows)


# # ---------------------------------------------------------------------------
# # Result cards
# # ---------------------------------------------------------------------------
# def render_profile_card(result: Dict[str, Any]) -> None:
#     """
#     Show a user record as a readable profile.

#     Only approved fields reach here: the output guardrail has already reduced
#     the Graph record before the UI sees it.
#     """
#     name = esc(result.get("displayName") or result.get("userPrincipalName") or "User")

#     enabled = result.get("accountEnabled")
#     if enabled is True:
#         status = '<span class="ta-pill ta-pill-ok">Active</span>'
#     elif enabled is False:
#         status = '<span class="ta-pill ta-pill-off">Disabled</span>'
#     else:
#         status = ""

#     pairs = [(label, esc(result.get(key))) for key, label in PROFILE_FIELDS]
#     if status:
#         pairs.append(("Account status", status))

#     st.markdown(
#         f'<div class="ta-card ta-card-accent-ok">'
#         f'<div class="ta-name">{name}</div>'
#         f'<div class="ta-sub">User record</div>'
#         f'<div class="ta-grid">{grid_rows(pairs)}</div>'
#         f"</div>",
#         unsafe_allow_html=True,
#     )


# def render_reset_card(result: Dict[str, Any], message: str) -> None:
#     """
#     Show the outcome of a password reset.

#     The temporary password is deliberately absent. The output guardrail removes
#     it before the response leaves the flow, and the approved wording explains
#     that credentials went out through a separate channel.
#     """
#     account = esc(result.get("user_principal") or "the account")

#     st.markdown(
#         f'<div class="ta-card ta-card-accent-ok">'
#         f'<div class="ta-headline">Password reset completed</div>'
#         f'<div class="ta-body">{esc(message)}</div>'
#         f'<div class="ta-grid" style="margin-top:0.8rem;">'
#         f'<div class="ta-label">Account</div>'
#         f'<div class="ta-value">{account}</div>'
#         f"</div></div>",
#         unsafe_allow_html=True,
#     )


# def render_blocked_card(response: Dict[str, Any]) -> None:
#     """
#     Show a request the guardrails refused.

#     Only the generic message is shown. The rule that fired and what it matched
#     go to the audit log; putting them on screen would tell someone probing the
#     system exactly what to change.
#     """
#     st.markdown(
#         f'<div class="ta-card ta-card-accent-block">'
#         f'<div class="ta-headline">Request not permitted</div>'
#         f'<div class="ta-body">{esc(response.get("message"))}</div>'
#         f"</div>",
#         unsafe_allow_html=True,
#     )


# def render_error_card(response: Dict[str, Any]) -> None:
#     """Show a request that failed for a reason other than a guardrail."""
#     st.markdown(
#         f'<div class="ta-card ta-card-accent-warn">'
#         f'<div class="ta-headline">Could not complete the request</div>'
#         f'<div class="ta-body">{esc(response.get("message"))}</div>'
#         f"</div>",
#         unsafe_allow_html=True,
#     )


# def render_technical_details(response: Dict[str, Any]) -> None:
#     """
#     Everything a developer needs, kept out of everyone else's way.

#     Confidence and the guardrail outcome are included, so a misclassification
#     can still be diagnosed from the UI without reading the logs.
#     """
#     with st.expander("Technical details"):
#         rows = []

#         confidence = response.get("confidence")
#         if isinstance(confidence, (int, float)) and confidence:
#             rows.append(("Intent confidence", f"{confidence:.0%}"))

#         for key, label in TECHNICAL_FIELDS:
#             if response.get(key):
#                 rows.append((label, esc(response.get(key))))

#         tool_result = response.get("tool_result") or {}
#         for key, label in (("status", "Tool status"), ("operation_id", "Operation ID")):
#             if tool_result.get(key):
#                 rows.append((label, esc(tool_result.get(key))))

#         if response.get("guardrail_action"):
#             rows.append(("Guardrail action", esc(response["guardrail_action"])))

#         filtered = response.get("guardrails_output_filtered")
#         if filtered:
#             rows.append(("Fields withheld by policy", esc(", ".join(filtered))))

#         if rows:
#             st.markdown(
#                 f'<div class="ta-grid">{grid_rows(rows)}</div>',
#                 unsafe_allow_html=True,
#             )

#         if response.get("explanation"):
#             st.caption(response["explanation"])

#     with st.expander("Raw response (JSON)"):
#         st.json(response)


# def render_response(response: Dict[str, Any]) -> None:
#     """Render one workflow response for an end user."""
#     # A confirmation request is only summarised here; the buttons are drawn by
#     # render_confirmation_controls so they appear once, under the transcript.
#     if response.get("confirmation_required"):
#         st.markdown(
#             f'<div class="ta-card ta-card-accent-warn">'
#             f'<div class="ta-headline">Confirmation required</div>'
#             f'<div class="ta-body">{esc(response.get("confirmation_prompt"))}</div>'
#             f"</div>",
#             unsafe_allow_html=True,
#         )
#         render_technical_details(response)
#         return

#     if response.get("guardrail_blocked"):
#         render_blocked_card(response)
#         render_technical_details(response)
#         return

#     if response.get("clarification_required"):
#         st.info(response.get("clarification_question") or "More information is needed.")
#         render_technical_details(response)
#         return

#     tool_result = response.get("tool_result") or {}
#     result = tool_result.get("result") or response.get("result")

#     if response.get("success") and isinstance(result, dict) and result:
#         if response.get("intent") == "password_reset":
#             render_reset_card(result, response.get("message") or "")
#         else:
#             render_profile_card(result)
#     elif response.get("success"):
#         st.success(response.get("message") or "Completed successfully.")
#     else:
#         render_error_card(response)

#     render_technical_details(response)


# # ---------------------------------------------------------------------------
# # Sidebar
# # ---------------------------------------------------------------------------
# def render_sidebar() -> None:
#     """System status and session controls. Collapsed by default."""
#     with st.sidebar:
#         st.subheader("System status")

#         status = get_config_status()
#         st.caption(f"Model: {status['model_name']}")
#         st.caption(f"Host: {status['ollama_host']}")

#         if st.button("Test connection", use_container_width=True):
#             is_ok, message = check_ollama()
#             st.success(message) if is_ok else st.error(message)

#         graph_keys = ("graph_client_id", "graph_client_secret", "graph_tenant_id")
#         if all(status[key] for key in graph_keys):
#             st.caption("Microsoft Graph: configured")
#         else:
#             st.warning("Microsoft Graph credentials are missing from .env")

#         st.divider()
#         st.caption("Active guardrails")
#         for name in GUARDRAIL_NAMES:
#             st.caption(f"• {name}")

#         st.divider()
#         st.caption(f"Audit log: {LOG_FILE}")

#         if st.session_state.conversation:
#             if st.button("Clear conversation", use_container_width=True):
#                 st.session_state.conversation = []
#                 st.session_state.pending_confirmation = None
#                 st.rerun()

#             st.download_button(
#                 "Download transcript",
#                 data=json.dumps(st.session_state.conversation, indent=2, default=str),
#                 file_name="techadmin_session.json",
#                 mime="application/json",
#                 use_container_width=True,
#             )


# # ---------------------------------------------------------------------------
# # Conversation helpers
# # ---------------------------------------------------------------------------
# def record(role: str, content: Any) -> None:
#     """Append one turn to the transcript."""
#     st.session_state.conversation.append(
#         {
#             "role": role,
#             "content": content,
#             "time": datetime.now().strftime("%H:%M:%S"),
#         }
#     )


# def run_and_render(query: str, confirmed: bool = False, request_id: str = None) -> None:
#     """
#     Run one query and draw both sides of the exchange.

#     Args:
#         query: The user's request.
#         confirmed: True when re-running after the user approved a sensitive
#             operation. The user turn is not repeated in that case.
#         request_id: Reuse the original request ID on a confirmed retry, so both
#             halves share one thread in the audit log.
#     """
#     service = get_service()

#     if not confirmed:
#         with st.chat_message("user"):
#             st.write(query)
#         record("user", query)

#     with st.chat_message("assistant"):
#         with st.spinner("Checking and processing your request..."):
#             response = service.run_query(
#                 query,
#                 confirmed=confirmed,
#                 request_id=request_id,
#             )
#         render_response(response)

#     record("assistant", response)

#     # Park the query so the confirmation buttons know what to re-run.
#     if response.get("confirmation_required"):
#         st.session_state.pending_confirmation = {
#             "query": query,
#             "request_id": response.get("request_id"),
#         }
#     else:
#         st.session_state.pending_confirmation = None


# def render_confirmation_controls() -> None:
#     """Draw Confirm and Cancel for a pending sensitive operation."""
#     pending = st.session_state.pending_confirmation
#     if not pending:
#         return

#     left, right = st.columns(2)

#     if left.button("Confirm and proceed", type="primary", use_container_width=True):
#         query = pending["query"]
#         request_id = pending["request_id"]
#         st.session_state.pending_confirmation = None
#         run_and_render(query, confirmed=True, request_id=request_id)

#     if right.button("Cancel", use_container_width=True):
#         st.session_state.pending_confirmation = None
#         with st.chat_message("assistant"):
#             st.info("Cancelled. No changes were made.")
#         record("assistant", {"message": "Cancelled by user.", "cancelled": True})


# # ---------------------------------------------------------------------------
# # Main
# # ---------------------------------------------------------------------------
# def main() -> None:
#     init_state()
#     st.markdown(STYLES, unsafe_allow_html=True)

#     st.title("TechAdmin IT Support")
#     st.caption("Ask for a user's details or request a password reset.")

#     # Replay the conversation so far.
#     for turn in st.session_state.conversation:
#         with st.chat_message(turn["role"]):
#             content = turn["content"]
#             if turn["role"] == "user":
#                 st.write(content)
#             elif isinstance(content, dict) and content.get("cancelled"):
#                 st.info(content["message"])
#             else:
#                 render_response(content)

#     query = st.session_state.queued_query or st.chat_input(
#         "e.g. Get details for amit.bhagat@coforge.com"
#     )
#     st.session_state.queued_query = None

#     if query:
#         run_and_render(query)
#     elif not st.session_state.conversation:
#         st.markdown(
#             '<div class="ta-card">'
#             '<div class="ta-headline">What would you like to do?</div>'
#             '<div class="ta-body">Try one of these, or type your own request below.</div>'
#             "</div>",
#             unsafe_allow_html=True,
#         )
#         for example in EXAMPLE_QUERIES:
#             if st.button(example, use_container_width=True, key=f"ex_{example}"):
#                 st.session_state.queued_query = example
#                 st.rerun()

#     # Drawn after the transcript so the buttons sit under the latest answer.
#     render_confirmation_controls()

#     # Rendered last so Clear and Download see the updated conversation on the
#     # same run as the first query.
#     render_sidebar()


# if __name__ == "__main__":
#     main()

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
    # "Reset password for aman.gupta",
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
    # --- ADDED FOR CONFIRMATION ---
    # Holds the query and request ID while a sensitive operation waits for the
    # user's approval.
    if "pending_confirmation" not in st.session_state:
        st.session_state.pending_confirmation = None
    # --- END ADDED FOR CONFIRMATION ---


# ---------------------------------------------------------------------------
# Result rendering
# ---------------------------------------------------------------------------
# Graph returns camelCase keys. These are the labels shown in the table, in the
# order they should appear.
# The fields that lead the table, in this order. Everything else Graph returns
# is appended automatically by pick_fields, so nothing is hidden.
USER_DETAIL_FIELDS = [
    ("displayName", "Display name"),
    ("givenName", "First name"),
    ("surname", "Last name"),
    ("userPrincipalName", "User principal name"),
    ("mail", "Mail"),
    ("jobTitle", "Job title"),
    ("department", "Department"),
    ("officeLocation", "Office location"),
    ("mobilePhone", "Mobile phone"),
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
    for key, value in sorted(data.items()):
        if key in known:
            continue

        # Lists and nested objects used to be dropped here, which silently hid
        # Graph fields such as businessPhones and assignedLicenses. They are
        # flattened for display instead, so the table shows everything the API
        # actually returned.
        if isinstance(value, list):
            if not value:
                continue
            value = ", ".join(
                str(item) if not isinstance(item, dict) else json.dumps(item)
                for item in value
            )
        elif isinstance(value, dict):
            if not value:
                continue
            value = json.dumps(value)

        rows.append((key.replace("_", " ").capitalize(), value))

    return rows


def render_result_table(intent: str, result: Dict[str, Any]) -> None:
    """Render the tool's result payload as a table."""
    if intent == "password_reset":
        # The password is shown outside the table rather than inside it, so it
        # gets its own labelled block and a warning instead of sitting in a
        # grid of ordinary values.
        show_table(
            pick_fields(result, PASSWORD_RESET_FIELDS, exclude={"new_password"}),
            "Result",
        )

        temp_password = result.get("new_password")
        if temp_password:
            st.warning(
                "Temporary password — visible for this demo only. "
                "In production this is delivered out of band and never rendered "
                "in a browser."
            )
            st.code(temp_password, language=None)
        else:
            st.caption(
                "Temporary password withheld by policy "
                "(set GUARDRAIL_SHOW_PASSWORD=true to display it)."
            )
        return

    show_table(pick_fields(result, USER_DETAIL_FIELDS), "All details returned by the API")


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
# --- ADDED FOR CONFIRMATION ---
# Words accepted as a typed yes or no, so someone who types "yes" instead of
# clicking the button is not sent round the loop again as a brand new query.
_YES_WORDS = {"yes", "y", "yeah", "yep", "confirm", "confirmed", "proceed", "ok", "okay"}
_NO_WORDS = {"no", "n", "nope", "cancel", "stop", "abort", "nevermind"}


def run_and_render(query: str, confirmed: bool = False, request_id: str = None) -> None:
    """
    Run one query, draw the result, and record the turn.

    Args:
        query: The user's request.
        confirmed: True when re-running after the user approved a sensitive
            operation. The user turn is not repeated in that case, because an
            approval is not a new request.
        request_id: Reuse the original request ID on a confirmed retry, so both
            halves of the exchange share one thread in the audit log.
    """
    service = get_service()
    timestamp = datetime.now().strftime("%H:%M:%S")

    if not confirmed:
        with st.chat_message("user"):
            st.write(query)
        st.session_state.conversation.append(
            {"role": "user", "content": query, "time": timestamp}
        )

    with st.chat_message("assistant"):
        with st.spinner("Checking and running the operation..."):
            response = service.run_query(
                query,
                confirmed=confirmed,
                request_id=request_id,
            )
        render_response(response)

    st.session_state.conversation.append(
        {"role": "assistant", "content": response, "time": timestamp}
    )

    # Park the query so the buttons below know what to re-run on approval.
    if response.get("confirmation_required"):
        st.session_state.pending_confirmation = {
            "query": query,
            "request_id": response.get("request_id"),
        }
    else:
        st.session_state.pending_confirmation = None


def cancel_pending() -> None:
    """Drop a pending confirmation and tell the user nothing happened."""
    st.session_state.pending_confirmation = None
    with st.chat_message("assistant"):
        st.info("Cancelled. No changes were made.")
    st.session_state.conversation.append(
        {
            "role": "assistant",
            "content": {"message": "Cancelled by user.", "cancelled": True},
            "time": datetime.now().strftime("%H:%M:%S"),
        }
    )


def render_confirmation_controls() -> None:
    """
    Draw Confirm and Cancel for a sensitive operation that is waiting.

    Without this the flow returns confirmation_required and the UI has no way
    to answer it, so a password reset can never complete.
    """
    pending = st.session_state.pending_confirmation
    if not pending:
        return

    st.warning("This operation is waiting for your approval.")
    left, right = st.columns(2)

    if left.button("Confirm and proceed", type="primary", use_container_width=True):
        query = pending["query"]
        request_id = pending["request_id"]
        st.session_state.pending_confirmation = None
        run_and_render(query, confirmed=True, request_id=request_id)

    if right.button("Cancel", use_container_width=True):
        cancel_pending()
# --- END ADDED FOR CONFIRMATION ---


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
            content = turn["content"]
            if turn["role"] == "user":
                st.write(content)
            elif isinstance(content, dict) and content.get("cancelled"):
                st.info(content["message"])
            else:
                render_response(content)

    # A queued example takes priority, otherwise use whatever was typed.
    query = st.session_state.queued_query or st.chat_input(
        "e.g. Get details for amit.bhagat@coforge.com"
    )
    st.session_state.queued_query = None

    if query:
        # --- ADDED FOR CONFIRMATION ---
        # A bare "yes" while an operation is waiting is an answer, not a new
        # request. Sending it through the extractor classifies it as an unknown
        # intent, and the reset silently never happens.
        pending = st.session_state.pending_confirmation
        answer = query.strip().lower().rstrip(".!")

        if pending and answer in _YES_WORDS:
            with st.chat_message("user"):
                st.write(query)
            st.session_state.conversation.append(
                {"role": "user", "content": query,
                 "time": datetime.now().strftime("%H:%M:%S")}
            )
            st.session_state.pending_confirmation = None
            run_and_render(
                pending["query"],
                confirmed=True,
                request_id=pending["request_id"],
            )

        elif pending and answer in _NO_WORDS:
            with st.chat_message("user"):
                st.write(query)
            st.session_state.conversation.append(
                {"role": "user", "content": query,
                 "time": datetime.now().strftime("%H:%M:%S")}
            )
            cancel_pending()

        else:
            run_and_render(query)
        # --- END ADDED FOR CONFIRMATION ---

    elif not st.session_state.conversation:
        st.info(
            "Enter a request below, or pick an example from the sidebar.\n\n"
            "Examples:\n"
            "- Get details for amit.bhagat@coforge.com\n"
            # "- Reset password for aman.gupta"
        )

    # --- ADDED FOR CONFIRMATION ---
    # Drawn after the transcript so the buttons sit under the latest answer.
    render_confirmation_controls()
    # --- END ADDED FOR CONFIRMATION ---

    # The sidebar is rendered last, after the conversation has been updated, so
    # the Clear and Download controls appear on the same run as the first query
    # rather than only after the next interaction. Streamlit places this content
    # in the sidebar regardless of when it is called.
    render_sidebar()


if __name__ == "__main__":
    main()

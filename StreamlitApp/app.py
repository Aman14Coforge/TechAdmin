# # """
# # TechAdmin Streamlit UI with guardrail confirmation and session password display.

# # Features:
# #     - Structured tables only for workflow results.
# #     - Guardrail confirmation controls for sensitive operations.
# #     - Reuses request ID and correlation ID after confirmation.
# #     - Displays generated temporary passwords in a dedicated session panel.
# #     - Removes the dashboard-only secret before conversation history and JSON download.
# #     - Supports Microsoft Graph and PowerShell result shapes.
# #     - Avoids conditional Streamlit expressions that can render DeltaGenerator details.

# # Run from the project root:
# #     python -m streamlit run StreamlitApp/app.py
# # """

# # from __future__ import annotations

# # import copy
# # import json
# # from datetime import datetime
# # from typing import Any, Dict, Iterable

# # import pandas as pd
# # import streamlit as st

# # from flow_service import (
# #     LOG_FILE,
# #     FlowService,
# #     check_ollama,
# #     get_config_status,
# # )


# # # ---------------------------------------------------------------------------
# # # Page configuration
# # # ---------------------------------------------------------------------------

# # st.set_page_config(
# #     page_title="TechAdmin IT Support",
# #     page_icon="🛠️",
# #     layout="centered",
# # )


# # EXAMPLES = [
# #     "Get user details for Shreesanyog.Rath@Coforge.com",
# #     "Get user details for Shreesanyog.Rath@Coforge.com via script",
# #     "Get user details for Shreesanyog.Rath@Coforge.com via API",
# #     "Reset password for MigrationTest2@Coforge.com",
# #     "Reset password for MigrationTest2@Coforge.com via script",
# #     "Add user MigrationTest2@Coforge.com to group TechAI_Group",
# #     "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
# # ]

# # YES_WORDS = {
# #     "yes",
# #     "y",
# #     "confirm",
# #     "confirmed",
# #     "proceed",
# #     "approve",
# #     "approved",
# #     "ok",
# #     "okay",
# # }

# # NO_WORDS = {
# #     "no",
# #     "n",
# #     "cancel",
# #     "stop",
# #     "abort",
# #     "nevermind",
# # }

# # SENSITIVE_HISTORY_KEYS = {
# #     "new_password",
# #     "temporary_password",
# #     "password",
# #     "initial_password",
# #     "domain_password",
# #     "admin_password",
# #     "client_secret",
# #     "access_token",
# #     "refresh_token",
# #     "_dashboard_secret",
# # }


# # # ---------------------------------------------------------------------------
# # # Service and session state
# # # ---------------------------------------------------------------------------


# # @st.cache_resource(show_spinner="Starting TechAdmin...")
# # def get_service() -> FlowService:
# #     """Create and cache the workflow service."""

# #     return FlowService()


# # def init_state() -> None:
# #     """Initialize the Streamlit session keys used by the application."""

# #     st.session_state.setdefault("conversation", [])
# #     st.session_state.setdefault("queued_query", None)
# #     st.session_state.setdefault("pending_confirmation", None)
# #     st.session_state.setdefault("password_cards", [])
# #     st.session_state.setdefault("ollama_check_result", None)


# # # ---------------------------------------------------------------------------
# # # Generic data and table helpers
# # # ---------------------------------------------------------------------------


# # def display_text(value: Any) -> str:
# #     """Convert a value into readable table text."""

# #     if value is None or value == "":
# #         return "—"

# #     if isinstance(value, bool):
# #         return "Yes" if value else "No"

# #     return str(value)


# # def show_table(
# #     rows: Iterable[tuple[str, Any]],
# #     caption: str = "",
# # ) -> None:
# #     """Render a two-column Field/Value table."""

# #     prepared_rows = [
# #         (label, value)
# #         for label, value in rows
# #         if value not in (None, "")
# #     ]

# #     if not prepared_rows:
# #         return

# #     if caption:
# #         st.markdown(f"**{caption}**")

# #     frame = pd.DataFrame(
# #         [
# #             {
# #                 "Field": label,
# #                 "Value": display_text(value),
# #             }
# #             for label, value in prepared_rows
# #         ]
# #     )

# #     st.dataframe(
# #         frame,
# #         hide_index=True,
# #         width="stretch",
# #     )


# # def flatten_rows(
# #     data: Dict[str, Any],
# #     excluded: set[str] | None = None,
# # ) -> list[tuple[str, Any]]:
# #     """Convert a dictionary into readable rows without dropping nested data."""

# #     excluded_keys = excluded or set()
# #     rows: list[tuple[str, Any]] = []

# #     for key, value in data.items():
# #         if key in excluded_keys or value in (None, ""):
# #             continue

# #         if isinstance(value, (dict, list)):
# #             value = json.dumps(
# #                 value,
# #                 ensure_ascii=False,
# #                 default=str,
# #             )

# #         rows.append(
# #             (
# #                 key.replace("_", " ").capitalize(),
# #                 value,
# #             )
# #         )

# #     return rows


# # def redact_sensitive_history(value: Any) -> Any:
# #     """Remove plaintext credentials from conversation history and downloads."""

# #     if isinstance(value, dict):
# #         cleaned: dict[str, Any] = {}

# #         for key, item in value.items():
# #             normalized_key = key.strip().casefold()

# #             if normalized_key in SENSITIVE_HISTORY_KEYS:
# #                 if normalized_key != "_dashboard_secret":
# #                     cleaned[key] = "[redacted]"
# #                 continue

# #             cleaned[key] = redact_sensitive_history(item)

# #         return cleaned

# #     if isinstance(value, list):
# #         return [redact_sensitive_history(item) for item in value]

# #     return value


# # # ---------------------------------------------------------------------------
# # # Temporary-password dashboard
# # # ---------------------------------------------------------------------------


# # def register_dashboard_secret(response: Dict[str, Any]) -> bool:
# #     """
# #     Move `_dashboard_secret` from the response into current session state.

# #     FlowService must create `_dashboard_secret` before returning the response.
# #     This function removes that field before the response is added to normal
# #     conversation history or shown as raw JSON.
# #     """

# #     secret = response.pop("_dashboard_secret", None)

# #     if not isinstance(secret, dict):
# #         return False

# #     password = secret.get("password")

# #     if (
# #         not isinstance(password, str)
# #         or not password
# #         or password.casefold() == "[redacted]"
# #     ):
# #         return False

# #     password_card = {
# #         "password": password,
# #         "user": secret.get("user") or "Unknown user",
# #         "backend": secret.get("backend") or "unknown",
# #         "operation_id": secret.get("operation_id"),
# #         "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
# #     }

# #     st.session_state.password_cards.insert(0, password_card)
# #     return True


# # def render_password_cards() -> None:
# #     """Display generated temporary passwords during the current UI session."""

# #     cards = st.session_state.password_cards

# #     if not cards:
# #         return

# #     st.markdown("### Generated temporary passwords")

# #     for index, card in enumerate(list(cards)):
# #         with st.container(border=True):
# #             show_table(
# #                 [
# #                     ("Account", card.get("user")),
# #                     ("Backend", card.get("backend")),
# #                     ("Generated", card.get("created_at")),
# #                     ("Operation ID", card.get("operation_id")),
# #                 ]
# #             )

# #             st.markdown("**Temporary password**")
# #             st.code(
# #                 card.get("password") or "",
# #                 language=None,
# #             )

# #             if st.button(
# #                 "Remove password",
# #                 key=f"remove_password_{index}",
# #                 width="content",
# #             ):
# #                 st.session_state.password_cards.pop(index)
# #                 st.rerun()

# #     if st.button(
# #         "Clear displayed passwords",
# #         type="secondary",
# #         width="content",
# #     ):
# #         st.session_state.password_cards = []
# #         st.rerun()

# #     st.divider()


# # # ---------------------------------------------------------------------------
# # # Workflow result rendering
# # # ---------------------------------------------------------------------------


# # def render_script_execution(execution: Dict[str, Any]) -> None:
# #     """Render PowerShell execution evidence."""

# #     show_table(
# #         [
# #             ("Success", execution.get("success")),
# #             ("Operation", execution.get("operation")),
# #             ("Script", execution.get("script_name")),
# #             ("Exit code", execution.get("exit_code")),
# #             ("Duration seconds", execution.get("duration_seconds")),
# #             ("Dry run", execution.get("dry_run")),
# #             ("Standard output", execution.get("stdout")),
# #             ("Standard error", execution.get("stderr")),
# #             ("Error", execution.get("error")),
# #         ],
# #         "Script execution",
# #     )


# # def render_guardrails(response: Dict[str, Any]) -> None:
# #     """Render guardrail decisions and violations as tables."""

# #     show_table(
# #         [
# #             ("Action", response.get("guardrail_action")),
# #             ("Blocked", response.get("guardrail_blocked")),
# #             ("Confirmation required", response.get("confirmation_required")),
# #             ("Confirmation prompt", response.get("confirmation_prompt")),
# #             ("Output filtered fields", response.get("guardrails_output_filtered")),
# #         ],
# #         "Guardrails",
# #     )

# #     violations = response.get("guardrail_violations")

# #     if not isinstance(violations, list):
# #         return

# #     for index, violation in enumerate(violations, start=1):
# #         if isinstance(violation, dict):
# #             show_table(
# #                 flatten_rows(violation),
# #                 f"Guardrail violation {index}",
# #             )


# # def render_result(intent: str, result: Dict[str, Any]) -> None:
# #     """Render API or script operation results."""

# #     execution = result.get("execution")
# #     user_record = result.get("user")

# #     excluded = {
# #         "execution",
# #         "user",
# #         "new_password",
# #         "temporary_password",
# #     }

# #     if isinstance(user_record, dict):
# #         result_rows = [("Backend", result.get("backend"))]
# #         result_rows.extend(flatten_rows(user_record))
# #     else:
# #         result_rows = flatten_rows(result, excluded)

# #     show_table(result_rows, "Result")

# #     if isinstance(execution, dict):
# #         render_script_execution(execution)

# #     if intent == "password_reset":
# #         redacted_value = (
# #             result.get("new_password")
# #             or result.get("temporary_password")
# #         )

# #         if redacted_value == "[redacted]":
# #             show_table(
# #                 [
# #                     (
# #                         "Password display",
# #                         (
# #                             "The normal response is redacted. The generated "
# #                             "password appears in the dashboard panel only when "
# #                             "FlowService receives the original value before "
# #                             "output sanitization."
# #                         ),
# #                     )
# #                 ],
# #                 "Password status",
# #             )


# # def render_response(response: Dict[str, Any]) -> None:
# #     """Render workflow data without success/error notification boxes."""

# #     confidence = response.get("confidence")

# #     show_table(
# #         [
# #             ("Succeeded", response.get("success")),
# #             ("Intent", response.get("intent")),
# #             (
# #                 "Confidence",
# #                 (
# #                     f"{confidence:.0%}"
# #                     if isinstance(confidence, (int, float))
# #                     else None
# #                 ),
# #             ),
# #             ("Request ID", response.get("request_id")),
# #             ("Correlation ID", response.get("correlation_id")),
# #             ("Explanation", response.get("explanation")),
# #             ("Message", response.get("message")),
# #             ("Error", response.get("error")),
# #         ],
# #         "Summary",
# #     )

# #     metadata = response.get("metadata")

# #     if isinstance(metadata, dict):
# #         show_table(
# #             flatten_rows(metadata),
# #             "Extracted metadata",
# #         )

# #     render_guardrails(response)

# #     show_table(
# #         [
# #             ("Agent", response.get("selected_agent")),
# #             ("MCP server", response.get("selected_mcp_server")),
# #             ("MCP tool", response.get("selected_mcp_tool")),
# #             ("Application tool", response.get("selected_tool")),
# #         ],
# #         "Routing",
# #     )

# #     execution_context = response.get("execution_context")

# #     if isinstance(execution_context, dict):
# #         show_table(
# #             flatten_rows(execution_context),
# #             "Execution context",
# #         )

# #     tool_result = response.get("tool_result")

# #     if isinstance(tool_result, dict) and tool_result:
# #         show_table(
# #             [
# #                 ("Tool name", tool_result.get("tool_name")),
# #                 ("Status", tool_result.get("status")),
# #                 ("Operation ID", tool_result.get("operation_id")),
# #                 ("Succeeded", tool_result.get("success")),
# #                 ("Message", tool_result.get("message")),
# #                 ("Error", tool_result.get("error")),
# #                 ("API integration pending", tool_result.get("api_integration_pending")),
# #             ],
# #             "Tool execution",
# #         )

# #         result = tool_result.get("result")

# #         if isinstance(result, dict):
# #             render_result(
# #                 response.get("intent") or "",
# #                 result,
# #             )

# #     with st.expander("Raw response (JSON)"):
# #         st.json(response)


# # # ---------------------------------------------------------------------------
# # # Confirmation workflow
# # # ---------------------------------------------------------------------------


# # def set_pending_confirmation(
# #     response: Dict[str, Any],
# #     query: str,
# # ) -> None:
# #     """Store a request while guardrails wait for operator confirmation."""

# #     if response.get("confirmation_required"):
# #         st.session_state.pending_confirmation = {
# #             "query": query,
# #             "request_id": response.get("request_id"),
# #             "correlation_id": response.get("correlation_id"),
# #             "intent": response.get("intent"),
# #             "prompt": response.get("confirmation_prompt"),
# #         }
# #     else:
# #         st.session_state.pending_confirmation = None


# # def append_conversation(
# #     role: str,
# #     content: Any,
# #     timestamp: str,
# # ) -> None:
# #     """Append a password-safe conversation item."""

# #     st.session_state.conversation.append(
# #         {
# #             "role": role,
# #             "content": redact_sensitive_history(
# #                 copy.deepcopy(content)
# #             ),
# #             "time": timestamp,
# #         }
# #     )


# # def execute_and_render(
# #     query: str,
# #     *,
# #     confirmed: bool = False,
# #     request_id: str | None = None,
# #     correlation_id: str | None = None,
# #     add_user_turn: bool = True,
# # ) -> Dict[str, Any]:
# #     """Execute one workflow request and save the password-safe result."""

# #     timestamp = datetime.now().strftime("%H:%M:%S")

# #     if add_user_turn:
# #         with st.chat_message("user"):
# #             st.write(query)

# #         append_conversation(
# #             "user",
# #             query,
# #             timestamp,
# #         )

# #     with st.chat_message("assistant"):
# #         with st.spinner("Checking and running the operation..."):
# #             response = get_service().run_query(
# #                 query,
# #                 confirmed=confirmed,
# #                 request_id=request_id,
# #                 correlation_id=correlation_id,
# #             )

# #         register_dashboard_secret(response)
# #         render_response(response)

# #     append_conversation(
# #         "assistant",
# #         response,
# #         timestamp,
# #     )

# #     set_pending_confirmation(response, query)
# #     return response


# # def cancel_pending_confirmation() -> None:
# #     """Cancel the pending operation without running the tool."""

# #     pending = st.session_state.pending_confirmation
# #     st.session_state.pending_confirmation = None

# #     response = {
# #         "success": False,
# #         "cancelled": True,
# #         "request_id": (
# #             pending.get("request_id")
# #             if isinstance(pending, dict)
# #             else None
# #         ),
# #         "correlation_id": (
# #             pending.get("correlation_id")
# #             if isinstance(pending, dict)
# #             else None
# #         ),
# #         "intent": (
# #             pending.get("intent")
# #             if isinstance(pending, dict)
# #             else None
# #         ),
# #         "message": "Operation cancelled. No changes were made.",
# #         "error": None,
# #     }

# #     append_conversation(
# #         "assistant",
# #         response,
# #         datetime.now().strftime("%H:%M:%S"),
# #     )

# #     st.rerun()


# # def render_confirmation_controls() -> None:
# #     """Render trusted confirmation controls for a pending operation."""

# #     pending = st.session_state.pending_confirmation

# #     if not isinstance(pending, dict):
# #         return

# #     with st.container(border=True):
# #         st.markdown("**Approval required**")
# #         st.write(
# #             pending.get("prompt")
# #             or "Confirm this operation before continuing."
# #         )

# #         confirm_column, cancel_column = st.columns(2)

# #         if confirm_column.button(
# #             "Confirm and proceed",
# #             type="primary",
# #             width="stretch",
# #         ):
# #             st.session_state.pending_confirmation = None

# #             execute_and_render(
# #                 pending["query"],
# #                 confirmed=True,
# #                 request_id=pending.get("request_id"),
# #                 correlation_id=pending.get("correlation_id"),
# #                 add_user_turn=False,
# #             )

# #             st.rerun()

# #         if cancel_column.button(
# #             "Cancel",
# #             width="stretch",
# #         ):
# #             cancel_pending_confirmation()


# # # ---------------------------------------------------------------------------
# # # Sidebar
# # # ---------------------------------------------------------------------------


# # def safe_conversation_download() -> str:
# #     """Serialize password-safe conversation history."""

# #     return json.dumps(
# #         redact_sensitive_history(
# #             copy.deepcopy(st.session_state.conversation)
# #         ),
# #         indent=2,
# #         ensure_ascii=False,
# #         default=str,
# #     )


# # def render_sidebar() -> None:
# #     """Render environment, examples, and session controls."""

# #     with st.sidebar:
# #         st.header("Environment")

# #         status = get_config_status()
# #         show_table(flatten_rows(status))

# #         if st.button(
# #             "Test Ollama connection",
# #             width="stretch",
# #         ):
# #             connected, message = check_ollama()
# #             st.session_state.ollama_check_result = {
# #                 "connected": connected,
# #                 "message": message,
# #             }

# #         ollama_result = st.session_state.ollama_check_result

# #         if isinstance(ollama_result, dict):
# #             show_table(flatten_rows(ollama_result))

# #         st.divider()
# #         st.caption("Example queries")

# #         for index, example in enumerate(EXAMPLES):
# #             if st.button(
# #                 example,
# #                 key=f"example_{index}",
# #                 width="stretch",
# #             ):
# #                 st.session_state.queued_query = example
# #                 st.rerun()

# #         st.divider()
# #         st.caption(f"Logs: {LOG_FILE}")

# #         if st.session_state.conversation:
# #             if st.button(
# #                 "Clear conversation",
# #                 width="stretch",
# #             ):
# #                 st.session_state.conversation = []
# #                 st.session_state.pending_confirmation = None
# #                 st.rerun()

# #             st.download_button(
# #                 "Download as JSON",
# #                 data=safe_conversation_download(),
# #                 file_name="techadmin_session.json",
# #                 mime="application/json",
# #                 width="stretch",
# #             )


# # # ---------------------------------------------------------------------------
# # # Main application
# # # ---------------------------------------------------------------------------


# # def main() -> None:
# #     """Run the TechAdmin Streamlit application."""

# #     init_state()

# #     st.title("🛠️ TechAdmin IT Support")
# #     st.caption(
# #         "Guardrailed identity operations through Microsoft Graph and PowerShell."
# #     )

# #     render_password_cards()

# #     for turn in st.session_state.conversation:
# #         with st.chat_message(turn["role"]):
# #             if turn["role"] == "user":
# #                 st.write(turn["content"])
# #             elif isinstance(turn["content"], dict):
# #                 render_response(turn["content"])

# #     query = (
# #         st.session_state.queued_query
# #         or st.chat_input("Type an identity operation...")
# #     )

# #     st.session_state.queued_query = None

# #     if query:
# #         pending = st.session_state.pending_confirmation
# #         normalized_answer = query.strip().casefold().rstrip(".!")

# #         if isinstance(pending, dict) and normalized_answer in YES_WORDS:
# #             append_conversation(
# #                 "user",
# #                 query,
# #                 datetime.now().strftime("%H:%M:%S"),
# #             )

# #             st.session_state.pending_confirmation = None

# #             execute_and_render(
# #                 pending["query"],
# #                 confirmed=True,
# #                 request_id=pending.get("request_id"),
# #                 correlation_id=pending.get("correlation_id"),
# #                 add_user_turn=False,
# #             )

# #         elif isinstance(pending, dict) and normalized_answer in NO_WORDS:
# #             append_conversation(
# #                 "user",
# #                 query,
# #                 datetime.now().strftime("%H:%M:%S"),
# #             )
# #             cancel_pending_confirmation()

# #         else:
# #             execute_and_render(query)

# #         st.rerun()

# #     render_confirmation_controls()
# #     render_sidebar()


# # if __name__ == "__main__":
# #     main()


# """
# TechAdmin Streamlit UI with guardrail confirmation and session password display.

# Features:
#     - Structured tables only for workflow results.
#     - Guardrail confirmation controls for sensitive operations.
#     - Reuses request ID and correlation ID after confirmation.
#     - Displays generated temporary passwords in a dedicated session panel.
#     - Removes the dashboard-only secret before conversation history and JSON download.
#     - Supports Microsoft Graph and PowerShell result shapes.
#     - Avoids conditional Streamlit expressions that can render DeltaGenerator details.

# Run from the project root:
#     python -m streamlit run StreamlitApp/app.py
# """

# from __future__ import annotations

# import copy
# import json
# from datetime import datetime
# from typing import Any, Dict, Iterable

# import pandas as pd
# import streamlit as st

# from flow_service import (
#     LOG_FILE,
#     FlowService,
#     check_ollama,
#     get_config_status,
# )

# # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# from flow_service import (
#     build_password_download,
#     email_is_configured,
#     send_password_to_manager,
# )
# # --- END ADDED FOR PASSWORD ENHANCEMENTS ---


# # ---------------------------------------------------------------------------
# # Page configuration
# # ---------------------------------------------------------------------------

# st.set_page_config(
#     page_title="TechAdmin IT Support",
#     page_icon="🛠️",
#     layout="centered",
# )


# EXAMPLES = [
#     "Get user details for Shreesanyog.Rath@Coforge.com",
#     "Get user details for Shreesanyog.Rath@Coforge.com via script",
#     "Get user details for Shreesanyog.Rath@Coforge.com via API",
#     "Reset password for MigrationTest2@Coforge.com",
#     "Reset password for MigrationTest2@Coforge.com via script",
#     "Add user MigrationTest2@Coforge.com to group TechAI_Group",
#     "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
# ]

# YES_WORDS = {
#     "yes",
#     "y",
#     "confirm",
#     "confirmed",
#     "proceed",
#     "approve",
#     "approved",
#     "ok",
#     "okay",
# }

# NO_WORDS = {
#     "no",
#     "n",
#     "cancel",
#     "stop",
#     "abort",
#     "nevermind",
# }

# SENSITIVE_HISTORY_KEYS = {
#     "new_password",
#     "temporary_password",
#     "password",
#     "initial_password",
#     "domain_password",
#     "admin_password",
#     "client_secret",
#     "access_token",
#     "refresh_token",
#     "_dashboard_secret",
# }


# # ---------------------------------------------------------------------------
# # Service and session state
# # ---------------------------------------------------------------------------


# @st.cache_resource(show_spinner="Starting TechAdmin...")
# def get_service() -> FlowService:
#     """Create and cache the workflow service."""

#     return FlowService()


# def init_state() -> None:
#     """Initialize the Streamlit session keys used by the application."""

#     st.session_state.setdefault("conversation", [])
#     st.session_state.setdefault("queued_query", None)
#     st.session_state.setdefault("pending_confirmation", None)
#     st.session_state.setdefault("password_cards", [])
#     st.session_state.setdefault("ollama_check_result", None)


# # ---------------------------------------------------------------------------
# # Generic data and table helpers
# # ---------------------------------------------------------------------------


# def display_text(value: Any) -> str:
#     """Convert a value into readable table text."""

#     if value is None or value == "":
#         return "—"

#     if isinstance(value, bool):
#         return "Yes" if value else "No"

#     return str(value)


# def show_table(
#     rows: Iterable[tuple[str, Any]],
#     caption: str = "",
# ) -> None:
#     """Render a two-column Field/Value table."""

#     prepared_rows = [
#         (label, value)
#         for label, value in rows
#         if value not in (None, "")
#     ]

#     if not prepared_rows:
#         return

#     if caption:
#         st.markdown(f"**{caption}**")

#     frame = pd.DataFrame(
#         [
#             {
#                 "Field": label,
#                 "Value": display_text(value),
#             }
#             for label, value in prepared_rows
#         ]
#     )

#     st.dataframe(
#         frame,
#         hide_index=True,
#         width="stretch",
#     )


# def flatten_rows(
#     data: Dict[str, Any],
#     excluded: set[str] | None = None,
# ) -> list[tuple[str, Any]]:
#     """Convert a dictionary into readable rows without dropping nested data."""

#     excluded_keys = excluded or set()
#     rows: list[tuple[str, Any]] = []

#     for key, value in data.items():
#         if key in excluded_keys or value in (None, ""):
#             continue

#         if isinstance(value, (dict, list)):
#             value = json.dumps(
#                 value,
#                 ensure_ascii=False,
#                 default=str,
#             )

#         rows.append(
#             (
#                 key.replace("_", " ").capitalize(),
#                 value,
#             )
#         )

#     return rows


# def redact_sensitive_history(value: Any) -> Any:
#     """Remove plaintext credentials from conversation history and downloads."""

#     if isinstance(value, dict):
#         cleaned: dict[str, Any] = {}

#         for key, item in value.items():
#             normalized_key = key.strip().casefold()

#             if normalized_key in SENSITIVE_HISTORY_KEYS:
#                 if normalized_key != "_dashboard_secret":
#                     cleaned[key] = "[redacted]"
#                 continue

#             cleaned[key] = redact_sensitive_history(item)

#         return cleaned

#     if isinstance(value, list):
#         return [redact_sensitive_history(item) for item in value]

#     return value


# # ---------------------------------------------------------------------------
# # Temporary-password dashboard
# # ---------------------------------------------------------------------------


# def register_dashboard_secret(response: Dict[str, Any]) -> bool:
#     """
#     Move `_dashboard_secret` from the response into current session state.

#     FlowService must create `_dashboard_secret` before returning the response.
#     This function removes that field before the response is added to normal
#     conversation history or shown as raw JSON.
#     """

#     secret = response.pop("_dashboard_secret", None)

#     if not isinstance(secret, dict):
#         return False

#     password = secret.get("password")

#     if (
#         not isinstance(password, str)
#         or not password
#         or password.casefold() == "[redacted]"
#     ):
#         return False

#     password_card = {
#         "password": password,
#         "user": secret.get("user") or "Unknown user",
#         "backend": secret.get("backend") or "unknown",
#         "operation_id": secret.get("operation_id"),
#         "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
#     }

#     st.session_state.password_cards.insert(0, password_card)
#     return True


# def render_password_cards() -> None:
#     """Display generated temporary passwords during the current UI session."""

#     cards = st.session_state.password_cards

#     if not cards:
#         return

#     st.markdown("### Generated temporary passwords")

#     for index, card in enumerate(list(cards)):
#         with st.container(border=True):
#             show_table(
#                 [
#                     ("Account", card.get("user")),
#                     ("Backend", card.get("backend")),
#                     ("Generated", card.get("created_at")),
#                     ("Operation ID", card.get("operation_id")),
#                 ]
#             )

#             st.markdown("**Temporary password**")
#             st.code(
#                 card.get("password") or "",
#                 language=None,
#             )

#             if st.button(
#                 "Remove password",
#                 key=f"remove_password_{index}",
#                 width="content",
#             ):
#                 st.session_state.password_cards.pop(index)
#                 st.rerun()

#     if st.button(
#         "Clear displayed passwords",
#         type="secondary",
#         width="content",
#     ):
#         st.session_state.password_cards = []
#         st.rerun()

#     st.divider()


# # ---------------------------------------------------------------------------
# # Workflow result rendering
# # ---------------------------------------------------------------------------


# def render_script_execution(execution: Dict[str, Any]) -> None:
#     """Render PowerShell execution evidence."""

#     show_table(
#         [
#             ("Success", execution.get("success")),
#             ("Operation", execution.get("operation")),
#             ("Script", execution.get("script_name")),
#             ("Exit code", execution.get("exit_code")),
#             ("Duration seconds", execution.get("duration_seconds")),
#             ("Dry run", execution.get("dry_run")),
#             ("Standard output", execution.get("stdout")),
#             ("Standard error", execution.get("stderr")),
#             ("Error", execution.get("error")),
#         ],
#         "Script execution",
#     )


# def render_guardrails(response: Dict[str, Any]) -> None:
#     """Render guardrail decisions and violations as tables."""

#     show_table(
#         [
#             ("Action", response.get("guardrail_action")),
#             ("Blocked", response.get("guardrail_blocked")),
#             ("Confirmation required", response.get("confirmation_required")),
#             ("Confirmation prompt", response.get("confirmation_prompt")),
#             ("Output filtered fields", response.get("guardrails_output_filtered")),
#         ],
#         "Guardrails",
#     )

#     violations = response.get("guardrail_violations")

#     if not isinstance(violations, list):
#         return

#     for index, violation in enumerate(violations, start=1):
#         if isinstance(violation, dict):
#             show_table(
#                 flatten_rows(violation),
#                 f"Guardrail violation {index}",
#             )


# # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# def render_password_reset_actions(result: Dict[str, Any]) -> None:
#     """
#     Show the outcome of a password reset.

#     Displays the masked password, the manager, and the two operator actions.
#     The original password is not present in `result` at all: the tool returns a
#     masked form plus an opaque token, and the token is what the buttons use.

#     Args:
#         result: The tool result payload from the reset.
#     """
#     st.success("Password Reset Successful")

#     manager_name = result.get("manager_name") or "Not Available"
#     manager_email = result.get("manager_email") or "Not Available"

#     show_table(
#         [
#             ("Username", result.get("user_name") or result.get("user_principal_name")),
#             ("Employee name", result.get("employee_name")),
#             ("Temporary password", result.get("masked_password") or "Not Available"),
#             ("Manager", manager_name),
#             ("Manager email", manager_email),
#             ("Backend", result.get("backend")),
#         ],
#         "Result",
#     )

#     execution = result.get("execution")
#     if isinstance(execution, dict):
#         render_script_execution(execution)

#     if manager_name == "Not Available":
#         st.info(
#             "No manager is assigned to this account, so the email option is "
#             "unavailable. The password file can still be downloaded."
#         )

#     token = result.get("password_token")

#     if not token:
#         st.warning(
#             "The password is no longer retrievable for this reset, so the "
#             "download and email actions are unavailable."
#         )
#         return

#     render_password_actions(token, manager_email)


# def render_password_actions(token: str, manager_email: str) -> None:
#     """
#     Draw the Send Email and Download buttons for a completed reset.

#     Both actions are explicit. Nothing is emailed as a side effect of the reset
#     itself; the mail goes out only when the operator presses the button.

#     Args:
#         token: The password token from the reset result.
#         manager_email: Recipient, or "Not Available".
#     """
#     # Keyed by token so two resets in one session keep separate buttons and
#     # separate status lines.
#     status_key = f"email_status_{token}"
#     file_key = f"password_file_{token}"
#     st.session_state.setdefault(status_key, None)

#     can_email = bool(manager_email) and manager_email != "Not Available"

#     left, right = st.columns(2)

#     if left.button(
#         "Send Email To Manager",
#         key=f"send_{token}",
#         disabled=not can_email,
#     ):
#         with st.spinner("Sending email..."):
#             sent, message, recipient = send_password_to_manager(token)
#         st.session_state[status_key] = {
#             "sent": sent,
#             "message": message,
#             "recipient": recipient,
#         }

#     # The file is built only when the operator asks for it, so an unused reset
#     # never materialises the password into a downloadable payload.
#     if right.button("Prepare Password TXT", key=f"prep_{token}"):
#         ok, filename, content, message = build_password_download(token)
#         if ok:
#             st.session_state[file_key] = {"name": filename, "content": content}
#         else:
#             st.session_state[file_key] = None
#             st.error(message)

#     prepared = st.session_state.get(file_key)
#     if prepared:
#         st.download_button(
#             "Download Password TXT",
#             data=prepared["content"],
#             file_name=prepared["name"],
#             mime="text/plain",
#             key=f"dl_{token}",
#         )

#     status = st.session_state.get(status_key)

#     if status is None:
#         st.caption("Email status: Not Sent")
#     elif status["sent"]:
#         st.success(f"Email status: Sent Successfully to {status['recipient']}")
#     else:
#         # A failed send is reported but does not undo the reset, which has
#         # already succeeded. The TXT download stays available.
#         st.error(f"Email status: Failed. {status['message']}")
# # --- END ADDED FOR PASSWORD ENHANCEMENTS ---


# def render_result(intent: str, result: Dict[str, Any]) -> None:
#     """Render API or script operation results."""

#     execution = result.get("execution")
#     user_record = result.get("user")

#     excluded = {
#         "execution",
#         "user",
#         "new_password",
#         "temporary_password",
#     }

#     if isinstance(user_record, dict):
#         result_rows = [("Backend", result.get("backend"))]
#         result_rows.extend(flatten_rows(user_record))
#     else:
#         result_rows = flatten_rows(result, excluded)

#     show_table(result_rows, "Result")

#     if isinstance(execution, dict):
#         render_script_execution(execution)

#     # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
#     if intent == "password_reset" and result.get("password_token"):
#         render_password_reset_actions(result)
#         return
#     # --- END ADDED FOR PASSWORD ENHANCEMENTS ---

#     if intent == "password_reset":
#         redacted_value = (
#             result.get("new_password")
#             or result.get("temporary_password")
#         )

#         if redacted_value == "[redacted]":
#             show_table(
#                 [
#                     (
#                         "Password display",
#                         (
#                             "The normal response is redacted. The generated "
#                             "password appears in the dashboard panel only when "
#                             "FlowService receives the original value before "
#                             "output sanitization."
#                         ),
#                     )
#                 ],
#                 "Password status",
#             )


# def render_response(response: Dict[str, Any]) -> None:
#     """Render workflow data without success/error notification boxes."""

#     confidence = response.get("confidence")

#     show_table(
#         [
#             ("Succeeded", response.get("success")),
#             ("Intent", response.get("intent")),
#             (
#                 "Confidence",
#                 (
#                     f"{confidence:.0%}"
#                     if isinstance(confidence, (int, float))
#                     else None
#                 ),
#             ),
#             ("Request ID", response.get("request_id")),
#             ("Correlation ID", response.get("correlation_id")),
#             ("Explanation", response.get("explanation")),
#             ("Message", response.get("message")),
#             ("Error", response.get("error")),
#         ],
#         "Summary",
#     )

#     metadata = response.get("metadata")

#     if isinstance(metadata, dict):
#         show_table(
#             flatten_rows(metadata),
#             "Extracted metadata",
#         )

#     render_guardrails(response)

#     show_table(
#         [
#             ("Agent", response.get("selected_agent")),
#             ("MCP server", response.get("selected_mcp_server")),
#             ("MCP tool", response.get("selected_mcp_tool")),
#             ("Application tool", response.get("selected_tool")),
#         ],
#         "Routing",
#     )

#     execution_context = response.get("execution_context")

#     if isinstance(execution_context, dict):
#         show_table(
#             flatten_rows(execution_context),
#             "Execution context",
#         )

#     tool_result = response.get("tool_result")

#     if isinstance(tool_result, dict) and tool_result:
#         show_table(
#             [
#                 ("Tool name", tool_result.get("tool_name")),
#                 ("Status", tool_result.get("status")),
#                 ("Operation ID", tool_result.get("operation_id")),
#                 ("Succeeded", tool_result.get("success")),
#                 ("Message", tool_result.get("message")),
#                 ("Error", tool_result.get("error")),
#                 ("API integration pending", tool_result.get("api_integration_pending")),
#             ],
#             "Tool execution",
#         )

#         result = tool_result.get("result")

#         if isinstance(result, dict):
#             render_result(
#                 response.get("intent") or "",
#                 result,
#             )

#     with st.expander("Raw response (JSON)"):
#         st.json(response)


# # ---------------------------------------------------------------------------
# # Confirmation workflow
# # ---------------------------------------------------------------------------


# def set_pending_confirmation(
#     response: Dict[str, Any],
#     query: str,
# ) -> None:
#     """Store a request while guardrails wait for operator confirmation."""

#     if response.get("confirmation_required"):
#         st.session_state.pending_confirmation = {
#             "query": query,
#             "request_id": response.get("request_id"),
#             "correlation_id": response.get("correlation_id"),
#             "intent": response.get("intent"),
#             "prompt": response.get("confirmation_prompt"),
#         }
#     else:
#         st.session_state.pending_confirmation = None


# def append_conversation(
#     role: str,
#     content: Any,
#     timestamp: str,
# ) -> None:
#     """Append a password-safe conversation item."""

#     st.session_state.conversation.append(
#         {
#             "role": role,
#             "content": redact_sensitive_history(
#                 copy.deepcopy(content)
#             ),
#             "time": timestamp,
#         }
#     )


# def execute_and_render(
#     query: str,
#     *,
#     confirmed: bool = False,
#     request_id: str | None = None,
#     correlation_id: str | None = None,
#     add_user_turn: bool = True,
# ) -> Dict[str, Any]:
#     """Execute one workflow request and save the password-safe result."""

#     timestamp = datetime.now().strftime("%H:%M:%S")

#     if add_user_turn:
#         with st.chat_message("user"):
#             st.write(query)

#         append_conversation(
#             "user",
#             query,
#             timestamp,
#         )

#     with st.chat_message("assistant"):
#         with st.spinner("Checking and running the operation..."):
#             response = get_service().run_query(
#                 query,
#                 confirmed=confirmed,
#                 request_id=request_id,
#                 correlation_id=correlation_id,
#             )

#         register_dashboard_secret(response)
#         render_response(response)

#     append_conversation(
#         "assistant",
#         response,
#         timestamp,
#     )

#     set_pending_confirmation(response, query)
#     return response


# def cancel_pending_confirmation() -> None:
#     """Cancel the pending operation without running the tool."""

#     pending = st.session_state.pending_confirmation
#     st.session_state.pending_confirmation = None

#     response = {
#         "success": False,
#         "cancelled": True,
#         "request_id": (
#             pending.get("request_id")
#             if isinstance(pending, dict)
#             else None
#         ),
#         "correlation_id": (
#             pending.get("correlation_id")
#             if isinstance(pending, dict)
#             else None
#         ),
#         "intent": (
#             pending.get("intent")
#             if isinstance(pending, dict)
#             else None
#         ),
#         "message": "Operation cancelled. No changes were made.",
#         "error": None,
#     }

#     append_conversation(
#         "assistant",
#         response,
#         datetime.now().strftime("%H:%M:%S"),
#     )

#     st.rerun()


# def render_confirmation_controls() -> None:
#     """Render trusted confirmation controls for a pending operation."""

#     pending = st.session_state.pending_confirmation

#     if not isinstance(pending, dict):
#         return

#     with st.container(border=True):
#         st.markdown("**Approval required**")
#         st.write(
#             pending.get("prompt")
#             or "Confirm this operation before continuing."
#         )

#         confirm_column, cancel_column = st.columns(2)

#         if confirm_column.button(
#             "Confirm and proceed",
#             type="primary",
#             width="stretch",
#         ):
#             st.session_state.pending_confirmation = None

#             execute_and_render(
#                 pending["query"],
#                 confirmed=True,
#                 request_id=pending.get("request_id"),
#                 correlation_id=pending.get("correlation_id"),
#                 add_user_turn=False,
#             )

#             st.rerun()

#         if cancel_column.button(
#             "Cancel",
#             width="stretch",
#         ):
#             cancel_pending_confirmation()


# # ---------------------------------------------------------------------------
# # Sidebar
# # ---------------------------------------------------------------------------


# def safe_conversation_download() -> str:
#     """Serialize password-safe conversation history."""

#     return json.dumps(
#         redact_sensitive_history(
#             copy.deepcopy(st.session_state.conversation)
#         ),
#         indent=2,
#         ensure_ascii=False,
#         default=str,
#     )


# def render_sidebar() -> None:
#     """Render environment, examples, and session controls."""

#     with st.sidebar:
#         st.header("Environment")

#         status = get_config_status()
#         show_table(flatten_rows(status))

#         if st.button(
#             "Test Ollama connection",
#             width="stretch",
#         ):
#             connected, message = check_ollama()
#             st.session_state.ollama_check_result = {
#                 "connected": connected,
#                 "message": message,
#             }

#         ollama_result = st.session_state.ollama_check_result

#         if isinstance(ollama_result, dict):
#             show_table(flatten_rows(ollama_result))

#         st.divider()
#         st.caption("Example queries")

#         for index, example in enumerate(EXAMPLES):
#             if st.button(
#                 example,
#                 key=f"example_{index}",
#                 width="stretch",
#             ):
#                 st.session_state.queued_query = example
#                 st.rerun()

#         st.divider()
#         st.caption(f"Logs: {LOG_FILE}")

#         if st.session_state.conversation:
#             if st.button(
#                 "Clear conversation",
#                 width="stretch",
#             ):
#                 st.session_state.conversation = []
#                 st.session_state.pending_confirmation = None
#                 st.rerun()

#             st.download_button(
#                 "Download as JSON",
#                 data=safe_conversation_download(),
#                 file_name="techadmin_session.json",
#                 mime="application/json",
#                 width="stretch",
#             )


# # ---------------------------------------------------------------------------
# # Main application
# # ---------------------------------------------------------------------------


# def main() -> None:
#     """Run the TechAdmin Streamlit application."""

#     init_state()

#     st.title("🛠️ TechAdmin IT Support")
#     st.caption(
#         "Guardrailed identity operations through Microsoft Graph and PowerShell."
#     )

#     # CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): the plaintext password
#     # dashboard is gone. The specification forbids the original password on the
#     # UI; the reset result now shows a masked form with Download and Send Email
#     # actions instead.
#     # render_password_cards()

#     for turn in st.session_state.conversation:
#         with st.chat_message(turn["role"]):
#             if turn["role"] == "user":
#                 st.write(turn["content"])
#             elif isinstance(turn["content"], dict):
#                 render_response(turn["content"])

#     query = (
#         st.session_state.queued_query
#         or st.chat_input("Type an identity operation...")
#     )

#     st.session_state.queued_query = None

#     if query:
#         pending = st.session_state.pending_confirmation
#         normalized_answer = query.strip().casefold().rstrip(".!")

#         if isinstance(pending, dict) and normalized_answer in YES_WORDS:
#             append_conversation(
#                 "user",
#                 query,
#                 datetime.now().strftime("%H:%M:%S"),
#             )

#             st.session_state.pending_confirmation = None

#             execute_and_render(
#                 pending["query"],
#                 confirmed=True,
#                 request_id=pending.get("request_id"),
#                 correlation_id=pending.get("correlation_id"),
#                 add_user_turn=False,
#             )

#         elif isinstance(pending, dict) and normalized_answer in NO_WORDS:
#             append_conversation(
#                 "user",
#                 query,
#                 datetime.now().strftime("%H:%M:%S"),
#             )
#             cancel_pending_confirmation()

#         else:
#             execute_and_render(query)

#         st.rerun()

#     render_confirmation_controls()
#     render_sidebar()


# if __name__ == "__main__":
#     main()


"""
TechAdmin Streamlit UI with guardrail confirmation and session password display.

Features:
    - Structured tables only for workflow results.
    - Guardrail confirmation controls for sensitive operations.
    - Reuses request ID and correlation ID after confirmation.
    - Displays generated temporary passwords in a dedicated session panel.
    - Removes the dashboard-only secret before conversation history and JSON download.
    - Supports Microsoft Graph and PowerShell result shapes.
    - Avoids conditional Streamlit expressions that can render DeltaGenerator details.

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
    check_ollama,
    get_config_status,
)

# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
from flow_service import (
    build_password_download,
    email_is_configured,
    send_password_to_manager,
)
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---


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

    .tech-hero {
        padding: 1rem 0 1.25rem;
        border-bottom: 1px solid var(--tech-line);
        margin-bottom: 1.5rem;
        text-align: left;
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

    .tech-brand {
        color: #0d4f87;
        font-size: 1rem;
        font-weight: 800;
        letter-spacing: 0.16em;
        margin-left: 0.35rem;
    }

    .tech-hero h1 {
        color: var(--tech-ink);
        font-size: clamp(2rem, 4vw, 3.4rem);
        line-height: 1.05;
        margin: 0;
    }

    .tech-hero p {
        color: var(--tech-muted);
        font-size: 1rem;
        margin: 0.85rem 0 0;
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

    .operation-card.success { border-left-color: #18864b; }
    .operation-card.warning { border-left-color: #b7791f; }
    .operation-card.failure { border-left-color: #c53030; }

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


def require_authentication() -> dict[str, Any]:
    """Require a Microsoft Entra session before loading the dashboard."""

    local_user = st.session_state.get("local_authenticated_user")
    if isinstance(local_user, dict):
        render_authenticated_user(local_user)
        return local_user

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

    claims = dict(st.user)
    expected_tenant = str(
        st.secrets.get("entra", {}).get("allowed_tenant_id", "")
    ).strip()
    actual_tenant = str(claims.get("tid", "")).strip()

    if expected_tenant and actual_tenant != expected_tenant:
        st.error("This Microsoft tenant is not authorized for TechAdmin.")
        if st.button("Sign out", width="content"):
            st.logout()
        st.stop()

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
    expected_password = os.getenv("TECHADMIN_LOCAL_LOGIN_PASSWORD", "")

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
    st.rerun()


def render_authenticated_user(claims: dict[str, Any]) -> None:
    """Render identity and provide a logout action for either auth method."""

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
            if st.button("Sign out", key="local_sign_out", width="stretch"):
                st.session_state.pop("local_authenticated_user", None)
                st.rerun()
        elif st.button("Sign out", key="sign_out", width="stretch"):
            st.logout()


EXAMPLES = [
    "Get user details for MigrationTest2@Coforge.com",
    "Get user details for MigrationTest2@Coforge.com via script",
    "Get user details for MigrationTest2@Coforge.com via API",
    "Reset password for MigrationTest2@Coforge.com",
    "Reset password for MigrationTest2@Coforge.com via script",
    "Add user MigrationTest2@Coforge.com to group TechAI_Group",
    "Remove user MigrationTest2@Coforge.com from group TechAI_Group",
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
}


# ---------------------------------------------------------------------------
# Service and session state
# ---------------------------------------------------------------------------


@st.cache_resource(show_spinner="Starting TechAdmin...")
def get_service() -> FlowService:
    """Create and cache the workflow service."""

    return FlowService()


def init_state() -> None:
    """Initialize the Streamlit session keys used by the application."""

    st.session_state.setdefault("conversation", [])
    st.session_state.setdefault("queued_query", None)
    st.session_state.setdefault("pending_confirmation", None)
    st.session_state.setdefault("password_cards", [])
    st.session_state.setdefault("ollama_check_result", None)


# ---------------------------------------------------------------------------
# Generic data and table helpers
# ---------------------------------------------------------------------------


def display_text(value: Any) -> str:
    """Convert a value into readable table text."""

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
    """Convert a dictionary into readable rows without dropping nested data."""

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
    """Remove plaintext credentials from conversation history and downloads."""

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
        return [redact_sensitive_history(item) for item in value]

    return value


# ---------------------------------------------------------------------------
# Temporary-password dashboard
# ---------------------------------------------------------------------------


def register_dashboard_secret(response: Dict[str, Any]) -> bool:
    """
    Move `_dashboard_secret` from the response into current session state.

    FlowService must create `_dashboard_secret` before returning the response.
    This function removes that field before the response is added to normal
    conversation history or shown as raw JSON.
    """

    secret = response.pop("_dashboard_secret", None)

    if not isinstance(secret, dict):
        return False

    password = secret.get("password")

    if (
        not isinstance(password, str)
        or not password
        or password.casefold() == "[redacted]"
    ):
        return False

    password_card = {
        "password": password,
        "user": secret.get("user") or "Unknown user",
        "backend": secret.get("backend") or "unknown",
        "operation_id": secret.get("operation_id"),
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

    st.session_state.password_cards.insert(0, password_card)
    return True


def render_password_cards() -> None:
    """Display generated temporary passwords during the current UI session."""

    cards = st.session_state.password_cards

    if not cards:
        return

    st.markdown("### Generated temporary passwords")

    for index, card in enumerate(list(cards)):
        with st.container(border=True):
            show_table(
                [
                    ("Account", card.get("user")),
                    ("Backend", card.get("backend")),
                    ("Generated", card.get("created_at")),
                    ("Operation ID", card.get("operation_id")),
                ]
            )

            st.markdown("**Temporary password**")
            st.code(
                card.get("password") or "",
                language=None,
            )

            if st.button(
                "Remove password",
                key=f"remove_password_{index}",
                width="content",
            ):
                st.session_state.password_cards.pop(index)
                st.rerun()

    if st.button(
        "Clear displayed passwords",
        type="secondary",
        width="content",
    ):
        st.session_state.password_cards = []
        st.rerun()

    st.divider()


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
    """Render guardrail decisions and violations as tables."""

    show_table(
        [
            ("Action", response.get("guardrail_action")),
            ("Blocked", response.get("guardrail_blocked")),
            ("Confirmation required", response.get("confirmation_required")),
            ("Confirmation prompt", response.get("confirmation_prompt")),
            ("Output filtered fields", response.get("guardrails_output_filtered")),
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


# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
def render_password_reset_actions(result: Dict[str, Any]) -> None:
    """
    Show the outcome of a password reset.

    Displays the masked password, the manager, and the two operator actions.
    The original password is not present in `result` at all: the tool returns a
    masked form plus an opaque token, and the token is what the buttons use.

    Args:
        result: The tool result payload from the reset.
    """
    st.success("Password Reset Successful")

    manager_name = result.get("manager_name") or "Not Available"
    manager_email = result.get("manager_email") or "Not Available"

    show_table(
        [
            ("Username", result.get("user_name") or result.get("user_principal_name")),
            ("Employee name", result.get("employee_name")),
            ("Temporary password", result.get("masked_password") or "Not Available"),
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


def render_password_actions(token: str, manager_email: str) -> None:
    """
    Draw the Send Email and Download buttons for a completed reset.

    Both actions are explicit. Nothing is emailed as a side effect of the reset
    itself; the mail goes out only when the operator presses the button.

    Args:
        token: The password token from the reset result.
        manager_email: Recipient, or "Not Available".
    """
    # Keyed by token so two resets in one session keep separate buttons and
    # separate status lines.
    status_key = f"email_status_{token}"
    st.session_state.setdefault(status_key, None)

    can_email = bool(manager_email) and manager_email != "Not Available"

    left, right = st.columns(2)

    if left.button(
        "Send Email To Manager",
        key=f"send_{token}",
        disabled=not can_email,
    ):
        with st.spinner("Sending email..."):
            sent, message, recipient = send_password_to_manager(token)
        st.session_state[status_key] = {
            "sent": sent,
            "message": message,
            "recipient": recipient,
        }

    # CHANGED (Amit Bhagat): one button, as the specification shows. An earlier
    # version needed Prepare and then Download, which meant two clicks and a
    # dead-looking first press. st.download_button needs its data up front, so
    # the file is built while rendering.
    ok, filename, content, message = build_password_download(token)

    if ok:
        right.download_button(
            "Download Password TXT",
            data=content,
            file_name=filename,
            mime="text/plain",
            key=f"dl_{token}",
        )
    else:
        # Generation failures are reported without disturbing the reset, which
        # has already succeeded.
        right.button(
            "Download Password TXT",
            key=f"dl_disabled_{token}",
            disabled=True,
        )
        st.caption(message)

    status = st.session_state.get(status_key)

    if status is None:
        st.caption("Email status: Not Sent")
    elif status["sent"]:
        st.success(f"Email status: Sent Successfully to {status['recipient']}")
    else:
        # A failed send is reported but does not undo the reset, which has
        # already succeeded. The TXT download stays available.
        st.error(f"Email status: Failed. {status['message']}")
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---


def render_result(intent: str, result: Dict[str, Any]) -> None:
    """Render API or script operation results."""

    execution = result.get("execution")
    user_record = result.get("user")

    excluded = {
        "execution",
        "user",
        "new_password",
        "temporary_password",
    }

    if isinstance(user_record, dict):
        result_rows = [("Backend", result.get("backend"))]
        result_rows.extend(flatten_rows(user_record))
    else:
        result_rows = flatten_rows(result, excluded)

    show_table(result_rows, "Result")

    if isinstance(execution, dict):
        render_script_execution(execution)

    # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
    if intent == "password_reset" and result.get("password_token"):
        render_password_reset_actions(result)
        return
    # --- END ADDED FOR PASSWORD ENHANCEMENTS ---

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
                            "The normal response is redacted. The generated "
                            "password appears in the dashboard panel only when "
                            "FlowService receives the original value before "
                            "output sanitization."
                        ),
                    )
                ],
                "Password status",
            )


def render_response(response: Dict[str, Any]) -> None:
    """Render workflow data without success/error notification boxes."""

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
            flatten_rows(metadata),
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
                ("API integration pending", tool_result.get("api_integration_pending")),
            ],
            "Tool execution",
        )

        result = tool_result.get("result")

        if isinstance(result, dict):
            render_result(
                response.get("intent") or "",
                result,
            )

    with st.expander("Raw response (JSON)"):
        st.json(response)


def render_operation_summary(response: Dict[str, Any]) -> None:
    """Show the key operation state before detailed result tables."""

    intent = str(response.get("intent") or "Identity operation")
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
            <div class="operation-meta"><strong>Target:</strong> {safe_target} &nbsp; | &nbsp; <strong>Status:</strong> {safe_status}</div>
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
        timeline.append(("Operation completed", response.get("success") is True))

    st.markdown("**Operation timeline**")
    st.caption("  ·  ".join(
        f"{'✓' if complete else '○'} {label}"
        for label, complete in timeline
    ))


# ---------------------------------------------------------------------------
# Confirmation workflow
# ---------------------------------------------------------------------------


def set_pending_confirmation(
    response: Dict[str, Any],
    query: str,
) -> None:
    """Store a request while guardrails wait for operator confirmation."""

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
    """Append a password-safe conversation item."""

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
    """Execute one workflow request and save the password-safe result."""

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
    """Cancel the pending operation without running the tool."""

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
    """Render trusted confirmation controls for a pending operation."""

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
# Sidebar
# ---------------------------------------------------------------------------


def safe_conversation_download() -> str:
    """Serialize password-safe conversation history."""

    return json.dumps(
        redact_sensitive_history(
            copy.deepcopy(st.session_state.conversation)
        ),
        indent=2,
        ensure_ascii=False,
        default=str,
    )


def render_sidebar() -> None:
    """Render environment, examples, and session controls."""

    with st.sidebar:
        st.header("System status")

        status = get_config_status()
        show_table(
            [
                ("Microsoft Graph", "Configured" if status.get("graph_client_id") and status.get("graph_client_secret") and status.get("graph_tenant_id") else "Incomplete"),
                ("PowerShell", "Enabled" if status.get("powershell_operations_enabled") else "Disabled"),
                ("Destructive actions", "Enabled" if status.get("destructive_operations_enabled") else "Disabled"),
                ("Configuration", "Valid" if status.get("config_valid") else "Invalid"),
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
                        "Connected" if ollama_result.get("connected") else "Unavailable",
                    ),
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

        for example in EXAMPLES:
            st.caption(example)

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
    """Show completed session operations without exposing sensitive values."""

    operations = []
    for turn in reversed(st.session_state.conversation):
        if turn.get("role") != "assistant" or not isinstance(turn.get("content"), dict):
            continue

        response = turn["content"]
        metadata = response.get("metadata")
        target = "Unknown target"
        if isinstance(metadata, dict):
            target = metadata.get("email") or metadata.get("username") or target

        operations.append(
            {
                "Operation": str(response.get("intent") or "Identity operation").replace("_", " ").title(),
                "Target": target,
                "Status": "Completed" if response.get("success") else "Failed",
                "Time": turn.get("time", ""),
            }
        )

        if len(operations) == 5:
            break

    if operations:
        st.markdown("#### Recent operations")
        st.dataframe(pd.DataFrame(operations), hide_index=True, width="stretch")


def render_command_center() -> None:
    """Render guidance before the conversation has any messages."""

    if st.session_state.conversation:
        return

    st.markdown(
        """
        <div class="tech-panel">
            <strong>What do you need to take care of?</strong>
            <span>Ask for a user lookup, password reset, account unlock, or access change. Sensitive actions pause for confirmation.</span>
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

    # CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat): the plaintext password
    # dashboard is gone. The specification forbids the original password on the
    # UI; the reset result now shows a masked form with Download and Send Email
    # actions instead.
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

        if isinstance(pending, dict) and normalized_answer in YES_WORDS:
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

        elif isinstance(pending, dict) and normalized_answer in NO_WORDS:
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

# # """Dual-backend identity tools compatible with output guardrails."""
# # from __future__ import annotations
# # import json
# # from typing import Any
# # from App.integration.microsoft_graph import MicrosoftGraphClient
# # from App.integration.powershell_runner import PowerShellScriptRunner
# # from App.workflow.state import ExecutionBackend, ToolName, ToolRequest, ToolResult, ToolStatus


# # class HybridGetUserDetailsTool:
# #     name = ToolName.GET_USER_DETAILS

# #     def __init__(self, graph_client=None, runner=None) -> None:
# #         self.graph = graph_client or MicrosoftGraphClient()
# #         self.runner = runner or PowerShellScriptRunner()

# #     def execute(self, request: ToolRequest) -> ToolResult:
# #         m = request.metadata
# #         identifier = m.email or m.user_id or m.username
# #         backend = m.execution_backend
# #         if not identifier or backend is None:
# #             return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

# #         if backend == ExecutionBackend.API:
# #             data = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
# #             if not data:
# #                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
# #             return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="User details retrieved through Microsoft Graph API.", result={"backend": "api", "user": data})

# #         execution = self.runner.execute("get_user_details", {"UserIdentifier": identifier})
# #         user: dict[str, Any] | None = None
# #         if execution.success and execution.stdout:
# #             try:
# #                 parsed = json.loads(execution.stdout)
# #                 user = parsed if isinstance(parsed, dict) else {"raw_output": execution.stdout}
# #             except json.JSONDecodeError:
# #                 user = {"raw_output": execution.stdout}
# #         return ToolResult(
# #             success=execution.success,
# #             tool_name=self.name,
# #             status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
# #             message="User details retrieved through PowerShell." if execution.success else "PowerShell user lookup failed.",
# #             result={"backend": "script", "user": user, "execution": execution.model_dump(mode="json")},
# #             error=execution.error,
# #         )


# # class HybridPasswordResetTool:
# #     name = ToolName.RESET_PASSWORD

# #     def __init__(self, graph_client=None, runner=None) -> None:
# #         self.graph = graph_client or MicrosoftGraphClient()
# #         self.runner = runner or PowerShellScriptRunner()

# #     def execute(self, request: ToolRequest) -> ToolResult:
# #         m = request.metadata
# #         identifier = m.email or m.user_id or m.username
# #         backend = m.execution_backend
# #         if not identifier or backend is None:
# #             return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

# #         if backend == ExecutionBackend.API:
# #             user = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
# #             if not user or not user.get("id"):
# #                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
# #             password = self.graph.reset_password(user["id"])
# #             if not password:
# #                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message="Microsoft Graph password reset failed.", error="Password reset failed")
# #             return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="Password reset completed through Microsoft Graph API.", result={"backend": "api", "user_principal_name": user.get("userPrincipalName"), "temporary_password_generated": True, "new_password": password})

# #         password = self.graph.generate_temp_password()
# #         execution = self.runner.execute(
# #             "reset_password",
# #             {"UserName": m.username or identifier.split("@", 1)[0]},
# #             secret_environment={"TECHADMIN_NEW_PASSWORD": password},
# #             approval_granted=m.approval_granted,
# #         )
# #         return ToolResult(
# #             success=execution.success,
# #             tool_name=self.name,
# #             status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
# #             message="Password reset completed through PowerShell." if execution.success else "PowerShell password reset failed.",
# #             result={"backend": "script", "user_name": m.username or identifier, "temporary_password_generated": execution.success, "new_password": password if execution.success else None, "execution": execution.model_dump(mode="json")},
# #             error=execution.error,
# #         )
# """Dual-backend identity tools compatible with output guardrails."""
# from __future__ import annotations
# import json
# from typing import Any
# from App.integration.microsoft_graph import MicrosoftGraphClient
# from App.integration.powershell_runner import PowerShellScriptRunner
# from App.workflow.state import ExecutionBackend, ToolName, ToolRequest, ToolResult, ToolStatus
# # --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
# from App.services.password_vault import password_vault
# from App.utils.password_masking import mask_password
# from loguru import logger

# NOT_AVAILABLE = "Not Available"


# def _manager_from_script(user: dict[str, Any] | None) -> tuple[str, str]:
#     """
#     Read the manager fields out of the PowerShell script's JSON output.

#     Args:
#         user: The parsed object from Invoke-GetUserDetails.ps1 or
#             Invoke-ResetPassword.ps1.

#     Returns:
#         Tuple of (manager_name, manager_email), each falling back to
#         "Not Available".
#     """
#     if not isinstance(user, dict):
#         return NOT_AVAILABLE, NOT_AVAILABLE

#     return (
#         user.get("ManagerName") or NOT_AVAILABLE,
#         user.get("ManagerEmail") or NOT_AVAILABLE,
#     )
# # --- END ADDED FOR PASSWORD ENHANCEMENTS ---


# class HybridGetUserDetailsTool:
#     name = ToolName.GET_USER_DETAILS

#     def __init__(self, graph_client=None, runner=None) -> None:
#         self.graph = graph_client or MicrosoftGraphClient()
#         self.runner = runner or PowerShellScriptRunner()

#     def execute(self, request: ToolRequest) -> ToolResult:
#         m = request.metadata
#         identifier = m.email or m.user_id or m.username
#         backend = m.execution_backend
#         if not identifier or backend is None:
#             return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

#         if backend == ExecutionBackend.API:
#             data = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
#             if not data:
#                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
#             # --- ADDED FOR MANAGER LOOKUP ---
#             # A second Graph call: the manager is a navigation property, not a
#             # field on the user. It never raises, so a missing manager cannot
#             # turn a successful lookup into a failure.
#             manager = self.graph.get_manager(data.get("id") or identifier)
#             data = dict(data)
#             data["manager_name"] = manager.get("manager_name", NOT_AVAILABLE)
#             data["manager_email"] = manager.get("manager_email", NOT_AVAILABLE)

#             logger.info(
#                 "USER_LOOKUP_SUCCESS | request_id={} | target_user={} | backend=api | manager_resolved={}",
#                 request.request_id,
#                 data.get("userPrincipalName"),
#                 data["manager_name"] != NOT_AVAILABLE,
#             )
#             # --- END ADDED FOR MANAGER LOOKUP ---

#             return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="User details retrieved through Microsoft Graph API.", result={"backend": "api", "user": data})

#         execution = self.runner.execute("get_user_details", {"UserIdentifier": identifier})
#         user: dict[str, Any] | None = None
#         if execution.success and execution.stdout:
#             try:
#                 parsed = json.loads(execution.stdout)
#                 user = parsed if isinstance(parsed, dict) else {"raw_output": execution.stdout}
#             except json.JSONDecodeError:
#                 user = {"raw_output": execution.stdout}

#         # --- ADDED FOR MANAGER LOOKUP ---
#         # Invoke-GetUserDetails.ps1 now returns ManagerName and ManagerEmail.
#         # They are copied to snake_case so the UI reads one shape whichever
#         # backend ran.
#         if isinstance(user, dict):
#             manager_name, manager_email = _manager_from_script(user)
#             user["manager_name"] = manager_name
#             user["manager_email"] = manager_email

#         logger.info(
#             "USER_LOOKUP_{} | request_id={} | target_user={} | backend=script",
#             "SUCCESS" if execution.success else "FAILED",
#             request.request_id,
#             identifier,
#         )
#         # --- END ADDED FOR MANAGER LOOKUP ---

#         return ToolResult(
#             success=execution.success,
#             tool_name=self.name,
#             status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
#             message="User details retrieved through PowerShell." if execution.success else "PowerShell user lookup failed.",
#             result={"backend": "script", "user": user, "execution": execution.model_dump(mode="json")},
#             error=execution.error,
#         )


# class HybridPasswordResetTool:
#     name = ToolName.RESET_PASSWORD

#     def __init__(self, graph_client=None, runner=None) -> None:
#         self.graph = graph_client or MicrosoftGraphClient()
#         self.runner = runner or PowerShellScriptRunner()

#     def execute(self, request: ToolRequest) -> ToolResult:
#         m = request.metadata
#         identifier = m.email or m.user_id or m.username
#         backend = m.execution_backend
#         if not identifier or backend is None:
#             return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

#         if backend == ExecutionBackend.API:
#             user = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
#             if not user or not user.get("id"):
#                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
#             password = self.graph.reset_password(user["id"])
#             if not password:
#                 return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message="Microsoft Graph password reset failed.", error="Password reset failed")
#             # --- CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
#             # The original password no longer leaves this method. It goes into
#             # the vault; the result carries a masked form and an opaque token.
#             # The download and email actions exchange the token for the real
#             # value server-side, so the password cannot reach an API response,
#             # the UI, or a log line.
#             manager = self.graph.get_manager(user.get("id") or identifier)
#             return self._password_result(
#                 request=request,
#                 backend="api",
#                 username=user.get("userPrincipalName") or identifier,
#                 employee_name=user.get("displayName") or user.get("userPrincipalName") or identifier,
#                 password=password,
#                 manager_name=manager.get("manager_name", NOT_AVAILABLE),
#                 manager_email=manager.get("manager_email", NOT_AVAILABLE),
#                 message="Password reset completed through Microsoft Graph API.",
#             )
#             # --- END CHANGED FOR PASSWORD ENHANCEMENTS ---

#         password = self.graph.generate_temp_password()
#         execution = self.runner.execute(
#             "reset_password",
#             {"UserName": m.username or identifier.split("@", 1)[0]},
#             secret_environment={"TECHADMIN_NEW_PASSWORD": password},
#             approval_granted=m.approval_granted,
#         )
#         # --- CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
#         # Invoke-ResetPassword.ps1 now returns JSON carrying the manager, so a
#         # second lookup is not needed. On failure nothing is vaulted: there is
#         # no password to deliver.
#         script_user: dict[str, Any] | None = None
#         if execution.success and execution.stdout:
#             try:
#                 parsed = json.loads(execution.stdout)
#                 script_user = parsed if isinstance(parsed, dict) else None
#             except json.JSONDecodeError:
#                 script_user = None

#         if not execution.success:
#             logger.warning(
#                 "PASSWORD_RESET_FAILED | request_id={} | target_user={} | backend=script",
#                 request.request_id,
#                 identifier,
#             )
#             return ToolResult(
#                 success=False,
#                 tool_name=self.name,
#                 status=ToolStatus.FAILED,
#                 message="PowerShell password reset failed.",
#                 result={"backend": "script", "user_name": m.username or identifier, "temporary_password_generated": False, "execution": execution.model_dump(mode="json")},
#                 error=execution.error,
#             )

#         manager_name, manager_email = _manager_from_script(script_user)

#         return self._password_result(
#             request=request,
#             backend="script",
#             username=(script_user or {}).get("UserName") or m.username or identifier,
#             employee_name=(script_user or {}).get("DisplayName") or m.username or identifier,
#             password=password,
#             manager_name=manager_name,
#             manager_email=manager_email,
#             message="Password reset completed through PowerShell.",
#             execution=execution.model_dump(mode="json"),
#         )

#     def _password_result(
#         self,
#         *,
#         request: ToolRequest,
#         backend: str,
#         username: str,
#         employee_name: str,
#         password: str,
#         manager_name: str,
#         manager_email: str,
#         message: str,
#         execution: dict[str, Any] | None = None,
#     ) -> ToolResult:
#         """
#         Build the reset result, with the original password held back.

#         Shared by both backends so the API and script paths return the same
#         shape and neither can accidentally leak the password.

#         Args:
#             request: The originating tool request.
#             backend: "api" or "script".
#             username: The account that was reset.
#             employee_name: Display name, used in the email body.
#             password: The original password. Vaulted here, never returned.
#             manager_name: Resolved manager display name, or "Not Available".
#             manager_email: Resolved manager address, or "Not Available".
#             message: Operator-facing success message.
#             execution: Script execution evidence, when one ran.

#         Returns:
#             A ToolResult whose payload carries masked_password and
#             password_token in place of the original value.
#         """
#         token = password_vault.store(
#             password=password,
#             username=username,
#             employee_name=employee_name,
#             manager_name=manager_name,
#             manager_email=manager_email,
#         )

#         logger.info(
#             "PASSWORD_RESET_SUCCESS | request_id={} | target_user={} | backend={} | manager_resolved={}",
#             request.request_id,
#             username,
#             backend,
#             manager_name != NOT_AVAILABLE,
#         )

#         result: dict[str, Any] = {
#             "backend": backend,
#             "user_name": username,
#             "user_principal_name": username,
#             "employee_name": employee_name,
#             "temporary_password_generated": True,
#             "masked_password": mask_password(password),
#             "password_token": token,
#             "manager_name": manager_name,
#             "manager_email": manager_email,
#             "email_sent": False,
#             "download_available": True,
#         }

#         if execution is not None:
#             result["execution"] = execution

#         return ToolResult(
#             success=True,
#             tool_name=self.name,
#             status=ToolStatus.COMPLETED,
#             message=message,
#             result=result,
#         )
#         # --- END CHANGED FOR PASSWORD ENHANCEMENTS ---


"""Dual-backend identity tools compatible with output guardrails."""
from __future__ import annotations
import json
from typing import Any
from App.integration.microsoft_graph import MicrosoftGraphClient
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import ExecutionBackend, ToolName, ToolRequest, ToolResult, ToolStatus
# --- ADDED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
from App.services.password_vault import password_vault
from App.utils.password_masking import mask_password
from loguru import logger

NOT_AVAILABLE = "Not Available"


def _manager_from_script(user: dict[str, Any] | None) -> tuple[str, str]:
    """
    Read the manager fields out of the PowerShell script's JSON output.

    Args:
        user: The parsed object from Invoke-GetUserDetails.ps1 or
            Invoke-ResetPassword.ps1.

    Returns:
        Tuple of (manager_name, manager_email), each falling back to
        "Not Available".
    """
    if not isinstance(user, dict):
        return NOT_AVAILABLE, NOT_AVAILABLE

    return (
        user.get("ManagerName") or NOT_AVAILABLE,
        user.get("ManagerEmail") or NOT_AVAILABLE,
    )
# --- END ADDED FOR PASSWORD ENHANCEMENTS ---


class HybridGetUserDetailsTool:
    name = ToolName.GET_USER_DETAILS

    def __init__(self, graph_client=None, runner=None) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        m = request.metadata
        identifier = m.email or m.user_id or m.username
        backend = m.execution_backend
        if not identifier or backend is None:
            return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

        if backend == ExecutionBackend.API:
            data = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
            if not data:
                return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
            # --- ADDED FOR MANAGER LOOKUP (Amit Bhagat) ---
            # A second Graph call: the manager is a navigation property, not a
            # field on the user. It never raises, so a missing manager cannot
            # turn a successful lookup into a failure.
            manager = self.graph.get_manager(data.get("id") or identifier)
            data = dict(data)
            data["manager_name"] = manager.get("manager_name", NOT_AVAILABLE)
            data["manager_email"] = manager.get("manager_email", NOT_AVAILABLE)

            logger.info(
                "USER_LOOKUP_SUCCESS | request_id={} | target_user={} | backend=api | manager_resolved={}",
                request.request_id,
                data.get("userPrincipalName"),
                data["manager_name"] != NOT_AVAILABLE,
            )
            # --- END ADDED FOR MANAGER LOOKUP ---

            return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="User details retrieved through Microsoft Graph API.", result={"backend": "api", "user": data})

        execution = self.runner.execute("get_user_details", {"UserIdentifier": identifier})
        user: dict[str, Any] | None = None
        if execution.success and execution.stdout:
            try:
                parsed = json.loads(execution.stdout)
                user = parsed if isinstance(parsed, dict) else {"raw_output": execution.stdout}
            except json.JSONDecodeError:
                user = {"raw_output": execution.stdout}

        # --- ADDED FOR MANAGER LOOKUP (Amit Bhagat) ---
        # Invoke-GetUserDetails.ps1 now returns ManagerName and ManagerEmail.
        # They are copied to snake_case so the UI reads one shape whichever
        # backend ran.
        if isinstance(user, dict):
            manager_name, manager_email = _manager_from_script(user)
            user["manager_name"] = manager_name
            user["manager_email"] = manager_email

        logger.info(
            "USER_LOOKUP_{} | request_id={} | target_user={} | backend=script",
            "SUCCESS" if execution.success else "FAILED",
            request.request_id,
            identifier,
        )
        # --- END ADDED FOR MANAGER LOOKUP ---

        return ToolResult(
            success=execution.success,
            tool_name=self.name,
            status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
            message="User details retrieved through PowerShell." if execution.success else "PowerShell user lookup failed.",
            result={"backend": "script", "user": user, "execution": execution.model_dump(mode="json")},
            error=execution.error,
        )


class HybridPasswordResetTool:
    name = ToolName.RESET_PASSWORD

    def __init__(self, graph_client=None, runner=None) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        m = request.metadata
        identifier = m.email or m.user_id or m.username
        backend = m.execution_backend
        if not identifier or backend is None:
            return ToolResult(success=False, tool_name=self.name, status=ToolStatus.REJECTED, message="User identifier and execution backend are required.", error="Missing identifier or backend")

        if backend == ExecutionBackend.API:
            user = self.graph.get_user_details(identifier) if "@" in identifier else self.graph.find_user_by_username(identifier)
            if not user or not user.get("id"):
                return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message=f"User '{identifier}' was not found through Microsoft Graph.", error="User not found")
            password = self.graph.reset_password(user["id"])
            if not password:
                return ToolResult(success=False, tool_name=self.name, status=ToolStatus.FAILED, message="Microsoft Graph password reset failed.", error="Password reset failed")
            # --- CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
            # The original password no longer leaves this method. It goes into
            # the vault; the result carries a masked form and an opaque token.
            # The download and email actions exchange the token for the real
            # value server-side, so the password cannot reach an API response,
            # the UI, or a log line.
            manager = self.graph.get_manager(user.get("id") or identifier)
            return self._password_result(
                request=request,
                backend="api",
                username=user.get("userPrincipalName") or identifier,
                employee_name=user.get("displayName") or user.get("userPrincipalName") or identifier,
                password=password,
                manager_name=manager.get("manager_name", NOT_AVAILABLE),
                manager_email=manager.get("manager_email", NOT_AVAILABLE),
                message="Password reset completed through Microsoft Graph API.",
            )
            # --- END CHANGED FOR PASSWORD ENHANCEMENTS ---

        password = self.graph.generate_temp_password()
        execution = self.runner.execute(
            "reset_password",
            {"UserName": m.username or identifier.split("@", 1)[0]},
            secret_environment={"TECHADMIN_NEW_PASSWORD": password},
            approval_granted=m.approval_granted,
        )
        # --- CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
        # Invoke-ResetPassword.ps1 now returns JSON carrying the manager, so a
        # second lookup is not needed. On failure nothing is vaulted: there is
        # no password to deliver.
        script_user: dict[str, Any] | None = None
        if execution.success and execution.stdout:
            try:
                parsed = json.loads(execution.stdout)
                script_user = parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError:
                script_user = None

        if not execution.success:
            logger.warning(
                "PASSWORD_RESET_FAILED | request_id={} | target_user={} | backend=script",
                request.request_id,
                identifier,
            )
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message="PowerShell password reset failed.",
                result={"backend": "script", "user_name": m.username or identifier, "temporary_password_generated": False, "execution": execution.model_dump(mode="json")},
                error=execution.error,
            )

        manager_name, manager_email = _manager_from_script(script_user)

        return self._password_result(
            request=request,
            backend="script",
            username=(script_user or {}).get("UserName") or m.username or identifier,
            employee_name=(script_user or {}).get("DisplayName") or m.username or identifier,
            password=password,
            manager_name=manager_name,
            manager_email=manager_email,
            message="Password reset completed through PowerShell.",
            execution=execution.model_dump(mode="json"),
        )

    def _password_result(
        self,
        *,
        request: ToolRequest,
        backend: str,
        username: str,
        employee_name: str,
        password: str,
        manager_name: str,
        manager_email: str,
        message: str,
        execution: dict[str, Any] | None = None,
    ) -> ToolResult:
        """
        Build the reset result, with the original password held back.

        Shared by both backends so the API and script paths return the same
        shape and neither can accidentally leak the password.

        Args:
            request: The originating tool request.
            backend: "api" or "script".
            username: The account that was reset.
            employee_name: Display name, used in the email body.
            password: The original password. Vaulted here, never returned.
            manager_name: Resolved manager display name, or "Not Available".
            manager_email: Resolved manager address, or "Not Available".
            message: Operator-facing success message.
            execution: Script execution evidence, when one ran.

        Returns:
            A ToolResult whose payload carries masked_password and
            password_token in place of the original value.
        """
        token = password_vault.store(
            password=password,
            username=username,
            employee_name=employee_name,
            manager_name=manager_name,
            manager_email=manager_email,
        )

        logger.info(
            "PASSWORD_RESET_SUCCESS | request_id={} | target_user={} | backend={} | manager_resolved={}",
            request.request_id,
            username,
            backend,
            manager_name != NOT_AVAILABLE,
        )

        result: dict[str, Any] = {
            # --- CHANGED FOR PASSWORD ENHANCEMENTS (Amit Bhagat) ---
            # The MCP servers run in a short-lived subprocess, so a vault entry
            # written here dies with that process. The password is handed back
            # over the MCP boundary under this internal key and re-vaulted in
            # the application process, which is what the download and email
            # buttons can actually reach.
            #
            # This key is backend-to-backend only. demo_flow strips it before
            # the response is sanitized, so it never reaches an API response,
            # the UI or a log line.
            "_transient_password": password,
            # --- END CHANGED FOR PASSWORD ENHANCEMENTS ---
            "backend": backend,
            "user_name": username,
            "user_principal_name": username,
            "employee_name": employee_name,
            "temporary_password_generated": True,
            "masked_password": mask_password(password),
            "password_token": token,
            "manager_name": manager_name,
            "manager_email": manager_email,
            "email_sent": False,
            "download_available": True,
        }

        if execution is not None:
            result["execution"] = execution

        return ToolResult(
            success=True,
            tool_name=self.name,
            status=ToolStatus.COMPLETED,
            message=message,
            result=result,
        )
        # --- END CHANGED FOR PASSWORD ENHANCEMENTS ---

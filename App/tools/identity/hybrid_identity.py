"""Dual-backend identity tools compatible with output guardrails."""
from __future__ import annotations
import json
from typing import Any
from App.integration.microsoft_graph import MicrosoftGraphClient
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import ExecutionBackend, ToolName, ToolRequest, ToolResult, ToolStatus


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
            return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="User details retrieved through Microsoft Graph API.", result={"backend": "api", "user": data})

        execution = self.runner.execute("get_user_details", {"UserIdentifier": identifier})
        user: dict[str, Any] | None = None
        if execution.success and execution.stdout:
            try:
                parsed = json.loads(execution.stdout)
                user = parsed if isinstance(parsed, dict) else {"raw_output": execution.stdout}
            except json.JSONDecodeError:
                user = {"raw_output": execution.stdout}
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
            return ToolResult(success=True, tool_name=self.name, status=ToolStatus.COMPLETED, message="Password reset completed through Microsoft Graph API.", result={"backend": "api", "user_principal_name": user.get("userPrincipalName"), "temporary_password_generated": True, "new_password": password})

        password = self.graph.generate_temp_password()
        execution = self.runner.execute(
            "reset_password",
            {"UserName": m.username or identifier.split("@", 1)[0]},
            secret_environment={"TECHADMIN_NEW_PASSWORD": password},
            approval_granted=m.approval_granted,
        )
        return ToolResult(
            success=execution.success,
            tool_name=self.name,
            status=ToolStatus.COMPLETED if execution.success else ToolStatus.FAILED,
            message="Password reset completed through PowerShell." if execution.success else "PowerShell password reset failed.",
            result={"backend": "script", "user_name": m.username or identifier, "temporary_password_generated": execution.success, "new_password": password if execution.success else None, "execution": execution.model_dump(mode="json")},
            error=execution.error,
        )

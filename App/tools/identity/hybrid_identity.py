"""Dual-backend password-reset and user-details tools."""
from __future__ import annotations

import json
from typing import Any

from loguru import logger

from App.integration.microsoft_graph import MicrosoftGraphClient
from App.integration.powershell_runner import PowerShellScriptRunner
from App.workflow.state import (
    ExecutionBackend,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class HybridGetUserDetailsTool:
    """Retrieve user details through Microsoft Graph or PowerShell."""

    name = ToolName.GET_USER_DETAILS

    def __init__(
        self,
        graph_client: MicrosoftGraphClient | None = None,
        runner: PowerShellScriptRunner | None = None,
    ) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        identifier = metadata.email or metadata.user_id or metadata.username
        backend = metadata.execution_backend

        if not identifier or backend is None:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message="User identifier and execution backend are required.",
                error="Missing identifier or backend",
            )

        if backend == ExecutionBackend.API:
            try:
                data = (
                    self.graph.get_user_details(identifier)
                    if "@" in identifier
                    else self.graph.find_user_by_username(identifier)
                )
                if not data:
                    return ToolResult(
                        success=False,
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        message=f"User '{identifier}' was not found through Microsoft Graph.",
                        error="User not found",
                    )

                safe_data = {
                    key: data.get(key)
                    for key in (
                        "id",
                        "displayName",
                        "userPrincipalName",
                        "accountEnabled",
                        "onPremisesSyncEnabled",
                        "userType",
                        "mail",
                    )
                }
                return ToolResult(
                    success=True,
                    tool_name=self.name,
                    status=ToolStatus.COMPLETED,
                    message="User details retrieved through Microsoft Graph API.",
                    result={"backend": "api", "user": safe_data},
                )
            except Exception as exc:
                logger.exception("GET_USER_DETAILS_API_FAILED | error_type={}", type(exc).__name__)
                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message="User-details lookup through Microsoft Graph failed.",
                    error=type(exc).__name__,
                )

        script_result = self.runner.execute(
            "get_user_details",
            {"UserIdentifier": identifier},
        )
        user_data: dict[str, Any] | None = None
        if script_result.success and script_result.stdout:
            try:
                parsed = json.loads(script_result.stdout)
                if isinstance(parsed, dict):
                    user_data = parsed
            except json.JSONDecodeError:
                user_data = {"raw_output": script_result.stdout}

        return ToolResult(
            success=script_result.success,
            tool_name=self.name,
            status=(
                ToolStatus.COMPLETED
                if script_result.success
                else ToolStatus.FAILED
            ),
            message=(
                "User details retrieved through the PowerShell script."
                if script_result.success
                else "PowerShell user lookup failed."
            ),
            result={
                "backend": "script",
                "user": user_data,
                "execution": script_result.model_dump(mode="json"),
            },
            error=script_result.error,
        )


class HybridPasswordResetTool:
    """Reset a password through Microsoft Graph or PowerShell."""

    name = ToolName.RESET_PASSWORD

    def __init__(
        self,
        graph_client: MicrosoftGraphClient | None = None,
        runner: PowerShellScriptRunner | None = None,
    ) -> None:
        self.graph = graph_client or MicrosoftGraphClient()
        self.runner = runner or PowerShellScriptRunner()

    def execute(self, request: ToolRequest) -> ToolResult:
        metadata = request.metadata
        identifier = metadata.email or metadata.user_id or metadata.username
        backend = metadata.execution_backend

        if not identifier or backend is None:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message="User identifier and execution backend are required.",
                error="Missing identifier or backend",
            )

        if backend == ExecutionBackend.API:
            try:
                user = (
                    self.graph.get_user_details(identifier)
                    if "@" in identifier
                    else self.graph.find_user_by_username(identifier)
                )
                if not user or not user.get("id"):
                    return ToolResult(
                        success=False,
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        message=f"User '{identifier}' was not found through Microsoft Graph.",
                        error="User not found",
                    )

                temporary_password = self.graph.reset_password(user["id"])
                if not isinstance(temporary_password, str) or not temporary_password:
                    return ToolResult(
                        success=False,
                        tool_name=self.name,
                        status=ToolStatus.FAILED,
                        message="Microsoft Graph password reset did not return a temporary password.",
                        error="Temporary password missing",
                    )

                return ToolResult(
                    success=True,
                    tool_name=self.name,
                    status=ToolStatus.COMPLETED,
                    message="Password reset completed through Microsoft Graph API.",
                    result={
                        "backend": "api",
                        "user_principal_name": user.get("userPrincipalName"),
                        "temporary_password_generated": True,
                        "temporary_password": temporary_password,
                        "temporary_password_redacted": False,
                    },
                )
            except Exception as exc:
                logger.exception("PASSWORD_RESET_API_FAILED | error_type={}", type(exc).__name__)
                return ToolResult(
                    success=False,
                    tool_name=self.name,
                    status=ToolStatus.FAILED,
                    message="Password reset through Microsoft Graph failed.",
                    error=type(exc).__name__,
                )

        if not metadata.approval_granted:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message="Explicit approval is required for script-based password reset.",
                error="Approval required",
            )

        username = metadata.username or identifier.split("@", 1)[0]
        try:
            temporary_password = self.graph.generate_temp_password()
            if not isinstance(temporary_password, str) or not temporary_password:
                raise ValueError("Temporary password generation failed")

            script_result = self.runner.execute(
                "reset_password",
                {"UserName": username},
                secret_environment={"TECHADMIN_NEW_PASSWORD": temporary_password},
                approval_granted=True,
            )

            return ToolResult(
                success=script_result.success,
                tool_name=self.name,
                status=(
                    ToolStatus.COMPLETED
                    if script_result.success
                    else ToolStatus.FAILED
                ),
                message=(
                    "Password reset completed through the PowerShell script."
                    if script_result.success
                    else "PowerShell password reset failed."
                ),
                result={
                    "backend": "script",
                    "user_name": username,
                    "temporary_password_generated": script_result.success,
                    "temporary_password": (
                        temporary_password if script_result.success else None
                    ),
                    "temporary_password_redacted": not script_result.success,
                    "execution": script_result.model_dump(mode="json"),
                },
                error=script_result.error,
            )
        except Exception as exc:
            logger.exception("PASSWORD_RESET_SCRIPT_FAILED | error_type={}", type(exc).__name__)
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message="Password reset through PowerShell failed.",
                error=type(exc).__name__,
            )

"""
Access Management Tool

Purpose:
    Execute access grant or access revoke using the configured identity
    integration.
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from App.workflow.state import (
    IntentType,
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class AccessManagementClient(Protocol):
    def manage_access(
        self,
        *,
        action: str,
        username: str,
        email: str | None,
        employee_number: str | None,
        group_name: str,
        correlation_id: str,
    ) -> dict[str, Any]:
        ...


class AccessManagementTool:
    name = ToolName.MANAGE_ACCESS

    def __init__(
        self,
        client: AccessManagementClient | None = None,
    ) -> None:
        self.client = client

        logger.info(
            "AccessManagementTool initialized"
        )

    def execute(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        if request.intent not in {
            IntentType.GRANT_ACCESS,
            IntentType.REVOKE_ACCESS,
        }:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "The access-management tool received "
                    "an unsupported intent."
                ),
                error=(
                    f"Unsupported intent: "
                    f"{request.intent.value}"
                ),
            )

        metadata = request.metadata

        action = (
            "grant"
            if request.intent
            is IntentType.GRANT_ACCESS
            else "revoke"
        )

        logger.info(
            "TOOL_CALL | request_id={} | "
            "correlation_id={} | intent={} | "
            "tool={} | action={} | username={} | "
            "email={} | employee_number={} | "
            "group_name={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            action,
            metadata.username,
            metadata.email,
            metadata.employee_number,
            metadata.group_name,
        )

        if not metadata.username:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "Username is required for access "
                    "management."
                ),
                error="Missing username",
            )

        if not metadata.group_name:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "Group name is required for access "
                    "management."
                ),
                error="Missing group name",
            )

        if self.client is None:
            result = ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.NOT_IMPLEMENTED,
                message=(
                    f"Access {action} tool was called, but "
                    "the access-management client has not "
                    "been registered."
                ),
                api_integration_pending=True,
                result={
                    "action": action,
                    "username": metadata.username,
                    "group_name":
                        metadata.group_name,
                },
                error=None,
            )

            logger.info(
                "TOOL_RESULT | request_id={} | "
                "correlation_id={} | tool={} | "
                "action={} | status={} | operation_id={}",
                request.request_id,
                request.correlation_id,
                result.tool_name.value,
                action,
                result.status.value,
                result.operation_id,
            )

            return result

        try:
            api_result = self.client.manage_access(
                action=action,
                username=metadata.username,
                email=metadata.email,
                employee_number=(
                    metadata.employee_number
                ),
                group_name=metadata.group_name,
                correlation_id=request.correlation_id,
            )

            success = bool(
                api_result.get("success")
            )

            result = ToolResult(
                success=success,
                tool_name=self.name,
                status=(
                    ToolStatus.COMPLETED
                    if success
                    else ToolStatus.FAILED
                ),
                message=api_result.get(
                    "message",
                    (
                        f"Access {action} completed."
                        if success
                        else f"Access {action} failed."
                    ),
                ),
                result=api_result.get("result"),
                error=api_result.get("error"),
            )

            logger.info(
                "TOOL_RESULT | request_id={} | "
                "correlation_id={} | tool={} | "
                "action={} | status={} | operation_id={}",
                request.request_id,
                request.correlation_id,
                result.tool_name.value,
                action,
                result.status.value,
                result.operation_id,
            )

            return result

        except Exception as exc:
            logger.exception(
                "Access-management tool failed"
            )

            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message=(
                    f"Access {action} operation failed."
                ),
                error=type(exc).__name__,
            )
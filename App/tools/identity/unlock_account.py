"""
Account Unlock Tool

Purpose:
    Execute account unlock through the configured identity integration.
"""

from __future__ import annotations

from typing import Any, Protocol

from loguru import logger

from App.workflow.state import (
    ToolName,
    ToolRequest,
    ToolResult,
    ToolStatus,
)


class AccountUnlockClient(Protocol):
    def unlock_account(
        self,
        *,
        username: str,
        email: str | None,
        employee_number: str | None,
        correlation_id: str,
    ) -> dict[str, Any]:
        ...


class AccountUnlockTool:
    name = ToolName.UNLOCK_ACCOUNT

    def __init__(
        self,
        client: AccountUnlockClient | None = None,
    ) -> None:
        self.client = client

        logger.info(
            "AccountUnlockTool initialized"
        )

    def execute(
        self,
        request: ToolRequest,
    ) -> ToolResult:
        metadata = request.metadata

        logger.info(
            "TOOL_CALL | request_id={} | "
            "correlation_id={} | intent={} | "
            "tool={} | username={} | email={} | "
            "employee_number={}",
            request.request_id,
            request.correlation_id,
            request.intent.value,
            self.name.value,
            metadata.username,
            metadata.email,
            metadata.employee_number,
        )

        if not metadata.username:
            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.REJECTED,
                message=(
                    "Username is required for account "
                    "unlock."
                ),
                error="Missing username",
            )

        if self.client is None:
            result = ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.NOT_IMPLEMENTED,
                message=(
                    "Account unlock tool was called, but "
                    "the account-unlock client has not been "
                    "registered."
                ),
                api_integration_pending=True,
                result={
                    "username": metadata.username,
                },
                error=None,
            )

            logger.info(
                "TOOL_RESULT | request_id={} | "
                "correlation_id={} | tool={} | "
                "status={} | operation_id={}",
                request.request_id,
                request.correlation_id,
                result.tool_name.value,
                result.status.value,
                result.operation_id,
            )

            return result

        try:
            api_result = self.client.unlock_account(
                username=metadata.username,
                email=metadata.email,
                employee_number=(
                    metadata.employee_number
                ),
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
                        "Account unlocked successfully."
                        if success
                        else "Account unlock failed."
                    ),
                ),
                result=api_result.get("result"),
                error=api_result.get("error"),
            )

            logger.info(
                "TOOL_RESULT | request_id={} | "
                "correlation_id={} | tool={} | "
                "status={} | operation_id={}",
                request.request_id,
                request.correlation_id,
                result.tool_name.value,
                result.status.value,
                result.operation_id,
            )

            return result

        except Exception as exc:
            logger.exception(
                "Account-unlock tool failed"
            )

            return ToolResult(
                success=False,
                tool_name=self.name,
                status=ToolStatus.FAILED,
                message="Account unlock failed.",
                error=type(exc).__name__,
            )